# 7주차 두 번째 실습 · 관리 화면까지 완성

시작 코드 → 첫 실습 ZIP을 적용한 `week7` 폴더에 이 ZIP의 파일을 **덮어쓰기** 합니다. 서버를 끈 뒤 복사하고, `instance/app.db`는 그대로 두세요. 같은 터미널에서 아래 명령을 실행합니다.

```text
python -m flask --app app init-db
python -m flask --app app run --debug --port 5000
```

`init-db`는 없는 표와 관리 필드를 추가하며 기존 계정과 글을 지우지 않습니다. `SECRET_KEY`는 시작 코드에서 설정한 무작위 값을 계속 사용합니다. 새 터미널이면 다시 설정하세요. 첫 실행이라면 7주차 강의 페이지의 시작 코드 설치부터 진행합니다.

관리자를 만들려면 실습용 계정 `admin7`으로 먼저 가입합니다. 서버 터미널에서 `Ctrl+C`를 누르고 아래처럼 **로컬 터미널**에서 지정한 뒤 서버를 다시 시작합니다. 웹의 회원가입으로 관리자 권한을 선택할 수는 없습니다.

Windows Anaconda Prompt:

```bat
set "WEEK7_ADMIN_USERNAME=admin7"
python -m flask --app app promote-admin
python -m flask --app app run --debug --port 5000
```

macOS Terminal:

```sh
export WEEK7_ADMIN_USERNAME='admin7'
python -m flask --app app promote-admin
python -m flask --app app run --debug --port 5000
```

관리자로 로그인하면 상단에 `관리 화면` 링크가 생깁니다. 먼저 **연습 계정·글 무작위 생성**을 눌러 임의 이름의 계정 2개와 글 4개를 만듭니다. 화면에 한 번만 나오는 두 아이디와 공통 비밀번호를 적어 두세요. 관리자에서 로그아웃해 연습 계정 B로 로그인한 뒤 A의 글을 신고합니다. 관리자로 다시 로그인해 `신고된 글만 보기`, 검색, 글 삭제, 연습 계정 차단·해제를 시험합니다. 연습 계정은 `/admin` 접근 시 403입니다.

시험이 끝나면 관리 화면의 **연습 데이터 모두 삭제**를 누르세요. `users.is_test=1`인 계정과 그 계정의 글·관련 신고만 삭제되며 직접 만든 일반 계정과 글은 남습니다. 새로고침 후 임시 비밀번호 표시가 사라졌다면 새 연습 묶음을 만들거나 기존 연습 데이터를 지우고 다시 만드세요. 한 계정은 1분에 글을 최대 3개만 작성할 수 있고 같은 글을 두 번 신고할 수 없습니다.

`app.py`의 `BOARD_TITLE`·`BOARD_QUESTION`과 `templates/comments.html`의 문구, `static/style.css`를 바꿔 자신만의 주제로 만드세요. `.gitignore`가 `instance/`를 제외합니다. 실습 DB·`SECRET_KEY`·비밀번호는 Git에 올리지 않습니다. GitHub Pages는 Flask를 실행하지 못합니다.

## 실습 2 · Render 배포와 제출

완성한 `week7` 폴더를 GitHub에 push하고 Render에서 **New → Web Service**로 연결합니다. Root Directory는 `week7`, Build Command는 `pip install -r requirements.txt`, Start Command는 다음과 같습니다.

```sh
python -m flask --app app init-db && python -m flask --app app ensure-admin && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2
```

Render의 Environment에 `SECRET_KEY`(64자리 무작위 값), `WEEK7_ADMIN_USERNAME`(실습용 관리자 ID), `WEEK7_ADMIN_PASSWORD`(12자 이상 실습용 PW), `APP_HTTPS=1`, `PYTHON_VERSION=3.12.12`를 설정합니다. 관리자 비밀번호는 `python -c "import secrets; print(secrets.token_urlsafe(18))"`로 만들 수 있습니다. 시작 명령의 `ensure-admin`은 빈 DB에 관리자 계정을 만들고, 재시작 때 기존 관리자 비밀번호를 환경변수 값으로 맞춥니다. 같은 아이디의 일반 계정이 이미 있으면 관리자 아이디를 바꿔야 합니다.

배포된 `https://...onrender.com/`에서 관리자 로그인, 연습 데이터 생성·삭제를 확인하세요. 무료 서비스의 SQLite 파일은 재시작·재배포 때 초기화될 수 있으므로 장기 보관용이 아닙니다. **사이버캠퍼스 7주차 과제 제출란**에 GitHub 저장소 URL, Render URL, 관리자 ID, 관리자 PW를 적습니다. 관리자 ID·PW는 사이버캠퍼스에만 적고 공개 저장소·README·스크린샷에 넣지 마세요. `SECRET_KEY`와 DB 파일은 제출하지 않습니다.
