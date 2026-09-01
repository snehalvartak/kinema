"""Kinema web app: draw a curve, watch evolution invent a machine that draws it."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import threading
import time

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from engine.kinematics import synthesize, linkage_frames, resample, align_target_to_machine, curves, N

app = FastAPI(title="Kinema")

PRESETS = {
    "heart": lambda t: np.stack([16 * np.sin(t) ** 3,
                                 -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))], axis=1) / 16,
    "star": lambda t: None,  # built below
    "infinity": lambda t: np.stack([np.cos(t) / (1 + np.sin(t) ** 2),
                                    np.sin(t) * np.cos(t) / (1 + np.sin(t) ** 2)], axis=1) * 2,
    "teardrop": lambda t: np.stack([np.sin(t) * (1 - np.cos(t)), 1 - np.cos(t)], axis=1),
    "figure8": lambda t: np.stack([np.sin(2 * t) * 0.7, np.sin(t)], axis=1),
    "ellipse": lambda t: np.stack([np.cos(t), 0.55 * np.sin(t)], axis=1),
}


def _star_points():
    pts = []
    R, r = 1.0, 0.5
    for i in range(5):
        ao = -np.pi / 2 + i * 2 * np.pi / 5
        ai = ao + np.pi / 5
        pts.append([R * np.cos(ao), R * np.sin(ao)])
        pts.append([r * np.cos(ai), r * np.sin(ai)])
    return np.array(pts)


PRESETS["star"] = lambda t: _star_points()


class CancelFlag:
    def __init__(self):
        self.cancelled = False


# ---- lazy preset cache: first synthesis streams live; later ones replay instantly ----
PRESET_CACHE = {}          # key -> "done" payload
PRESET_LOCK = threading.Lock()


def preset_key(points, cfg) -> str:
    import hashlib
    h = hashlib.sha1()
    h.update(np.round(np.asarray(points, float), 2).tobytes())
    h.update(str(sorted(cfg.items())).encode())
    return h.hexdigest()[:16]


def run_synthesis_stream(points, cfg, send, cancel: CancelFlag):
    """Blocking synthesis that streams generation updates via send(dict)."""
    key = preset_key(points, cfg)
    with PRESET_LOCK:
        cached = PRESET_CACHE.get(key)
    seed_pop = None
    warm = False
    if cached is not None:
        # warm start: seed the population with the previous winner — evolution still
        # runs live and streams, it just starts from a much better place
        seed_pop = [cached["params"]]
        warm = True

    def on_generation(gen, best_params, best_loss):
        if cancel.cancelled:
            raise KeyboardInterrupt
        # throttle: send ~ every 4 generations
        if gen % 4 == 0 or gen == cfg["generations"] - 1:
            c, _ = curves(best_params[None, :])
            curve = c[0]
            send({"type": "gen", "gen": gen, "loss": round(best_loss, 6),
                  "curve": np.round(curve, 5).tolist(), "warm": warm})

    out = synthesize(points, generations=cfg["generations"], popsize=cfg["popsize"],
                     seed=cfg["seed"], restarts=cfg["restarts"], on_generation=on_generation,
                     seed_population=seed_pop)
    frames = linkage_frames(out["params"])
    target_machine = align_target_to_machine(out["curve"], points)
    payload = {
        "type": "done",
        "params": out["params"],
        "loss": out["loss"],
        "chamfer": out["chamfer"],
        "elapsed": out["elapsed"],
        "warm": warm,
        "history": out["history"][::4],
        "curve": np.round(out["curve"], 5).tolist(),
        "target": np.round(out["target"], 5).tolist(),
        "target_machine": np.round(target_machine, 5).tolist(),
        "links": frames["links"],
        "valid": frames["valid"],
        "transmission": frames.get("transmission"),
        "frames": {k: np.round(v, 5).tolist() for k, v in
                   (("O2", frames["O2"]), ("O4", frames["O4"]), ("A", frames["A"]),
                    ("B", frames["B"]), ("P", frames["P"]))},
    }
    with PRESET_LOCK:
        PRESET_CACHE[key] = payload
    send(payload)


def render_gif(params, target_points) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter

    frames = linkage_frames(params)
    target = np.asarray(target_points)
    tn = target - target.mean(axis=0)
    tn = tn / np.sqrt((tn ** 2).sum(axis=1).mean())

    curve = frames["P"]
    cn = curve - curve.mean(axis=0)
    cn = cn / np.sqrt((cn ** 2).sum(axis=1).mean())

    scale = max(np.abs(tn).max(), np.abs(frames["P"]).max()) * 1.25
    a, b, c, d = (frames["links"][k] for k in ("a", "b", "c", "d"))

    fig, ax = plt.subplots(figsize=(5, 5), dpi=90)
    ax.set_xlim(-scale, scale)
    ax.set_ylim(-scale, scale)
    ax.set_aspect("equal")
    ax.axis("off")
    (trace,) = ax.plot([], [], "-", color="#e5484d", lw=2.2, alpha=0.9)
    (tgt,) = ax.plot(tn[:, 0], tn[:, 1], "--", color="#888", lw=1.2, alpha=0.7)
    (path_full,) = ax.plot(curve[:, 0], curve[:, 1], "-", color="#e5484d", lw=1.2, alpha=0.25)
    crank, = ax.plot([], [], "-o", color="#3b82f6", lw=3, ms=5)
    coupler, = ax.plot([], [], "-o", color="#111", lw=2, ms=4)
    rocker, = ax.plot([], [], "-o", color="#10b981", lw=2, ms=4)
    ground, = ax.plot([], [], "s", color="#666", ms=6)
    ppoint, = ax.plot([], [], "o", color="#e5484d", ms=6)
    lab_crank = ax.text(0, 0, "crank", color="#3b82f6", fontsize=9, fontweight="bold", ha="center")
    lab_coupler = ax.text(0, 0, "coupler", color="#111", fontsize=9, fontweight="bold", ha="center")
    lab_rocker = ax.text(0, 0, "rocker", color="#10b981", fontsize=9, fontweight="bold", ha="center")
    lab_pen = ax.text(0, 0, "pen", color="#e5484d", fontsize=10, fontweight="bold", ha="left")
    txt = ax.text(0.02, 0.02, "", transform=ax.transAxes, fontsize=8, color="#555")
    ax.set_title("a machine invented by evolution", fontsize=11, color="#333")

    def update(i):
        A, B, P = frames["A"][i], frames["B"][i], frames["P"][i]
        O2, O4 = frames["O2"][i], frames["O4"][i]
        ground.set_data([O2[0], O4[0]], [O2[1], O4[1]])
        crank.set_data([O2[0], A[0]], [O2[1], A[1]])
        coupler.set_data([A[0], B[0]], [A[1], B[1]])
        rocker.set_data([O4[0], B[0]], [O4[1], B[1]])
        ppoint.set_data([P[0]], [P[1]])
        lab_crank.set_position([(O2[0] + A[0]) / 2, (O2[1] + A[1]) / 2])
        lab_coupler.set_position([(A[0] + B[0]) / 2, (A[1] + B[1]) / 2])
        lab_rocker.set_position([(O4[0] + B[0]) / 2, (O4[1] + B[1]) / 2])
        lab_pen.set_position([P[0] + scale * 0.03, P[1] + scale * 0.03])
        k = max(2, int(i * 3 % N))
        idx = np.arange(0, k)
        trace.set_data(curve[idx, 0], curve[idx, 1])
        txt.set_text(f"a={a:.2f} b={b:.2f} c={c:.2f} d={d:.2f}")
        return trace, crank, coupler, rocker, ground, ppoint

    ani = FuncAnimation(fig, update, frames=N, interval=40, blit=True)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        ani.save(tmp_path, writer=PillowWriter(fps=25))
        with open(tmp_path, "rb") as f:
            data = f.read()
    finally:
        os.remove(tmp_path)
    plt.close(fig)
    return data


@app.get("/")
def index():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/static/{path:path}")
def static_file(path: str):
    from fastapi.responses import FileResponse
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    full = os.path.normpath(os.path.join(base, path))
    if not full.startswith(base) or not os.path.isfile(full):
        return Response(status_code=404)
    return FileResponse(full)


@app.post("/gif")
def gif(body: dict):
    params = np.asarray(body["params"], float)
    pts = np.asarray(body["points"], float)
    data = render_gif(params, pts)
    return Response(content=data, media_type="image/gif",
                    headers={"Content-Disposition": "attachment; filename=kinema.gif"})


@app.websocket("/ws/synthesize")
async def ws_synthesize(ws: WebSocket):
    await ws.accept()
    loop = asyncio.get_event_loop()
    cancel = CancelFlag()
    running = {"task": None}

    async def run_job(cfg):
        points = np.asarray(cfg["points"], float)
        q: asyncio.Queue = asyncio.Queue(maxsize=64)

        def send(msg):
            loop.call_soon_threadsafe(q.put_nowait, msg)

        def worker():
            try:
                run_synthesis_stream(points, cfg, send, cancel)
            except KeyboardInterrupt:
                send({"type": "cancelled"})
            except Exception as e:  # noqa
                send({"type": "error", "message": str(e)})
            finally:
                send({"type": "_end"})

        threading.Thread(target=worker, daemon=True).start()
        try:
            while True:
                msg = await q.get()
                if msg.get("type") == "_end":
                    break
                await ws.send_text(json.dumps(msg))
        except Exception:
            cancel.cancelled = True

    try:
        while True:
            raw = await ws.receive_text()
            cfg = json.loads(raw)
            if cfg.get("type") == "cancel":
                cancel.cancelled = True
                continue
            if cfg.get("type") == "synthesize":
                if running["task"] is not None and not running["task"].done():
                    cancel.cancelled = True
                    try:
                        await asyncio.wait_for(running["task"], timeout=5)
                    except Exception:
                        pass
                cancel = CancelFlag()
                running["task"] = asyncio.create_task(run_job(cfg))
    except WebSocketDisconnect:
        cancel.cancelled = True


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")), name="static")
