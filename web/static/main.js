/* Kinema frontend */
"use strict";

const $ = (id) => document.getElementById(id);
const drawCv = $("draw"), stageCv = $("stage"), sparkCv = $("spark");
const dctx = drawCv.getContext("2d"), sctx = stageCv.getContext("2d"), kctx = sparkCv.getContext("2d");

const PRESETS = {
  heart: (t) => [16 * Math.sin(t) ** 3, -(13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t)) / 16],
  star: null, // built below
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
let sketch = [];          // array of [x, y] in canvas coords
let drawing = false;
let last = performance.now();

function clearDraw() {
  sketch = [];
  dctx.clearRect(0, 0, drawCv.width, drawCv.height);
}

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
  presetName = null;   // hand-drawn: fresh synthesis, no cache
  sketch = [];
  const p = pos(e);
  sketch.push(p);
  drawSketchLine(sketch, false);
});
drawCv.addEventListener("pointermove", (e) => {
  if (!drawing) return;
  const p = pos(e);
  const q = sketch[sketch.length - 1];
  if (Math.hypot(p[0] - q[0], p[1] - q[1]) > 2) {
    sketch.push(p);
    if (performance.now() - last > 16) { drawSketchLine(sketch, false); last = performance.now(); }
  }
});
window.addEventListener("pointerup", () => {
  if (drawing) { drawing = false; drawSketchLine(sketch); }
});
function pos(e) {
  const r = drawCv.getBoundingClientRect();
  return [(e.clientX - r.left) * (drawCv.width / r.width),
          (e.clientY - r.top) * (drawCv.height / r.height)];
}

// ---------- presets ----------
const chipsEl = $("presets");
let presetName = null;   // set when the current sketch came from a preset (enables cache hit)
for (const name of Object.keys(PRESETS)) {
  const b = document.createElement("button");
  b.className = "chip";
  b.textContent = name;
  b.onclick = () => {
    if (running) return;
    const t = [];
    const n = 220;
    for (let i = 0; i < n; i++) t.push((i / n) * 2 * Math.PI);
    const f = PRESETS[name];
    const raw = name === "star" ? f() : t.map((tt) => f(tt));
    const xs = raw.map((p) => p[0]), ys = raw.map((p) => p[1]);
    const minx = Math.min(...xs), maxx = Math.max(...xs);
    const miny = Math.min(...ys), maxy = Math.max(...ys);
    const s = Math.min((drawCv.width - 80) / (maxx - minx), (drawCv.height - 80) / (maxy - miny));
    const cx = (minx + maxx) / 2, cy = (miny + maxy) / 2;
    sketch = raw.map(([x, y]) => [drawCv.width / 2 + (x - cx) * s, drawCv.height / 2 + (y - cy) * s]);
    presetName = name;
    drawSketchLine(sketch);
  };
  chipsEl.appendChild(b);
}
$("clear").onclick = clearDraw;

// ---------- websocket + evolution ----------
let ws = null, running = false, frames = null, animId = null, lastPoints = null;
let genStart = null, lastGenTime = null;

function setRunning(v) {
  running = v;
  $("evolve").disabled = v;
  $("evolve").textContent = v ? "Evolving…" : "Invent my machine";
  $("doneRow").hidden = true;
  $("legend").hidden = true;
}

function narrate(html) { $("narration").innerHTML = html; }

function fitTransform(pts, W, H, pad = 40) {
  let minx = 1e9, miny = 1e9, maxx = -1e9, maxy = -1e9;
  for (const [x, y] of pts) { minx = Math.min(minx, x); maxx = Math.max(maxx, x); miny = Math.min(miny, y); maxy = Math.max(maxy, y); }
  const s = Math.min((W - pad * 2) / (maxx - minx || 1), (H - pad * 2) / (maxy - miny || 1));
  const cx = (minx + maxx) / 2, cy = (miny + maxy) / 2;
  return (p) => [W / 2 + (p[0] - cx) * s, H / 2 + (p[1] - cy) * s, s];
}

function drawEvolution(targetPts, curvePts, gen, loss) {
  const W = stageCv.width, H = stageCv.height;
  sctx.clearRect(0, 0, W, H);
  if (!targetPts) return;
  const all = curvePts ? targetPts.concat(curvePts) : targetPts;
  const tf = fitTransform(all, W, H);
  // target (ghost)
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

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/synthesize`);
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "gen") {
      const now = performance.now();
      if (genStart === null) genStart = now;
      if (lastGenTime !== null && m.gen > 0) {
        const rate = (now - lastGenTime) / 6;      // ms per generation
        const remaining = (320 - m.gen) * rate;
        $("time").textContent = "eta ~" + Math.max(0, remaining / 1000).toFixed(0) + "s";
      }
      lastGenTime = now;
      $("gen").textContent = "gen " + m.gen;
      $("loss").textContent = m.loss.toFixed(4);
      $("match").textContent = Math.max(0, (1 - m.loss) * 100).toFixed(1) + "%";
      lossHist.push(m.loss);
      drawSpark();
      drawEvolution(lastPoints ? m.curve : m.curve, m.curve, m.gen, m.loss);
      narrate(m.replay
        ? `<strong>Replaying a cached result</strong> (this preset was already evolved once) &mdash; the machine was invented in a previous run; here it is again.`
        : `<strong>Generation ${m.gen}.</strong> 200 random machines were mutated and tested.
        The red path is the best machine's pen so far &mdash; watch it hug your sketch
        (dashed). Machines that trace it better survive; the rest are discarded.`);
    } else if (m.type === "done") {
      frames = m;
      $("time").textContent = m.elapsed.toFixed(1) + "s";
      $("match").textContent = Math.max(0, (1 - m.loss) * 100).toFixed(1) + "%";
      const L = m.links;
      const tr = m.transmission;
      $("linkInfo").textContent =
        `machine: crank ${L.a.toFixed(2)} · coupler ${L.b.toFixed(2)} · rocker ${L.c.toFixed(2)} · ground ${L.d.toFixed(2)} · pen (${L.px.toFixed(2)}, ${L.py.toFixed(2)})`
        + (tr ? ` · transmission angle min ${tr.min_deg.toFixed(0)}°` : "");
      $("doneRow").hidden = false;
      setRunning(false);
      startAnimation(m);
      narrate(`<strong>Evolution finished in ${m.elapsed.toFixed(1)}s.</strong> Your machine was
        <em>invented, not programmed</em>: four bars and one pen point, found by mutating and
        selecting machines. The crank (blue) spins; the pen (red) draws your curve. Full path = faint red; your sketch = dashed.`);
    } else if (m.type === "error") {
      console.error(m.message);
      setRunning(false);
    }
  };
  ws.onopen = () => { $("footNote").textContent = ""; };
}
connect();

$("evolve").onclick = () => {
  if (running) return;
  if (sketch.length < 10) { alert("Draw a closed curve first (or click a preset)."); return; }
  // degenerate-sketch guard: reject tiny/invisible shapes
  const xs = sketch.map((p) => p[0]), ys = sketch.map((p) => p[1]);
  const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
  if (Math.hypot(w, h) < 40) { alert("That sketch is too small to be a curve — draw something bigger."); return; }
  lastPoints = sketch.map((p) => p);
  startSynthesis(lastPoints);
};

function startSynthesis(points) {
  if (ws.readyState !== 1) { connect(); setTimeout(() => startSynthesis(points), 300); return; }
  lossHist = [];
  genStart = null; lastGenTime = null;
  frames = null;
  if (animId) cancelAnimationFrame(animId);
  sctx.clearRect(0, 0, stageCv.width, stageCv.height);
  $("stageTitle").textContent = "2 · Watch the evolution";
  setRunning(true);
  narrate("<strong>Seeding generation 0…</strong> 200 machines with random bar lengths are being born. " +
          "Almost none of them can even rotate — evolution will fix that first.");
  // draw the target as ghost immediately (unit-boxed)
  const tf0 = fitTransform(points, stageCv.width, stageCv.height);
  const ghost = points.map((p) => { const q = tf0(p); return [(p[0] - 260) / 240, (p[1] - 260) / 240]; });
  drawEvolution(ghost, null, 0, null);
  const seed = presetName ? 42 : Math.floor(Math.random() * 1e9);
  ws.send(JSON.stringify({ type: "synthesize", points: points, generations: 320, popsize: 200, restarts: 2, seed: seed }));
}

$("gifBtn").onclick = () => {
  if (!frames) return;
  fetch("/gif", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params: frames.params, points: lastPoints }),
  }).then((r) => r.blob()).then((b) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(b);
    a.download = "kinema-machine.gif";
    a.click();
  });
};

// ---------- machine animation ----------
function startAnimation(m) {
  $("stageTitle").textContent = "3 · Your machine, tracing the curve";
  $("legend").hidden = false;
  const { O2, O4, A, B, P } = m.frames;
  const tm = m.target_machine;
  const all = O2.concat(O4, A, B, P, tm);
  const tf = fitTransform(all, stageCv.width, stageCv.height, 55);
  const N = P.length;
  let t0 = null;

  function label(text, x, y, color) {
    sctx.font = "600 11px 'Segoe UI', sans-serif";
    sctx.fillStyle = color;
    sctx.fillText(text, x, y);
  }

  function frame(ts) {
    if (!t0) t0 = ts;
    const i = Math.floor(((ts - t0) / 55) % N);
    sctx.clearRect(0, 0, stageCv.width, stageCv.height);
    // ghost target
    sctx.strokeStyle = "rgba(139,150,165,0.5)";
    sctx.setLineDash([5, 5]);
    sctx.lineWidth = 1.4;
    sctx.beginPath();
    tm.forEach(([x, y], j) => { const q = tf([x, y]); j ? sctx.lineTo(q[0], q[1]) : sctx.moveTo(q[0], q[1]); });
    sctx.closePath();
    sctx.stroke();
    sctx.setLineDash([]);
    // full pen path (faint) + growing bright trace
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
    // links
    const g2 = tf(O2[i]), g4 = tf(O4[i]), a2 = tf(A[i]), b2 = tf(B[i]), p2 = tf(P[i]);
    sctx.strokeStyle = "#3d4653";
    sctx.lineWidth = 5;
    sctx.beginPath(); sctx.moveTo(g2[0], g2[1]); sctx.lineTo(g4[0], g4[1]); sctx.stroke();  // ground
    sctx.strokeStyle = "#5aa2ff";
    sctx.lineWidth = 4.5;
    sctx.beginPath(); sctx.moveTo(g2[0], g2[1]); sctx.lineTo(a2[0], a2[1]); sctx.stroke();  // crank
    sctx.strokeStyle = "#e8edf2";
    sctx.lineWidth = 3.5;
    sctx.beginPath(); sctx.moveTo(a2[0], a2[1]); sctx.lineTo(b2[0], b2[1]); sctx.stroke();  // coupler
    sctx.strokeStyle = "#2dd4a7";
    sctx.lineWidth = 3.5;
    sctx.beginPath(); sctx.moveTo(g4[0], g4[1]); sctx.lineTo(b2[0], b2[1]); sctx.stroke();  // rocker
    // joints
    for (const q of [g2, g4]) { sctx.fillStyle = "#8b96a5"; sctx.beginPath(); sctx.arc(q[0], q[1], 4.5, 0, 7); sctx.fill(); }
    for (const q of [a2, b2]) { sctx.fillStyle = "#e8edf2"; sctx.beginPath(); sctx.arc(q[0], q[1], 3.6, 0, 7); sctx.fill(); }
    sctx.fillStyle = "#e5484d";
    sctx.beginPath(); sctx.arc(p2[0], p2[1], 5.5, 0, 7); sctx.fill();
    // labels
    label("crank", (g2[0] + a2[0]) / 2 - 18, (g2[1] + a2[1]) / 2 - 6, "#5aa2ff");
    label("coupler", (a2[0] + b2[0]) / 2 + 8, (a2[1] + b2[1]) / 2 - 6, "#e8edf2");
    label("rocker", (g4[0] + b2[0]) / 2 + 8, (g4[1] + b2[1]) / 2 - 6, "#2dd4a7");
    label("pen", p2[0] + 9, p2[1] - 8, "#e5484d");
    animId = requestAnimationFrame(frame);
  }
  animId = requestAnimationFrame(frame);
}
