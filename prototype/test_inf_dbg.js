const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
code = code.replace(
  "  let nr = 0, ni = 0;\n  for (let i = 0; i < Nc; i++) {\n    nr += wr[i] * bxr[i] + wi[i] * bxi[i];\n    ni += wr[i] * bxi[i] - wi[i] * bxr[i];\n  }",
  "  let nr = 0, ni = 0;\n  for (let i = 0; i < Nc; i++) {\n    nr += wr[i] * bxr[i] + wi[i] * bxi[i];\n    ni += wr[i] * bxi[i] - wi[i] * bxr[i];\n  }\n  globalThis.__dbg = { bestShift, mag: bestMag, nr, ni };");
code += "\nglobalThis.__align = alignTargetToMachine;";
global.self = { postMessage: () => {} };
(0, eval)(code);
const d = JSON.parse(fs.readFileSync("prototype/inf_debug.json", "utf8"));
const f = (t) => [Math.cos(t)/(1+Math.sin(t)**2), Math.sin(t)*Math.cos(t)/(1+Math.sin(t)**2)];
const pts = Array.from({length:220},(_,i)=>{const [x,y]=f(i/220*2*Math.PI);return [x*2,y*2];});
globalThis.__align(d.curve, pts);
console.log("JS dbg:", JSON.stringify(globalThis.__dbg));
