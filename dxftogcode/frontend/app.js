const fileInput = document.getElementById("dxfFile");
const fileStatus = document.getElementById("fileStatus");
const settingsForm = document.getElementById("settingsForm");
const convertBtn = document.getElementById("convertBtn");
const downloadBtn = document.getElementById("downloadBtn");
const convertStatus = document.getElementById("convertStatus");
const gcodeOutput = document.getElementById("gcodeOutput");
const previewStatus = document.getElementById("previewStatus");
const canvas = document.getElementById("preview");
const ctx = canvas.getContext("2d");

let lastGcode = "";
let lastFilename = "output.nc";

fileInput.addEventListener("change", () => {
  const f = fileInput.files[0];
  fileStatus.textContent = f ? `Selected: ${f.name} (${(f.size / 1024).toFixed(1)} KB)` : "";
  fileStatus.classList.remove("error");
});

convertBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) {
    setStatus(fileStatus, "Pick a .dxf file first.", true);
    return;
  }

  const formData = new FormData(settingsForm);
  formData.set("dxf", file);
  formData.set(
    "normalize_origin",
    settingsForm.elements["normalize_origin"].checked ? "true" : "false"
  );

  convertBtn.disabled = true;
  setStatus(convertStatus, "Converting...", false);

  try {
    const res = await fetch("/convert", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      setStatus(convertStatus, data.error || "Conversion failed.", true);
      return;
    }
    lastGcode = data.gcode;
    lastFilename = data.filename;
    gcodeOutput.value = lastGcode;
    downloadBtn.disabled = false;
    setStatus(convertStatus, `Done. ${lastGcode.split("\n").length} lines generated.`, false);
    drawPreview(lastGcode);
  } catch (err) {
    setStatus(convertStatus, `Request failed: ${err}`, true);
  } finally {
    convertBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", () => {
  const blob = new Blob([lastGcode], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = lastFilename;
  a.click();
  URL.revokeObjectURL(url);
});

function setStatus(el, msg, isError) {
  el.textContent = msg;
  el.classList.toggle("error", !!isError);
}

function drawPreview(gcode) {
  const moves = [];
  let x = 0, y = 0;
  let torchOn = false;

  for (const rawLine of gcode.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("(")) continue;
    if (line === "M3") { torchOn = true; continue; }
    if (line === "M5") { torchOn = false; continue; }

    const isRapid = line.startsWith("G0");
    const isFeed = line.startsWith("G1");
    if (!isRapid && !isFeed) continue;

    const xm = line.match(/X(-?[0-9.]+)/);
    const ym = line.match(/Y(-?[0-9.]+)/);
    const nx = xm ? parseFloat(xm[1]) : x;
    const ny = ym ? parseFloat(ym[1]) : y;

    if (xm || ym) {
      moves.push({ x1: x, y1: y, x2: nx, y2: ny, cutting: isFeed && torchOn });
    }
    x = nx; y = ny;
  }

  if (moves.length === 0) {
    previewStatus.textContent = "Nothing to preview.";
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }

  const xs = moves.flatMap((m) => [m.x1, m.x2]);
  const ys = moves.flatMap((m) => [m.y1, m.y2]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = 20;
  const w = canvas.width - pad * 2;
  const h = canvas.height - pad * 2;
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const scale = Math.min(w / spanX, h / spanY);

  const toPx = (px, py) => [
    pad + (px - minX) * scale,
    canvas.height - pad - (py - minY) * scale,
  ];

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const m of moves) {
    const [sx, sy] = toPx(m.x1, m.y1);
    const [ex, ey] = toPx(m.x2, m.y2);
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(ex, ey);
    if (m.cutting) {
      ctx.strokeStyle = "#4f9dff";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([]);
    } else {
      ctx.strokeStyle = "#6a7078";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
    }
    ctx.stroke();
  }
  ctx.setLineDash([]);
  previewStatus.textContent = `${moves.filter((m) => m.cutting).length} cut moves, ${moves.filter((m) => !m.cutting).length} rapid moves.`;
}
