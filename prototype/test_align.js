const fs = require("fs");
const code = fs.readFileSync("docs/engine.worker.js", "utf8");
const messages = [];
global.self = { postMessage: (m) => messages.push(m) };
(0, eval)(code);
const f = (t) => [Math.cos(t)/(1+Math.sin(t)**2), Math.sin(t)*Math.cos(t)/(1+Math.sin(t)**2)];
const pts = Array.from({length: 220}, (_, i) => { const [x,y] = f(i/220*2*Math.PI); return [x*2, y*2]; });
global.self.onmessage({ data: { points: pts, cfg: { generations: 320, popsize: 200, seed: 42 } } });
const r = messages.find((m) => m.type === "done");
// orderless gap: for each tm point, min distance to any curve point (both centered+normalized)
function norm(P) {
  let mx=0,my=0; for (const p of P){mx+=p[0];my+=p[1];} mx/=P.length;my/=P.length;
  let ss=0; for (const p of P) ss+=(p[0]-mx)**2+(p[1]-my)**2;
  const rms=Math.sqrt(ss/P.length);
  return P.map(([x,y])=>[(x-mx)/rms,(y-my)/rms]);
}
const A = norm(r.target_machine), B = norm(r.curve);
let g1=0, g2=0;
for (const [x,y] of A) { let m=1e9; for (const [u,v] of B) m=Math.min(m, Math.hypot(x-u,y-v)); g1+=m; }
for (const [x,y] of B) { let m=1e9; for (const [u,v] of A) m=Math.min(m, Math.hypot(x-u,y-v)); g2+=m; }
console.log("orderless mean gap tm->curve:", (g1/A.length).toFixed(4), " curve->tm:", (g2/B.length).toFixed(4));
