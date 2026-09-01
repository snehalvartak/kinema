const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
// instrument align internals
code = code.replace("const mag = Math.hypot(nr, ni) || 1e-9;", "const mag = Math.hypot(nr, ni) || 1e-9; globalThis.__dbg = {bestShift, nr, ni, mag};");
code += "\nglobalThis.__align = alignTargetToMachine;";
global.self = { postMessage: () => {} };
(0, eval)(code);
const pts = Array.from({length: 128}, (_, i) => { const t = i/128*2*Math.PI; return [Math.cos(t), 0.6*Math.sin(t) + 0.2]; });
const tm = globalThis.__align(pts, pts);
console.log("dbg:", JSON.stringify(globalThis.__dbg));
console.log("tm[0..2]:", JSON.stringify(tm.slice(0,3)));
console.log("curve centered [0..2]:", JSON.stringify(pts.slice(0,3).map(([x,y])=>[x, y-0.2])));
