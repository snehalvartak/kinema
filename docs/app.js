/* Kinema frontend — standalone client-side version (GitHub Pages).
   The synthesis engine runs in a Web Worker; no server involved. */
"use strict";

const $ = (id) => document.getElementById(id);
const drawCv = $("draw"), stageCv = $("stage"), sparkCv = $("spark");
const dctx = drawCv.getContext("2d"), sctx = stageCv.getContext("2d"), kctx = sparkCv.getContext("2d");

const PRESETS = {
  heart: (t) => [(16 * Math.sin(t) ** 3) / 16, -(13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t)) / 16],
  infinity: (t) => [Math.cos(t) / (1 + Math.sin(t) ** 2), Math.sin(t) * Math.cos(t) / (1 + Math.sin(t) ** 2)],
  teardrop: (t) => [Math.sin(t) * (1 - Math.cos(t)), (1 - Math.cos(t))],
  figure8: (t) => [Math.sin(2 * t) * 0.7, Math.sin(t)],
  ellipse: (t) => [Math.cos(t), 0.55 * Math.sin(t)],
};
function starPreset() {
  const pts = [], R = 1, r = 0.5;
  for (let i = 0; i < 5; i++) {
    const ao = -Math.PI / 2 + (i * 2 * Math.PI) / 5, ai = ao + Math.PI / 5;
    pts.push([R * Math.cos(ao), R * Math.sin(ao)], [r * Math.cos(ai), r * Math.sin(ai)]);
  }
  return pts;
}
PRESETS.star = () => starPreset();

// ---------- drawing ----------
let sketch = [], presetName = null, drawing = false, last = performance.now();

function clearDraw() { sketch = []; presetName = null; dctx.clearRect(0, 0, drawCv.width, drawCv.height); }

function drawSketchLine(pts, close = true) {
  dctx.clearRect(0, 0, drawCv.width, drawCv.height);
  if (pts.length < 2) return;
  dctx.strokeStyle = "#e8edf2";
  dctx.lineWidth = 3;
  dctx.lineJoin = "round";
  dctx.lineCap = "round";
  dctx.beginPath();
  dctx.moveTo(pts[0][0], pts[0][1]);
  for (const [x, y] of pts) dctx.lineTo(x, y);
  if (close) dctx.closePath();
  dctx.stroke();
}

drawCv.addEventListener("pointerdown", (e) => {
  if (running) return;
  drawing = true;
  presetName = null;
  sketch = [];
  sketch.push(pos(e));
  drawSketchLine(sketch, false);
});
drawCv.addEventListener("pointermove", (e) => {
  if (!drawing) return;
  const p = pos(e), q = sketch[sketch.length - 1];
  if (Math.hypot(p[0] - q[0], p[1] - q[1]) > 2) {
    sketch.push(p);
    if (performance.now() - last > 16) { drawSketchLine(sketch, false); last = performance.now(); }
  }
});
window.addEventListener("pointerup", () => { if (drawing) { drawing = false; drawSketchLine(sketch); } });
function pos(e) {
  const r = drawCv.getBoundingClientRect();
  return [(e.clientX - r.left) * (drawCv.width / r.width),
          (e.clientY - r.top) * (drawCv.height / r.height)];
}

// ---------- presets ----------
const chipsEl = $("presets");
for (const name of Object.keys(PRESETS)) {
  const b = document.createElement("button");
  b.className = "chip";
  b.textContent = name;
  b.onclick = () => {
    if (running) return;
    const n = 220, t = Array.from({ length: n }, (_, i) => (i / n) * 2 * Math.PI);
    const f = PRESETS[name];
    const raw = name === "star" ? f() : t.map((tt) => f(tt));
    const xs = raw.map((p) => p[0]), ys = raw.map((p) => p[1]);
    const s = Math.min((drawCv.width - 80) / (Math.max(...xs) - Math.min(...xs)),
                       (drawCv.height - 80) / (Math.max(...ys) - Math.min(...ys)));
    const cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2;
    sketch = raw.map(([x, y]) => [drawCv.width / 2 + (x - cx) * s, drawCv.height / 2 + (y - cy) * s]);
    presetName = name;
    drawSketchLine(sketch);
  };
  chipsEl.appendChild(b);
}
$("clear").onclick = clearDraw;

// ---------- worker ----------
let running = false, frames = null, animId = null, lastPoints = null, genStart = null, lastGenTime = null;
let worker = null, totalGens = 320, speed = "full";

// speed control
for (const b of document.querySelectorAll(".speed-chip")) {
  b.onclick = () => {
    if (running) return;
    speed = b.dataset.speed;
    for (const x of document.querySelectorAll(".speed-chip")) x.classList.toggle("selected", x === b);
  };
}
const SPEED_CFG = {
  fast: { generations: 120, popsize: 120 },
  full: { generations: 320, popsize: 200 },
};

function setRunning(v) {
  running = v;
  $("evolve").disabled = v;
  $("evolve").textContent = v ? "Evolving…" : "Invent my machine";
  $("doneRow").hidden = true;
  $("legend").hidden = true;
  $("bar").style.width = "0%";
}
function narrate(html) { $("narration").innerHTML = html; }

function fitTransform(pts, W, H, pad = 40) {
  let minx = 1e9, miny = 1e9, maxx = -1e9, maxy = -1e9;
  for (const [x, y] of pts) { minx = Math.min(minx, x); maxx = Math.max(maxx, x); miny = Math.min(miny, y); maxy = Math.max(maxy, y); }
  const s = Math.min((W - pad * 2) / (maxx - minx || 1), (H - pad * 2) / (maxy - miny || 1));
  const cx = (minx + maxx) / 2, cy = (miny + maxy) / 2;
  return (p) => [W / 2 + (p[0] - cx) * s, H / 2 + (p[1] - cy) * s, s];
}

function drawEvolution(targetPts, curvePts) {
  const W = stageCv.width, H = stageCv.height;
  sctx.clearRect(0, 0, W, H);
  if (!targetPts) return;
  const all = curvePts ? targetPts.concat(curvePts) : targetPts;
  const tf = fitTransform(all, W, H);
  sctx.strokeStyle = "rgba(139,150,165,0.75)";
  sctx.setLineDash([5, 5]);
  sctx.lineWidth = 1.6;
  sctx.beginPath();
  targetPts.forEach(([x, y], i) => { const q = tf([x, y]); i ? sctx.lineTo(q[0], q[1]) : sctx.moveTo(q[0], q[1]); });
  sctx.closePath();
  sctx.stroke();
  sctx.setLineDash([]);
  if (curvePts) {
    sctx.strokeStyle = "#e5484d";
    sctx.lineWidth = 2.4;
    sctx.beginPath();
    curvePts.forEach(([x, y], i) => { const q = tf([x, y]); i ? sctx.lineTo(q[0], q[1]) : sctx.moveTo(q[0], q[1]); });
    sctx.stroke();
  }
}

let lossHist = [];
function drawSpark() {
  const W = sparkCv.width, H = sparkCv.height;
  kctx.clearRect(0, 0, W, H);
  if (lossHist.length < 2) return;
  const maxV = Math.max(...lossHist), minV = Math.min(...lossHist);
  kctx.strokeStyle = "#5aa2ff";
  kctx.lineWidth = 1.6;
  kctx.beginPath();
  lossHist.forEach((v, i) => {
    const x = (i / (lossHist.length - 1)) * (W - 10) + 5;
    const y = H - 8 - ((v - minV) / (maxV - minV || 1)) * (H - 16);
    i ? kctx.lineTo(x, y) : kctx.moveTo(x, y);
  });
  kctx.stroke();
}

function startWorker(points) {
  if (worker) worker.terminate();
  lossHist = [];
  genStart = null;
  lastGenTime = null;
  totalGens = SPEED_CFG[speed].generations;
  if (animId) cancelAnimationFrame(animId);
  sctx.clearRect(0, 0, stageCv.width, stageCv.height);
  $("stageTitle").textContent = "2 · Watch the evolution";
  worker = new Worker("engine.worker.js");
  worker.onmessage = (e) => {
    const m = e.data;
    if (m.type === "gen") {
      const now = performance.now();
      if (genStart === null) genStart = now;
      if (lastGenTime !== null && m.gen > 0) {
        const rate = (now - lastGenTime) / 6;
        $("time").textContent = "eta ~" + Math.max(0, ((totalGens - m.gen) * rate) / 1000).toFixed(0) + "s";
      }
      lastGenTime = now;
      $("gen").textContent = "gen " + m.gen;
      $("bar").style.width = Math.min(100, (m.gen / totalGens) * 100).toFixed(1) + "%";
      $("loss").textContent = m.loss.toFixed(4);
      $("match").textContent = Math.max(0, (1 - m.loss) * 100).toFixed(1) + "%";
      lossHist.push(m.loss);
      drawSpark();
      drawEvolution(lastPoints, m.curve);
      narrate(`<strong>Generation ${m.gen}.</strong> ${SPEED_CFG[speed].popsize} random machines were mutated and tested in your browser.
        The red path is the best machine's pen so far &mdash; watch it hug your sketch
        (dashed). Machines that trace it better survive; the rest are discarded.`);
    } else if (m.type === "done") {
      frames = m;
      $("bar").style.width = "100%";
      $("time").textContent = ((performance.now() - genStart) / 1000).toFixed(1) + "s";
      $("match").textContent = Math.max(0, (1 - m.loss) * 100).toFixed(1) + "%";
      const L = m.links, tr = m.transmission;
      $("linkInfo").textContent =
        `machine: crank ${L.a.toFixed(2)} · coupler ${L.b.toFixed(2)} · rocker ${L.c.toFixed(2)} · ground ${L.d.toFixed(2)} · pen (${L.px.toFixed(2)}, ${L.py.toFixed(2)})`
        + ` · transmission angle min ${tr.min_deg.toFixed(0)}°`;
      $("doneRow").hidden = false;
      setRunning(false);
      startAnimation(m);
      narrate(`<strong>Evolution finished.</strong> Your machine was <em>invented, not programmed</em>:
        four bars and one pen point, found by mutating and selecting machines entirely in your browser.
        The crank (blue) spins; the pen (red) draws your curve.`);
    } else if (m.type === "error") {
      narrate("<strong>Something went wrong:</strong> " + m.message);
      setRunning(false);
    }
  };
  worker.postMessage({ points, cfg: { ...SPEED_CFG[speed], seed: 42 } });
}

$("evolve").onclick = () => {
  if (running) return;
  if (sketch.length < 10) { alert("Draw a closed curve first (or click a preset)."); return; }
  const xs = sketch.map((p) => p[0]), ys = sketch.map((p) => p[1]);
  if (Math.hypot(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) < 40) {
    alert("That sketch is too small to be a curve — draw something bigger.");
    return;
  }
  lastPoints = sketch.map((p) => p);
  startWorker(lastPoints);
};

// ---------- GIF export (client-side, gif.js) ----------
$("gifBtn").onclick = () => {
  if (!frames) return;
  narrate("<strong>Encoding GIF…</strong> rendering the machine frame by frame.");
  const size = 450;
  const off = document.createElement("canvas");
  off.width = size; off.height = size;
  const octx = off.getContext("2d");
  const { O2, O4, A, B, P } = frames.frames;
  const tm = frames.target_machine;
  const all = O2.concat(O4, A, B, P, tm);
  const tf = fitTransform(all, size, size, 46);
  const Nn = P.length;
  const gif = new GIF({ workers: 2, quality: 8, width: size, height: size, workerScript: "gif.worker.js" });

  function renderFrame(i) {
    octx.fillStyle = "#0b0d10";
    octx.fillRect(0, 0, size, size);
    octx.strokeStyle = "rgba(139,150,165,0.5)";
    octx.setLineDash([5, 5]);
    octx.lineWidth = 1.4;
    octx.beginPath();
    tm.forEach(([x, y], j) => { const q = tf([x, y]); j ? octx.lineTo(q[0], q[1]) : octx.moveTo(q[0], q[1]); });
    octx.closePath();
    octx.stroke();
    octx.setLineDash([]);
    octx.strokeStyle = "rgba(229,72,77,0.25)";
    octx.lineWidth = 1.4;
    octx.beginPath();
    P.forEach(([x, y], j) => { const q = tf([x, y]); j ? octx.lineTo(q[0], q[1]) : octx.moveTo(q[0], q[1]); });
    octx.closePath();
    octx.stroke();
    const g2 = tf(O2[i]), g4 = tf(O4[i]), a2 = tf(A[i]), b2 = tf(B[i]), p2 = tf(P[i]);
    octx.lineWidth = 5; octx.strokeStyle = "#3d4653";
    octx.beginPath(); octx.moveTo(g2[0], g2[1]); octx.lineTo(g4[0], g4[1]); octx.stroke();
    octx.lineWidth = 4.5; octx.strokeStyle = "#5aa2ff";
    octx.beginPath(); octx.moveTo(g2[0], g2[1]); octx.lineTo(a2[0], a2[1]); octx.stroke();
    octx.lineWidth = 3.5; octx.strokeStyle = "#e8edf2";
    octx.beginPath(); octx.moveTo(a2[0], a2[1]); octx.lineTo(b2[0], b2[1]); octx.stroke();
    octx.strokeStyle = "#2dd4a7";
    octx.beginPath(); octx.moveTo(g4[0], g4[1]); octx.lineTo(b2[0], b2[1]); octx.stroke();
    for (const q of [g2, g4]) { octx.fillStyle = "#8b96a5"; octx.beginPath(); octx.arc(q[0], q[1], 4.5, 0, 7); octx.fill(); }
    for (const q of [a2, b2]) { octx.fillStyle = "#e8edf2"; octx.beginPath(); octx.arc(q[0], q[1], 3.6, 0, 7); octx.fill(); }
    octx.fillStyle = "#e5484d";
    octx.beginPath(); octx.arc(p2[0], p2[1], 5.5, 0, 7); octx.fill();
    octx.font = "600 12px 'Segoe UI', sans-serif";
    octx.fillStyle = "#5aa2ff"; octx.fillText("crank", (g2[0] + a2[0]) / 2 - 18, (g2[1] + a2[1]) / 2 - 6);
    octx.fillStyle = "#e5484d"; octx.fillText("pen", p2[0] + 9, p2[1] - 8);
    // trace up to i
    octx.strokeStyle = "#e5484d";
    octx.lineWidth = 2.6;
    octx.beginPath();
    for (let j = 0; j <= i; j++) { const q = tf(P[j]); j ? octx.lineTo(q[0], q[1]) : octx.moveTo(q[0], q[1]); }
    octx.stroke();
    octx.fillStyle = "#e8edf2";
    octx.font = "700 13px 'Segoe UI', sans-serif";
    octx.fillText("invented by evolution · kinema", 12, size - 14);
  }

  // sample every 2nd frame for size, 2 loops
  for (let loop = 0; loop < 2; loop++) {
    for (let i = 0; i < Nn; i += 2) {
      renderFrame(i);
      gif.addFrame(off, { copy: true, delay: 55 });
    }
  }
  gif.on("finished", (blob) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "kinema-machine.gif";
    a.click();
    narrate("<strong>GIF exported.</strong> Your machine is downloaded — share it.");
  });
  gif.render();
};

// ---------- machine animation ----------
function startAnimation(m) {
  $("stageTitle").textContent = "3 · Your machine, tracing the curve";
  $("legend").hidden = false;
  const { O2, O4, A, B, P } = m.frames;
  const tm = m.target_machine;
  const all = O2.concat(O4, A, B, P, tm);
  const tf = fitTransform(all, stageCv.width, stageCv.height, 55);
  const Nn = P.length;
  let t0 = null;
  function label(text, x, y, color) {
    sctx.font = "600 11px 'Segoe UI', sans-serif";
    sctx.fillStyle = color;
    sctx.fillText(text, x, y);
  }
  function frame(ts) {
    if (!t0) t0 = ts;
    const i = Math.floor(((ts - t0) / 55) % Nn);
    sctx.clearRect(0, 0, stageCv.width, stageCv.height);
    sctx.strokeStyle = "rgba(139,150,165,0.5)";
    sctx.setLineDash([5, 5]);
    sctx.lineWidth = 1.4;
    sctx.beginPath();
    tm.forEach(([x, y], j) => { const q = tf([x, y]); j ? sctx.lineTo(q[0], q[1]) : sctx.moveTo(q[0], q[1]); });
    sctx.closePath();
    sctx.stroke();
    sctx.setLineDash([]);
    sctx.strokeStyle = "rgba(229,72,77,0.28)";
    sctx.lineWidth = 1.6;
    sctx.beginPath();
    P.forEach(([x, y], j) => { const q = tf([x, y]); j ? sctx.lineTo(q[0], q[1]) : sctx.moveTo(q[0], q[1]); });
    sctx.closePath();
    sctx.stroke();
    const k = Math.max(2, i + 1);
    sctx.strokeStyle = "#e5484d";
    sctx.lineWidth = 2.8;
    sctx.beginPath();
    for (let j = 0; j < k; j++) { const q = tf(P[j]); j ? sctx.lineTo(q[0], q[1]) : sctx.moveTo(q[0], q[1]); }
    sctx.stroke();
    const g2 = tf(O2[i]), g4 = tf(O4[i]), a2 = tf(A[i]), b2 = tf(B[i]), p2 = tf(P[i]);
    sctx.strokeStyle = "#3d4653";
    sctx.lineWidth = 5;
    sctx.beginPath(); sctx.moveTo(g2[0], g2[1]); sctx.lineTo(g4[0], g4[1]); sctx.stroke();
    sctx.strokeStyle = "#5aa2ff";
    sctx.lineWidth = 4.5;
    sctx.beginPath(); sctx.moveTo(g2[0], g2[1]); sctx.lineTo(a2[0], a2[1]); sctx.stroke();
    sctx.strokeStyle = "#e8edf2";
    sctx.lineWidth = 3.5;
    sctx.beginPath(); sctx.moveTo(a2[0], a2[1]); sctx.lineTo(b2[0], b2[1]); sctx.stroke();
    sctx.strokeStyle = "#2dd4a7";
    sctx.beginPath(); sctx.moveTo(g4[0], g4[1]); sctx.lineTo(b2[0], b2[1]); sctx.stroke();
    for (const q of [g2, g4]) { sctx.fillStyle = "#8b96a5"; sctx.beginPath(); sctx.arc(q[0], q[1], 4.5, 0, 7); sctx.fill(); }
    for (const q of [a2, b2]) { sctx.fillStyle = "#e8edf2"; sctx.beginPath(); sctx.arc(q[0], q[1], 3.6, 0, 7); sctx.fill(); }
    sctx.fillStyle = "#e5484d";
    sctx.beginPath(); sctx.arc(p2[0], p2[1], 5.5, 0, 7); sctx.fill();
    label("crank", (g2[0] + a2[0]) / 2 - 18, (g2[1] + a2[1]) / 2 - 6, "#5aa2ff");
    label("coupler", (a2[0] + b2[0]) / 2 + 8, (a2[1] + b2[1]) / 2 - 6, "#e8edf2");
    label("rocker", (g4[0] + b2[0]) / 2 + 8, (g4[1] + b2[1]) / 2 - 6, "#2dd4a7");
    label("pen", p2[0] + 9, p2[1] - 8, "#e5484d");
    animId = requestAnimationFrame(frame);
  }
  animId = requestAnimationFrame(frame);
}
