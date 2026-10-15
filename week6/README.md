# 6주차 실행 예제

Python 3.12 환경을 사용합니다. 전체 수업 설명은 강의 사이트의 6주차 자료에 있습니다.

## 이미지 실험실

```sh
python -m pip install -r requirements.txt
python -m flask --app app run --debug --port 5000
```

브라우저에서 http://127.0.0.1:5000 을 엽니다. VS Code Live Server로 HTML을 열지 않습니다.
샘플 이미지는 `static/sample.png`입니다. 사진은 JPEG/PNG, 5 MiB 및 800만 픽셀 이하입니다.

## 서버 TTS

이미지 서버를 Ctrl+C로 종료한 뒤 실행합니다.

```sh
python -m pip install -r requirements-tts.txt
python -m piper.download_voices en_US-lessac-low en_US-amy-low en_GB-alan-low --download-dir models
python -m flask --app tts_app run --debug --port 5000
```

http://127.0.0.1:5000/tts 를 엽니다. 기본 모델은 영어용입니다.
영어 문장을 보내면 서버가 WAV를 만들고 브라우저가 파형, 서버 생성 시간, 음성 길이와 파일 크기를 표시합니다.
실습실에 스피커가 없어도 파형으로 결과를 확인할 수 있습니다. 재생과 다운로드는 선택 기능입니다.

### 작은 낭독 친구들

화면 아래의 모찌(민트색 젤리), 포포(노란 솜뭉치), 콩이(보라색 콩)가 문장을 읽어줍니다.
문장 입력란 바로 아래의 선택 버튼에서 친구를 고른 뒤 음성을 생성하세요. 하단 캐릭터를 클릭해도 같은 선택이 적용됩니다.
기본값은 랜덤이며, 선택 변경은 **다음 음성 생성부터** 적용됩니다.
생성이 끝나면 기존 오디오 재생 버튼을 누릅니다. 자동으로 재생하지 않으며, 같은 WAV를 다시 재생하면 같은 친구가 같은 문장을 읽습니다.

재생 중 말풍선에 제출한 문장이 표시되고, WAV의 40ms 구간별 음량에 맞춰 입이 움직입니다.
일시정지하면 입과 몸짓도 멈추고, 재생이 끝나면 다시 돌아다닙니다. 긴 말풍선은 내부에서 스크롤할 수 있습니다.
세 친구는 서로 다른 Piper 모델로 읽습니다. 각 모델은 첫 요청 때 로드하고 이후 재사용하므로 친구별 첫 생성에는 시간이 더 걸릴 수 있습니다.

| 친구 | Piper 모델 | 언어 |
| --- | --- | --- |
| 모찌 | `en_US-lessac-low` | 미국 영어 |
| 포포 | `en_US-amy-low` | 미국 영어 |
| 콩이 | `en_GB-alan-low` | 영국 영어 |

`POST /api/tts`는 기존 `text`, `length_scale`과 함께 `creature` 값(`mochi`, `popo`, `kongi`)을 받습니다.
`creature`를 생략하면 기존 모찌 목소리를 사용합니다. 랜덤 선택은 브라우저에서 한 번 확정해 전송하므로 말풍선의 친구와 합성 모델이 일치합니다.
응답은 `audio/wav`이며 `X-TTS-Creature` 헤더로 사용한 친구를 확인할 수 있습니다.
선택한 모델이 없으면 해당 친구 이름과 함께 오류를 표시합니다. 다른 모델로 자동 대체하지 않습니다.
기존 `TTS_MODEL` 환경변수는 모찌에 적용되며, 포포와 콩이는 각각 `TTS_MODEL_POPO`, `TTS_MODEL_KONGI`로 모델 경로를 지정할 수 있습니다.

운영체제의 움직임 줄이기 설정을 켜면 애니메이션 대신 화자 표시와 말풍선으로 상태를 알려줍니다.

### 브라우저 검증

TTS 환경에 Playwright와 Chrome이 있으면 `week6`에서 다음 명령으로 실행합니다.
테스트는 임시 포트로 로컬 서버를 열고, 무음 구간이 있는 WAV로 재생·탐색·다시 재생·선택 변경·오류 복구·모바일 배치를 확인합니다.

```sh
python -m pip install playwright
python -m unittest discover -s tests -p test_tts_voices.py -v
python tests/test_tts_creatures.py
```

서버 테스트는 모델 선택·캐싱·잘못된 입력·모델 누락·오류 후 재시도를 확인합니다.
실제 Piper 모델 세 개로 같은 문장 생성과 재생까지 확인하려면 PowerShell에서 `$env:TTS_TEST_REAL = '1'`을 설정한 뒤 브라우저 테스트를 실행합니다.
화면 캡처는 임시 폴더의 `campus-tts-check`에 저장합니다.

### 실행 범위와 모델

이 TTS 실습은 Windows PC의 로컬 서버에서 실행하며 별도 배포하지 않습니다.
모델은 직접 내려받으며 이 배포 파일에는 포함하지 않습니다.
엔진과 음성 모델의 이용 조건은 각 프로젝트에서 확인합니다.

- Piper: https://github.com/OHF-Voice/piper1-gpl
- [Lessac 모델 카드](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/low/MODEL_CARD)
- [Amy 모델 카드](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/amy/low/MODEL_CARD)
- [Alan 모델 카드](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/alan/low/MODEL_CARD)

## Render 이미지 앱 설정

학생 저장소의 `week6` 폴더에 이 파일들을 둡니다.
Root Directory: `week6`
Build Command: `pip install -r requirements.txt`
Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120`
Python은 3.12 계열을 지정합니다. 수업 자료의 배포 절차를 확인하세요.

이 앱은 업로드 이미지와 생성한 결과를 영구 저장하지 않습니다.
프론트엔드는 같은 Flask 서버가 제공하므로 별도 CORS 설정은 사용하지 않습니다.
