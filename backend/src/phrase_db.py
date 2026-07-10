"""
phrase_db.py
-------------
フレーズをSQLiteで管理するモジュール。
CSVでの1回きりのバッチ処理から、継続運用(「未使用のフレーズを取得して動画化」
「N日前のフレーズを復習用に再度動画化」)に対応するための永続化層。

使い方(モジュールとしてimportする場合):
    from phrase_db import init_db, insert_phrases, get_unused_phrases, mark_used

    init_db()
    insert_phrases(phrases, theme="レストラン")          # phrases = [(english, japanese), ...]
    todays_phrases = get_unused_phrases(3)               # [{"id":.., "english":.., ...}, ...]
    # ... video_pipeline.run_pipeline() などで動画化 ...
    mark_used([p["id"] for p in todays_phrases])

コマンドラインから直接実行する場合:
    python3 phrase_db.py init                        # DB初期化
    python3 phrase_db.py stats                        # テーマ別の在庫数(未使用/合計)を表示
    python3 phrase_db.py import <csv_path> [theme]    # 既存CSVからフレーズをインポート

重複判定は english の完全一致で行う(同じフレーズの再INSERTはスキップされる)。
"""

import datetime
import os
import sqlite3
import sys

DB_PATH = "data/phrases.db"
DEFAULT_REVIEW_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS phrases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    english TEXT NOT NULL UNIQUE,
    japanese TEXT NOT NULL,
    theme TEXT,
    created_at TEXT NOT NULL,
    used_at TEXT,
    times_used INTEGER NOT NULL DEFAULT 0
);
"""


def get_connection(db_path=DB_PATH):
    """DB接続を返す(保存先ディレクトリがなければ作成)。行はdict風にアクセスできる。"""
    out_dir = os.path.dirname(db_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=DB_PATH):
    """テーブルが無ければ作成する(既にあれば何もしない)"""
    conn = get_connection(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    conn.close()


def insert_phrases(phrases, theme=None, db_path=DB_PATH):
    """
    [(english, japanese), ...] をDBに挿入する。english完全一致の重複はスキップする。

    Returns:
        実際に挿入した件数
    """
    init_db(db_path)
    conn = get_connection(db_path)
    now = datetime.datetime.now().isoformat()
    inserted = 0
    for english, japanese in phrases:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO phrases (english, japanese, theme, created_at) "
            "VALUES (?, ?, ?, ?)",
            (english, japanese, theme, now),
        )
        if cursor.rowcount:
            inserted += 1
    conn.commit()
    conn.close()
    return inserted


def get_unused_phrases(n, theme=None, db_path=DB_PATH):
    """未使用(used_at IS NULL)のフレーズをn件取得する。theme指定で絞り込み可能。"""
    conn = get_connection(db_path)
    if theme:
        rows = conn.execute(
            "SELECT * FROM phrases WHERE used_at IS NULL AND theme = ? "
            "ORDER BY created_at LIMIT ?",
            (theme, n),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM phrases WHERE used_at IS NULL ORDER BY created_at LIMIT ?",
            (n,),
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_review_phrases(n, days_ago=DEFAULT_REVIEW_DAYS, db_path=DB_PATH):
    """days_ago日以上前に使用したフレーズを復習用にn件取得する(使用日が古い順)。"""
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days_ago)).isoformat()
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM phrases WHERE used_at IS NOT NULL AND used_at <= ? "
        "ORDER BY used_at LIMIT ?",
        (cutoff, n),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_used(phrase_ids, db_path=DB_PATH):
    """指定したidのフレーズを使用済みにする(used_atを現在時刻に更新、times_used+1)"""
    conn = get_connection(db_path)
    now = datetime.datetime.now().isoformat()
    conn.executemany(
        "UPDATE phrases SET used_at = ?, times_used = times_used + 1 WHERE id = ?",
        [(now, pid) for pid in phrase_ids],
    )
    conn.commit()
    conn.close()


def stats_by_theme(db_path=DB_PATH):
    """テーマ別の在庫数(未使用件数/合計件数)を返す"""
    conn = get_connection(db_path)
    rows = conn.execute(
        """
        SELECT
            COALESCE(theme, '(未分類)') AS theme,
            COUNT(*) AS total,
            SUM(CASE WHEN used_at IS NULL THEN 1 ELSE 0 END) AS unused
        FROM phrases
        GROUP BY theme
        ORDER BY theme
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def import_csv(csv_path, theme=None, db_path=DB_PATH):
    """既存の load_phrases_from_csv() を使ってCSVのフレーズをDBにインポートする"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phrase_image_generator import load_phrases_from_csv

    phrases = load_phrases_from_csv(csv_path, has_header=True)
    return insert_phrases(phrases, theme=theme, db_path=db_path)


def main():
    if len(sys.argv) < 2:
        print("使い方:")
        print("  python3 phrase_db.py init")
        print("  python3 phrase_db.py stats")
        print("  python3 phrase_db.py import <csv_path> [theme]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        init_db()
        print(f"DB initialized: {DB_PATH}")
    elif command == "stats":
        init_db()
        rows = stats_by_theme()
        if not rows:
            print("(フレーズが登録されていません)")
        for row in rows:
            print(f"{row['theme']}: {row['unused']}/{row['total']} 未使用")
    elif command == "import":
        if len(sys.argv) < 3:
            print("使い方: python3 phrase_db.py import <csv_path> [theme]")
            sys.exit(1)
        csv_path = sys.argv[2]
        theme = sys.argv[3] if len(sys.argv) > 3 else None
        count = import_csv(csv_path, theme=theme)
        print(f"imported: {count} new phrases from {csv_path}")
    else:
        print(f"unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
