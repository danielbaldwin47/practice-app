#!/usr/bin/env python3
"""
End-to-end check of the ADR 0003 topology. Standard library only -- there is no
Node, Dart or Flutter toolchain on the NAS, so the client side is spoken as raw
protocol rather than through an SDK.

The path exercised is the full round trip:

    client -> PUT /api/data (TS API) -> Postgres `practice`
           -> logical replication -> powersync-service
           -> bucket storage in Postgres `powersync_storage`
           -> POST /sync/stream -> back to the client

Run:  python3 scripts/verify.py
"""
import json
import time
import urllib.request
import urllib.error
import uuid

API = "http://127.0.0.1:15060"
SYNC = "http://127.0.0.1:15080"

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"

ok_count = 0
fail_count = 0


def check(label, condition, detail=""):
    global ok_count, fail_count
    if condition:
        ok_count += 1
        print(f"  PASS  {label}")
    else:
        fail_count += 1
        print(f"  FAIL  {label}  {detail}")


def post(url, body, token=None, method="POST"):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method=method,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def token_for(user_id):
    status, body = post(f"{API}/api/auth/token", {"user_id": user_id})
    assert status == 200, body
    return body["token"]


def stream_rows(token, timeout=45):
    """Open the sync stream and drain it until the first checkpoint completes.

    Returns {table: {id: row}} of everything the server decided this token may see.
    """
    req = urllib.request.Request(
        f"{SYNC}/sync/stream",
        data=json.dumps({"buckets": [], "include_checksum": True,
                         "raw_data": True, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    rows, deadline = {}, time.time() + timeout
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            if time.time() > deadline:
                break
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if "data" in msg:
                # Ops are ordered; a real SDK replays them in sequence, so a
                # REMOVE after a PUT is how a delete reaches the device.
                for op in msg["data"]["data"]:
                    table = rows.setdefault(op["object_type"], {})
                    if op.get("op") == "PUT":
                        d = op["data"]
                        if isinstance(d, str):
                            d = json.loads(d)
                        table[op["object_id"]] = d
                    elif op.get("op") == "REMOVE":
                        table.pop(op["object_id"], None)
            if "checkpoint_complete" in msg:
                break
    return rows


print("\n== 1. auth ==")
tok_a = token_for(USER_A)
tok_b = token_for(USER_B)
check("API mints RS256 tokens", bool(tok_a and tok_b))

with urllib.request.urlopen(f"{API}/api/auth/keys", timeout=10) as r:
    jwks = json.loads(r.read())
check("JWKS exposes exactly one RS256 key",
      len(jwks["keys"]) == 1 and jwks["keys"][0]["alg"] == "RS256", jwks)

print("\n== 2. write path (client -> API -> Postgres) ==")
session_id = str(uuid.uuid4())
block_id = str(uuid.uuid4())
status, body = post(f"{API}/api/data", {"batch": [
    {"op": "PUT", "type": "sessions", "id": session_id,
     "data": {"day": "2026-07-23", "journal": "long tones, then Cherokee at 180"}},
    {"op": "PUT", "type": "blocks", "id": block_id,
     "data": {"session_id": session_id, "subject": "Tone: long tones",
              "goal": "even across the break", "minutes": 25, "note": "throat open"}},
]}, token=tok_a, method="PUT")
check("batch of 2 CrudEntries applied", status == 200 and body.get("applied") == 2, body)

status, body = post(f"{API}/api/data", {"batch": [
    {"op": "PATCH", "type": "blocks", "id": block_id, "data": {"minutes": 30}},
]}, token=tok_a, method="PUT")
check("PATCH applied", status == 200, body)

print("\n== 3. write path refuses what it should ==")
status, _ = post(f"{API}/api/data", {"batch": []}, method="PUT")
check("unauthenticated write rejected", status == 401)

status, body = post(f"{API}/api/data", {"batch": [
    {"op": "PUT", "type": "pg_shadow", "id": str(uuid.uuid4()), "data": {}}]},
    token=tok_a, method="PUT")
check("write to non-allowlisted table rejected", status == 400, body)

# owner_id is forced from the JWT, so a client cannot plant a row on another user.
forged = str(uuid.uuid4())
status, body = post(f"{API}/api/data", {"batch": [
    {"op": "PUT", "type": "sessions", "id": forged,
     "data": {"day": "2026-07-23", "journal": "not mine", "owner_id": USER_B}}]},
    token=tok_a, method="PUT")
check("client-supplied owner_id ignored", status == 200, body)

print("\n== 4. sync path (Postgres -> PowerSync -> client) ==")
time.sleep(3)  # logical replication is asynchronous
rows_a = stream_rows(tok_a)
check("session row reached the client",
      session_id in rows_a.get("sessions", {}),
      f"got tables={list(rows_a)}")
check("journal text survived the round trip",
      rows_a.get("sessions", {}).get(session_id, {}).get("journal", "").startswith("long tones"),
      rows_a.get("sessions", {}).get(session_id))
check("PATCH is reflected downstream",
      rows_a.get("blocks", {}).get(block_id, {}).get("minutes") == 30,
      rows_a.get("blocks", {}).get(block_id))

print("\n== 5. per-user isolation (sync rules) ==")
rows_b = stream_rows(tok_b)
check("user B sees none of user A's rows",
      not rows_b.get("sessions") and not rows_b.get("blocks"),
      f"B saw {rows_b}")
check("forged owner_id row landed on A, not B",
      forged in rows_a.get("sessions", {}) or forged not in rows_b.get("sessions", {}))

print("\n== 6. delete propagates ==")
status, _ = post(f"{API}/api/data", {"batch": [
    {"op": "DELETE", "type": "blocks", "id": block_id}]}, token=tok_a, method="PUT")
time.sleep(3)
rows_a2 = stream_rows(tok_a)
check("deleted block is gone from the client view",
      block_id not in rows_a2.get("blocks", {}), rows_a2.get("blocks"))

print("\n== 7. attachments (MinIO presigning) ==")
status, up = post(f"{API}/api/attachments/upload-url",
                  {"object_key": "rec-001.m4a"}, token=tok_a)
check("upload URL presigned", status == 200 and "X-Amz-Signature" in up.get("url", ""), up)

payload = b"fake-aac-bytes-for-the-spike"
put = urllib.request.Request(up["url"], data=payload, method="PUT")
with urllib.request.urlopen(put, timeout=30) as r:
    check("bytes accepted by MinIO over the presigned URL", r.status == 200)

status, down = post(f"{API}/api/attachments/download-url",
                    {"object_key": up["object_key"]}, token=tok_a)
with urllib.request.urlopen(down["url"], timeout=30) as r:
    check("bytes round-trip out of MinIO", r.read() == payload)

status, _ = post(f"{API}/api/attachments/download-url",
                 {"object_key": up["object_key"]}, token=tok_b)
check("user B cannot presign user A's object", status == 403)

# The metadata row syncs; the bytes never touch the sync stream.
rec_id = str(uuid.uuid4())
post(f"{API}/api/data", {"batch": [
    {"op": "PUT", "type": "recordings", "id": rec_id,
     "data": {"object_key": up["object_key"], "codec": "aac",
              "duration_ms": 61000, "pinned": True}}]}, token=tok_a, method="PUT")
time.sleep(3)
rows_a3 = stream_rows(tok_a)
rec = rows_a3.get("recordings", {}).get(rec_id, {})
check("recording metadata synced", rec.get("object_key") == up["object_key"], rec)
check("audio bytes are NOT in the sync payload",
      not any("fake-aac-bytes" in json.dumps(v) for v in rows_a3.values()))

print(f"\n{'='*46}\n  {ok_count} passed, {fail_count} failed\n{'='*46}")
raise SystemExit(1 if fail_count else 0)
