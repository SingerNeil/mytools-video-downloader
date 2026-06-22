const urlInput = document.querySelector("#urlInput");
const cookieSource = document.querySelector("#cookieSource");
const downloadScope = document.querySelector("#downloadScope");
const platformHint = document.querySelector("#platformHint");
const quality = document.querySelector("#quality");
const compressionTarget = document.querySelector("#compressionTarget");
const outputDir = document.querySelector("#outputDir");
const probeBtn = document.querySelector("#probeBtn");
const downloadBtn = document.querySelector("#downloadBtn");
const cancelBtn = document.querySelector("#cancelBtn");
const localVideoInput = document.querySelector("#localVideoInput");
const localCompressionTarget = document.querySelector("#localCompressionTarget");
const compressLocalBtn = document.querySelector("#compressLocalBtn");
const envBadge = document.querySelector("#envBadge");
const jobState = document.querySelector("#jobState");
const progressBar = document.querySelector("#progressBar");
const message = document.querySelector("#message");
const title = document.querySelector("#title");
const savedFile = document.querySelector("#savedFile");
const log = document.querySelector("#log");

let pollTimer = null;
let saveOutputDirTimer = null;
let lastLinkDefaultsKey = "";
let currentJobId = null;

const stateLabels = {
  queued: "排队中",
  running: "处理中",
  completed: "已完成",
  error: "出错",
  canceled: "已停止",
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
  "任务已停止": "任务已停止",
};

const platformLabels = {
  waiting: "待识别",
  generic: "通用链接",
  bilibili: "哔哩哔哩",
  youtube: "YouTube",
  xiaohongshu: "小红书",
  douyin: "抖音",
};

function writeLog(line) {
  const time = new Date().toLocaleTimeString();
  log.textContent = `${log.textContent}[${time}] ${line}\n`;
  log.scrollTop = log.scrollHeight;
}

function setBusy(isBusy) {
  probeBtn.disabled = isBusy;
  downloadBtn.disabled = isBusy;
  compressLocalBtn.disabled = isBusy;
  localVideoInput.disabled = isBusy;
  cancelBtn.disabled = !isBusy || !currentJobId;
}

function setState(state) {
  jobState.textContent = stateLabels[state] || state;
  jobState.className = `state ${state}`;
}

function updateProgress(value) {
  const progress = Math.max(0, Math.min(100, Number(value) || 0));
  progressBar.style.width = `${progress}%`;
}

function extractFirstUrl(value) {
  const match = value.trim().match(/https?:\/\/[^\s，。；、]+/);
  if (!match) {
    return value.trim();
  }
  return match[0].replace(/[.,;:!?)]}"'，。；：！？）】」』]+$/g, "");
}

function detectPlatform(parsedUrl) {
  const host = parsedUrl.hostname.toLowerCase();
  if (host.includes("douyin.com") || host.includes("iesdouyin.com") || host.includes("amemv.com")) {
    return "douyin";
  }
  if (host.includes("bilibili.com") || host === "b23.tv") {
    return "bilibili";
  }
  if (host.includes("youtube.com") || host === "youtu.be") {
    return "youtube";
  }
  if (host.includes("xiaohongshu.com") || host === "xhslink.com") {
    return "xiaohongshu";
  }
  return "generic";
}

function detectRecommendedScope(parsedUrl, platform) {
  const path = parsedUrl.pathname.toLowerCase();
  if (platform === "youtube" && parsedUrl.searchParams.has("list")) {
    return "collection";
  }
  if (platform === "bilibili") {
    if (parsedUrl.searchParams.has("p")) {
      return "collection";
    }
    if (path.includes("/medialist/") || path.includes("/list/") || path.includes("/bangumi/play/")) {
      return "collection";
    }
  }
  return "single";
}

function applyLinkDefaults() {
  const rawValue = urlInput.value.trim();
  if (!rawValue) {
    platformHint.value = "waiting";
    lastLinkDefaultsKey = "";
    return;
  }

  const firstUrl = extractFirstUrl(rawValue);
  let parsedUrl;
  try {
    parsedUrl = new URL(firstUrl);
  } catch {
    platformHint.value = "waiting";
    return;
  }

  const platform = detectPlatform(parsedUrl);
  const recommendedScope = detectRecommendedScope(parsedUrl, platform);
  const nextKey = `${platform}:${recommendedScope}:${firstUrl}`;
  platformHint.value = platform;
  downloadScope.value = recommendedScope;

  if (nextKey !== lastLinkDefaultsKey) {
    const scopeText = recommendedScope === "collection" ? "下载整个合集/列表" : "仅下载当前视频";
    message.textContent = `已识别：${platformLabels[platform]}，已切换为“${scopeText}”。`;
    lastLinkDefaultsKey = nextKey;
  }
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

async function saveOutputDir(silent = false) {
  const value = outputDir.value.trim();
  if (!value) {
    return;
  }
  const data = await api("/api/settings", { output_dir: value });
  outputDir.value = data.output_dir || value;
  if (!silent) {
    writeLog(`保存位置已记住：${outputDir.value}`);
  }
}

function requestPayload() {
  return {
    url: urlInput.value.trim(),
    cookie_source: cookieSource.value,
    download_scope: downloadScope.value,
    quality: quality.value,
    compression_target_mb: Number(compressionTarget.value),
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
  if (!data.youtube_ejs_available) {
    writeLog("YouTube 下载需要 Node 22+ 和 yt-dlp-ejs；请停止服务后重新运行 ./run.sh 安装依赖。");
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
    const platformText = data.platform && data.platform.label ? `${data.platform.label}，` : "";
    message.textContent = `检测成功：${platformText}${data.extractor || "解析器"} 找到 ${data.format_count || 0} 个可用格式${scopeText}。`;
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
    await saveOutputDir(true);
    const job = await api("/api/download", payload);
    currentJobId = job.id;
    setBusy(true);
    writeLog(`下载任务已创建：${job.id}`);
    pollJob(job.id);
  } catch (error) {
    message.textContent = error.message;
    writeLog(`下载启动失败：${error.message}`);
    setState("error");
    setBusy(false);
  }
}

async function startLocalCompression() {
  const file = localVideoInput.files && localVideoInput.files[0];
  if (!file) {
    message.textContent = "请先选择一个本地视频文件。";
    return;
  }

  setBusy(true);
  setState("running");
  updateProgress(0);
  title.textContent = file.name;
  savedFile.textContent = "-";
  message.textContent = "正在读取本地视频，请稍等。";
  writeLog(`正在读取本地视频：${file.name}`);

  try {
    await saveOutputDir(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("compression_target_mb", localCompressionTarget.value);
    formData.append("output_dir", outputDir.value.trim());
    const response = await fetch("/api/compress-local", {
      method: "POST",
      body: formData,
    });
    const job = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(job.detail || "本地视频上传失败");
    }
    currentJobId = job.id;
    setBusy(true);
    writeLog(`本地视频压缩任务已创建：${job.id}`);
    pollJob(job.id);
  } catch (error) {
    message.textContent = error.message;
    writeLog(`本地视频压缩启动失败：${error.message}`);
    setState("error");
    setBusy(false);
  }
}

async function cancelDownload() {
  if (!currentJobId) {
    return;
  }

  cancelBtn.disabled = true;
  message.textContent = "正在停止任务，请稍等。";
  writeLog("正在停止当前任务。");
  try {
    await api(`/api/jobs/${currentJobId}/cancel`, {});
  } catch (error) {
    writeLog(`停止任务失败：${error.message}`);
    cancelBtn.disabled = false;
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
      writeLog(`任务完成${countText}：${job.output_path || "文件已保存"}`);
      currentJobId = null;
      setBusy(false);
      return;
    }

    if (job.status === "error") {
      writeLog(`下载失败：${job.error || "未知错误"}`);
      currentJobId = null;
      setBusy(false);
      return;
    }

    if (job.status === "canceled") {
      writeLog("任务已停止。");
      currentJobId = null;
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
compressLocalBtn.addEventListener("click", startLocalCompression);
cancelBtn.addEventListener("click", cancelDownload);
urlInput.addEventListener("input", applyLinkDefaults);
urlInput.addEventListener("paste", () => {
  window.setTimeout(applyLinkDefaults, 0);
});
outputDir.addEventListener("change", () => {
  saveOutputDir().catch((error) => writeLog(`保存位置失败：${error.message}`));
});
outputDir.addEventListener("input", () => {
  window.clearTimeout(saveOutputDirTimer);
  saveOutputDirTimer = window.setTimeout(() => {
    saveOutputDir(true).catch((error) => writeLog(`保存位置失败：${error.message}`));
  }, 800);
});
loadHealth().catch((error) => {
  envBadge.textContent = "服务异常";
  envBadge.className = "badge warn";
  writeLog(error.message);
});
