/* Node smoke test for docs/engine.worker.js (loads it with a fake `self`). */
const fs = require("fs");
const path = require("path");

const code = fs.readFileSync(path.join(__dirname, "..", "docs", "engine.worker.js"), "utf8");
const messages = [];
global.self = { postMessage: (m) => messages.push(m) };
(0, eval)(code);

const t = Array.from({ length: 220 }, (_, i) => {
  const th = (i / 220) * 2 * Math.PI;
  return [Math.cos(th) / (1 + Math.sin(th) ** 2) * 2, (Math.sin(th) * Math.cos(th)) / (1 + Math.sin(th) ** 2) * 2];
});

const t0 = Date.now();
global.self.onmessage({ data: { points: t, cfg: { generations: 320, popsize: 200, seed: 42 } } });
const dt = Date.now() - t0;

const done = messages.find((m) => m.type === "done");
const gens = messages.filter((m) => m.type === "gen");
if (!done) { console.error("FAIL: no done message", messages.slice(0, 3)); process.exit(1); }
console.log(`loss=${done.loss.toFixed(5)} valid=${done.valid} elapsed=${(dt / 1000).toFixed(1)}s gens_streamed=${gens.length}`);
console.log(`transmission: min=${done.transmission.min_deg.toFixed(0)}deg  params=[${done.params.map((v) => v.toFixed(2)).join(", ")}]`);
if (done.loss > 0.08) { console.error("FAIL: loss too high for JS engine"); process.exit(1); }
console.log("JS ENGINE OK");
