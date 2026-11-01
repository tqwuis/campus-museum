"""7주차 시작 코드: 회원가입, 로그인, 로그아웃을 먼저 확인합니다."""

import os
import re
import secrets
import sqlite3
from pathlib import Path

from flask import Flask, abort, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


secret_key = os.environ.get("SECRET_KEY", "")
if len(secret_key) < 32:
    raise RuntimeError("SECRET_KEY 환경변수에 충분히 긴 무작위 값을 설정하세요. README를 확인하세요.")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=secret_key,
    DATABASE=os.environ.get("WEEK7_DB_PATH", str(Path(app.instance_path) / "app.db")),
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("APP_HTTPS") == "1",
)

# 학생이 자신의 게시판 주제로 바꾸는 곳입니다.
BOARD_TITLE = "공강 시간 한 줄 추천"
BOARD_QUESTION = "공강 두 시간, 어디서 보내고 싶나요?"
USERNAME_RULE = re.compile(r"[A-Za-z0-9_]{3,20}\Z")


def get_db():
    """요청 중에는 연결을 재사용하고 요청이 끝나면 닫습니다."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"], timeout=5)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.cli.command("init-db")
def init_db_command():
    """없는 표만 만듭니다. 이미 저장된 계정은 유지합니다."""
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with app.open_resource("schema.sql") as schema:
        get_db().executescript(schema.read().decode("utf-8"))
    print(f"DB 준비 완료: {app.config['DATABASE']}")


@app.before_request
def load_user_and_check_csrf():
    g.user = None
    user_id = session.get("user_id")
    if isinstance(user_id, int):
        g.user = get_db().execute(
            "SELECT id, username, is_admin, is_blocked FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if g.user is None or g.user["is_blocked"]:
            g.user = None
            session.clear()
    elif user_id is not None:
        session.clear()

    if request.method == "POST":
        expected = session.get("_csrf_token")
        received = request.form.get("_csrf_token")
        if not expected or not received or not secrets.compare_digest(expected, received):
            abort(400, description="요청 확인 값이 없거나 맞지 않습니다. 페이지를 다시 열어 주세요.")


@app.context_processor
def template_values():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return {
        "csrf_token": token,
        "current_user": g.get("user"),
        "board_title": BOARD_TITLE,
        "board_question": BOARD_QUESTION,
    }


@app.get("/")
def index():
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth.html", mode="register")
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not USERNAME_RULE.fullmatch(username):
        return render_template("auth.html", mode="register", error="아이디는 영문·숫자·밑줄 3~20자여야 합니다.", username=username), 400
    if len(password) < 8 or len(password) > 128:
        return render_template("auth.html", mode="register", error="비밀번호는 8~128자로 입력하세요.", username=username), 400
    try:
        db = get_db()
        db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return render_template("auth.html", mode="register", error="이미 사용 중인 아이디입니다.", username=username), 400
    return redirect(url_for("login", registered=1))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth.html", mode="login")
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    user = get_db().execute(
        "SELECT id, password_hash, is_blocked FROM users WHERE username = ?", (username,)
    ).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("auth.html", mode="login", error="아이디 또는 비밀번호를 확인하세요.", username=username), 401
    if user["is_blocked"]:
        return render_template("auth.html", mode="login", error="차단된 계정입니다.", username=username), 403
    session.clear()
    session["user_id"] = user["id"]
    session["_csrf_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("index"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(429)
def request_error(error):
    return render_template("error.html", message=error.description), error.code
