"""실습 2: 이미지 앱에 서버 TTS 경로를 추가합니다."""
from io import BytesIO
from pathlib import Path
from threading import Lock
from time import perf_counter
import os
import wave

from flask import render_template, request, send_file
from app import app

voices = {}
voice_lock = Lock()
MODEL_DIR = Path(__file__).parent / "models"
CREATURE_NAMES = {"mochi": "모찌", "popo": "포포", "kongi": "콩이"}
MODELS = {
    # Keep the original TTS_MODEL override for the default voice.
    "mochi": Path(os.environ.get("TTS_MODEL", str(MODEL_DIR / "en_US-lessac-low.onnx"))),
    "popo": Path(os.environ.get("TTS_MODEL_POPO", str(MODEL_DIR / "en_US-amy-low.onnx"))),
    "kongi": Path(os.environ.get("TTS_MODEL_KONGI", str(MODEL_DIR / "en_GB-alan-low.onnx"))),
}


@app.get("/tts")
def tts_page():
    return render_template("tts.html")


@app.post("/api/tts")
def tts():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "JSON 객체로 text를 보내세요."}, 400
    text = data.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 300:
        return {"error": "1~300자의 영어 문장을 입력하세요."}, 400
    if not text.isascii() or not any(char.isalpha() for char in text):
        return {"error": "기본 모델은 영어용입니다. 영문 문장으로 시험하세요."}, 400
    try:
        length_scale = float(data.get("length_scale", 1.0))
    except (TypeError, ValueError):
        return {"error": "음성 길이 배율은 숫자여야 합니다."}, 400
    if length_scale not in (0.8, 1.0, 1.25):
        return {"error": "배율은 0.8, 1.0, 1.25 중 하나입니다."}, 400
    creature = data.get("creature", "mochi")
    if not isinstance(creature, str) or creature not in MODELS:
        return {"error": "읽을 친구는 mochi, popo, kongi 중 하나여야 합니다."}, 400
    model = MODELS[creature]
    if not model.is_file() or not Path(str(model) + ".json").is_file():
        return {"error": f"{CREATURE_NAMES[creature]}의 음성 모델과 설정 파일이 없습니다. README의 모델 다운로드 단계를 실행하세요."}, 503
    try:
        from piper import PiperVoice, SynthesisConfig
    except ImportError:
        return {"error": "requirements-tts.txt의 패키지를 설치하세요."}, 503
    if not voice_lock.acquire(blocking=False):
        return {"error": "다른 음성을 만드는 중입니다. 잠시 뒤 다시 시도하세요."}, 429
    started = perf_counter()
    try:
        if creature not in voices:
            # Load each distinct voice once, under the same synthesis lock.
            voices[creature] = PiperVoice.load(str(model))
        voice = voices[creature]
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            voice.synthesize_wav(text.strip(), wav_file,
                                 syn_config=SynthesisConfig(length_scale=length_scale))
        buffer.seek(0)
        response = send_file(buffer, mimetype="audio/wav", download_name="speech.wav", max_age=0)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Processing-Ms"] = f"{(perf_counter() - started) * 1000:.1f}"
        response.headers["X-TTS-Creature"] = creature
        return response
    except Exception:
        app.logger.exception("TTS 생성 실패")
        return {"error": "음성을 만들지 못했습니다. 서버 터미널에서 오류를 확인하세요."}, 500
    finally:
        voice_lock.release()
