# Evolution vs LLMs — mechanism design benchmark

Task: given a target closed curve, output the 7 parameters of a 4-bar crank-rocker
linkage whose pen traces it. Everyone scored by the same simulator.
Aggregation: per target we report the best, mean and median of that competitor's attempts.
Note: models are GLM-family (all four); other vendors were not tested.

## Leaderboard

| competitor | best-of-attempts (per target, mean over targets) | mean attempt | median attempt | parsed | valid | attempts |
|---|---|---|---|---|---|---|
| **Kinema evolution (DE baseline, fixed budget)** | 0.0400 | 0.0400 | 0.0395 | 6/6 | 6/6 | 6 |
| z-ai/glm-5.3-flash | 0.1320 | 0.7887 | 0.2100 | 17/18 | 17/18 | 18 |
| z-ai/glm-4.5-air | 0.1421 | 2.3940 | 1.8655 | 18/18 | 14/18 | 18 |
| z-ai/glm-5.2 | 0.1601 | 0.2854 | 0.2992 | 18/18 | 18/18 | 18 |
| z-ai/glm-4.6 | 0.1670 | 0.2201 | 0.2154 | 18/18 | 18/18 | 18 |

## Per-target detail

| target | glm-5.3-flash | glm-5.2 | glm-4.6 | glm-4.5-air | evolution |
|---|---|---|---|---|---|
| ellipse | 0.0071 | 0.1109 | 0.0783 | 0.0074 | 0.0055 |
| figure8 | 0.3472 | 0.4237 | 0.3915 | 0.4760 | 0.0826 |
| heart | 0.0560 | 0.1040 | 0.1167 | 0.0528 | 0.0570 |
| infinity | 0.1992 | 0.1570 | 0.2416 | 0.1717 | 0.0331 |
| star | 0.1628 | 0.1313 | 0.1316 | 0.0804 | 0.0460 |
| teardrop | 0.0197 | 0.0337 | 0.0425 | 0.0642 | 0.0160 |