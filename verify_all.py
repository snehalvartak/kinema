"""Final verification: every submission artifact works."""
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

ok = True


def check(name, cond, detail=""):
    global ok
    mark = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{mark}] {name} {detail}")


# 1. app serves + WS + gif
from starlette.testclient import TestClient
from web.app import app

client = TestClient(app)
r = client.get("/")
check("GET /", r.status_code == 200)
r2 = client.get("/static/main.js")
check("GET /static/main.js", r2.status_code == 200 and "startAnimation" in r2.text)
r3 = client.get("/static/style.css")
check("GET /static/style.css", r3.status_code == 200)

t = np.linspace(0, 2 * np.pi, 200)
pts = np.stack([np.cos(t), 0.6 * np.sin(t)], axis=1).tolist()
with client.websocket_connect("/ws/synthesize") as ws:
    ws.send_text(json.dumps({"type": "synthesize", "points": pts,
                             "generations": 20, "popsize": 60, "restarts": 1, "seed": 3}))
    done = None
    while done is None:
        m = json.loads(ws.receive_text())
        if m["type"] == "done":
            done = m
        if m["type"] == "error":
            break
check("WS synthesize -> done", done is not None and done["loss"] < 1.0,
      f"loss={done['loss'] if done else None}")
check("done payload fields", done and all(k in done for k in
      ("frames", "target_machine", "transmission", "links", "history")))
r4 = client.post("/gif", json={"params": done["params"], "points": pts})
check("POST /gif", r4.status_code == 200 and r4.headers["content-type"] == "image/gif" and len(r4.content) > 100000)

# 2. engine quality on a fresh target (quick budget)
from engine.kinematics import synthesize
out = synthesize(pts, generations=60, popsize=120, restarts=1, seed=5)
check("engine quick synth", out["loss"] < 0.1, f"loss={out['loss']:.4f} in {out['elapsed']:.0f}s")

# 3. benchmark artifacts
res = json.load(open("benchmark/results.json"))
n_att = sum(len(v["attempts"]) for md in res["llm"].values() for v in md.values())
check("benchmark attempts", n_att >= 72, f"{n_att} attempts")
check("DE baseline 6 targets", len(res["de"]) == 6)
check("feedback arm", len(res.get("feedback", {})) == 3)
check("hybrid arm", len(res.get("hybrid", {})) == 3)
for f in ["benchmark/leaderboard.md", "benchmark/chart.png"]:
    check(f, os.path.exists(f) and os.path.getsize(f) > 1000)
gifs = [f for f in os.listdir("benchmark/gifs") if f.endswith(".gif") and os.path.getsize(os.path.join("benchmark/gifs", f)) > 1000]
check("benchmark gifs", len(gifs) >= 10, f"{len(gifs)} valid")
v = [f for f in os.listdir("assets/versus") if f.endswith(".gif") and os.path.getsize(os.path.join("assets/versus", f)) > 1000]
check("versus gifs", len(v) >= 4, f"{len(v)} valid")
check("hero gif", os.path.getsize("assets/hero_infinity.gif") > 300000)
check("capacity figure", os.path.exists("assets/capacity_limit.png"))
for f in ["README.md", "DECISIONS.md", "DEMO.md", "requirements.txt", "assets/post_drafts.md", "deploy/public_url.ps1"]:
    check(f, os.path.exists(f))

print("\nOVERALL:", "ALL PASS" if ok else "SOME FAILED")
