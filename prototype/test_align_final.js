const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
code += "\nglobalThis.__align = alignTargetToMachine;";
global.self = { postMessage: () => {} };
(0, eval)(code);
function norm(P){let mx=0,my=0;for(const p of P){mx+=p[0];my+=p[1];}mx/=P.length;my/=P.length;let ss=0;for(const p of P)ss+=(p[0]-mx)**2+(p[1]-my)**2;const rms=Math.sqrt(ss/P.length);return P.map(([x,y])=>[(x-mx)/rms,(y-my)/rms]);}
function orderless(A,B){const A2=norm(A),B2=norm(B);let g=0;for(const [x,y] of A2){let m=1e9;for(const [u,v] of B2)m=Math.min(m,Math.hypot(x-u,y-v));g+=m;}return g/A2.length;}
const presets = {
  infinity: (t) => [Math.cos(t)/(1+Math.sin(t)**2), Math.sin(t)*Math.cos(t)/(1+Math.sin(t)**2)],
  figure8: (t) => [Math.sin(2*t)*0.7, Math.sin(t)],
};
const cache = {};
for (const [name, f] of Object.entries(presets)) {
  const pts = Array.from({length:220},(_,i)=>{const [x,y]=f(i/220*2*Math.PI);return [x*2,y*2];});
  const messages = [];
  global.self.postMessage = (m)=>messages.push(m);
  global.self.onmessage({ data: { points: pts, cfg: { generations: 40, popsize: 80, seed: 42 } } });
  const r = messages.find(m=>m.type==="done");
  cache[name] = r.curve;
  const tm = globalThis.__align(r.curve, pts);
  const g = orderless(tm, r.curve);
  console.log(name, "ghost orderless gap:", g.toFixed(4));
}
