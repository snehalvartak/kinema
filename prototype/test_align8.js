const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
code += "\nglobalThis.__align = alignTargetToMachine;";
global.self = { postMessage: () => {} };
(0, eval)(code);
const pts = Array.from({length: 128}, (_, i) => { const t = i/128*2*Math.PI; return [Math.cos(t), 0.6*Math.sin(t) + 0.2]; });
const tm = globalThis.__align(pts, pts);
fs.writeFileSync("prototype/trivial_dump.json", JSON.stringify({ curve: pts, tm }));
console.log("dumped");
