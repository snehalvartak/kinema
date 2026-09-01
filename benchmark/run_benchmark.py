"""Evolution vs LLMs: mechanism design benchmark.

Task given to every competitor: given a target closed curve (a resampled polyline),
output the 7 parameters of a 4-bar crank-rocker linkage whose coupler-point path
traces it. Everyone is scored by the exact same simulator and metrics:

  index loss : mean squared gap between pen path and sketch (phase/rotation/scale
               invariant, matches what the Kinema app optimizes)
  chamfer    : orderless symmetric mean squared distance (sharp-feature sensitive)
  valid      : does the linkage obey Grashof + assemble for a full crank rotation?

Baselines: the Kinema differential-evolution engine with its shipped budget
(generations=320, popsize=200, restarts=2) on identical targets.

Usage:
  python benchmark/run_benchmark.py --quick          # 1 model, 1 target, 1 attempt
  python benchmark/run_benchmark.py                  # full run (resumable)
Results: benchmark/results.json, benchmark/leaderboard.md, benchmark/chart.png,
         benchmark/gifs/*.gif
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.kinematics import (  # noqa: E402
    BOUNDS, curves, resample, normalize_batch, chamfer_loss, synthesize, linkage_frames,
)

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.environ.get("KINEMA_RESULTS", os.path.join(HERE, "results.json"))

MODELS = [
    "z-ai/glm-5.3-flash",
    "z-ai/glm-5.2",
    "z-ai/glm-4.6",
    "z-ai/glm-4.5-air",
]

TARGET_N = 64  # points shown to the models (engine resamples to N=160 internally)


# ---------------------------------------------------------------- targets
def _star():
    pts = []
    R, r = 1.0, 0.5
    for i in range(5):
        ao = -np.pi / 2 + i * 2 * np.pi / 5
        ai = ao + np.pi / 5
        pts.append([R * np.cos(ao), R * np.sin(ao)])
        pts.append([r * np.cos(ai), r * np.sin(ai)])
    return np.array(pts)


def make_targets():
    t = np.linspace(0, 2 * np.pi, 240)
    return {
        "ellipse": np.stack([np.cos(t), 0.55 * np.sin(t)], axis=1),
        "teardrop": np.stack([np.sin(t) * (1 - np.cos(t)), 1 - np.cos(t)], axis=1),
        "infinity": np.stack([np.cos(t) / (1 + np.sin(t) ** 2),
                              np.sin(t) * np.cos(t) / (1 + np.sin(t) ** 2)], axis=1) * 2,
        "figure8": np.stack([np.sin(2 * t) * 0.7, np.sin(t)], axis=1),
        "heart": np.stack([16 * np.sin(t) ** 3,
                           -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))], axis=1) / 16,
        "star": _star(),
    }


# ---------------------------------------------------------------- scoring
def score_params(params, target_norm):
    """Returns dict(valid, index_loss, chamfer). Invalid linkages get BIG losses."""
    p = np.asarray(params, float)
    if p.shape != (7,):
        return {"valid": False, "index_loss": 10.0, "chamfer": 10.0, "curve": None}
    c2d, ok = curves(p[None, :])
    if not ok[0]:
        return {"valid": False, "index_loss": 10.0, "chamfer": 10.0, "curve": None}
    cn = normalize_batch(c2d)[0]
    zc = cn[:, 0] + 1j * cn[:, 1]
    zt = target_norm[:, 0] + 1j * target_norm[:, 1]
    corr_zt = np.conj(np.fft.fft(zt))
    best = 1e9
    for x in (zc, np.conj(zc[::-1])):
        corr = np.fft.ifft(np.conj(np.fft.fft(x)) * corr_zt)
        m = np.abs(corr).max() / len(zt)
        best = min(best, 2.0 - 2.0 * min(m, 1.0))
    ch = chamfer_loss(c2d[0], target_norm)
    return {"valid": True, "index_loss": float(best), "chamfer": float(ch), "curve": c2d[0]}


# ---------------------------------------------------------------- LLM calls
def load_key():
    for line in open(os.path.join(os.path.dirname(HERE), ".env")):
        line = line.strip()
        if line.startswith("OPENROUTER_API_KEY=") and len(line) > 20:
            return line.split("=", 1)[1].strip()
    raise SystemExit("OPENROUTER_API_KEY missing in .env")


def call_model(model, prompt, key, max_tokens=8000, temperature=0.7):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": temperature}
    # reasoning models need reasoning suppressed or they exhaust the token budget thinking
    reasoning_cfgs = [{"reasoning": {"effort": "low"}},   # works on flash-class reasoning models
                      {"reasoning": {"enabled": False}}]
    req = None
    err = None
    for attempt in range(3):
        try:
            body.update(reasoning_cfgs[min(attempt, len(reasoning_cfgs) - 1)])
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            r = urllib.request.urlopen(req, timeout=300)
            d = json.loads(r.read())
            content = d["choices"][0]["message"]["content"]
            if content:
                return content, None
            err = "empty content (finish_reason=%s)" % d["choices"][0].get("finish_reason")
        except Exception as e:
            err = str(e)
            try:
                err += " :: " + e.read().decode()[:200]
            except Exception:
                pass
            time.sleep(4 * (attempt + 1))
    return None, err


def parse_params(text):
    """Extract the 7 params from a model reply; tolerate JSON in code fences etc."""
    if text is None:
        return None
    import re
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
    except Exception:
        return None
    try:
        branch = j.get("branch", j.get("s", j.get("sign", 1)))
        vals = [float(j["a"]), float(j["b"]), float(j["c"]), float(j["d"]),
                float(j["px"]), float(j["py"]), float(branch)]
        if vals[6] == 0:
            vals[6] = 1.0
        return vals
    except Exception:
        return None


def build_prompt(target_pts: np.ndarray) -> str:
    pts = [[round(float(x), 3), round(float(y), 3)] for x, y in target_pts]
    lines = ",".join(f"[{x},{y}]" for x, y in pts)
    return f"""You are designing a planar four-bar crank-rocker linkage whose coupler point traces a target closed curve.

GEOMETRY (all lengths in abstract units):
- Ground pivots: O2=(0,0) and O4=(d,0).
- Crank: rigid bar of length 'a' from O2 to A. The crank rotates FULLY (a full circle).
- A(θ) = (a·cosθ, a·sinθ), θ sweeping 0..2π.
- Coupler: rigid bar of length 'b' from A to B.
- Rocker: rigid bar of length 'c' from B to O4.
- B is the intersection of the circle of radius b around A with the circle of radius c around O4
  (choose one consistent branch; branch = +1 or -1).
- Pen point P is fixed on the coupler, expressed in the frame with origin at A,
  u = unit vector from A to B, n = perp(u) = (-u_y, u_x):
      P = A + px·u + py·n.
- The pen traces a closed curve as θ goes 0..2π.

HARD CONSTRAINTS:
1. Grashof crank-rocker: 'a' must be the SHORTEST of the four links, and
   (shortest + longest) <= (sum of the other two).
2. The circle intersection must exist for EVERY θ: |b - c| <= dist(A,O4) <= b + c for all θ.
3. If these fail, the linkage is INVALID and scores the maximum error.

TARGET CURVE: {TARGET_N} points, traversed in order (closed curve, first point repeats at the end implicitly):
[{lines}]

The curve is normalized: centroid at origin, RMS radius = 1. Your linkage may be any scale,
position or orientation; scoring is invariant to translation, scale, rotation, starting phase
and traversal direction.

Pick parameters (a, b, c, d, px, py, branch) so the pen path matches this shape as closely as possible.
Think about what class of coupler curve (ellipse-like, figure-eight, cusped, lobed) can be produced
by which linkage proportions, and remember the pen point (px, py) controls much of the shape variety.

Respond with ONLY a JSON object, no prose:
{{"a": <number>, "b": <number>, "c": <number>, "d": <number>, "px": <number>, "py": <number>, "branch": <1 or -1>}}"""


# ---------------------------------------------------------------- persistence
def load_results():
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            return json.load(f)
    return {"llm": {}, "de": {}, "meta": {"started": time.strftime("%Y-%m-%d %H:%M:%S")}}


def save_results(res):
    with open(RESULTS, "w") as f:
        json.dump(res, f, indent=1)


# ---------------------------------------------------------------- runners
def run_llm_bench(models, targets, attempts, key):
    res = load_results()
    target_norm = {name: normalize_batch(resample(pts)[None])[0] for name, pts in targets.items()}
    # prompts need the TARGET_N-point polyline
    prompts = {}
    for name, pts in targets.items():
        rs = resample(pts, TARGET_N)
        rs = normalize_batch(rs[None])[0]
        prompts[name] = build_prompt(rs)

    for model in models:
        res["llm"].setdefault(model, {})
        for tname in targets:
            ent = res["llm"][model].setdefault(tname, {"attempts": []})
            todo = attempts - len(ent["attempts"])
            for k in range(todo):
                t0 = time.time()
                text, err = call_model(model, prompts[tname], key)
                params = parse_params(text)
                sc = score_params(params, target_norm[tname]) if params else \
                    {"valid": False, "index_loss": 10.0, "chamfer": 10.0, "curve": None}
                ent["attempts"].append({
                    "params": params, "parse_ok": params is not None,
                    "valid": sc["valid"], "index_loss": round(sc["index_loss"], 6),
                    "chamfer": round(sc["chamfer"], 6), "seconds": round(time.time() - t0, 1),
                    "error": err,
                })
                save_results(res)  # resumable
                status = "valid" if sc["valid"] else ("PARSE-FAIL" if not params else "INVALID")
                print(f"  {model} / {tname} / attempt {k+1}: {status} "
                      f"index={sc['index_loss']:.4f} chamfer={sc['chamfer']:.4f} ({ent['attempts'][-1]['seconds']}s)")
    return res


def run_de_baseline(targets, budget):
    res = load_results()
    for tname, pts in targets.items():
        if tname in res["de"]:
            print(f"DE {tname}: cached ({res['de'][tname]['index_loss']:.5f})")
            continue
        print(f"DE {tname}: running…")
        out = synthesize(pts, **budget)
        res["de"][tname] = {
            "params": out["params"], "index_loss": round(out["loss"], 6),
            "chamfer": round(out["chamfer"], 6), "seconds": round(out["elapsed"], 1),
        }
        save_results(res)
        print(f"DE {tname}: index={out['loss']:.5f} chamfer={out['chamfer']:.5f} in {out['elapsed']:.0f}s")
    return res


# ---------------------------------------------------------------- reporting
def write_report(res):
    llm, de = res["llm"], res["de"]
    lines = ["# Evolution vs LLMs — mechanism design benchmark", "",
             "Task: given a target closed curve, output the 7 parameters of a 4-bar crank-rocker",
             "linkage whose pen traces it. Everyone scored by the same simulator.",
             "Aggregation: per target we report the best, mean and median of that competitor's attempts.",
             "Note: models are GLM-family (all four); other vendors were not tested.",
             "", "## Leaderboard", ""]
    rows = []
    for model, per_t in llm.items():
        bests, means, medians = [], [], []
        n_att = n_valid = n_parse = 0
        for ent in per_t.values():
            att = ent["attempts"]
            losses = [a["index_loss"] for a in att]
            n_att += len(att)
            n_valid += sum(1 for a in att if a["valid"])
            n_parse += sum(1 for a in att if a["parse_ok"])
            if losses:
                bests.append(min(losses))
                means.append(float(np.mean(losses)))
                medians.append(float(np.median(losses)))
        geo_b = float(np.mean(bests)) if bests else 10.0
        geo_m = float(np.mean(means)) if means else 10.0
        geo_med = float(np.mean(medians)) if medians else 10.0
        rows.append((model, geo_b, geo_m, geo_med, n_parse, n_valid, n_att))
    de_scores = [v["index_loss"] for v in de.values()]
    if de_scores:
        rows.append(("**Kinema evolution (DE baseline, fixed budget)**",
                     float(np.mean(de_scores)), float(np.mean(de_scores)), float(np.median(de_scores)),
                     len(de_scores), len(de_scores), len(de_scores)))
    rows.sort(key=lambda r: r[1])
    lines += ["| competitor | best-of-attempts (per target, mean over targets) | mean attempt | median attempt | parsed | valid | attempts |",
              "|---|---|---|---|---|---|---|"]
    for model, gb, gm, gmed, np_, nv, na in rows:
        lines.append(f"| {model} | {gb:.4f} | {gm:.4f} | {gmed:.4f} | {np_}/{na} | {nv}/{na} | {na} |")
    lines += ["", "## Per-target detail", ""]
    all_targets = sorted({t for m in llm.values() for t in m} | set(de.keys()))
    header = "| target | " + " | ".join(m.split("/")[-1] for m in llm) + " | evolution |"
    lines += [header, "|" + "---|" * (len(llm) + 2)]
    for t in all_targets:
        row = [t]
        for m in llm:
            ent = llm[m].get(t, {"attempts": []})
            b = min((a["index_loss"] for a in ent["attempts"]), default=None)
            row.append(f"{b:.4f}" if b is not None else "—")
        row.append(f"{de[t]['index_loss']:.4f}" if t in de else "—")
        lines.append("| " + " | ".join(row) + " |")
    with open(os.path.join(HERE, "leaderboard.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


def write_chart(res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    llm, de = res["llm"], res["de"]
    targets = sorted(de.keys())
    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = np.arange(len(targets))
    width = 0.8 / (len(llm) + 1)
    colors = plt.cm.tab10(np.linspace(0, 1, len(llm) + 1))
    for i, (model, per_t) in enumerate(llm.items()):
        vals = [min((a["index_loss"] for a in per_t.get(t, {"attempts": []})["attempts"]), default=None)
                for t in targets]
        vals = [v if v is not None and v < 10 else np.nan for v in vals]
        ax.bar(x + i * width, vals, width, label=model.split("/")[-1], color=colors[i])
    devals = [de[t]["index_loss"] for t in targets if t in de]
    ax.bar(x + len(llm) * width, devals, width, label="Kinema evolution", color="#e5484d")
    ax.set_yscale("log")
    ax.set_ylabel("best index loss (lower = better, log scale)")
    ax.set_title("Mechanism design from a sketch: frontier LLMs vs differential evolution\n"
                 "(same task, same simulator; LLM bar missing = no valid linkage produced)")
    ax.set_xticks(x + width * len(llm) / 2)
    ax.set_xticklabels(targets)
    ax.axhline(0.1, color="#888", ls=":", lw=1)
    ax.text(len(targets) - 0.4, 0.105, "visible-error threshold", fontsize=8, color="#888", ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "chart.png"), dpi=130)
    print("chart saved")


def write_gifs(res, targets):
    gifdir = os.path.join(HERE, "gifs")
    os.makedirs(gifdir, exist_ok=True)
    from web.app import render_gif
    for tname, pts in targets.items():
        if tname not in res["de"]:
            continue
        # DE machine gif
        de = res["de"][tname]
        with open(os.path.join(gifdir, f"{tname}_evolution.gif"), "wb") as f:
            f.write(render_gif(np.asarray(de["params"]), pts))
        # best LLM gif (if any valid attempt)
        for model, per_t in res["llm"].items():
            ent = per_t.get(tname, {"attempts": []})
            ok = [a for a in ent["attempts"] if a["valid"] and a.get("params")]
            if not ok:
                continue
            best = min(ok, key=lambda a: a["index_loss"])
            with open(os.path.join(gifdir, f"{tname}_{model.split('/')[-1]}.gif"), "wb") as f:
                f.write(render_gif(np.asarray(best["params"]), pts))
    print("gifs saved to", gifdir)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--targets", nargs="*", default=None)
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-de", action="store_true")
    args = ap.parse_args()

    targets = make_targets()
    if args.targets:
        targets = {k: v for k, v in targets.items() if k in args.targets}
    if args.quick:
        models = args.models or ["z-ai/glm-5.3-flash"]
        attempts = 1
        targets = {k: v for k, v in targets.items() if k in ("ellipse",)}
    else:
        models = args.models or MODELS
        attempts = args.attempts

    if not args.no_llm:
        key = load_key()
        print(f"targets: {list(targets)}  models: {models}  attempts: {attempts}")
        run_llm_bench(models, targets, attempts, key)
    if not args.no_de:
        run_de_baseline(targets, budget={"generations": 320, "popsize": 200, "restarts": 2, "seed": 42})
    res = load_results()
    write_report(res)
    write_chart(res)
    if not args.quick:
        write_gifs(res, targets)


if __name__ == "__main__":
    main()
