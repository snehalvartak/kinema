"""Engine v1 smoke test: speed + quality on several target curves."""
import time
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from engine.kinematics import synthesize, linkage_frames, normalize_batch, N


def star():
    pts = []
    R, r = 1.0, 0.42
    for i in range(5):
        ao = -np.pi / 2 + i * 2 * np.pi / 5
        ai = ao + np.pi / 5
        pts.append([R * np.cos(ao), R * np.sin(ai - np.pi / 5) * 0 + r * np.sin(ai)])
        pts.append([r * np.cos(ai), r * np.sin(ai)])
    return np.array(pts)


def presets():
    t = np.linspace(0, 2 * np.pi, 240)
    heart = np.stack([16 * np.sin(t) ** 3,
                      -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))], axis=1) / 16
    s = np.stack([np.sin(2 * t) * 0.7, np.sin(t)], axis=1)  # lemniscate-ish "S/8"
    inf = np.stack([np.cos(t) / (1 + np.sin(t) ** 2), np.sin(t) * np.cos(t) / (1 + np.sin(t) ** 2)], axis=1) * 2
    drop = np.stack([np.sin(t) * (1 - np.cos(t)), 1 - np.cos(t)], axis=1)  # teardrop-ish
    return [("heart", heart), ("figure8", s), ("infinity", inf), ("teardrop", drop)]


def main():
    fig, axes = plt.subplots(2, 4, figsize=(18, 9))
    results = []
    for col, (name, pts) in enumerate(presets()):
        t0 = time.time()
        out = synthesize(pts, generations=320, popsize=200, seed=42, restarts=2)
        dt = time.time() - t0
        loss = out["loss"]
        results.append((name, loss, dt))
        print(f"{name}: loss={loss:.5f}  time={dt:.1f}s  params={np.round(out['params'],3)}")
        tn = out["target"]
        # aligned curve for plot: use brute alignment via fft best shift/rot
        zt = tn[:, 0] + 1j * tn[:, 1]
        zc = (normalize_batch(out["curve"][None])[0][:, 0]
              + 1j * normalize_batch(out["curve"][None])[0][:, 1])
        bestplot = None
        for x in (zc, np.conj(zc[::-1])):
            corr = np.fft.ifft(np.conj(np.fft.fft(x)) * np.conj(np.fft.fft(zt)))
            s_ = int(np.argmax(np.abs(corr)))
            w = np.roll(zt, -s_)
            num = np.sum(np.conj(w) * x)
            Rr = np.conj(num) / max(abs(num), 1e-12)
            cand = x * Rr
            err = np.mean(np.abs(w - cand) ** 2)
            if bestplot is None or err < bestplot[0]:
                bestplot = (err, cand)
        cn = np.stack([bestplot[1].real, bestplot[1].imag], axis=1)
        axes[0, col].plot(tn[:, 0], tn[:, 1], "k-", lw=2)
        axes[0, col].set_title(f"{name} (target)")
        axes[1, col].plot(cn[:, 0], cn[:, 1], "r-", lw=2)
        axes[1, col].plot(tn[:, 0], tn[:, 1], "k--", lw=0.8, alpha=0.5)
        axes[1, col].set_title(f"evolved err={loss:.4f} {dt:.0f}s")
        for row in range(2):
            axes[row, col].set_aspect("equal")
            axes[row, col].axis("off")
    fig.tight_layout()
    fig.savefig("prototype/engine_v1.png", dpi=110)
    print("\nSUMMARY:")
    for name, loss, dt in results:
        print(f"  {name}: {loss:.5f} in {dt:.1f}s")


if __name__ == "__main__":
    main()
