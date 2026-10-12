from flask import Flask, render_template, request

app = Flask(__name__)


@app.get("/")
def index():
    return '<h1>Flask 실행 성공!</h1><a href="/hello?name=구름">인사 페이지</a>'


@app.get("/hello")
def hello():
    name = request.args.get("name", "방문자").strip()[:30] or "방문자"
    return render_template("hello.html", name=name)
