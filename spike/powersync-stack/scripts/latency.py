#!/usr/bin/env python3
"""
Write-to-sync latency: how long from `PUT /api/data` returning until the row
arrives on a client that already has an open sync stream.

Measures the path the user actually feels on a second device -- API commit,
logical replication, bucket storage write, checkpoint, stream push.
"""
import json
import threading
import time
import urllib.request
import uuid

API = "http://127.0.0.1:15060"
SYNC = "http://127.0.0.1:15080"
USER = "33333333-3333-4333-8333-333333333333"
N = 8


def post(url, body, token=None, method="POST"):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method=method,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


token = post(f"{API}/api/auth/token", {"user_id": USER})["token"]
seen = {}
stop = threading.Event()


def reader():
    """Hold one long-lived stream open and stamp each row as it lands."""
    req = urllib.request.Request(
        f"{SYNC}/sync/stream",
        data=json.dumps({"buckets": [], "include_checksum": True,
                         "raw_data": True, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        for line in r:
            if stop.is_set():
                return
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if "data" in msg:
                for op in msg["data"]["data"]:
                    if op.get("op") == "PUT":
                        seen[op["object_id"]] = time.time()


t = threading.Thread(target=reader, daemon=True)
t.start()
time.sleep(4)  # let the initial checkpoint settle so we time steady state

samples = []
for i in range(N):
    sid = str(uuid.uuid4())
    sent = time.time()
    post(f"{API}/api/data", {"batch": [
        {"op": "PUT", "type": "sessions", "id": sid,
         "data": {"day": "2026-07-23", "journal": f"latency probe {i}"}}]},
        token=token, method="PUT")
    while sid not in seen and time.time() - sent < 30:
        time.sleep(0.01)
    if sid in seen:
        samples.append((seen[sid] - sent) * 1000)
        print(f"  probe {i + 1}: {samples[-1]:6.0f} ms")
    else:
        print(f"  probe {i + 1}: TIMED OUT")
    time.sleep(1)

stop.set()
if samples:
    samples.sort()
    print(f"\n  n={len(samples)}  min={samples[0]:.0f} ms  "
          f"median={samples[len(samples) // 2]:.0f} ms  max={samples[-1]:.0f} ms")
