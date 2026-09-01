const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
global.self = { postMessage: () => {} };
(0, eval)(code);
const presets = {
  heart: (t) => [(16 * Math.sin(t) ** 3) / 16, -(13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t)) / 16],
};
const messages = [];
global.self.postMessage = (m)=>messages.push(m);
const pts = Array.from({length:220},(_,i)=>{const [x,y]=presets.heart(i/220*2*Math.PI);return [x,y];});
global.self.onmessage({ data: { points: pts, cfg: { generations: 320, popsize: 200, seed: 42 } } });
const r = messages.find(m=>m.type==="done");
console.log("heart (fixed preset): loss =", r.loss.toFixed(4), "valid =", r.valid);
fs.writeFileSync("prototype/heart_fixed.json", JSON.stringify({curve: r.curve, tm: r.target_machine}));
