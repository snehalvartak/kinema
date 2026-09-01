"""Debug: (1) can DE recover a curve from the 4-bar family itself? (2) what do the found curves look like?"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import differential_evolution
import kinema_test as kt


def de(target, seed, maxiter=300):
    return differential_evolution(
        kt.loss_fn, kt.BOUNDS, args=(target,), seed=seed, popsize=40,
        maxiter=maxiter, tol=1e-9, mutation=(0.4, 1.0), recombination=0.85,
        polish=False, init="sobol", workers=-1,
    )


def main():
    true_params = np.array([0.8, 2.2, 2.0, 2.5, 0.9, 0.6, 1.0])
    target_raw = kt.coupler_curve(true_params)
    assert target_raw is not None, "true params invalid!"
    target = kt.normalize(target_raw)

    res = de(target, seed=1)
    found = kt.coupler_curve(res.x)
    err = kt.procrustes_loss(found, target)
    print(f"self-consistency: err={err:.5f}  (should be ~0 if pipeline correct)")

    star = kt.normalize(kt.resample_curve(kt.make_star()))
    res2 = de(star, seed=2)
    found2 = kt.coupler_curve(res2.x)
    err2 = kt.procrustes_loss(found2, star)
    print(f"star retry: err={err2:.5f}")

    rng = np.random.default_rng(0)
    valid = 0
    for _ in range(3000):
        p = np.array([rng.uniform(lo, hi) for lo, hi in kt.BOUNDS])
        if kt.coupler_curve(p) is not None:
            valid += 1
    print(f"valid param fraction: {valid/3000:.2%}")

    fig, ax = plt.subplots(1, 3, figsize=(15, 5))
    for a_, (c, t, title) in zip(ax, [
        (target, target, "target (true 4bar curve)"),
        (kt.normalize(found), target, f"recovered err={err:.4f}"),
        (kt.normalize(found2), star, f"star attempt err={err2:.4f}"),
    ]):
        a_.plot(t[:, 0], t[:, 1], "k--", lw=1.5, label="target")
        a_.plot(c[:, 0], c[:, 1], "r-", lw=2, label="found")
        a_.set_aspect("equal")
        a_.axis("off")
        a_.set_title(title)
        a_.legend()
    fig.savefig("prototype/debug.png", dpi=110, bbox_inches="tight")
    print("saved prototype/debug.png")


if __name__ == "__main__":
    main()
