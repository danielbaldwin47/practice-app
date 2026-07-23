/**
 * Practice app backend API -- the whole of it, as required by ADR 0002/0003/0004.
 *
 * PowerSync syncs Postgres DOWN to each device by itself. It does not do writes,
 * does not mint tokens, and does not touch object storage. Those three jobs are
 * this file, and this file is the spike's answer to "how much write-path code do
 * we actually need".
 *
 *   POST /api/auth/token             mint an RS256 JWT for a device
 *   GET  /api/auth/keys              JWKS, polled by powersync-service
 *   PUT  /api/data                   the write path: a batch of CrudEntry
 *   POST /api/attachments/upload-url presigned PUT into MinIO
 *   POST /api/attachments/download-url presigned GET from MinIO
 */
import express from 'express';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { generateKeyPair, exportJWK, importJWK, SignJWT, jwtVerify, type JWK } from 'jose';
import pg from 'pg';
import { S3Client, PutObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

const PORT = Number(process.env.PORT ?? 6060);
const AUDIENCE = 'powersync-practice';
const ISSUER = 'practice-api';
const KEY_FILE = process.env.KEY_FILE ?? '/data/jwks.json';

// ---------------------------------------------------------------- signing keys
// Persisted so a container restart doesn't invalidate every device's token while
// powersync-service is still holding a cached JWKS.
async function loadKeys() {
  if (existsSync(KEY_FILE)) {
    const { publicJwk, privateJwk } = JSON.parse(readFileSync(KEY_FILE, 'utf8'));
    return { publicJwk, privateKey: await importJWK(privateJwk, 'RS256') };
  }
  const { publicKey, privateKey } = await generateKeyPair('RS256', { extractable: true });
  const publicJwk = { ...(await exportJWK(publicKey)), alg: 'RS256', use: 'sig', kid: 'practice-1' };
  const privateJwk = { ...(await exportJWK(privateKey)), alg: 'RS256', kid: 'practice-1' };
  writeFileSync(KEY_FILE, JSON.stringify({ publicJwk, privateJwk }));
  return { publicJwk, privateKey };
}
const { publicJwk, privateKey } = await loadKeys();

const db = new pg.Pool({ connectionString: process.env.DATABASE_URI });

// A presigned URL is opened by the DEVICE, not by this container, and the host is
// part of what gets signed. Signing against the compose-internal `http://minio:9000`
// produces a URL no phone can resolve, so signing uses the public origin -- which
// means MinIO needs its own hostname through the tunnel (ADR 0004).
const s3 = (endpoint: string) => new S3Client({
  endpoint,
  region: 'us-east-1',
  forcePathStyle: true, // MinIO
  credentials: {
    accessKeyId: process.env.S3_ACCESS_KEY!,
    secretAccessKey: process.env.S3_SECRET_KEY!
  }
});
const s3Public = s3(process.env.S3_PUBLIC_ENDPOINT ?? process.env.S3_ENDPOINT!);
const BUCKET = process.env.S3_BUCKET ?? 'practice-audio';

const app = express();
app.use(express.json({ limit: '4mb' }));

// ---------------------------------------------------------------------- auth
app.get('/api/auth/keys', (_req, res) => res.json({ keys: [publicJwk] }));

// Real login is out of scope for 2-3 private users on a hardened tunnel; the
// shape (subject in, signed token out) is what PowerSync consumes either way.
app.post('/api/auth/token', async (req, res) => {
  const userId = req.body?.user_id;
  if (!userId) return res.status(400).json({ error: 'user_id required' });
  const token = await new SignJWT({})
    .setProtectedHeader({ alg: 'RS256', kid: 'practice-1' })
    .setSubject(userId)
    .setAudience(AUDIENCE)
    .setIssuer(ISSUER)
    .setIssuedAt()
    .setExpirationTime('12h')
    .sign(privateKey);
  res.json({ token, powersync_url: process.env.POWERSYNC_PUBLIC_URL });
});

async function requireUser(req: express.Request, res: express.Response): Promise<string | null> {
  const raw = req.header('authorization')?.replace(/^Bearer /i, '');
  if (!raw) { res.status(401).json({ error: 'missing token' }); return null; }
  try {
    const key = await importJWK(publicJwk as JWK, 'RS256');
    const { payload } = await jwtVerify(raw, key, { audience: AUDIENCE, issuer: ISSUER });
    return payload.sub!;
  } catch { res.status(401).json({ error: 'bad token' }); return null; }
}

// ----------------------------------------------------------------- write path
// Columns a client is allowed to write, per table. owner_id is never in this list:
// it is forced from the JWT below, which is what makes writes server-authoritative
// rather than merely server-relayed.
const WRITABLE: Record<string, string[]> = {
  sessions: ['day', 'journal', 'created_at', 'updated_at'],
  blocks: ['session_id', 'subject', 'goal', 'started_at', 'minutes', 'note'],
  recordings: ['block_id', 'object_key', 'codec', 'duration_ms', 'checksum', 'pinned', 'created_at']
};

app.put('/api/data', async (req, res) => {
  const userId = await requireUser(req, res);
  if (!userId) return;
  const batch = req.body?.batch;
  if (!Array.isArray(batch)) return res.status(400).json({ error: 'batch required' });

  const client = await db.connect();
  try {
    await client.query('BEGIN');
    for (const { op, type, id, data } of batch) {
      const allowed = WRITABLE[type];
      if (!allowed) throw new Error(`unknown table ${type}`);

      if (op === 'DELETE') {
        await client.query(`DELETE FROM ${type} WHERE id = $1 AND owner_id = $2`, [id, userId]);
        continue;
      }
      const cols = Object.keys(data ?? {}).filter((c) => allowed.includes(c));

      if (op === 'PATCH') {
        if (!cols.length) continue;
        const set = cols.map((c, i) => `${c} = $${i + 3}`).join(', ');
        await client.query(
          `UPDATE ${type} SET ${set} WHERE id = $1 AND owner_id = $2`,
          [id, userId, ...cols.map((c) => data[c])]
        );
        continue;
      }
      if (op === 'PUT') {
        // Upsert: the client may replay an insert it already sent before going offline.
        const names = ['id', 'owner_id', ...cols];
        const placeholders = names.map((_, i) => `$${i + 1}`).join(', ');
        const update = cols.length
          ? cols.map((c) => `${c} = EXCLUDED.${c}`).join(', ')
          : 'owner_id = EXCLUDED.owner_id';
        await client.query(
          `INSERT INTO ${type} (${names.join(', ')}) VALUES (${placeholders})
           ON CONFLICT (id) DO UPDATE SET ${update} WHERE ${type}.owner_id = $2`,
          [id, userId, ...cols.map((c) => data[c])]
        );
        continue;
      }
      throw new Error(`unknown op ${op}`);
    }
    await client.query('COMMIT');
    res.json({ ok: true, applied: batch.length });
  } catch (e: any) {
    await client.query('ROLLBACK');
    // A 4xx tells the SDK to drop the batch; a 5xx makes it retry forever. Bad
    // data must not become an infinite retry loop, so client errors are 400.
    res.status(400).json({ error: String(e.message ?? e) });
  } finally {
    client.release();
  }
});

// ------------------------------------------------------------------ audio bytes
app.post('/api/attachments/upload-url', async (req, res) => {
  const userId = await requireUser(req, res);
  if (!userId) return;
  const key = `${userId}/${req.body?.object_key}`;
  const url = await getSignedUrl(s3Public, new PutObjectCommand({ Bucket: BUCKET, Key: key }), { expiresIn: 900 });
  res.json({ url, object_key: key });
});

app.post('/api/attachments/download-url', async (req, res) => {
  const userId = await requireUser(req, res);
  if (!userId) return;
  const key: string = req.body?.object_key ?? '';
  // Keys are namespaced by user; refuse to sign anything outside the caller's prefix.
  if (!key.startsWith(`${userId}/`)) return res.status(403).json({ error: 'forbidden key' });
  const url = await getSignedUrl(s3Public, new GetObjectCommand({ Bucket: BUCKET, Key: key }), { expiresIn: 900 });
  res.json({ url });
});

app.get('/healthz', (_req, res) => res.json({ ok: true }));
app.listen(PORT, () => console.log(`practice api on :${PORT}`));
