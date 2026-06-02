const urlInput = document.querySelector("#urlInput");
const cookieSource = document.querySelector("#cookieSource");
const downloadScope = document.querySelector("#downloadScope");
const quality = document.querySelector("#quality");
const outputDir = document.querySelector("#outputDir");
const probeBtn = document.querySelector("#probeBtn");
const downloadBtn = document.querySelector("#downloadBtn");
const envBadge = document.querySelector("#envBadge");
const jobState = document.querySelector("#jobState");
const progressBar = document.querySelector("#progressBar");
const message = document.querySelector("#message");
const title = document.querySelector("#title");
const savedFile = document.querySelector("#savedFile");
const log = document.querySelector("#log");

let pollTimer = null;

const stateLabels = {
  queued: "排队中",
  running: "下载中",
  completed: "已完成",
  error: "出错",
  probing: "检测中",
  ready: "可下载",
  idle: "空闲",
};

const messageLabels = {
  Queued: "已加入下载队列",
  "Preparing download": "正在准备下载",
  Downloading: "正在下载",
  "Merging and finalizing": "正在合并并整理文件",
  "Converting to Mac-compatible H.264 MP4": "正在转换为 Mac 可播放的 H.264 MP4",
  Completed: "下载完成",
  Failed: "下载失败",
};

function writeLog(line) {
  const time = new Date().toLocaleTimeString();
  log.textContent = `${log.textContent}[${time}] ${line}\n`;
  log.scrollTop = log.scrollHeight;
}

function setBusy(isBusy) {
  probeBtn.disabled = isBusy;
  downloadBtn.disabled = isBusy;
}

function setState(state) {
  jobState.textContent = stateLabels[state] || state;
  jobState.className = `state ${state}`;
}

function updateProgress(value) {
  const progress = Math.max(0, Math.min(100, Number(value) || 0));
  progressBar.style.width = `${progress}%`;
}

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}

function requestPayload() {
  return {
    url: urlInput.value.trim(),
    cookie_source: cookieSource.value,
    download_scope: downloadScope.value,
    quality: quality.value,
    output_dir: outputDir.value.trim(),
  };
}

async function loadHealth() {
  const response = await fetch("/api/health");
  const data = await response.json();
  outputDir.value = data.default_output_dir || "";
  if (data.ffmpeg_available) {
    envBadge.textContent = "ffmpeg 已就绪";
    envBadge.className = "badge";
  } else {
    envBadge.textContent = "缺少 ffmpeg";
    envBadge.className = "badge warn";
    writeLog("缺少 ffmpeg，高清下载和格式转换需要先安装：brew install ffmpeg");
  }
}

async function probe() {
  const payload = requestPayload();
  if (!payload.url) {
    message.textContent = "请先输入视频链接。";
    return;
  }

  setBusy(true);
  setState("probing");
  updateProgress(0);
  try {
    const data = await api("/api/probe", payload);
    title.textContent = data.title || "-";
    savedFile.textContent = "-";
    const scopeText = data.download_scope === "collection" ? `，合集/列表内检测到 ${data.entry_count || 0} 个条目` : "";
    message.textContent = `检测成功：${data.extractor || "解析器"} 找到 ${data.format_count || 0} 个可用格式${scopeText}。`;
    writeLog(`检测成功：${data.title || data.webpage_url}`);
    if (!data.ffmpeg_available) {
      writeLog("缺少 ffmpeg，请运行：brew install ffmpeg");
    }
    setState("ready");
  } catch (error) {
    message.textContent = error.message;
    writeLog(`检测失败：${error.message}`);
    setState("error");
  } finally {
    setBusy(false);
  }
}

async function startDownload() {
  const payload = requestPayload();
  if (!payload.url) {
    message.textContent = "请先输入视频链接。";
    return;
  }

  setBusy(true);
  updateProgress(0);
  savedFile.textContent = "-";
  try {
    const job = await api("/api/download", payload);
    writeLog(`下载任务已创建：${job.id}`);
    pollJob(job.id);
  } catch (error) {
    message.textContent = error.message;
    writeLog(`下载启动失败：${error.message}`);
    setState("error");
    setBusy(false);
  }
}

async function pollJob(jobId) {
  if (pollTimer) {
    window.clearTimeout(pollTimer);
  }

  try {
    const response = await fetch(`/api/jobs/${jobId}`);
    const job = await response.json();
    if (!response.ok) {
      throw new Error(job.detail || "没有找到这个下载任务");
    }

    setState(job.status);
    updateProgress(job.progress);
    message.textContent = job.error || messageLabels[job.message] || stateLabels[job.status] || job.message || job.status;
    title.textContent = job.title || title.textContent || "-";
    if (Array.isArray(job.output_paths) && job.output_paths.length > 1) {
      savedFile.textContent = job.output_paths.join("\n");
    } else {
      savedFile.textContent = job.output_path || "-";
    }

    if (job.status === "completed") {
      const countText = Array.isArray(job.output_paths) && job.output_paths.length > 1 ? `，共 ${job.output_paths.length} 个文件` : "";
      writeLog(`下载完成${countText}：${job.output_path || "文件已保存"}`);
      setBusy(false);
      return;
    }

    if (job.status === "error") {
      writeLog(`下载失败：${job.error || "未知错误"}`);
      setBusy(false);
      return;
    }

    pollTimer = window.setTimeout(() => pollJob(jobId), 1000);
  } catch (error) {
    message.textContent = error.message;
    writeLog(`状态检查失败：${error.message}`);
    setState("error");
    setBusy(false);
  }
}

probeBtn.addEventListener("click", probe);
downloadBtn.addEventListener("click", startDownload);
loadHealth().catch((error) => {
  envBadge.textContent = "服务异常";
  envBadge.className = "badge warn";
  writeLog(error.message);
});
