# X post drafts — final numbers from benchmark/results.json (real runs)

## Post 1 — the hook (hero GIF: assets/hero_infinity.gif)
I drew this curve with my mouse.

Evolution invented a MACHINE that draws it — four bars, four joints, one pen.
Same mechanism family as a windshield wiper. No AI. No neural network.
200 random machines mutating for 20 seconds on a 2012 dual-core laptop.

Then I made four frontier LLMs do the same job. It wasn't close. 🧵

Reply with a shape and I'll evolve the machine that draws it.

## Post 2 — the benchmark (assets/versus/figure8_versus.gif + benchmark/chart.png)
Same task for everyone: "here's a closed curve, output the 7 numbers of a 4-bar
linkage whose pen traces it." Same simulator scores every design.

- glm-5.3-flash, one shot: error 0.347 — draws a thin arc, not a figure-8
- differential evolution, 64k evaluations, 2 cores: error 0.083 — traces it

Across 6 shapes × 4 GLM models: evolution wins every single target.
The typical LLM attempt is 7–170× worse than its own best attempt.
One of them (glm-4.5-air) built a machine that violates Grashof's law —
it would JAM — in 4 of 18 attempts.

## Post 3 — the twist (feedback data)
"Sure, the LLM lost because you didn't let it iterate."

So I put the simulator in the loop: after every attempt the model saw its own
pen path, its error score, and WHICH constraint it violated. 4 rounds each.

It didn't help. glm-5.3-flash's best ellipse design got WORSE with feedback
(0.007 cold → 0.053 with feedback). The LLMs can't steer by numbers.
Evolution doesn't need to read — it just dies and breeds. [numbers: results.json "feedback"]

## Post 4 — the science angle (assets/capacity_limit.png)
Bonus finding: 6 independent evolution runs on a heart shape all converge to the
same error within 0.2%. That's not the optimizer hitting a local optimum — that's
the exact moment where a shape leaves the 4-bar family's vocabulary. The machine
tells you what it cannot draw.

## Post 5 — try it
I made the whole thing interactive: draw ANY closed curve, watch 200 machines
evolve live in your browser, and the winner is a real mechanism animating over
your sketch. Export your machine as a GIF.

[URL — deploy/public_url.ps1 prints a free instant tunnel URL]
