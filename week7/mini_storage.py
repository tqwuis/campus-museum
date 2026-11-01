"""두 번 실행하면 리스트는 다시 시작하고 JSON·SQLite 파일은 남습니다."""

import json
import sqlite3
from pathlib import Path

folder = Path(__file__).resolve().parent / "instance"
folder.mkdir(parents=True, exist_ok=True)
text = "공강에는 도서관!"

# ① 리스트: 실행할 때마다 새로 만듭니다.
memory_comments = []
memory_comments.append(text)

# ② JSON: 이전 내용을 읽고, 새 글을 더해 다시 씁니다.
json_path = folder / "mini_comments.json"
if json_path.exists():
    file_comments = json.loads(json_path.read_text(encoding="utf-8"))
else:
    file_comments = []
file_comments.append(text)
json_path.write_text(
    json.dumps(file_comments, ensure_ascii=False, indent=2), encoding="utf-8"
)

# ③ SQLite: 표에 한 행을 추가하고 전체 행 수를 셉니다.
db_path = folder / "mini_comments.db"
with sqlite3.connect(db_path) as db:
    db.execute(
        "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, content TEXT NOT NULL)"
    )
    db.execute("INSERT INTO notes (content) VALUES (?)", (text,))
    db.commit()
    db_count = db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

print(f"Python 리스트: {len(memory_comments)}개")
print(f"JSON 파일: {len(file_comments)}개")
print(f"SQLite DB: {db_count}개")
