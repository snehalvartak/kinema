"""Bulletproofing arms for the Evolution-vs-LLM benchmark:

1. FEEDBACK arm  — LLM + simulator-in-the-loop: after each attempt the model sees
   its penalty verdict (which constraint failed), its numeric loss, and its own pen
   path; it revises. Answers the "you gave the search a budget and the LLM a dartboard"
   attack with data: how far does feedback take an LLM?

2. HYBRID arm    — LLM proposals seed the DE initial population. Two questions:
   (a) does LLM seeding beat pure random init at the same budget?
   (b) can LLM-seeded DE match pure DE at 10% of the budget? (efficiency story)

Usage: python benchmark/feedback_arm.py [--quick]
Appends to benchmark/results.json under "feedback" and "hybrid".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.kinematics import (  # noqa: E402
    resample, normalize_batch, synthesize, curves, BOUNDS,
)
from benchmark.run_benchmark import (  # noqa: E402
    make_targets, load_key, call_model, parse_params, score_params, MODELS,
    TARGET_N, load_results, save_results, RESULTS,
)

HERE = os.path.dirname(os.path.abspath(__file__))
FEEDBACK_ROUNDS = 4


def polyline_hint(target_norm, n=40):
    idx = np.linspace(0, len(target_norm) - 1, n, endpoint=False).astype(int)
    return [[round(float(x), 3), round(float(y), 3)] for x, y in target_norm[idx]]


def constraint_verdict(params, target_norm):
    """Human-readable reasons the linkage is invalid, plus the penalty state."""
    p = np.asarray(params, float)
    reasons = []
    a, b, c, d = p[:4]
    links = [a, b, c, d]
    if a > min(links) + 1e-9:
        reasons.append(f"the crank (a={a:.3f}) is not the shortest link (shortest={min(links):.3f}) — Grashof law violated")
    if min(links) + max(links) > sum(links) - min(links) - max(links) + 1e-9:
        reasons.append("Grashof condition s+l <= p+q violated — the crank cannot rotate fully")
    c2d, ok = curves(p[None, :])
    if not ok[0]:
        reasons.append("the loop cannot assemble for at least one crank angle "
                       "(circle intersection fails) — the machine jams")
    sc = score_params(p, target_norm)
    return reasons, sc


def build_feedback_prompt(params, reasons, sc, target_norm, curve):
    pts = polyline_hint(target_norm)
    mine = polyline_hint(normalize_batch(curve[None])[0]) if curve is not None else []
    fb = "PREVIOUS ATTEMPT:\n"
    fb += json.dumps({k: round(float(v), 4) for k, v in zip(
        ("a", "b", "c", "d", "px", "py", "branch"), params)})
    if reasons:
        fb += "\nVERDICT: INVALID linkage — " + "; ".join(reasons) + "."
    else:
        fb += f"\nVERDICT: valid linkage, but the pen path does not match the target well."
    fb += f"\nMeasured index loss of your attempt: {sc['index_loss']:.4f} " \
          f"(0.00 = perfect, 2.0 = uncorrelated, >2 broken)."
    if mine:
        fb += "\nYour pen path (normalized, 40 points): " + json.dumps(mine)
    fb += "\nTARGET (40 of its 64 points): " + json.dumps(pts)
    fb += """

Diagnose WHY your curve deviates (wrong proportions? pen point misplaced? wrong shape class
for these proportions?) and output a corrected JSON. Respond with ONLY:
{"a": <number>, "b": <number>, "c": <number>, "d": <number>, "px": <number>, "py": <number>, "branch": <1 or -1>}"""
    return fb


def run_feedback(models, targets, key):
    res = load_results()
    res.setdefault("feedback", {})
    target_norm = {n: normalize_batch(resample(p)[None])[0] for n, p in targets.items()}
    for model in models:
        res["feedback"].setdefault(model, {})
        for tname, pts in targets.items():
            tn = target_norm[tname]
            rs = resample(pts, TARGET_N)
            rs = normalize_batch(rs[None])[0]
            from benchmark.run_benchmark import build_prompt
            prompt = build_prompt(rs)
            hist = []
            best_loss, best_params, best_curve = None, None, None
            for rnd in range(FEEDBACK_ROUNDS):
                t0 = time.time()
                text, err = call_model(model, prompt, key)
                params = parse_params(text)
                if params is None:
                    hist.append({"round": rnd, "parse_ok": False, "error": err})
                    save_results(res)
                    continue
                reasons, sc = constraint_verdict(params, tn)
                hist.append({"round": rnd, "parse_ok": True, "valid": sc["valid"],
                             "index_loss": round(sc["index_loss"], 6),
                             "chamfer": round(sc["chamfer"], 6),
                             "seconds": round(time.time() - t0, 1)})
                if best_loss is None or sc["index_loss"] < best_loss:
                    best_loss, best_params, best_curve = sc["index_loss"], params, sc["curve"]
                prompt = build_feedback_prompt(params, reasons, sc, tn, sc["curve"])
                save_results(res)
                tag = "VALID" if sc["valid"] else "INVALID"
                print(f"  FEEDBACK {model}/{tname} r{rnd}: {tag} index={sc['index_loss']:.4f}")
            res["feedback"][model][tname] = {
                "rounds": hist,
                "best_index_loss": best_loss,
                "best_params": best_params,
            }
            save_results(res)
    return res


def run_hybrid(models, targets, budget_small, budget_full):
    res = load_results()
    res.setdefault("hybrid", {})
    for model in models:
        res["hybrid"].setdefault(model, {})
        for tname, pts in targets.items():
            tn = normalize_batch(resample(pts)[None])[0]
            entry = res["hybrid"][model].setdefault(tname, {})
            if "seeds" not in entry:
                rs = resample(pts, TARGET_N)
                rs = normalize_batch(rs[None])[0]
                from benchmark.run_benchmark import build_prompt
                text, _ = call_model(model, build_prompt(rs) +
                    "\n\nOutput FIVE different candidate designs as a JSON array of five objects, "
                    "each with keys a,b,c,d,px,py,branch. Diversify proportions. Only JSON.", load_key())
                import re
                seeds = []
                if text:
                    m = re.search(r"\[[\s\S]*\]", text)
                    if m:
                        try:
                            arr = json.loads(m.group(0))
                            for obj in arr:
                                try:
                                    seeds.append([float(obj["a"]), float(obj["b"]), float(obj["c"]),
                                                  float(obj["d"]), float(obj["px"]), float(obj["py"]),
                                                  float(obj.get("branch", 1)) or 1.0])
                                except Exception:
                                    pass
                        except Exception:
                            pass
                entry["seeds"] = seeds
                entry["seed_scores"] = [round(score_params(np.asarray(s), tn)["index_loss"], 6) if s else None
                                        for s in seeds]
                save_results(res)
            seeds = entry["seeds"]
            if not seeds:
                print(f"  HYBRID {model}/{tname}: no parsable seeds — skipping")
                continue
            if "hybrid_small" not in entry:
                out = synthesize(pts, **budget_small, seed_population=np.asarray(seeds), seed=42)
                entry["hybrid_small"] = {"index_loss": round(out["loss"], 6),
                                         "chamfer": round(out["chamfer"], 6),
                                         "params": out["params"], "seconds": round(out["elapsed"], 1)}
                save_results(res)
            if "hybrid_full" not in entry:
                out = synthesize(pts, **budget_full, seed_population=np.asarray(seeds), seed=42)
                entry["hybrid_full"] = {"index_loss": round(out["loss"], 6),
                                        "chamfer": round(out["chamfer"], 6),
                                        "params": out["params"], "seconds": round(out["elapsed"], 1)}
                save_results(res)
            print(f"  HYBRID {model}/{tname}: seeds={entry['seed_scores']} "
                  f"small={entry['hybrid_small']['index_loss']:.4f} full={entry['hybrid_full']['index_loss']:.4f}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--arm", choices=["feedback", "hybrid", "both"], default="both")
    ap.add_argument("--models", nargs="*", default=None)
    args = ap.parse_args()

    targets = make_targets()
    if args.quick:
        targets = {k: v for k, v in targets.items() if k in ("ellipse", "figure8")}
        models = args.models or ["z-ai/glm-5.3-flash"]
    else:
        models = args.models or MODELS
    key = load_key()
    budget_small = {"generations": 32, "popsize": 200, "restarts": 2}   # ~10% budget
    budget_full = {"generations": 320, "popsize": 200, "restarts": 2}   # shipped budget

    if args.arm in ("feedback", "both"):
        run_feedback(models, targets, key)
    if args.arm in ("hybrid", "both"):
        run_hybrid(models, targets, budget_small, budget_full)
    print("done — see results.json")


if __name__ == "__main__":
    main()
