const fs = require("fs");
let code = fs.readFileSync("docs/engine.worker.js", "utf8");
// expose alignTargetToMachine for direct testing
code += "\nglobalThis.__align = alignTargetToMachine;";
global.self = { postMessage: () => {} };
(0, eval)(code);
const d = JSON.parse(fs.readFileSync("prototype/align_debug.json", "utf8"));
fs.writeFileSync("prototype/tm_js_fixed.json", JSON.stringify(globalThis.__align(d.curve, d.points)));
console.log("js align done");
