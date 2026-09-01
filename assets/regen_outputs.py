"""Regenerate any zero-byte GIFs + all versus GIFs from merged results."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from benchmark.run_benchmark import make_targets, write_report, write_chart  # noqa: E402
from web.app import render_gif  # noqa: E402
from assets.make_versus_gif import render_pair, pick_llm_attempt  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    res = json.load(open(os.path.join(HERE, "benchmark", "results.json")))
    targets = make_targets()

    # 1) fix any zero-byte per-model gifs
    gifdir = os.path.join(HERE, "benchmark", "gifs")
    for tname, pts in targets.items():
        for model, per_t in res["llm"].items():
            ok = [a for a in per_t.get(tname, {}).get("attempts", [])
                  if a["valid"] and a.get("params")]
            if not ok:
                continue
            best = min(ok, key=lambda a: a["index_loss"])
            out = os.path.join(gifdir, f"{tname}_{model.split('/')[-1]}.gif")
            if not os.path.exists(out) or os.path.getsize(out) < 1000:
                with open(out, "wb") as f:
                    f.write(render_gif(np.asarray(best["params"]), pts))
                print("regenerated", out)

    # 2) versus gifs
    vd = os.path.join(HERE, "assets", "versus")
    os.makedirs(vd, exist_ok=True)
    for tname, pts in targets.items():
        de = res["de"].get(tname)
        if not de:
            continue
        llm = pick_llm_attempt(res, tname)
        de_loss = de["index_loss"]
        de_err = f"error {de_loss:.3f}  ·  2-core laptop, 64k evaluations"
        if llm:
            lerr, lmodel, lparams = llm
            short = lmodel.split("/")[-1]
            render_pair(np.asarray(lparams), np.asarray(de["params"]), pts,
                        f"{short} — one shot, cold", "Kinema — differential evolution",
                        os.path.join(vd, f"{tname}_versus.gif"),
                        err_a=f"error {lerr:.3f}  ·  {lerr / de_loss:.0f}x worse",
                        err_b=de_err)
        else:
            print("no valid LLM attempt for", tname)

    # 3) refresh report + chart from merged results
    write_report(res)
    write_chart(res)
    print("report + chart refreshed")


if __name__ == "__main__":
    main()
