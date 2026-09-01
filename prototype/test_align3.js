const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
// instrument: dump align intermediates
code = code.replace("const mag = Math.hypot(nr, ni) || 1e-9;", "const mag = Math.hypot(nr, ni) || 1e-9; self.postMessage({type:'dbg', bestShift, nr, ni, mag, firstX: Array.from(bxr).slice(0,3), firstXi: Array.from(bxi).slice(0,3)});");
const messages = [];
global.self = { postMessage: (m) => messages.push(m) };
(0, eval)(code);
const f = (t) => [Math.cos(t)/(1+Math.sin(t)**2), Math.sin(t)*Math.cos(t)/(1+Math.sin(t)**2)];
const pts = Array.from({length: 220}, (_, i) => { const [x,y] = f(i/220*2*Math.PI); return [x*2, y*2]; });
global.self.onmessage({ data: { points: pts, cfg: { generations: 5, popsize: 30, seed: 42 } } });
console.log(JSON.stringify(messages.find(m => m.type === 'dbg')));
