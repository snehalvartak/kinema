"""Re-score every stored design (LLM attempts, DE baseline, feedback, hybrid) under the
corrected correlation metric, so all competitors are evaluated uniformly."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.kinematics import chamfer_loss, normalize_batch, resample  # noqa: E402
from benchmark.run_benchmark import make_targets, score_params, load_results, save_results, RESULTS  # noqa: E402

res = load_results()
targets = make_targets()
target_norm = {n: normalize_batch(resample(p)[None])[0] for n, p in targets.items()}

# LLM attempts
for model, per_t in res["llm"].items():
    for tname, ent in per_t.items():
        for a in ent["attempts"]:
            if a.get("params"):
                sc = score_params(np.asarray(a["params"], float), target_norm[tname])
                a["index_loss"] = round(sc["index_loss"], 6)
                a["chamfer"] = round(sc["chamfer"], 6)
                a["valid"] = sc["valid"]

# DE baseline
for tname, ent in res["de"].items():
    sc = score_params(np.asarray(ent["params"], float), target_norm[tname])
    ent["index_loss"] = round(sc["index_loss"], 6)
    ent["chamfer"] = round(sc["chamfer"], 6)

# feedback arms
for model, per_t in res.get("feedback", {}).items():
    for tname, ent in per_t.items():
        if ent.get("best_params"):
            sc = score_params(np.asarray(ent["best_params"], float), target_norm[tname])
            ent["best_index_loss"] = sc["index_loss"]
        for h in ent.get("rounds", []):
            if h.get("parse_ok") and ent.get("best_params") is None:
                pass  # per-round params weren't stored individually; keep as-is

# hybrid arms
for model, per_t in res.get("hybrid", {}).items():
    for tname, ent in per_t.items():
        for key in ("hybrid_small", "hybrid_full"):
            if key in ent and ent[key].get("params"):
                sc = score_params(np.asarray(ent[key]["params"], float), target_norm[tname])
                ent[key]["index_loss"] = round(sc["index_loss"], 6)
                ent[key]["chamfer"] = round(sc["chamfer"], 6)

save_results(res)
print("rescored:", RESULTS)

# quick summary
for model, per_t in res["llm"].items():
    bests = [min(a["index_loss"] for a in ent["attempts"]) for ent in per_t.values()]
    print(f"  {model}: mean-best {np.mean(bests):.4f}")
print(f"  evolution: mean {np.mean([v['index_loss'] for v in res['de'].values()]):.4f}")
