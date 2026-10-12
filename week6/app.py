"""6주차: 같은 Flask 서버가 HTML과 이미지 처리 API를 제공합니다."""
import os
# 디코딩 전 OpenCV의 이미지 픽셀 상한도 정합니다.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(8_000_000))

from io import BytesIO
from time import perf_counter
import warnings

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError
from flask import Flask, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # multipart 본문 전체 6 MiB
cv2.setNumThreads(1)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/hello")
def hello():
    name = request.args.get("name", "방문자").strip()[:30] or "방문자"
    return render_template("hello.html", name=name)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.errorhandler(RequestEntityTooLarge)
def too_large(error):
    return {"error": "요청이 너무 큽니다. 5 MiB 이하의 사진을 선택하세요."}, 413


@app.post("/api/process")
def process_image():
    started = perf_counter()
    upload = request.files.get("image")
    operation = request.form.get("operation", "grayscale")
    if upload is None or upload.filename == "":
        return {"error": "이미지 파일을 선택하세요."}, 400
    if operation not in {"grayscale", "blur", "edge"}:
        return {"error": "지원하지 않는 처리 방법입니다."}, 400
    try:
        kernel = int(request.form.get("kernel", "15"))
    except ValueError:
        return {"error": "커널은 정수여야 합니다."}, 400
    if kernel < 3 or kernel > 51 or kernel % 2 == 0:
        return {"error": "커널은 3~51 사이의 홀수여야 합니다."}, 400

    raw = upload.read()
    if len(raw) > 5 * 1024 * 1024:
        return {"error": "파일은 5 MiB 이하여야 합니다."}, 413
    # 확장자만 믿지 않고 형식·크기를 확인한 다음 OpenCV로 디코딩합니다.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as header:
                if header.format not in {"JPEG", "PNG"}:
                    return {"error": "JPEG 또는 PNG 파일을 사용하세요."}, 400
                width, height = header.size
                if width * height > 8_000_000:
                    return {"error": "800만 픽셀 이하로 줄여 주세요."}, 413
                header.verify()
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return {"error": "이미지를 읽지 못했습니다."}, 400
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning, cv2.error):
        return {"error": "올바른 JPEG/PNG 이미지인지 확인하세요."}, 400

    # 수업용 서버가 큰 사진도 처리하도록 긴 변을 최대 1600px로 줄입니다.
    height, width = image.shape[:2]
    if max(height, width) > 1600:
        scale = 1600 / max(height, width)
        image = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))))
    compute_started = perf_counter()
    if operation == "grayscale":
        result = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif operation == "blur":
        result = cv2.GaussianBlur(image, (kernel, kernel), 0)
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        result = cv2.Canny(gray, 100, 200)
    compute_ms = (perf_counter() - compute_started) * 1000
    ok, encoded = cv2.imencode(".png", result)
    if not ok:
        return {"error": "결과 이미지를 만들지 못했습니다."}, 500
    response = send_file(BytesIO(encoded.tobytes()), mimetype="image/png",
                         download_name="processed.png", max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Compute-Ms"] = f"{compute_ms:.2f}"
    response.headers["X-Processing-Ms"] = f"{(perf_counter() - started) * 1000:.2f}"
    response.headers["X-Image-Size"] = f"{result.shape[1]}x{result.shape[0]}"
    return response
