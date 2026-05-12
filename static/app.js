const $ = (id) => document.getElementById(id);

const video = $("video");
const overlay = $("overlay");
const ctx = overlay.getContext("2d");

let activePanel = "offline";
let mode = "pivot";
let pivots = [];
let boxes = [];
let dragStart = null;
let draftBox = null;
let frameSize = null;
let statusTimer = null;
let offlineTimer = null;

const colors = ["#ffd447", "#ff9f43", "#4cd964", "#5ac8fa", "#ff5ac8", "#af7aff", "#d4ff5a", "#52ffe0"];

function setStatus(text) {
  $("statusText").textContent = text;
}

async function api(path, body = null) {
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || "操作失败");
  return data;
}

function count() {
  return Number($("count").value || 1);
}

function setPanel(next) {
  activePanel = next;
  $("offlinePanel").hidden = next !== "offline";
  $("livePanel").hidden = next !== "live";
  $("offlineTab").classList.toggle("active", next === "offline");
  $("liveTab").classList.toggle("active", next === "live");
  $("recBadge").textContent = next === "offline" ? "OFFLINE" : "READY";
  setStatus(next === "offline" ? "上传视频后在首帧上标定" : "打开摄像头后标定和录像");
}

function setMode(next) {
  mode = next;
  $("pivotMode").classList.toggle("active", mode === "pivot");
  $("boxMode").classList.toggle("active", mode === "box");
  drawOverlay();
}

function resetCalibration() {
  pivots = [];
  boxes = [];
  dragStart = null;
  draftBox = null;
  setMode("pivot");
  drawOverlay();
}

function fitCanvas() {
  if (!video.complete || !video.naturalWidth) return;
  const viewer = $("viewer").getBoundingClientRect();
  const scale = Math.min(viewer.width / video.naturalWidth, viewer.height / video.naturalHeight);
  const width = Math.round(video.naturalWidth * scale);
  const height = Math.round(video.naturalHeight * scale);
  overlay.width = width;
  overlay.height = height;
  video.style.width = `${width}px`;
  video.style.height = `${height}px`;
  overlay.style.width = `${width}px`;
  overlay.style.height = `${height}px`;
  drawOverlay();
}

function toFramePoint(evt) {
  const rect = overlay.getBoundingClientRect();
  const sx = frameSize ? frameSize.width / rect.width : video.naturalWidth / rect.width;
  const sy = frameSize ? frameSize.height / rect.height : video.naturalHeight / rect.height;
  return {
    x: (evt.clientX - rect.left) * sx,
    y: (evt.clientY - rect.top) * sy,
  };
}

function toCanvasPoint(point) {
  const sx = overlay.width / (frameSize?.width || video.naturalWidth || overlay.width);
  const sy = overlay.height / (frameSize?.height || video.naturalHeight || overlay.height);
  return { x: point.x * sx, y: point.y * sy };
}

function drawOverlay() {
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  ctx.lineWidth = 2;
  ctx.font = "14px Segoe UI";

  pivots.forEach((p, i) => {
    const c = toCanvasPoint(p);
    ctx.fillStyle = colors[i % colors.length];
    ctx.beginPath();
    ctx.arc(c.x, c.y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillText(`${i + 1}`, c.x + 8, c.y - 8);
  });

  boxes.forEach((b, i) => drawBox(b, colors[i % colors.length], `P${i + 1}`));
  if (draftBox) drawBox(draftBox, "#ffffff", "");
}

function drawBox(box, color, label) {
  const p = toCanvasPoint({ x: box.x, y: box.y });
  const q = toCanvasPoint({ x: box.x + box.w, y: box.y + box.h });
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.strokeRect(p.x, p.y, q.x - p.x, q.y - p.y);
  if (label) ctx.fillText(label, p.x + 5, p.y - 6);
}

function normalizeBox(a, b) {
  const x = Math.min(a.x, b.x);
  const y = Math.min(a.y, b.y);
  return { x, y, w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) };
}

function calibrationPayload() {
  return { pendulums: pivots.map((pivot, i) => ({ pivot, box: boxes[i] })) };
}

overlay.addEventListener("click", (evt) => {
  if (mode !== "pivot" || !frameSize || pivots.length >= count()) return;
  pivots.push(toFramePoint(evt));
  if (pivots.length >= count()) setMode("box");
  drawOverlay();
});

overlay.addEventListener("mousedown", (evt) => {
  if (mode !== "box" || !frameSize || boxes.length >= count()) return;
  dragStart = toFramePoint(evt);
  draftBox = { x: dragStart.x, y: dragStart.y, w: 0, h: 0 };
});

overlay.addEventListener("mousemove", (evt) => {
  if (!dragStart) return;
  draftBox = normalizeBox(dragStart, toFramePoint(evt));
  drawOverlay();
});

overlay.addEventListener("mouseup", (evt) => {
  if (!dragStart) return;
  const box = normalizeBox(dragStart, toFramePoint(evt));
  dragStart = null;
  draftBox = null;
  if (box.w > 4 && box.h > 4 && boxes.length < count()) boxes.push(box);
  drawOverlay();
});

$("offlineTab").onclick = () => setPanel("offline");
$("liveTab").onclick = () => setPanel("live");
$("pivotMode").onclick = () => setMode("pivot");
$("boxMode").onclick = () => setMode("box");
$("undo").onclick = () => {
  if (mode === "box" && boxes.length) boxes.pop();
  else if (pivots.length) pivots.pop();
  drawOverlay();
};
$("clear").onclick = resetCalibration;

$("uploadVideo").onclick = async () => {
  const file = $("videoFile").files[0];
  if (!file) {
    setStatus("先选择一个视频文件");
    return;
  }
  const form = new FormData();
  form.append("video", file);
  setStatus("正在载入视频首帧");
  const res = await fetch("/api/offline/upload", { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    setStatus(data.error || "视频载入失败");
    return;
  }
  frameSize = data.frameSize;
  video.src = `/api/offline/frame?t=${Date.now()}`;
  video.style.display = "block";
  $("emptyState").style.display = "none";
  $("videoInfo").innerHTML = `<div>${data.frameSize.width}×${data.frameSize.height} · ${data.sourceFps} FPS · ${data.totalFrames} 帧</div>`;
  $("offlineFps").placeholder = `默认 ${Math.round(data.sourceFps)}`;
  resetCalibration();
  setStatus("视频已载入，开始标定");
  startOfflinePolling();
};

$("saveCalibration").onclick = async () => {
  if (pivots.length !== count() || boxes.length !== count()) {
    setStatus("悬点和黄色点框数量需要与摆的数量一致");
    return;
  }
  try {
    const path = activePanel === "offline" ? "/api/offline/calibration" : "/api/calibration";
    await api(path, calibrationPayload());
    setStatus(activePanel === "offline" ? "标定已保存，可以开始离线分析" : "标定已应用，可以开始录像");
  } catch (err) {
    setStatus(err.message);
  }
};

$("startOffline").onclick = async () => {
  try {
    await api("/api/offline/analyze", {
      start: $("offlineStart").value,
      end: $("offlineEnd").value,
      fps: $("offlineFps").value,
      previewEvery: $("previewEvery").value,
    });
    $("offlineResult").innerHTML = "";
    $("progressBar").style.width = "0%";
    setStatus("离线分析开始");
    startOfflinePolling();
  } catch (err) {
    setStatus(err.message);
  }
};

function startOfflinePolling() {
  if (offlineTimer) return;
  offlineTimer = setInterval(async () => {
    try {
      const status = await api("/api/offline/status");
      if (status.frameSize) frameSize = status.frameSize;
      $("progressBar").style.width = `${Math.round((status.progress || 0) * 100)}%`;
      if (activePanel === "offline") setStatus(status.error || status.message || "离线模式");
      if (status.result) showOfflineResult(status.result);
    } catch {
      // Ignore brief polling interruptions.
    }
  }, 600);
}

function showOfflineResult(result) {
  $("offlineResult").innerHTML = `
    <div>已处理帧数：${result.frames}</div>
    <a href="${result.annotatedVideo}" target="_blank">标注视频</a>
    <a href="${result.wideCsv}" target="_blank">宽表 CSV</a>
    <a href="${result.longCsv}" target="_blank">长表 CSV</a>
    ${result.plot ? `<a href="${result.plot}" target="_blank">角度曲线</a>` : ""}
    <a href="${result.resultJson}" target="_blank">分析摘要</a>
  `;
}

$("startCamera").onclick = async () => {
  try {
    await api("/api/camera/start", {
      camera: Number($("camera").value),
      width: Number($("width").value),
      height: Number($("height").value),
      fps: Number($("fps").value),
      previewQuality: Number($("previewQuality").value),
    });
    frameSize = null;
    video.src = `/api/video?t=${Date.now()}`;
    video.style.display = "block";
    $("emptyState").style.display = "none";
    resetCalibration();
    setStatus("摄像头已打开，可以标定");
    startLivePolling();
  } catch (err) {
    setStatus(err.message);
  }
};

$("stopCamera").onclick = async () => {
  try {
    await api("/api/camera/stop", {});
    video.removeAttribute("src");
    video.style.display = "none";
    $("emptyState").style.display = "block";
    setStatus("摄像头已关闭");
  } catch (err) {
    setStatus(err.message);
  }
};

$("scanCamera").onclick = async () => {
  try {
    setStatus("正在检测摄像头");
    const data = await api("/api/cameras");
    const usable = data.devices.filter((item) => item.opened && item.frame);
    if (!usable.length) {
      $("deviceList").innerHTML = "<div>没有检测到可用摄像头</div>";
      setStatus("没有检测到可用摄像头");
      return;
    }
    $("deviceList").innerHTML = usable
      .map(
        (item) =>
          `<button type="button" data-camera="${item.index}" data-width="${item.width}" data-height="${item.height}">摄像头 ${item.index} · ${item.width}×${item.height}${item.active ? " · 使用中" : ""}</button>`
      )
      .join("");
    $("deviceList").querySelectorAll("button").forEach((button) => {
      button.onclick = () => {
        $("camera").value = button.dataset.camera;
        if (button.dataset.width !== "null") $("width").value = button.dataset.width;
        if (button.dataset.height !== "null") $("height").value = button.dataset.height;
        setStatus(`已选择摄像头 ${button.dataset.camera}`);
      };
    });
    setStatus(`检测到 ${usable.length} 个可用摄像头`);
  } catch (err) {
    setStatus(err.message);
  }
};

$("startRecord").onclick = async () => {
  try {
    const data = await api("/api/record/start", {});
    $("result").innerHTML = `<div>保存目录：${data.runDir}</div>`;
    setStatus("正在录像");
  } catch (err) {
    setStatus(err.message);
  }
};

$("stopRecord").onclick = async () => {
  try {
    const data = await api("/api/record/stop", {});
    showLiveResult(data.result);
    setStatus("录像已保存");
  } catch (err) {
    setStatus(err.message);
  }
};

function showLiveResult(result) {
  if (!result) return;
  const runName = result.runDir.split(/[\\/]/).slice(-1)[0];
  $("result").innerHTML = `
    <div>帧数：${result.frames}</div>
    <a href="/runs/${runName}/annotated_tracking.mp4" target="_blank">标注视频</a>
    <a href="/runs/${runName}/pendulum_tracking_wide.csv" target="_blank">宽表 CSV</a>
    <a href="/runs/${runName}/pendulum_tracking_long.csv" target="_blank">长表 CSV</a>
    <a href="/runs/${runName}/angle_timeseries.png" target="_blank">角度曲线</a>
  `;
}

function startLivePolling() {
  if (statusTimer) return;
  statusTimer = setInterval(async () => {
    try {
      const status = await api("/api/status");
      frameSize = status.frameSize || frameSize;
      $("recBadge").textContent = status.recording ? "REC" : activePanel === "offline" ? "OFFLINE" : "READY";
      $("recBadge").classList.toggle("recording", status.recording);
      $("fpsText").textContent = `实际 FPS: ${status.actualFps || "--"}`;
      if (status.error) setStatus(status.error);
      fitCanvas();
    } catch {
      // Keep current UI state.
    }
  }, 500);
}

video.onload = fitCanvas;
window.addEventListener("resize", fitCanvas);
setPanel("offline");
setMode("pivot");
startOfflinePolling();
