# 7주차 시작 코드 · 가입과 로그인

이 폴더의 이름을 `week7`로 두고 실행합니다. 처음에는 회원가입·로그인·로그아웃만 동작합니다. 7주차 강의 페이지의 순서대로 첫 실습 ZIP, 두 번째 실습 ZIP을 이 폴더에 **덮어쓰기** 하면 기능이 늘어납니다. `instance/app.db`는 덮어쓰지 말고 그대로 둡니다.

1. 6주차의 `wp6` conda 환경을 활성화하고 `week7` 폴더로 이동합니다.
2. `python -m pip install -r requirements.txt`를 실행합니다.
3. `python -c "import secrets; print(secrets.token_hex(32))"`의 출력값을 복사합니다.
4. Windows Anaconda Prompt: `set "SECRET_KEY=<방금 복사한 64자리 값>"` / macOS Terminal: `export SECRET_KEY='<방금 복사한 64자리 값>'`을 실행합니다. 꺾쇠 안 설명을 **실제 출력된 64자리 전체로 바꿔** 입력하세요.
5. `python -m flask --app app init-db`를 실행합니다.
6. `python -m flask --app app run --debug --port 5000`을 실행하고 새 탭에서 `http://127.0.0.1:5000`을 엽니다.

첫 명령은 무작위 32바이트를 16진수 64자리로 출력하며 파일을 만들지 않습니다. 두 번째 명령은 그 값을 현재 터미널의 환경변수에 넣어 Flask가 읽게 합니다. Flask는 비밀 키로 로그인 session 쿠키에 서명하므로 키를 모르는 사람이 쿠키의 사용자 번호를 바꾸기 어렵습니다. 이 키는 로그인 비밀번호가 아니며 쿠키 내용을 암호화하지도 않습니다.

같은 터미널에서 실행해야 환경변수가 유지됩니다. 새 터미널에서는 키를 다시 설정하세요. 키를 바꾸면 기존 로그인은 풀릴 수 있지만 DB 데이터는 그대로입니다. `init-db`는 없는 표만 만들며 기존 계정은 지우지 않습니다. 실제 키·개인정보·평소 쓰는 비밀번호를 Git에 넣지 마세요. `instance/`는 `.gitignore`에 포함됩니다.
