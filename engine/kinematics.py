"""Kinema synthesis engine: vectorized 4-bar linkage synthesis via differential evolution.

A planar 4-bar crank-rocker (Grashof, crank fully rotatable) is parameterized by
(a, b, c, d, px, py, s):
    a      crank length          (O2 -> A, driven at constant speed)
    b      coupler length        (A -> B)
    c      rocker length         (B -> O4)
    d      ground length         (O2 -> O4, placed on the x-axis)
    px,py  coupler-point offset in the coupler frame (u = A->B unit, n = perp(u))
    s      assembly-mode branch sign in [-1, 1]

The coupler point P traces a closed curve as the crank rotates. We search for the
linkage whose coupler curve best matches a user-sketched closed curve, invariant to
translation, scale, rotation, traversal direction and starting phase.
"""
from __future__ import annotations

import numpy as np

N = 160  # crank samples per revolution (also target resample count)
BIG = 10.0

THETA = np.linspace(0.0, 2.0 * np.pi, N, endpoint=False)
COS, SIN = np.cos(THETA), np.sin(THETA)

# param bounds: a, b, c, d, px, py, s
BOUNDS = np.array([
    [0.15, 2.2],   # a (crank, will be forced shortest via penalty-free parametrization)
    [0.4, 3.6],    # b (coupler)
    [0.4, 3.6],    # c (rocker)
    [0.6, 4.2],    # d (ground)
    [-1.6, 1.6],   # px
    [-1.6, 1.6],   # py
    [-1.0, 1.0],   # s (branch sign)
])
DIM = len(BOUNDS)


def curves(pop: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Coupler curves for a population of parameter vectors.

    pop: (P, 7) array in parameter units.
    Returns (P, N, 2) float array of coupler points and (P,) bool validity mask.
    Invalid individuals (non-Grashof or non-assemblable at some crank angle) are
    returned with finite garbage values and validity False.
    """
    a, b, c, d = pop[:, 0], pop[:, 1], pop[:, 2], pop[:, 3]
    px, py, s = pop[:, 4], pop[:, 5], pop[:, 6]
    P = pop.shape[0]

    links = np.stack([a, b, c, d], axis=1)  # (P,4)
    shortest = links.min(axis=1)
    longest = links.max(axis=1)
    sum_others = links.sum(axis=1) - shortest - longest
    # crank must be the shortest link and Grashof: s + l <= p + q
    ok = (a <= shortest + 1e-9) & (shortest + longest <= sum_others + 1e-9)

    A = np.stack([a[:, None] * COS[None, :], a[:, None] * SIN[None, :]], axis=2)  # (P,N,2)
    D = np.empty_like(A)
    D[..., 0] = d[:, None] - A[..., 0]
    D[..., 1] = -A[..., 1]
    e = np.linalg.norm(D, axis=2)  # (P,N)

    with np.errstate(divide="ignore", invalid="ignore"):
        cosphi = (b[:, None] ** 2 + e ** 2 - c[:, None] ** 2) / (2 * b[:, None] * e)
    assemblable = np.abs(cosphi) <= 1.0
    ok &= assemblable.all(axis=1)
    ok &= ~np.isnan(cosphi).any(axis=1)

    phi = np.sign(s)[:, None] * np.arccos(np.clip(cosphi, -1.0, 1.0))
    base = np.arctan2(D[..., 1], D[..., 0])
    ang = base + phi
    B = A + b[:, None, None] * np.stack([np.cos(ang), np.sin(ang)], axis=2)

    AB = B - A
    ABn = np.linalg.norm(AB, axis=2, keepdims=True)
    ABn = np.where(ABn < 1e-12, 1.0, ABn)
    u = AB / ABn
    nvec = np.stack([-u[..., 1], u[..., 0]], axis=2)

    Pv = A + px[:, None, None] * u + py[:, None, None] * nvec  # (P,N,2)
    Pv = np.where(ok[:, None, None], Pv, 0.0)
    return Pv, ok


def normalize_batch(C: np.ndarray) -> np.ndarray:
    """Centroid + RMS-radius normalization per curve. C: (..., N, 2)."""
    C = C - C.mean(axis=-2, keepdims=True)
    rms = np.sqrt((C ** 2).sum(axis=-1, keepdims=True).mean(axis=-2, keepdims=True))
    return C / np.maximum(rms, 1e-12)


def _loss_batch(pop: np.ndarray, zt: np.ndarray, corr_fft_zt: np.ndarray) -> np.ndarray:
    """Batched phase/direction/rotation-invariant shape loss for a population."""
    Pv, ok = curves(pop)
    C = normalize_batch(Pv)
    zc = C[..., 0] + 1j * C[..., 1]  # (P,N)

    best = np.full(pop.shape[0], BIG)
    for x in (zc, np.conj(zc[..., ::-1])):  # forward and reversed traversal
        fc = np.fft.fft(x, axis=1)
        corr = np.fft.ifft(np.conj(fc) * corr_fft_zt, axis=1)
        m = np.abs(corr).max(axis=1) / zt.shape[0]
        # residual = mean|zt - R x| = 2 - 2<corr>  (unit mean-square curves)
        loss = 2.0 - 2.0 * np.minimum(m, 1.0)
        best = np.minimum(best, np.where(ok, loss, BIG))
    return best


def resample(points: np.ndarray, n: int = N) -> np.ndarray:
    """Resample a polyline to n points equally spaced by arc length."""
    closed = np.vstack([points, points[:1]])
    seg = np.sqrt(((np.diff(closed, axis=0)) ** 2).sum(axis=1))
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = s[-1]
    if total <= 0:
        return np.zeros((n, 2))
    si = np.linspace(0.0, total, n, endpoint=False)
    return np.stack([np.interp(si, s, closed[:, 0]),
                     np.interp(si, s, closed[:, 1])], axis=1)


def prepare_target(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normalize a raw sketch into the target complex sequence + its FFT (for correlation).

    Uses fft(zt) (NOT conjugated): ifft(conj(fft(x))·fft(zt)) is the true circular
    correlation sum_i conj(x[i])·zt[i+s].
    """
    t = normalize_batch(resample(points)[None])[0]
    zt = t[:, 0] + 1j * t[:, 1]
    return t, np.fft.fft(zt)


def _sobol_population(popsize: int, rng: np.random.Generator) -> np.ndarray:
    from scipy.stats import qmc
    sob = qmc.Sobol(DIM, scramble=True, seed=int(rng.integers(2**31)))
    lo, hi = BOUNDS[:, 0], BOUNDS[:, 1]
    return lo + (hi - lo) * sob.random(popsize)


def chamfer_loss(curve: np.ndarray, target: np.ndarray) -> float:
    """Orderless symmetric mean distance between two normalized point sets.

    Captures sharp features (cusps) that index-wise correspondence underweights.
    Both inputs are normalized (N,2) curves; closest-point distances via KD-tree.
    """
    from scipy.spatial import cKDTree
    a = normalize_batch(curve[None])[0]
    b = target
    da = cKDTree(a).query(b)[0]
    db = cKDTree(b).query(a)[0]
    return float((da ** 2).mean() + (db ** 2).mean())


def synthesize(target_points: np.ndarray,
               generations: int = 320,
               popsize: int = 200,
               seed: int | None = None,
               restarts: int = 1,
               on_generation=None,
               time_budget: float | None = None,
               seed_population: np.ndarray | None = None):
    """Evolve a 4-bar linkage whose coupler curve matches the sketch.

    seed_population: optional (K, 7) array of parameter vectors to inject into the
    initial population (e.g. LLM proposals) — the rest stays sobol-random.
    on_generation(gen, best_params, best_loss) is called each generation when provided.
    Returns dict with params, loss, curve, joints (animation frames), meta.
    """
    import time
    t_start = time.time()
    rng = np.random.default_rng(seed)

    target, corr_fft_zt = prepare_target(target_points)
    F_lo, F_hi = 0.35, 0.95
    CR = 0.9

    best_overall = None
    for restart in range(restarts):
        pop = _sobol_population(popsize, rng)
        if seed_population is not None and restart == 0:
            sp = np.asarray(seed_population, float)
            sp = np.clip(sp, BOUNDS[:, 0], BOUNDS[:, 1])
            k = min(len(sp), popsize - 8)  # keep some pure-random exploration
            pop[:k] = sp[:k]
        fit = _loss_batch(pop, target, corr_fft_zt)
        history = [fit.min()]
        for gen in range(generations):
            F = rng.uniform(F_lo, F_hi, size=(popsize, 1))
            idx = np.arange(popsize)
            r1, r2, r3 = (rng.integers(0, popsize, popsize), rng.integers(0, popsize, popsize),
                          rng.integers(0, popsize, popsize))
            # guarantee distinct donors per row where possible
            for arr in (r1, r2, r3):
                clash = arr == idx
                arr[clash] = (arr[clash] + 1 + rng.integers(0, popsize - 1, clash.sum())) % popsize
            mutant = pop[r1] + F * (pop[r2] - pop[r3])
            mutant = np.clip(mutant, BOUNDS[:, 0], BOUNDS[:, 1])
            cross = rng.random((popsize, DIM)) < CR
            cross[rng.integers(0, popsize), rng.integers(0, DIM)] = True
            trial = np.where(cross, mutant, pop)
            f_t = _loss_batch(trial, target, corr_fft_zt)
            improve = f_t < fit
            pop[improve] = trial[improve]
            fit[improve] = f_t[improve]
            history.append(float(fit.min()))
            if on_generation is not None:
                on_generation(gen, pop[fit.argmin()].copy(), float(fit.min()))
            if time_budget is not None and time.time() - t_start > time_budget:
                break
        i = fit.argmin()
        if best_overall is None or fit[i] < best_overall[1]:
            best_overall = (pop[i].copy(), float(fit[i]), list(history))
        if time_budget is not None and time.time() - t_start > time_budget:
            break

    params, loss, history = best_overall
    # local polish stage 1: index-wise loss (Nelder-Mead)
    from scipy.optimize import minimize
    def f_obj(x):
        return float(_loss_batch(np.asarray(x, float)[None, :], target, corr_fft_zt)[0])
    r = minimize(f_obj, params, method="Nelder-Mead",
                 options={"maxiter": 1200, "xatol": 1e-6, "fatol": 1e-9})
    if r.fun < loss:
        cand = np.clip(r.x, BOUNDS[:, 0], BOUNDS[:, 1])
        cand_loss = f_obj(cand)  # re-check AFTER clipping: clipping can break Grashof
        if cand_loss < loss:
            params, loss = cand, cand_loss

    # local polish stage 2: orderless chamfer loss (sharpens cusps, fixes correspondences)
    t_norm = normalize_batch(resample(target_points)[None])[0]
    def f_cham(x):
        c2d, ok = curves(np.asarray(x, float)[None, :])
        if not ok[0]:
            return BIG
        return chamfer_loss(c2d[0], t_norm)
    base_cham = f_cham(params)
    r2 = minimize(f_cham, params, method="Nelder-Mead",
                  options={"maxiter": 800, "xatol": 1e-6, "fatol": 1e-9})
    if r2.fun < base_cham:
        cand = np.clip(r2.x, BOUNDS[:, 0], BOUNDS[:, 1])
        cand_cham = f_cham(cand)  # re-check AFTER clipping
        if cand_cham < base_cham and f_obj(cand) < BIG:
            params = cand
    cham = f_cham(params)
    idx_after = f_obj(params)

    curve2d, _ = curves(np.asarray(params, float)[None, :])
    curve2d = curve2d[0]
    return {
        "params": params.tolist(),
        "loss": loss,
        "chamfer": cham,
        "index_loss_after_chamfer_polish": idx_after,
        "history": history,
        "curve": curve2d,
        "target": target,
        "restarts_used": restart,
        "elapsed": time.time() - t_start,
    }


def align_target_to_machine(curve: np.ndarray, target_points: np.ndarray) -> np.ndarray:
    """Express the sketch target in the machine's coordinate frame (best shift+rotation+scale).

    Used to overlay the user's sketch on the animated linkage. Works with any curve
    length (the target is resampled to match).
    """
    cen = curve.mean(axis=0)
    rms = np.sqrt(((curve - cen) ** 2).sum(axis=1).mean())
    zn = normalize_batch(curve)
    zc = zn[:, 0] + 1j * zn[:, 1]
    tn = normalize_batch(resample(target_points, len(curve)))
    zt = tn[:, 0] + 1j * tn[:, 1]
    corr_fft_zt = np.fft.fft(zt)
    # Two pairing hypotheses, both with clean rotations (no conjugation of x):
    #   fwd: machine index i  <-> target index (i+s)  — num(s) = ifft(conj(fft(zt))·fft(zc))[s]
    #   rev: machine index i  <-> target index (s-i)  — num(s) = ifft(fft(conj(zt))·fft(zc))[s]
    # residual(s) = 2 - 2|num(s)|/N (unit-RMS curves); pick branch+shift with min residual.
    # ghost:  tm[m] = R^-1 * zt[pair(m)] * rms + centroid,  R^-1 = num/|num|
    num_fwd = np.fft.ifft(np.conj(corr_fft_zt) * np.fft.fft(zc))
    num_rev = np.fft.ifft(np.fft.fft(np.conj(zt)) * np.fft.fft(zc))
    cands = [("fwd", num_fwd, lambda m, s: (m + s) % N),
             ("rev", num_rev, lambda m, s: (s - m) % N)]
    best = None
    for label, nums, pair in cands:
        s = int(np.argmax(np.abs(nums)))
        mag = abs(nums[s]) / N
        Rinv = nums[s] / max(abs(nums[s]), 1e-12)
        res = 2.0 - 2.0 * min(mag, 1.0)
        tm = np.empty(N, dtype=complex)
        for m in range(N):
            tm[m] = Rinv * zt[pair(m, s)] * rms
        tm2 = np.stack([tm.real + cen[0], tm.imag + cen[1]], axis=1)
        if best is None or res < best[0]:
            best = (res, tm2, label)
    return best[1]


def linkage_frames(params) -> dict:
    """Joint positions per crank angle for animation + the coupler curve."""
    p = np.asarray(params, float)[None, :]
    Pv, ok = curves(p)
    a, b, c, d = p[0, :4]
    px, py = p[0, 4], p[0, 5]
    A = np.stack([a * COS, a * SIN], axis=1)
    D = np.stack([d - A[:, 0], -A[:, 1]], axis=1)
    e = np.linalg.norm(D, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        cosphi = np.clip((b ** 2 + e ** 2 - c ** 2) / (2 * b * e), -1, 1)
    phi = np.sign(p[0, 6]) * np.arccos(cosphi)
    ang = np.arctan2(D[:, 1], D[:, 0]) + phi
    B = A + b * np.stack([np.cos(ang), np.sin(ang)], axis=1)
    u = (B - A) / b
    nvec = np.stack([-u[:, 1], u[:, 0]], axis=1)
    Ppts = A + px * u + py * nvec
    O2 = np.zeros((N, 2))
    O4 = np.stack([np.full(N, d), np.zeros(N)], axis=1)
    # transmission angle: angle between coupler AB and rocker BO4
    BO4 = O4 - B
    with np.errstate(divide="ignore", invalid="ignore"):
        cosg = np.abs(np.sum(u * BO4 / np.maximum(np.linalg.norm(BO4, axis=1, keepdims=True), 1e-9), axis=1))
    gamma = np.degrees(np.arccos(np.clip(cosg, -1, 1)))  # 0 deg = collinear (bad)
    finite = np.isfinite(gamma)
    return {
        "O2": O2, "O4": O4, "A": A, "B": B, "P": Ppts,
        "links": {"a": float(a), "b": float(b), "c": float(c), "d": float(d),
                  "px": float(px), "py": float(py)},
        "valid": bool(ok[0] and finite.all()),
        "transmission": {"min_deg": float(gamma[finite].min()) if finite.any() else 0.0,
                         "mean_deg": float(gamma[finite].mean()) if finite.any() else 0.0},
    }
