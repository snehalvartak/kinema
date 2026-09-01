const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
code += "\nglobalThis.__align = alignTargetToMachine;";
global.self = { postMessage: () => {} };
(0, eval)(code);
const pts = Array.from({length: 128}, (_, i) => { const t = i/128*2*Math.PI; return [Math.cos(t), 0.6*Math.sin(t) + 0.2]; });
const tm = globalThis.__align(pts, pts);
// tm should equal curve (centered, radius ~rms)
let mx=0,my=0; for (const p of pts){mx+=p[0];my+=p[1];} mx/=128;my/=128;
let ss=0; for (const p of pts) ss+=(p[0]-mx)**2+(p[1]-my)**2;
const rms=Math.sqrt(ss/128);
const expect = pts.map(([x,y])=>[(x-mx)*rms,(y-my)*rms]);
let g=0; for (let i=0;i<128;i++) g+=Math.hypot(tm[i][0]-expect[i][0], tm[i][1]-expect[i][1]);
console.log("JS trivial align mean gap:", (g/128).toFixed(5));
fs.writeFileSync("prototype/tm_js_trivial.json", JSON.stringify(tm));
