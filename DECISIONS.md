# Decision Record

## Process
1. Two independent ideation subagents produced 8 Frontier + 8 Viral concepts (16 distinct ideas).
2. Two independent critique subagents (adversarial judge; feasibility engineer) attacked the shortlist.
3. Both critiques independently converged on **Kinema** (evolutionary linkage synthesis) as #1.
4. Judge proposed fusing Kinema + MechBench into one dual-track submission.
5. Kill-experiment run directly before committing (see below).

## Selected concept: "Kinema — Draw a curve. Evolution invents a machine that draws it."
**One submission, both tracks:**

- **Frontier Build**: Web app where you sketch any closed curve; a differential-evolution
  engine synthesizes a real planar linkage (bars + joints) whose coupler point physically
  traces the sketch, with live evolution visualization. Mechanism synthesis is a real
  mechanical-engineering problem; the optimizer is the moat — not clonable in a weekend.
- **Most Viral / data-science spillover**: "Evolution vs GPT" benchmark — frontier LLMs get
  the same sketch-to-mechanism task with simulator ground truth. Headline claim:
  *gradient-free search on a dual-core laptop beats GPT-class models at mechanism design.*
  Shareable side-by-side GIFs: evolved machine vs LLM's attempt.

## Why this wins (from critique)
- Only shortlisted concept where the hard part is genuinely hard (constraint-valid kinematics,
  phase-invariant shape matching, escape from local optima) — a weak result still shows a moving machine.
- Demo is self-explanatory in 5 seconds; gif-gold.
- Weak laptop is a non-issue (pure numpy, no GPU, no big API bill).
- Saturated alternatives were killed: FuzzArena (PAIR/Garak exist), Agent Honeypot (traffic lottery),
  Spot the Bot (Human-or-Not did it), ModelPrint (signals die to jitter).

## Verified before committing (kill experiment, `prototype/kinema_test.py`)
- 4-bar closed-form kinematics + Grashof constraint: valid ~32% of parameter space.
- DE (scipy, popsize 40, 350 iters, sobol init) matches star/heart/S-curve sketches:
  err 0.067 / 0.035 / 0.081 (mean-squared, RMS-radius units) in **13–19 s on 2 cores**.
- Shape loss validated against an independent brute-force matcher (all shifts × optimal rotation,
  both traversal directions): exact agreement after fixing two bugs we found:
  1. Phase-invariance was missing (closed-curve start-point mismatch) → FFT circular shift search.
  2. Normalization used mean radius instead of RMS → shortcut formula silently under-reported.

## Architecture
- Python 3.11 + numpy + scipy: synthesis engine (`engine/`).
- FastAPI + WebSocket + vanilla JS canvas: draw → stream generations → animate linkage → export GIF.
- LLM benchmark: `benchmark/` — OpenRouter (key in `.env`), simulator-scored, no fabricated results.
