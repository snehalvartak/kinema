const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
code = code.replace("  const mag = Math.hypot(nr, ni) || 1e-9;\n  const Rr = nr / mag, Ri = ni / mag;",
"  const mag = Math.hypot(nr, ni) || 1e-9;\n  globalThis.__dbg = {bestShift, nr, ni, mag, rms};\n  const Rr = nr / mag, Ri = ni / mag;");
code += "\nglobalThis.__align = alignTargetToMachine;";
global.self = { postMessage: () => {} };
(0, eval)(code);
const pts = Array.from({length: 128}, (_, i) => { const t = i/128*2*Math.PI; return [Math.cos(t), 0.6*Math.sin(t) + 0.2]; });
const tm = globalThis.__align(pts, pts);
console.log("dbg:", JSON.stringify(globalThis.__dbg));
const xs = tm.map(p=>p[0]), ys = tm.map(p=>p[1]);
console.log("tm extents x:", Math.min(...xs).toFixed(3), Math.max(...xs).toFixed(3), " y:", Math.min(...ys).toFixed(3), Math.max(...ys).toFixed(3));
const cxs = pts.map(p=>p[0]), cys = pts.map(p=>p[1]);
console.log("curve extents x:", Math.min(...cxs).toFixed(3), Math.max(...cxs).toFixed(3), " y:", Math.min(...cys).toFixed(3), Math.max(...cys).toFixed(3));
