const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
code = code.replace("      const c = xcorr(xr, xi, cRe, cIm);\n      for (let s = 0; s < Nc; s++) {",
"      const c = xcorr(xr, xi, cRe, cIm);\n      if (rev === false) { globalThis.__c0 = Math.hypot(c.re[0], c.im[0]); globalThis.__c63 = Math.hypot(c.re[63], c.im[63]); globalThis.__c64 = Math.hypot(c.re[64], c.im[64]); }");
code += "\nglobalThis.__align = alignTargetToMachine;";
global.self = { postMessage: () => {} };
(0, eval)(code);
const pts = Array.from({length: 128}, (_, i) => { const t = i/128*2*Math.PI; return [Math.cos(t), 0.6*Math.sin(t) + 0.2]; });
globalThis.__align(pts, pts);
console.log("fwd |c[0]|:", globalThis.__c0.toFixed(3), " |c[63]|:", globalThis.__c63.toFixed(3), " |c[64]|:", globalThis.__c64.toFixed(3));
