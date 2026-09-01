/* Kinema engine — client-side port of engine/kinematics.py (4-bar DE synthesis).
   Runs in a Web Worker. N = 128 crank samples (power of 2 for the radix-2 FFT). */
"use strict";

const N = 128;
const THETA = Array.from({ length: N }, (_, i) => (i / N) * 2 * Math.PI);
const COS = THETA.map(Math.cos), SIN = THETA.map(Math.sin);
const BOUNDS = [
  [0.15, 2.2], [0.4, 3.6], [0.4, 3.6], [0.6, 4.2],
  [-1.6, 1.6], [-1.6, 1.6], [-1.0, 1.0],
];
const DIM = 7, BIG = 10.0;

// ---------- rng ----------
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------- fft (radix-2, in place) ----------
function fft(re, im, inverse) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      let t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = ((inverse ? 2 : -2) * Math.PI) / len;
    const wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const ur = re[i + k], ui = im[i + k];
        const vr = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci;
        const vi = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr;
        re[i + k] = ur + vr; im[i + k] = ui + vi;
        re[i + k + len / 2] = ur - vr; im[i + k + len / 2] = ui - vi;
        const ncr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = ncr;
      }
    }
  }
  if (inverse) for (let i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
}

// cross-correlation c[s] = sum_i conj(x[i]) y[(i+s) mod n]  via FFT
function xcorr(xr, xi, ftr, fti) {
  const n = xr.length;
  const cr = Float64Array.from(xr), ci = Float64Array.from(xi);
  fft(cr, ci, false);
  const pr = new Float64Array(n), pi = new Float64Array(n);
  for (let k = 0; k < n; k++) {
    pr[k] = cr[k] * ftr[k] + ci[k] * fti[k];   // Re(conj(X)·Y) = Xr·Yr + Xi·Yi
    pi[k] = ci[k] * ftr[k] - cr[k] * fti[k];   // Im(conj(X)·Y) = Xi·Yr - Xr·Yi
  }
  fft(pr, pi, true);
  return { re: pr, im: pi };
}

// ---------- curve utils ----------
function resample(points, n) {
  const closed = points.concat([points[0]]);
  const seg = [];
  let total = 0;
  for (let i = 0; i < closed.length - 1; i++) {
    const d = Math.hypot(closed[i + 1][0] - closed[i][0], closed[i + 1][1] - closed[i][1]);
    seg.push(d); total += d;
  }
  const out = [];
  for (let j = 0; j < n; j++) {
    const s = (j / n) * total;
    let acc = 0, i = 0;
    while (i < seg.length - 1 && acc + seg[i] < s) { acc += seg[i]; i++; }
    const f = seg[i] > 1e-12 ? (s - acc) / seg[i] : 0;
    out.push([closed[i][0] + f * (closed[i + 1][0] - closed[i][0]),
              closed[i][1] + f * (closed[i + 1][1] - closed[i][1])]);
  }
  return out;
}

function normalizePts(c) {
  let mx = 0, my = 0;
  for (const p of c) { mx += p[0]; my += p[1]; }
  mx /= c.length; my /= c.length;
  let ss = 0;
  for (const p of c) ss += (p[0] - mx) ** 2 + (p[1] - my) ** 2;
  const rms = Math.sqrt(ss / c.length) || 1e-9;
  return c.map((p) => [(p[0] - mx) / rms, (p[1] - my) / rms]);
}

// ---------- 4-bar forward kinematics for one individual ----------
// returns {P: Float64Array(2N), valid} ; joints A,B,O2,O4 computed on demand
function couplerCurve(p, out) {
  const a = p[0], b = p[1], c = p[2], d = p[3], px = p[4], py = p[5], sgn = p[6] >= 0 ? 1 : -1;
  const links = [a, b, c, d];
  const mn = Math.min(...links), mx = Math.max(...links);
  if (a > mn + 1e-9) return false;
  if (mn + mx > links.reduce((u, v) => u + v, 0) - mn - mx + 1e-9) return false;
  for (let i = 0; i < N; i++) {
    const ax = a * COS[i], ay = a * SIN[i];
    const dx = d - ax, dy = -ay;
    const e = Math.hypot(dx, dy);
    if (e < 1e-12) return false;
    const cosphi = (b * b + e * e - c * c) / (2 * b * e);
    if (!(Math.abs(cosphi) <= 1)) return false;
    const ang = Math.atan2(dy, dx) + sgn * Math.acos(cosphi);
    const bx = ax + b * Math.cos(ang), by = ay + b * Math.sin(ang);
    const ux = (bx - ax) / b, uy = (by - ay) / b;
    out[2 * i] = ax + px * ux - py * uy;
    out[2 * i + 1] = ay + px * uy + py * ux;
  }
  return true;
}

function normalizeArr(P) {  // Float64Array(2N) -> normalized copy
  let mx = 0, my = 0;
  for (let i = 0; i < N; i++) { mx += P[2 * i]; my += P[2 * i + 1]; }
  mx /= N; my /= N;
  let ss = 0;
  for (let i = 0; i < N; i++) ss += (P[2 * i] - mx) ** 2 + (P[2 * i + 1] - my) ** 2;
  const rms = Math.sqrt(ss / N) || 1e-9;
  const out = new Float64Array(2 * N);
  for (let i = 0; i < N; i++) {
    out[2 * i] = (P[2 * i] - mx) / rms;
    out[2 * i + 1] = (P[2 * i + 1] - my) / rms;
  }
  return out;
}

// loss for one candidate curve vs precomputed target correlation
function lossOfCurve(P, corrRe, corrIm) {
  const zn = normalizeArr(P);
  const xr = new Float64Array(N), xi = new Float64Array(N);
  for (let i = 0; i < N; i++) { xr[i] = zn[2 * i]; xi[i] = zn[2 * i + 1]; }
  let best = BIG;
  for (const rev of [false, true]) {
    const xr2 = new Float64Array(N), xi2 = new Float64Array(N);
    for (let i = 0; i < N; i++) {
      const j = rev ? N - 1 - i : i;
      xr2[i] = xr[j]; xi2[i] = xi[j];  // reversal = traversal direction flip
    }
    const c = xcorr(xr2, xi2, corrRe, corrIm);
    let m = 0;
    for (let s = 0; s < N; s++) m = Math.max(m, Math.hypot(c.re[s], c.im[s]));
    m /= N;
    best = Math.min(best, 2 - 2 * Math.min(m, 1));
  }
  return best;
}

function lossOfParams(p, corrRe, corrIm, curveBuf) {
  if (!couplerCurve(p, curveBuf)) return BIG;
  return lossOfCurve(curveBuf, corrRe, corrIm);
}

// ---------- DE ----------
function synthesize(points, cfg, onGen) {
  const generations = cfg.generations || 320;
  const popsize = cfg.popsize || 200;
  const rng = mulberry32(cfg.seed || 42);

  const target = normalizePts(resample(points, N));
  const tr = new Float64Array(N), ti = new Float64Array(N);
  for (let i = 0; i < N; i++) { tr[i] = target[i][0]; ti[i] = target[i][1]; }
  // conj(fft(target))
  const tfr = Float64Array.from(tr), tfi = Float64Array.from(ti);
  fft(tfr, tfi, false);
  const corrRe = Float64Array.from(tfr), corrIm = Float64Array.from(tfi).map((v) => -v);

  const curveBuf = new Float64Array(2 * N);
  const pop = [], fit = new Float64Array(popsize);
  for (let i = 0; i < popsize; i++) {
    const ind = new Float64Array(DIM);
    for (let k = 0; k < DIM; k++) ind[k] = BOUNDS[k][0] + rng() * (BOUNDS[k][1] - BOUNDS[k][0]);
    pop.push(ind);
    fit[i] = lossOfParams(ind, corrRe, corrIm, curveBuf);
  }
  const history = [Math.min(...fit)];

  for (let gen = 0; gen < generations; gen++) {
    for (let i = 0; i < popsize; i++) {
      let r1 = (rng() * popsize) | 0, r2 = (rng() * popsize) | 0, r3 = (rng() * popsize) | 0;
      if (r1 === i) r1 = (r1 + 1) % popsize;
      if (r2 === i) r2 = (r2 + 1) % popsize;
      if (r3 === i) r3 = (r3 + 1) % popsize;
      const F = 0.35 + rng() * 0.6;
      const trial = new Float64Array(DIM);
      const jr = (rng() * DIM) | 0;
      for (let k = 0; k < DIM; k++) {
        let v = pop[r1][k] + F * (pop[r2][k] - pop[r3][k]);
        if (rng() < 0.9 || k === jr) {
          v = Math.min(BOUNDS[k][1], Math.max(BOUNDS[k][0], v));
          trial[k] = v;
        } else trial[k] = pop[i][k];
      }
      const f = lossOfParams(trial, corrRe, corrIm, curveBuf);
      if (f < fit[i]) { fit[i] = f; pop[i] = trial; }
    }
    const bl = Math.min(...fit);
    history.push(bl);
    if (onGen && (gen % 6 === 0 || gen === generations - 1)) {
      const bi = fit.indexOf(bl);
      const c2 = new Float64Array(2 * N);
      couplerCurve(pop[bi], c2);
      onGen(gen, bl, Array.from(c2), pop[bi].slice());
    }
  }

  // hill-climb polish on the winner
  let bi = fit.indexOf(Math.min(...fit));
  let best = pop[bi].slice(), bl = fit[bi];
  const sigma = [0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.4];
  for (let it = 0; it < 2500; it++) {
    const cand = best.slice();
    const sc = 1 - it / 2600;
    for (let k = 0; k < DIM; k++) {
      cand[k] = Math.min(BOUNDS[k][1], Math.max(BOUNDS[k][0], cand[k] + (rng() * 2 - 1) * sigma[k] * sc));
    }
    const f = lossOfParams(cand, corrRe, corrIm, curveBuf);
    if (f < bl) { bl = f; best = cand; }
  }

  // final artifacts
  const c2 = new Float64Array(2 * N);
  couplerCurve(best, c2);
  const curve = [];
  for (let i = 0; i < N; i++) curve.push([c2[2 * i], c2[2 * i + 1]]);

  const valid = bl < BIG;
  // joints per crank angle
  const A = [], B = [], P = [], O2 = [], O4 = [];
  const a = best[0], b = best[1], c = best[2], d = best[3], px = best[4], py = best[5], sgn = best[6] >= 0 ? 1 : -1;
  let okAll = true;
  for (let i = 0; i < N; i++) {
    const ax = a * COS[i], ay = a * SIN[i];
    const dx = d - ax, dy = -ay;
    const e = Math.hypot(dx, dy);
    const cosphi = (b * b + e * e - c * c) / (2 * b * e);
    if (!(Math.abs(cosphi) <= 1) || e < 1e-12) { okAll = false; }
    const ang = Math.atan2(dy, dx) + sgn * Math.acos(Math.max(-1, Math.min(1, cosphi)));
    const bx = ax + b * Math.cos(ang), by = ay + b * Math.sin(ang);
    const ux = (bx - ax) / b, uy = (by - ay) / b;
    A.push([ax, ay]); B.push([bx, by]);
    P.push([ax + px * ux - py * uy, ay + px * uy + py * ux]);
    O2.push([0, 0]); O4.push([d, 0]);
  }
  // transmission angle
  let gmin = 180, gsum = 0;
  for (let i = 0; i < N; i++) {
    const bx = B[i][0] - A[i][0], by = B[i][1] - A[i][1];
    const rx = O4[i][0] - B[i][0], ry = O4[i][1] - B[i][1];
    const blen = Math.hypot(bx, by) || 1e-9, rlen = Math.hypot(rx, ry) || 1e-9;
    const g = (Math.acos(Math.max(-1, Math.min(1, Math.abs((bx * rx + by * ry) / (blen * rlen))))) * 180) / Math.PI;
    gmin = Math.min(gmin, g); gsum += g;
  }
  // target in machine frame: normalize target, rotate to match curve, scale by curve rms
  const cn = normalizePts(curve);
  let rmsC = 0;
  { let mx = 0, my = 0; for (const p of curve) { mx += p[0]; my += p[1]; } mx /= N; my /= N;
    let ss = 0; for (const p of curve) ss += (p[0] - mx) ** 2 + (p[1] - my) ** 2;
    rmsC = Math.sqrt(ss / N); }
  const zc = cn.map((p) => ({ re: p[0], im: p[1] }));
  const zt = target.map((p) => ({ re: p[0], im: p[1] }));
  // find best shift+rotation mapping curve -> target, then invert to place target on machine
  let bestShift = 0, bestMag = -1, bestRev = false;
  for (const rev of [false, true]) {
    const xr = new Float64Array(N), xi = new Float64Array(N);
    for (let i = 0; i < N; i++) {
      const j = rev ? N - 1 - i : i;
      xr[i] = zc[j].re; xi[i] = zc[j].im;
    }
    const c = xcorr(xr, xi, corrRe, corrIm);
    for (let s = 0; s < N; s++) {
      const m = Math.hypot(c.re[s], c.im[s]);
      if (m > bestMag) { bestMag = m; bestShift = s; bestRev = rev; }
    }
  }
  // target_machine[i] corresponds to machine angle i: roll target so it starts where pen starts
  const tm = [];
  {
    // rotation aligning normalized curve to target: R = conj(sum conj(w) x)/|..| with w = roll(zt,-s)
    const xr = new Float64Array(N), xi = new Float64Array(N);
    for (let i = 0; i < N; i++) {
      const j = bestRev ? N - 1 - i : i;
      xr[i] = zc[j].re; xi[i] = zc[j].im;
    }
    const wr = new Float64Array(N), wi = new Float64Array(N);
    for (let i = 0; i < N; i++) { wr[i] = zt[(i + bestShift) % N].re; wi[i] = zt[(i + bestShift) % N].im; }
    let nr = 0, ni = 0;
    for (let i = 0; i < N; i++) { nr += wr[i] * xr[i] + wi[i] * xi[i]; ni += wr[i] * xi[i] - wi[i] * xr[i]; }
    const mag = Math.hypot(nr, ni) || 1e-9;
    const Rr = nr / mag, Ri = -ni / mag;  // conj(num)/|num|
    // machine-frame target point i: rotate normalized target point (i+shift) by conj(R), scale rms, reverse if needed
    for (let i = 0; i < N; i++) {
      const j = bestRev ? (N - i) % N : (i + bestShift) % N;
      const zx = zt[j].re, zy = zt[j].im;
      const qx = zx * Rr - zy * Ri, qy = zx * Ri + zy * Rr;
      tm.push([qx * rmsC, qy * rmsC]);
    }
  }

  return {
    params: Array.from(best), loss: bl, valid: valid && okAll,
    history, curve,
    target: target,
    target_machine: tm,
    links: { a, b, c, d, px, py },
    transmission: { min_deg: gmin, mean_deg: gsum / N },
    frames: { A, B, P, O2, O4 },
  };
}

self.onmessage = (e) => {
  const { points, cfg } = e.data;
  try {
    const result = synthesize(points, cfg || {}, (gen, loss, curve, params) => {
      self.postMessage({ type: "gen", gen, loss, curve });
    });
    self.postMessage({ type: "done", ...result });
  } catch (err) {
    self.postMessage({ type: "error", message: String(err && err.stack || err) });
  }
};
