"""Final end-to-end verification: app pages, WS flow, GIF, cache, static assets."""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from starlette.testclient import TestClient
from web.app import app

client = TestClient(app)
ok = True

# 1) page + static
r = client.get("/")
assert r.status_code == 200 and "narration" in r.text and "explainer" in r.text
for f in ("/static/main.js", "/static/style.css"):
    r = client.get(f)
    assert r.status_code == 200, f
print("page + static OK")

# 2) WS flow: hand-drawn-ish wobbly circle (fresh synthesis), then replay (cache hit)
t = np.linspace(0, 2 * np.pi, 200)
wobble = 1 + 0.07 * np.sin(3 * t)
pts = np.stack([np.cos(t) * wobble, 0.7 * np.sin(t) * wobble], axis=1).tolist()

with client.websocket_connect("/ws/synthesize") as ws:
    ws.send_text(json.dumps({"type": "synthesize", "points": pts,
                             "generations": 60, "popsize": 120, "restarts": 1, "seed": 5}))
    done = None
    while done is None:
        m = json.loads(ws.receive_text())
        if m["type"] == "done":
            done = m
        assert m["type"] != "error", m
assert done["valid"] and done["loss"] < 0.05, done["loss"]
assert done.get("transmission") and "min_deg" in done["transmission"]
print(f"synthesis OK: loss={done['loss']:.4f} valid={done['valid']} "
      f"transmission_min={done['transmission']['min_deg']:.0f}deg elapsed={done['elapsed']:.1f}s")

with client.websocket_connect("/ws/synthesize") as ws:
    ws.send_text(json.dumps({"type": "synthesize", "points": pts,
                             "generations": 60, "popsize": 120, "restarts": 1, "seed": 5}))
    replayed = False
    t0 = time.time()
    while not replayed:
        m = json.loads(ws.receive_text())
        if m.get("replay") and m["type"] == "done":
            replayed = True
        assert time.time() - t0 < 20
print("preset cache replay OK")

# 3) GIF endpoint
r = client.post("/gif", json={"params": done["params"], "points": pts})
assert r.status_code == 200 and r.headers["content-type"] == "image/gif" and len(r.content) > 100000
print(f"GIF OK: {len(r.content)//1024} KB")

print("\nALL CHECKS PASSED")
