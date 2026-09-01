const fs = require("fs");
const path = require("path");
const code = fs.readFileSync("docs/engine.worker.js", "utf8");
global.self = { postMessage: (m) => messages.push(m) };
const messages = [];
(0, eval)(code);
const PRESETS = {
  ellipse: (t) => [Math.cos(t), 0.55 * Math.sin(t)],
  teardrop: (t) => [Math.sin(t) * (1 - Math.cos(t)), 1 - Math.cos(t)],
  infinity: (t) => [Math.cos(t) / (1 + Math.sin(t) ** 2), Math.sin(t) * Math.cos(t) / (1 + Math.sin(t) ** 2)],
  figure8: (t) => [Math.sin(2 * t) * 0.7, Math.sin(t)],
  heart: (t) => [16 * Math.sin(t) ** 3, -(13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t)) / 16],
};
const PYTHON = { ellipse: 0.0046, teardrop: 0.0160, infinity: 0.0180, figure8: 0.0826, heart: 0.0351 };
(async () => {
  for (const [name, f] of Object.entries(PRESETS)) {
    messages.length = 0;
    const pts = Array.from({ length: 220 }, (_, i) => f((i / 220) * 2 * Math.PI));
    const t0 = Date.now();
    global.self.onmessage({ data: { points: pts, cfg: { generations: 320, popsize: 200, seed: 42 } } });
    const dt = (Date.now() - t0) / 1000;
    const r = messages.find((m) => m.type === "done");
    let dsum = 0;
    for (let i = 0; i < 128; i++) dsum += Math.hypot(r.target_machine[i][0] - r.curve[i][0], r.target_machine[i][1] - r.curve[i][1]);
    console.log(`${name}: js=${r.loss.toFixed(4)}  py=${PYTHON[name].toFixed(4)}  ${dt.toFixed(0)}s  overlay_gap=${(dsum/128).toFixed(3)}  valid=${r.valid}`);
  }
})();
