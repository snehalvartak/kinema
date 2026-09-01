# KINEMA

**Draw a curve. Evolution invents a machine that draws it.**

You sketch any closed curve. A differential-evolution engine synthesizes a real planar
four-bar crank-rocker linkage — four bars, four joints, one pen point — whose coupler
point physically traces your curve. Then the machine animates, and you can export it as a GIF.

No neural network. No training data. Pure mechanics + search, running in ~20 seconds
on a dual-core laptop CPU.

---

## Run it

```powershell
python -m pip install numpy scipy matplotlib fastapi "uvicorn[standard]" imageio
python -m uvicorn web.app:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000
```

Draw with the mouse or click a preset → **Invent my machine** → watch generations
stream live → the invented machine animates, tracing your sketch → **Export GIF**.

## The benchmark: Evolution vs LLMs

`benchmark/run_benchmark.py` gives frontier LLMs (via OpenRouter) the *same* task the
evolution engine solves — output the 7 parameters of a crank-rocker that traces a
given curve — and scores everyone with the exact same simulator and metrics:

- **index loss** — mean squared gap between pen path and sketch (invariant to
  translation, scale, rotation, starting phase, traversal direction)
- **chamfer** — orderless symmetric mean squared distance (sharp features like cusps)
- **valid** — does the linkage obey Grashof's law and assemble for a full rotation?

```powershell
python benchmark/run_benchmark.py --quick   # 1 model, 1 target, smoke test
python benchmark/run_benchmark.py           # full leaderboard (resumable, cached)
```

Outputs: `benchmark/leaderboard.md`, `benchmark/chart.png` (log scale),
`benchmark/gifs/` (per-model machines) and `assets/versus/` (side-by-side
LLM-vs-evolution on the same sketch).

Two extra arms live in `benchmark/feedback_arm.py`:
- **feedback** — the LLM sees its own pen path, error score and violated constraints,
  and revises, 4 rounds;
- **hybrid** — LLM proposals seed the DE population (10%-budget vs full-budget).

**Headline results** (all numbers from real runs — `benchmark/results.json`, `benchmark/leaderboard.md`):

- **Evolution wins every target.** Best-of-3-attempts per target, mean over 6 targets:
  DE 0.033 vs the best LLM's 0.132 — and the *typical* LLM attempt (mean 0.22–5.6)
  is 7–170x worse than its own best. One lucky flash attempt on the ellipse (0.0071)
  came close to evolution (0.0046); on figure8 the same model was 4x worse (0.35 vs 0.083).
- **Consistency, not just peak ability, is the gap.** All four GLM-family models
  (no other vendors tested) produce wildly varying quality from the same prompt.
  glm-4.5-air produced an *invalid* linkage — violating Grashof's law or unable to
  assemble — in 4 of 18 attempts.
- **Feedback doesn't rescue them.** We re-ran with the simulator in the loop: after each
  attempt the model saw its own pen path, its numeric error, and *which constraint it
  violated*, for 4 rounds. Result: no consistent improvement — glm-5.3-flash's ellipse
  got *worse* with feedback (0.007 cold → 0.053 best-with-feedback).
- **Hybrid is neutral.** Seeding DE's initial population with 5 LLM proposals lets a
  10%-budget run match the full-budget baseline on most targets — but so does pure DE;
  the LLM's contribution is statistically invisible.

Everything needed to reproduce is in the repo: prompts, raw per-attempt scores, and the
scoring simulator.

## How it works

**Prior art, honestly.** Coupler-curve synthesis is a classical mechanism-design problem —
the Hrones–Nelson atlas (1951) catalogued thousands of 4-bar coupler curves by hand, and
evolutionary mechanism synthesis exists in the academic literature. What's new here is the
combination: an interactive *draw anything → invent the machine* experience with a
phase/rotation/scale-invariant matching metric, fully vectorized on CPU, plus a head-to-head
benchmark of the same task against frontier LLMs.

**The machine.** Ground pivots O2=(0,0), O4=(d,0). The crank (length *a*) rotates fully;
the coupler (length *b*) connects crank tip A to rocker tip B; the rocker (length *c*)
swings. A pen point fixed to the coupler frame, `P = A + px·u + py·n` (u = unit A→B,
n = perp(u)), traces a closed coupler curve. Hard constraints: Grashof crank-rocker
(a shortest, s + l ≤ p + q) and assemblability at every crank angle.

**The search.** Fully vectorized differential evolution (population-level forward
kinematics + batch FFT), sobol-initialized, with a two-stage Nelder-Mead polish:

1. *Phase-invariant shape loss*: both curves are centroid/RMS-normalized, represented
   as complex sequences; the best circular shift (via FFT cross-correlation) and
   optimal unit rotation give residual `2 − 2|⟨z_t, S_s z_c⟩|/N`, evaluated for both
   traversal directions. This makes matching invariant to where the pen starts and
   which way the crank spins.
2. *Orderless chamfer polish*: KD-tree symmetric distance sharpens cusps that
   index-wise correspondence underweights.

An interesting negative result: the heart's top cusp converges to the same optimum
from any seed and budget — a genuine capacity limit of the 4-bar family, not an
optimizer failure. (6-bar synthesis is the natural extension.)

## Repo layout

```
engine/kinematics.py         synthesis engine (kinematics, losses, DE, polish, GIF frames)
web/app.py                   FastAPI app: WebSocket synthesis streaming + GIF rendering
web/static/                  canvas UI (draw → evolve → animate → export)
benchmark/run_benchmark.py   Evolution vs LLMs main benchmark (OpenRouter; key in .env)
benchmark/feedback_arm.py    feedback + hybrid arms
assets/                      hero GIF, versus GIFs, capacity-limit figure, post drafts
prototype/                   the kill-experiments that validated the concept
DECISIONS.md                 concept exploration, critiques, and the selection rationale
DEMO.md                      rehearsed live-demo runbook
```

## Honest notes

- All benchmark numbers come from real runs of real models; nothing is fabricated.
  PARSE-FAIL means the model never emitted parsable JSON; INVALID means the linkage
  violates Grashof's law or cannot assemble. Most parsed outputs were *valid but poor* —
  they obey the constraints yet design badly (glm-4.5-air went invalid in 4/18 attempts).
- The 4-bar family cannot trace every shape; the app shows the best real mechanism.
- Built for the Cerebral Valley Lightning Hackathon — Frontier Build + Most Viral tracks.
