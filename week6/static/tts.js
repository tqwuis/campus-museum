let audioURL = null;
let decodedAudio = null;
const form = document.querySelector("#tts-form");
const controls = document.querySelector("#tts-controls");
const status = document.querySelector("#tts-status");
const result = document.querySelector("#tts-result");
const canvas = document.querySelector("#waveform");
const audio = document.querySelector("#audio");
const download = document.querySelector("#wav-download");
const creatures = window.creatureStage;

function drawWaveform(buffer) {
  const pixelRatio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(canvas.clientWidth * pixelRatio));
  const height = Math.round(240 * pixelRatio);
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  const samples = buffer.getChannelData(0);
  const middle = height / 2;
  const step = Math.max(1, Math.ceil(samples.length / width));

  ctx.fillStyle = "#eaf3ff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#9fb6ca";
  ctx.beginPath();
  ctx.moveTo(0, middle);
  ctx.lineTo(width, middle);
  ctx.stroke();
  ctx.strokeStyle = "#245f94";
  ctx.lineWidth = Math.max(1, pixelRatio);
  ctx.beginPath();
  for (let x = 0; x < width; x++) {
    let minimum = 1;
    let maximum = -1;
    const end = Math.min(samples.length, (x + 1) * step);
    for (let i = x * step; i < end; i++) {
      minimum = Math.min(minimum, samples[i]);
      maximum = Math.max(maximum, samples[i]);
    }
    if (end <= x * step) break;
    ctx.moveTo(x, middle - maximum * middle * 0.9);
    ctx.lineTo(x, middle - minimum * middle * 0.9);
  }
  ctx.stroke();
}

window.addEventListener("resize", () => {
  if (decodedAudio) drawWaveform(decodedAudio);
});

form.addEventListener("submit", async function (event) {
  event.preventDefault();
  if (controls.disabled) return;
  const data = {
    text: document.querySelector("#text").value,
    length_scale: Number(document.querySelector("#length-scale").value)
  };
  data.creature = creatures.begin(data.text);
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  audio.hidden = true;
  download.hidden = true;
  download.removeAttribute("href");
  result.hidden = true;
  decodedAudio = null;
  if (audioURL) URL.revokeObjectURL(audioURL);
  audioURL = null;
  controls.disabled = true;
  status.textContent = "Processing... 서버가 WAV를 생성하고 있습니다.";

  try {
    const response = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    if (!response.ok) {
      let message = "HTTP " + response.status;
      if ((response.headers.get("Content-Type") || "").includes("application/json")) {
        const error = await response.json();
        message = error.error || message;
      }
      throw new Error(message);
    }
    if (!(response.headers.get("Content-Type") || "").includes("audio/wav")) {
      throw new Error("서버가 WAV 대신 다른 응답을 보냈습니다.");
    }
    const blob = await response.blob();
    const context = new (window.AudioContext || window.webkitAudioContext)();
    let buffer;
    try {
      buffer = await context.decodeAudioData(await blob.arrayBuffer());
    } finally {
      await context.close();
    }
    if (!Number.isFinite(buffer.duration) || buffer.duration <= 0) {
      throw new Error("음성 길이를 확인할 수 없습니다.");
    }
    document.querySelector("#tts-time").textContent =
      (response.headers.get("X-Processing-Ms") || "측정 불가") + " ms";
    document.querySelector("#tts-duration").textContent = buffer.duration.toFixed(2) + "초";
    document.querySelector("#tts-size").textContent = (blob.size / 1024).toFixed(1) + " KiB";
    result.hidden = false;
    decodedAudio = buffer;
    drawWaveform(buffer);
    audioURL = URL.createObjectURL(blob);
    audio.src = audioURL;
    audio.hidden = false;
    download.href = audioURL;
    download.hidden = false;
    creatures.ready(buffer);
    status.textContent = "완료 · WAV를 받아 파형을 그렸습니다. 재생하면 아래의 친구가 읽어줍니다.";
  } catch (error) {
    result.hidden = true;
    decodedAudio = null;
    creatures.fail();
    status.textContent = "음성을 확인하지 못했습니다. " + error.message;
  } finally {
    controls.disabled = false;
  }
});

audio.addEventListener("error", () => {
  if (!audio.error || !audio.getAttribute("src")) return;
  creatures.fail();
  status.textContent = "음성을 재생하지 못했습니다. 음성을 다시 만들어 주세요.";
});
