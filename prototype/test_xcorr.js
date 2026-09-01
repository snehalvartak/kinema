const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
code += "\nglobalThis.__xcorr = xcorr; globalThis.__fft = fft;";
global.self = { postMessage: () => {} };
(0, eval)(code);
const n = 128;
const pts = Array.from({length: n}, (_, i) => { const t = i/n*2*Math.PI; return [Math.cos(t), 0.6*Math.sin(t)]; });
const zr = new Float64Array(n), zi = new Float64Array(n);
for (let i = 0; i < n; i++) { zr[i] = pts[i][0]; zi[i] = pts[i][1]; }
const fr = Float64Array.from(zr), fi = Float64Array.from(zi);
globalThis.__fft(fr, fi, false);
const c = globalThis.__xcorr(zr, zi, fr, fi);
const brute = [];
for (let s = 0; s < n; s++) {
  let rr = 0, ii = 0;
  for (let i = 0; i < n; i++) {
    const j = (i + s) % n;
    rr += zr[i]*zr[j] + zi[i]*zi[j];
    ii += zi[i]*zr[j] - zr[i]*zi[j];
  }
  brute.push(Math.hypot(rr, ii));
}
const fftm = Array.from({length: n}, (_, s) => Math.hypot(c.re[s], c.im[s]));
let maxdiff = 0, argb = 0, argf = 0;
for (let s = 0; s < n; s++) { if (brute[s] > brute[argb]) argb = s; if (fftm[s] > fftm[argf]) argf = s; maxdiff = Math.max(maxdiff, Math.abs(brute[s]-fftm[s])); }
console.log("max |fft - brute|:", maxdiff.toFixed(6), " brute argmax:", argb, " fft argmax:", argf, " brute[64]:", brute[64].toFixed(3), " fft[64]:", fftm[64].toFixed(3));
