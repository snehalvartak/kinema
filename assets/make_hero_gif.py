"""Hero GIF: sketch draws itself -> evolution converges -> the invented machine traces it."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

from engine.kinematics import synthesize, linkage_frames, resample

HERE = os.path.dirname(os.path.abspath(__file__))
N = 160


def make_infinity():
    t = np.linspace(0, 2 * np.pi, 240)
    pts = np.stack([np.cos(t) / (1 + np.sin(t) ** 2),
                    np.sin(t) * np.cos(t) / (1 + np.sin(t) ** 2)], axis=1) * 2
    return pts


def main():
    target = resample(make_infinity())
    tn = target - target.mean(axis=0)
    tn = tn / np.sqrt((tn ** 2).sum(axis=1).mean())

    # 1) run synthesis, capturing generation snapshots
    snaps = []

    def on_gen(gen, params, loss):
        if gen % 12 == 0:
            from engine.kinematics import curves
            c, _ = curves(np.asarray(params)[None])
            snaps.append((gen, c[0].copy(), loss))

    out = synthesize(target, generations=320, popsize=200, restarts=2, seed=42,
                     on_generation=on_gen)
    print("synthesis done:", round(out["loss"], 5), "snaps:", len(snaps))

    frames = linkage_frames(out["params"])
    curve = frames["P"]
    scale = max(np.abs(curve).max(), 1.2) * 1.35

    fig, ax = plt.subplots(figsize=(5.6, 5.6), dpi=96)
    fig.patch.set_facecolor("#0b0d10")
    ax.set_facecolor("#0b0d10")
    ax.set_xlim(-scale, scale)
    ax.set_ylim(-scale, scale)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("I drew a curve. Evolution invented a machine that draws it.",
                 fontsize=11, color="#e8edf2", pad=12)

    (tgt,) = ax.plot([], [], "--", color="#8b96a5", lw=1.3, alpha=0.85)
    (best_curve,) = ax.plot([], [], "-", color="#5aa2ff", lw=2.0, alpha=0.95)
    (trace,) = ax.plot([], [], "-", color="#e5484d", lw=2.6)
    crank, = ax.plot([], [], "-o", color="#5aa2ff", lw=3.4, ms=5)
    coupler, = ax.plot([], [], "-o", color="#e8edf2", lw=2.4, ms=4)
    rocker, = ax.plot([], [], "-o", color="#2dd4a7", lw=2.4, ms=4)
    ground, = ax.plot([], [], "s", color="#8b96a5", ms=6)
    ppoint, = ax.plot([], [], "o", color="#e5484d", ms=7)
    status = ax.text(0.03, 0.03, "", transform=ax.transAxes, fontsize=10.5,
                     color="#e8edf2", fontweight="bold")

    tgt.set_data(tn[:, 0], tn[:, 1])

    n_draw = 0
    n_evo = len(snaps) - 1
    n_machine = N
    total = n_evo + n_machine

    def update(i):
        if i < n_evo:
            gen, c, loss = snaps[i]
            cn = c - c.mean(axis=0)
            cn = cn / np.sqrt((cn ** 2).sum(axis=1).mean())
            # align rotation to target via fft for stable visuals
            zc = cn[:, 0] + 1j * cn[:, 1]
            zt = tn[:, 0] + 1j * tn[:, 1]
            corr = np.fft.ifft(np.conj(np.fft.fft(zc)) * np.conj(np.fft.fft(zt)))
            s = int(np.argmax(np.abs(corr)))
            w = np.roll(zt, -s)
            num = np.sum(np.conj(w) * zc)
            R = np.conj(num) / max(abs(num), 1e-12)
            zc2 = zc * R
            best_curve.set_data(zc2.real, zc2.imag)
            crank.set_data([], [])
            coupler.set_data([], [])
            rocker.set_data([], [])
            ground.set_data([], [])
            ppoint.set_data([], [])
            trace.set_data([], [])
            status.set_text(f"generation {gen:3d}  ·  error {loss:.3f}")
        else:
            j = i - n_evo
            A, B, P = frames["A"][j], frames["B"][j], frames["P"][j]
            O2, O4 = frames["O2"][j], frames["O4"][j]
            ground.set_data([O2[0], O4[0]], [O2[1], O4[1]])
            crank.set_data([O2[0], A[0]], [O2[1], A[1]])
            coupler.set_data([A[0], B[0]], [A[1], B[1]])
            rocker.set_data([O4[0], B[0]], [O4[1], B[1]])
            ppoint.set_data([P[0]], [P[1]])
            best_curve.set_data([], [])
            k = max(2, j + 1)
            trace.set_data(curve[:k, 0], curve[:k, 1])
            if j < N - 4:
                status.set_text("the machine — invented, not programmed")
            else:
                status.set_text("")
        return (tgt, best_curve, trace, crank, coupler, rocker, ground, ppoint, status)

    ani = FuncAnimation(fig, update, frames=total, interval=70, blit=True)
    out_path = os.path.join(HERE, "hero_infinity.gif")
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".gif", delete=False)
    tmp.close()
    try:
        ani.save(tmp.name, writer=PillowWriter(fps=14))
        os.replace(tmp.name, out_path)
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)
    print("saved", out_path, os.path.getsize(out_path) // 1024, "KB")


if __name__ == "__main__":
    main()
