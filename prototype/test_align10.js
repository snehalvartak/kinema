const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
const marker = "const c = xcorr(xr, xi, cRe, cIm);";
const idx = code.indexOf(marker);
console.log("marker found at:", idx);
// insert debug after the marker's enclosing lines using splice on lines
const lines = code.split("\n");
for (let i = 0; i < lines.length; i++) {
  if (lines[i].includes("const c = xcorr(xr, xi, cRe, cIm);")) {
    lines.splice(i + 1, 0, "      globalThis.__dbg2 = { rev, c0: Math.hypot(c.re[0], c.im[0]), c63: Math.hypot(c.re[63], c.im[63]), c64: Math.hypot(c.re[64], c.im[64]) };");
    break;
  }
}
code = lines.join("\n") + "\nglobalThis.__align = alignTargetToMachine;";
global.self = { postMessage: () => {} };
(0, eval)(code);
const pts = Array.from({length: 128}, (_, i) => { const t = i/128*2*Math.PI; return [Math.cos(t), 0.6*Math.sin(t) + 0.2]; });
globalThis.__align(pts, pts);
console.log("dbg2:", JSON.stringify(globalThis.__dbg2));
