const form = document.querySelector("#image-form");
const status = document.querySelector("#status");
let originalURL = null;
let resultURL = null;
function clearResult() {
  if (resultURL) URL.revokeObjectURL(resultURL);
  resultURL = null;
  document.querySelector("#result").hidden = true;
  document.querySelector("#result").removeAttribute("src");
  document.querySelector("#download").hidden = true;
  document.querySelector("#download").removeAttribute("href");
  document.querySelector("#timing").textContent = "새 결과를 기다립니다.";
}
document.querySelector("#image").addEventListener("change", function () {
  clearResult();
  if (originalURL) URL.revokeObjectURL(originalURL);
  originalURL = null;
  const file = this.files[0];
  const preview = document.querySelector("#original");
  preview.hidden = !file;
  preview.removeAttribute("src");
  if (file) {
    originalURL = URL.createObjectURL(file);
    preview.src = originalURL;
  }
  status.textContent = "처리할 방법을 고르고 서버에서 처리를 누르세요.";
});
form.addEventListener("submit", async function (event) {
  // 이 버튼은 JavaScript 가로채기 없이 HTML form의 기본 제출을 사용합니다.
  if (event.submitter && event.submitter.id === "native") return;
  event.preventDefault();
  const data = new FormData(form); // 비활성화 전에 입력을 담습니다.
  const controls = document.querySelector("#controls");
  clearResult();
  controls.disabled = true;
  status.textContent = "Processing... 서버에서 처리 중입니다.";
  const started = performance.now();
  try {
    const response = await fetch("/api/process", { method: "POST", body: data });
    if (!response.ok) {
      let message = "처리에 실패했습니다. HTTP " + response.status;
      if ((response.headers.get("Content-Type") || "").includes("application/json")) {
        const error = await response.json();
        message = error.error || message;
      }
      throw new Error(message);
    }
    const blob = await response.blob();
    resultURL = URL.createObjectURL(blob);
    document.querySelector("#result").src = resultURL;
    document.querySelector("#result").hidden = false;
    document.querySelector("#download").href = resultURL;
    document.querySelector("#download").hidden = false;
    const roundTrip = performance.now() - started;
    document.querySelector("#timing").textContent =
      "알고리즘 " + response.headers.get("X-Compute-Ms") + " ms · 서버 처리 " +
      response.headers.get("X-Processing-Ms") + " ms · 왕복 " + roundTrip.toFixed(1) + " ms";
    status.textContent = "완료 · 결과 크기 " + response.headers.get("X-Image-Size");
  } catch (error) {
    status.textContent = "처리하지 못했습니다. " + error.message + " 서버 실행 여부도 확인하세요.";
  } finally {
    controls.disabled = false;
  }
});
