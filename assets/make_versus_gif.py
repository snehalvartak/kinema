"""Side-by-side viral GIF: the LLM's machine vs the evolution-designed machine, same sketch.

Burned-in captions so it reads with sound off. Requires benchmark/results.json.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

from engine.kinematics import linkage_frames, resample, N

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(os.path.dirname(HERE), "benchmark")
OUT = os.path.join(HERE, "versus")

TARGETS = {
    "teardrop": lambda t: np.stack([np.sin(t) * (1 - np.cos(t)), 1 - np.cos(t)], axis=1),
    "figure8": lambda t: np.stack([np.sin(2 * t) * 0.7, np.sin(t)], axis=1),
    "infinity": lambda t: np.stack([np.cos(t) / (1 + np.sin(t) ** 2),
                                    np.sin(t) * np.cos(t) / (1 + np.sin(t) ** 2)], axis=1) * 2,
    "heart": lambda t: np.stack([16 * np.sin(t) ** 3,
                                 -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))], axis=1) / 16,
    "star": None,
    "ellipse": lambda t: np.stack([np.cos(t), 0.55 * np.sin(t)], axis=1),
}


def target_pts(name):
    if name == "star":
        pts = []
        R, r = 1.0, 0.5
        for i in range(5):
            ao = -np.pi / 2 + i * 2 * np.pi / 5
            ai = ao + np.pi / 5
            pts.append([R * np.cos(ao), R * np.sin(ao)])
            pts.append([r * np.cos(ai), r * np.sin(ai)])
        return np.array(pts)
    return TARGETS[name](np.linspace(0, 2 * np.pi, 240))


def pick_llm_attempt(res, tname, exclude=None):
    """Best valid LLM attempt on this target (any model), or None."""
    best = None
    for model, per_t in res["llm"].items():
        if model == exclude:
            continue
        for a in per_t.get(tname, {}).get("attempts", []):
            if a["valid"] and a.get("params"):
                if best is None or a["index_loss"] < best[0]:
                    best = (a["index_loss"], model, np.asarray(a["params"]))
    return best


def normalize_frames(f):
    """Express all joint frames relative to the coupler curve (centroid + RMS scale).

    Scoring is translation/scale invariant, so both machines are drawn with their
    pen paths centered and the same RMS radius — a fair shape comparison.
    """
    curve = f["P"]
    cen = curve.mean(axis=0)
    rms = np.sqrt(((curve - cen) ** 2).sum(axis=1).mean())
    s = 1.0 / max(rms, 1e-9)
    out = {"P": (curve - cen) * s}
    for k in ("O2", "O4", "A", "B"):
        out[k] = (f[k] - cen) * s
    out["links"] = f["links"]
    return out


def render_pair(params_a, params_b, pts, caption_a, caption_b, out_path, err_a=None, err_b=None):
    fa = normalize_frames(linkage_frames(params_a))
    fb = normalize_frames(linkage_frames(params_b))
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 5.2), dpi=96)
    fig.patch.set_facecolor("#0b0d10")
    for ax, f, cap, err, accent in (
        (axes[0], fa, caption_a, err_a, "#5aa2ff"),
        (axes[1], fb, caption_b, err_b, "#e5484d"),
    ):
        curve = f["P"]
        allpts = np.vstack([f["P"], f["A"], f["B"], f["O2"], f["O4"]])
        cen = allpts.mean(axis=0)
        ext = max(np.abs(allpts - cen).max(), 1.5) * 1.15
        ax.set_facecolor("#0b0d10")
        ax.set_xlim(cen[0] - ext, cen[0] + ext)
        ax.set_ylim(cen[1] - ext, cen[1] + ext)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(cap, fontsize=11.5, color=accent, pad=10, fontweight="bold")
        (path_full,) = ax.plot(curve[:, 0], curve[:, 1], "-", color=accent, lw=1.0, alpha=0.22)
        (trace,) = ax.plot([], [], "-", color=accent, lw=2.4)
        crank, = ax.plot([], [], "-o", color=accent, lw=3, ms=4)
        coupler, = ax.plot([], [], "-o", color="#e8edf2", lw=1.8, ms=3)
        rocker, = ax.plot([], [], "-o", color="#2dd4a7", lw=1.8, ms=3)
        ground, = ax.plot([], [], "s", color="#8b96a5", ms=5)
        ppoint, = ax.plot([], [], "o", color=accent, ms=6)
        errt = ax.text(0.5, 0.01, err or "", transform=ax.transAxes, fontsize=9,
                       color="#8b96a5", ha="center")
        f["_artists"] = (path_full, trace, crank, coupler, rocker, ground, ppoint, errt)
        f["_accent"] = accent

    def update(i):
        out = []
        for f in (fa, fb):
            A, B, P = f["A"][i % N], f["B"][i % N], f["P"][i % N]
            O2, O4 = f["O2"][i % N], f["O4"][i % N]
            path_full, trace, crank, coupler, rocker, ground, ppoint, errt = f["_artists"]
            ground.set_data([O2[0], O4[0]], [O2[1], O4[1]])
            crank.set_data([O2[0], A[0]], [O2[1], A[1]])
            coupler.set_data([A[0], B[0]], [A[1], B[1]])
            rocker.set_data([O4[0], B[0]], [O4[1], B[1]])
            ppoint.set_data([P[0]], [P[1]])
            k = max(2, (i % N) + 1)
            trace.set_data(f["P"][:k, 0], f["P"][:k, 1])
            out.extend([trace, crank, coupler, rocker, ground, ppoint])
        return out

    fig.suptitle("same sketch, same scoring — pen paths shown at identical scale",
                 fontsize=10, color="#8b96a5", y=0.98)
    ani = FuncAnimation(fig, update, frames=N, interval=55, blit=True)
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".gif", delete=False)
    tmp.close()
    try:
        ani.save(tmp.name, writer=PillowWriter(fps=18))
        os.replace(tmp.name, out_path)
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)
    print("saved", out_path)


def main():
    import json
    with open(os.path.join(BENCH, "results.json")) as f:
        res = json.load(f)
    os.makedirs(OUT, exist_ok=True)
    for tname in TARGETS:
        pts = target_pts(tname)
        de = res["de"].get(tname)
        if not de:
            print("skip (no DE yet):", tname)
            continue
        llm = pick_llm_attempt(res, tname)
        de_err = f"error {de['index_loss']:.3f}  ·  2-core laptop, 64k evaluations"
        if llm:
            lerr, lmodel, lparams = llm
            caption_l = f"{lmodel.split('/')[-1]} — one shot, cold"
            render_pair(lparams, np.asarray(de["params"]), pts, caption_l,
                        "Kinema — differential evolution", os.path.join(OUT, f"{tname}_versus.gif"),
                        err_a=f"error {lerr:.3f}  ·  {lerr / de['index_loss']:.0f}x worse",
                        err_b=de_err)
        else:
            print("no valid LLM attempt for", tname)


if __name__ == "__main__":
    main()
