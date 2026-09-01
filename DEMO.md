# Demo runbook (rehearse this exact sequence)

## Pre-demo (night before)
1. `python -m pip install -r requirements.txt`
2. Warm the preset cache: start the app, click every preset once (each takes ~20-40s,
   then replays instantly forever). This makes the live demo snappy.
3. Check `.env` has OPENROUTER_API_KEY only if re-running the benchmark live —
   NEVER run API calls live on stage; results are precomputed in `benchmark/results.json`.

## Live sequence (~4 minutes)
1. Open http://127.0.0.1:8000 (hard-coded port; if occupied, kill the process first).
2. Point at the explainer: "A 4-bar linkage — the mechanism inside windshield wipers.
   The pen point fixed to the coupler traces a curve. That's its handwriting."
3. Draw a rough heart with the mouse (DO NOT use a preset for the first one — hand-drawn
   is the wow). Press "Invent my machine". While it evolves (~20-40s), narrate the
   narration text: random machines die, better ones breed.
4. Machine animates tracing the sketch. Say: "Invented, not programmed."
5. Click the "infinity" preset — replays instantly from cache (say "cached — already
   evolved this one").
6. Show `benchmark/chart.png`: "Same task, frontier LLMs, one shot each. A dumb
   evolutionary search on a 2012 laptop wins."

## Failure modes & answers
- **Synthesis too slow on stage**: preset cache + narration fills the time; worst case
  show the hero GIF while it runs.
- **Ugly hand-drawn sketch matches poorly**: "The app always shows the best REAL
  mechanism — some shapes a 4-bar physically cannot draw. We measured exactly where
  that capacity limit sits" (see `assets/capacity_limit.png`).
- **"Isn't this just scipy DE?"**: "The optimizer is one function call. The work is the
  constraint-valid kinematics, the phase/rotation-invariant FFT matching, batch
  vectorization to make 64k evaluations take 20 seconds on 2 cores — and proving what
  the 4-bar family can and cannot express."
- **"Did LLMs really lose?"**: show `benchmark/leaderboard.md` — every number is from a
  real run, models listed by name, prompts in the repo. Feedback-loop and hybrid arms
  included; the LLM gets every benefit of the doubt.

## Public URL (if internet available)
`powershell -File deploy/public_url.ps1` → prints a trycloudflare.app URL.
Fallback: screen-record the app + GIFs.
