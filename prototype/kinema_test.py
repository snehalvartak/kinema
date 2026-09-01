"""Kill-experiment: can DE synthesize a 4-bar linkage tracing a drawn curve, fast, on 2 CPU cores?"""
import time
import numpy as np
from scipy.optimize import differential_evolution
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

N = 128  # crank samples == target resample count

def resample_curve(pts, n=N):
    """Resample polyline to n points equally spaced by arc length."""
    d = np.sqrt(((np.diff(pts, axis=0)) ** 2).sum(axis=1))
    s = np.concatenate([[0], np.cumsum(d)])
    total = s[-1]
    if total == 0:
        return np.zeros((n, 2))
    si = np.linspace(0, total, n, endpoint=False)
    x = np.interp(si, s, pts[:, 0])
    y = np.interp(si, s, pts[:, 1])
    return np.stack([x, y], axis=1)

def normalize(c):
    c = c - c.mean(axis=0)
    r = np.sqrt((c ** 2).sum(axis=1).mean())  # RMS radius: makes mean|z|^2 = 1
    return c / max(r, 1e-9)

def procrustes_loss(moving, target):
    """MSE between curves after optimal rotation+translation+scale (no reflection)."""
    m = normalize(moving)
    t = normalize(target)
    H = m.T @ t
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0, d])
    R = Vt.T @ D @ U.T
    m = m @ R
    return ((m - t) ** 2).sum(axis=1).mean()


def shape_loss(moving, target):
    """Closed-curve matching invariant to phase shift, direction, rotation, scale.

    Both curves are normalized (centroid, RMS). Represented as complex sequences.
    For a circular shift s and unit-rotation R, residual = 2 - 2|<z_t, S_s z_c>|
    (unit-norm case). All shifts evaluated at once via FFT cross-correlation.
    """
    zc = normalize(moving) @ np.array([1, 1j])
    zt = normalize(target) @ np.array([1, 1j])

    def best(zc, zt):
        fc = np.fft.fft(zc)
        ft = np.fft.fft(zt)
        # cross-correlation: corr[s] = <z_t, S_s z_c> = sum conj(zc[i]) zt[i+s]
        corr = np.fft.ifft(np.conj(fc) * ft)
        mags = np.abs(corr)
        s = int(np.argmax(mags))
        m = mags[s] / len(zt)
        return 2.0 - 2.0 * min(m, 1.0)  # clip handles numerically slightly >1

    fwd = best(zc, zt)
    rev = best(zc[::-1], zt)
    return min(fwd, rev)

THETA = np.linspace(0, 2 * np.pi, N, endpoint=False)

def coupler_curve(params):
    """params: a (crank), b (coupler), c (rocker), d (ground), px, py (coupler point in coupler frame), sign."""
    a, b, c, d, px, py = params[:6]
    sign = params[6]
    # Grashof crank-rocker: a shortest, s+l<=p+q
    links = np.array([a, b, c, d])
    if a > min(links) + 1e-9:
        return None
    if links.min() + links.max() > (links.sum() - links.min() - links.max()) + 1e-9:
        return None
    O2 = np.zeros(2)
    O4 = np.array([d, 0.0])
    A = np.stack([a * np.cos(THETA), a * np.sin(THETA)], axis=1)  # (N,2)
    D = O4 - A                                                     # vector A->O4
    e = np.linalg.norm(D, axis=1)
    # circle intersection radius b around A, radius c around O4
    cosphi = (b * b + e * e - c * c) / (2 * b * e)
    if np.any(np.abs(cosphi) > 1):
        return None  # assembly impossible at some angle
    phi = sign * np.arccos(np.clip(cosphi, -1, 1))
    base = np.arctan2(D[:, 1], D[:, 0])
    ang = base + phi
    B = A + b * np.stack([np.cos(ang), np.sin(ang)], axis=1)
    u = (B - A) / b
    n = np.stack([-u[:, 1], u[:, 0]], axis=1)
    P = A + px * u + py * n
    return P

def loss_fn(params, target):
    c = coupler_curve(params)
    if c is None:
        return 10.0
    return shape_loss(c, target)

def make_star():
    pts = []
    R, r = 1.0, 0.42
    for i in range(6):
        ang_o = -np.pi / 2 + i * 2 * np.pi / 5
        ang_i = ang_o + np.pi / 5
        pts.append([R * np.cos(ang_o), R * np.sin(ang_o)])
        pts.append([r * np.cos(ang_i), r * np.sin(ang_i)])
    return np.array(pts)

def make_heart():
    t = np.linspace(0, 2 * np.pi, 200)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    return np.stack([x, -y], axis=1) / 16.0

def make_s():
    t = np.linspace(0, 2 * np.pi, 200)
    x = t / (2 * np.pi) - 0.5
    y = 0.5 * np.cos(t)
    return np.stack([x, y], axis=1)

BOUNDS = [(0.2, 2.0), (0.5, 3.5), (0.5, 3.5), (0.8, 4.0), (-1.5, 1.5), (-1.5, 1.5), (-1, 1)]

def align(moving, target):
    """Return moving aligned to target via best shift + optimal rotation (for plotting)."""
    zc = normalize(moving) @ np.array([1, 1j])
    zt = normalize(target) @ np.array([1, 1j])
    best = (None, None, 1e9)
    for x, rev in [(zc, False), (zc[::-1], True)]:
        corr = np.fft.ifft(np.conj(np.fft.fft(x)) * np.fft.fft(zt))
        s = int(np.argmax(np.abs(corr)))
        m = np.abs(corr[s]) / len(zt)
        if m < best[2]:
            w = np.roll(zt, -s)
            num = np.sum(np.conj(w) * x)
            R = np.conj(num) / max(abs(num), 1e-12)
            pts = x * R
            arr = np.stack([pts.real, pts.imag], axis=1)
            best = (arr, rev, m)
    return best[0]

def run(name, target_pts, seed=0, popsize=40, maxiter=350):
    target = normalize(resample_curve(target_pts))
    t0 = time.time()
    res = differential_evolution(
        loss_fn, BOUNDS, args=(target,), seed=seed, popsize=popsize,
        maxiter=maxiter, tol=1e-9, mutation=(0.4, 1.0), recombination=0.85,
        polish=False, init="sobol", workers=-1,
    )
    dt = time.time() - t0
    curve = coupler_curve(res.x)
    err = shape_loss(curve, target)
    print(f"{name}: loss={err:.5f}  time={dt:.1f}s  params={np.round(res.x[:6],3)}")
    fig, ax = plt.subplots(1, 2, figsize=(10, 5))
    tn = normalize(target)
    cn = align(curve, target)
    ax[0].plot(tn[:, 0], tn[:, 1], "k-", lw=2)
    ax[0].set_title(f"target: {name}")
    ax[1].plot(cn[:, 0], cn[:, 1], "r-", lw=2)
    ax[1].plot(tn[:, 0], tn[:, 1], "k--", lw=1, alpha=0.5)
    ax[1].set_title(f"evolved linkage (err={err:.4f}, {dt:.0f}s)")
    for a_ in ax:
        a_.set_aspect("equal")
        a_.axis("off")
    fig.savefig(f"prototype/out_{name}.png", dpi=110, bbox_inches="tight")
    return err, dt

if __name__ == "__main__":
    import os
    os.makedirs("prototype", exist_ok=True)
    results = []
    for name, pts in [("star", make_star()), ("heart", make_heart()), ("scurve", make_s())]:
        results.append((name, *run(name, pts)))
    print("\nSUMMARY (2-core laptop):")
    for name, err, dt in results:
        verdict = "PASS" if err < 0.01 else ("OK" if err < 0.03 else "FAIL")
        print(f"  {name}: err={err:.4f} in {dt:.0f}s -> {verdict}")
