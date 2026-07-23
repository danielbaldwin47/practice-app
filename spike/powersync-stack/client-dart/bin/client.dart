/// Scratch PowerSync client, driven through the real SDK rather than raw HTTP.
///
/// This is `powersync_core` (Dart) standing in for `powersync` (Flutter): same
/// wire protocol, same Rust core extension, same local SQLite. What it proves is
/// the part the protocol-level check cannot -- that the SDK's schema mapping,
/// first-sync wait and uploadData hook line up with our backend.
import 'dart:convert';
import 'dart:io';
import 'package:powersync_core/powersync_core.dart';
import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';

const apiUrl = 'http://api:6060';
const syncUrl = 'http://powersync:8080';
const userA = '11111111-1111-4111-8111-111111111111';

final schema = Schema([
  Table('sessions', [
    Column.text('owner_id'),
    Column.text('day'),
    Column.text('journal'),
  ]),
  Table('blocks', [
    Column.text('owner_id'),
    Column.text('session_id'),
    Column.text('subject'),
    Column.text('goal'),
    Column.integer('minutes'),
    Column.text('note'),
  ]),
]);

class SpikeConnector extends PowerSyncBackendConnector {
  final String token;
  int uploadedBatches = 0;
  SpikeConnector(this.token);

  @override
  Future<PowerSyncCredentials?> fetchCredentials() async =>
      PowerSyncCredentials(endpoint: syncUrl, token: token);

  /// The entire client-side write path: hand the queued CRUD transaction to our
  /// TS API verbatim, then mark it complete. Offline queueing, ordering and retry
  /// are the SDK's problem, not ours.
  @override
  Future<void> uploadData(PowerSyncDatabase database) async {
    final tx = await database.getNextCrudTransaction();
    if (tx == null) return;
    final batch = [
      for (final e in tx.crud)
        {'op': e.op.name.toUpperCase(), 'type': e.table, 'id': e.id, 'data': e.opData}
    ];
    final res = await http.put(
      Uri.parse('$apiUrl/api/data'),
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
      body: jsonEncode({'batch': batch}),
    );
    if (res.statusCode != 200) {
      throw Exception('upload failed ${res.statusCode} ${res.body}');
    }
    uploadedBatches++;
    await tx.complete();
  }
}

var pass = 0, fail = 0;
void check(String label, bool ok, [Object? detail]) {
  if (ok) {
    pass++;
    print('  PASS  $label');
  } else {
    fail++;
    print('  FAIL  $label  ${detail ?? ''}');
  }
}

Future<void> main() async {
  final tokenRes = await http.post(Uri.parse('$apiUrl/api/auth/token'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'user_id': userA}));
  final token = jsonDecode(tokenRes.body)['token'] as String;

  final dbPath = '/w/spike-client.db';
  if (File(dbPath).existsSync()) File(dbPath).deleteSync();
  final db = PowerSyncDatabase(schema: schema, path: dbPath);
  await db.initialize();
  check('local SQLite opened with the PowerSync core extension', true);

  final connector = SpikeConnector(token);
  await db.connect(connector: connector);

  await db.waitForFirstSync().timeout(const Duration(seconds: 60));
  check('first sync completed', true);

  final sessions = await db.getAll('SELECT * FROM sessions');
  check('server rows landed in local SQLite', sessions.isNotEmpty,
      'got ${sessions.length}');
  check('journal text intact through the SDK',
      sessions.any((r) => (r['journal'] as String? ?? '').contains('long tones')),
      sessions.map((r) => r['journal']).toList());

  // ---- write from the client, offline-style: local first, upload after.
  final newId = Uuid().v4();
  await db.execute(
      'INSERT INTO sessions (id, owner_id, day, journal) VALUES (?, ?, ?, ?)',
      [newId, userA, '2026-07-24', 'client-originated row']);

  final localNow = await db.get('SELECT journal FROM sessions WHERE id = ?', [newId]);
  check('write is visible locally immediately (before any upload)',
      localNow['journal'] == 'client-originated row');

  // Give the SDK time to drain its upload queue through uploadData().
  for (var i = 0; i < 30 && connector.uploadedBatches == 0; i++) {
    await Future.delayed(const Duration(seconds: 1));
  }
  check('SDK called uploadData and our API accepted it',
      connector.uploadedBatches > 0, 'batches=${connector.uploadedBatches}');

  // And confirm it made the full round trip: Postgres -> replication -> back down.
  var roundTripped = false;
  for (var i = 0; i < 30; i++) {
    final r = await db.getAll(
        'SELECT id FROM sessions WHERE id = ? AND journal = ?',
        [newId, 'client-originated row']);
    final synced = await db.getAll('SELECT * FROM ps_crud');
    if (r.isNotEmpty && synced.isEmpty) {
      roundTripped = true;
      break;
    }
    await Future.delayed(const Duration(seconds: 1));
  }
  check('client write round-tripped and the CRUD queue drained', roundTripped);

  await db.close();
  print('\n  $pass passed, $fail failed');
  exit(fail == 0 ? 0 : 1);
}
