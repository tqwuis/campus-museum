"""7주차 완성 코드: 짧은 글과 관리자 기능을 SQLite에 저장합니다."""

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
BOARD_TITLE = "친구를 위한 한마디"
BOARD_QUESTION = "열심히 공부하는 친구를 위해 한마디를 남겨 주세요."
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
    """없는 표만 만듭니다. 이미 저장된 사용·댓글 데이터는 유지합니다."""
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with app.open_resource("schema.sql") as schema:
        get_db().executescript(schema.read().decode("utf-8"))
    # 이전 7주차 예제의 DB를 그대로 쓰는 학생을 위한 작은 스키마 갱신.
    columns = {row["name"] for row in get_db().execute("PRAGMA table_info(users)")}
    for column in ("is_admin", "is_blocked", "is_test"):
        if column not in columns:
            get_db().execute(f"ALTER TABLE users ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
    get_db().commit()
    print(f"DB 준비 완료: {app.config['DATABASE']}")


@app.cli.command("promote-admin")
def promote_admin_command():
    """로컬 터미널에서만 첫 관리자 계정을 지정합니다."""
    username = os.environ.get("WEEK7_ADMIN_USERNAME", "").strip()
    if not username:
        raise RuntimeError("WEEK7_ADMIN_USERNAME에 가입한 아이디를 설정하세요.")
    db = get_db()
    result = db.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
    db.commit()
    if result.rowcount != 1:
        raise RuntimeError("가입한 아이디를 찾을 수 없습니다.")
    print(f"관리자 지정 완료: {username}")


@app.cli.command("ensure-admin")
def ensure_admin_command():
    """배포 시작 시 환경변수의 실습용 관리자를 준비합니다."""
    username = os.environ.get("WEEK7_ADMIN_USERNAME", "").strip()
    password = os.environ.get("WEEK7_ADMIN_PASSWORD", "")
    if not USERNAME_RULE.fullmatch(username) or not 12 <= len(password) <= 128:
        raise RuntimeError("WEEK7_ADMIN_USERNAME과 12자 이상 실습용 WEEK7_ADMIN_PASSWORD를 설정하세요.")
    db = get_db()
    user = db.execute("SELECT id, is_admin FROM users WHERE username = ?", (username,)).fetchone()
    if user is None:
        db.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (username, generate_password_hash(password)),
        )
    elif user["is_admin"]:
        db.execute(
            "UPDATE users SET password_hash = ?, is_blocked = 0 WHERE id = ?",
            (generate_password_hash(password), user["id"]),
        )
    else:
        raise RuntimeError("같은 아이디의 일반 계정이 있습니다. 다른 관리자 아이디를 정하세요.")
    db.commit()
    print(f"배포 관리자 준비 완료: {username}")


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
@app.get("/comments")
def comments():
    rows = get_db().execute(
        """SELECT comments.id, comments.content, comments.created_at,
                  users.id AS author_id, users.username
           FROM comments JOIN users ON comments.user_id = users.id
           ORDER BY comments.created_at DESC, comments.id DESC"""
    ).fetchall()
    return render_template("comments.html", comments=rows)


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
    return redirect(url_for("comments"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("comments"))


@app.post("/comments")
def add_comment():
    if g.user is None:
        abort(401, description="댓글을 쓰려면 로그인하세요.")
    content = request.form.get("content", "").strip()
    if not 1 <= len(content) <= 300:
        return render_template("error.html", message="댓글은 1~300자로 입력하세요."), 400
    db = get_db()
    recent = db.execute(
        "SELECT COUNT(*) FROM comments WHERE user_id = ? AND created_at >= datetime('now', '-1 minute')",
        (g.user["id"],),
    ).fetchone()[0]
    if recent >= 3:
        return render_template("error.html", message="1분에 글은 3개까지만 올릴 수 있습니다."), 429
    db.execute(
        "INSERT INTO comments (user_id, content) VALUES (?, ?)",
        (g.user["id"], content),
    )
    db.commit()
    return redirect(url_for("comments"))


@app.post("/comments/<int:comment_id>/delete")
def delete_comment(comment_id):
    if g.user is None:
        abort(401, description="댓글을 삭제하려면 로그인하세요.")
    db = get_db()
    comment = db.execute("SELECT user_id FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if comment is None:
        abort(404, description="댓글을 찾을 수 없습니다.")
    if comment["user_id"] != g.user["id"]:
        abort(403, description="자신의 댓글만 삭제할 수 있습니다.")
    db.execute("DELETE FROM comments WHERE id = ? AND user_id = ?", (comment_id, g.user["id"]))
    db.commit()
    return redirect(url_for("comments"))


@app.post("/comments/<int:comment_id>/report")
def report_comment(comment_id):
    if g.user is None:
        abort(401, description="신고하려면 로그인하세요.")
    reason = request.form.get("reason", "").strip()
    if not 3 <= len(reason) <= 100:
        abort(400, description="신고 이유는 3~100자로 적으세요.")
    db = get_db()
    comment = db.execute("SELECT user_id FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if comment is None:
        abort(404, description="글을 찾을 수 없습니다.")
    if comment["user_id"] == g.user["id"]:
        abort(400, description="자신의 글은 신고할 수 없습니다.")
    try:
        db.execute(
            "INSERT INTO reports (comment_id, reporter_id, reason) VALUES (?, ?, ?)",
            (comment_id, g.user["id"], reason),
        )
        db.commit()
    except sqlite3.IntegrityError:
        abort(400, description="이미 신고한 글입니다.")
    return redirect(url_for("comments", reported=1))


def require_admin():
    if g.user is None or not g.user["is_admin"]:
        abort(403, description="관리자만 열 수 있습니다.")


@app.get("/admin")
def admin():
    require_admin()
    query = request.args.get("q", "").strip()[:100]
    reported_only = request.args.get("reported") == "1"
    db = get_db()
    rows = db.execute(
        """SELECT comments.id, comments.content, comments.created_at,
                  users.username, COUNT(reports.id) AS report_count,
                  GROUP_CONCAT(reports.reason, ' / ') AS report_reasons
           FROM comments JOIN users ON users.id = comments.user_id
           LEFT JOIN reports ON reports.comment_id = comments.id
           WHERE instr(lower(comments.content), lower(?)) > 0
           GROUP BY comments.id
           HAVING (? = 0 OR COUNT(reports.id) > 0)
           ORDER BY comments.id DESC""",
        (query, int(reported_only)),
    ).fetchall()
    users = db.execute(
        "SELECT id, username, is_admin, is_blocked, is_test FROM users ORDER BY id"
    ).fetchall()
    test_user_count = sum(user["is_test"] for user in users)
    test_comment_count = db.execute(
        "SELECT COUNT(*) FROM comments JOIN users ON comments.user_id = users.id WHERE users.is_test = 1"
    ).fetchone()[0]
    return render_template(
        "admin.html", comments=rows, users=users, query=query, reported_only=reported_only,
        test_user_count=test_user_count, test_comment_count=test_comment_count,
        test_credentials=session.pop("test_credentials", None),
        test_notice=session.pop("test_notice", None),
    )


@app.post("/admin/test-data/create")
def create_test_data():
    require_admin()
    db = get_db()
    password = secrets.token_urlsafe(12)
    password_hash = generate_password_hash(password)
    samples = (
        "[연습] 조용한 공강 장소를 추천해 주세요!",
        "[연습] 오늘의 간식 후보: 붕어빵과 샌드위치",
        "[연습] 광고처럼 반복되는 글을 찾을 수 있나요?",
        "[연습] 친구와 함께 가고 싶은 학교 근처 장소",
        "[연습] 점심 메뉴를 하나만 고른다면?",
        "[연습] 이 글을 다른 계정으로 신고해 보세요.",
    )
    names = []
    for label in ("a", "b"):
        username = f"test_{label}_{secrets.token_hex(4)}"
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, is_test) VALUES (?, ?, 1)",
            (username, password_hash),
        )
        names.append(username)
        for content in secrets.SystemRandom().sample(samples, 2):
            db.execute("INSERT INTO comments (user_id, content) VALUES (?, ?)", (cursor.lastrowid, content))
    db.commit()
    session["test_credentials"] = {"names": names, "password": password}
    return redirect(url_for("admin"))


@app.post("/admin/test-data/delete")
def delete_test_data():
    require_admin()
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM users WHERE is_test = 1").fetchone()[0]
    db.execute("DELETE FROM reports WHERE reporter_id IN (SELECT id FROM users WHERE is_test = 1)")
    db.execute("DELETE FROM comments WHERE user_id IN (SELECT id FROM users WHERE is_test = 1)")
    db.execute("DELETE FROM users WHERE is_test = 1")
    db.commit()
    session.pop("test_credentials", None)
    session["test_notice"] = f"연습 계정 {count}개와 그 계정의 글을 삭제했습니다. 다른 계정과 글은 남아 있습니다."
    return redirect(url_for("admin"))


@app.post("/admin/users/<int:user_id>/block")
def block_user(user_id):
    require_admin()
    db = get_db()
    user = db.execute("SELECT is_admin, is_blocked FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404, description="사용자를 찾을 수 없습니다.")
    if user["is_admin"]:
        abort(403, description="관리자 계정은 여기서 차단할 수 없습니다.")
    db.execute("UPDATE users SET is_blocked = ? WHERE id = ?", (1 - user["is_blocked"], user_id))
    db.commit()
    return redirect(url_for("admin"))


@app.post("/admin/comments/<int:comment_id>/delete")
def admin_delete_comment(comment_id):
    require_admin()
    db = get_db()
    db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    db.commit()
    return redirect(url_for("admin"))


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(429)
def request_error(error):
    return render_template("error.html", message=error.description), error.code
