"""
job_store.py
-------------
動画生成ジョブの状態をSQLiteで永続化するモジュール。
サーバー(app.py)再起動をまたいでジョブの状態を保持し、複数ジョブの
キューイング(実行中は1件のみ、それ以外は queued で待機)に対応するための永続化層。

使い方(モジュールとしてimportする場合):
    import job_store

    job_store.init_db()                                   # DB初期化 + 起動時の復旧処理
    phrases = [("Break a leg!", "頑張ってね!")]
    job_store.create_job("ab12cd34", phrases, csv_path=csv_path, status="running")
    job_store.update_job("ab12cd34", current=1, total=3, current_phrase="Break a leg!")
    job = job_store.get_job("ab12cd34")                    # {} if not found
    running = job_store.list_jobs(status="running")
    next_job = job_store.claim_next_queued_job()           # 最古のqueuedジョブをrunningにして返す(なければNone)
    job_store.get_phrases(job)                             # -> [(en, jp), ...] (phrases_jsonをデコード)
    job_store.get_phrase_ids(job)                          # -> [id, ...] または None (phrase_ids_jsonをデコード)
    job_store.get_sequence(job)                            # -> ["en", "ja"] など (sequence_jsonをデコード、未指定なら["en"])

コマンドラインから直接実行する場合:
    python3 job_store.py init     # DB初期化(+ 中断ジョブのerror化)
    python3 job_store.py list     # 現在のジョブ一覧を表示

起動時の復旧について:
    init_db() を呼ぶと、前回プロセスで status="running" のまま残っているジョブを
    status="error"(error="Interrupted by server restart")に遷移させる。
    ffmpeg/TTSの実行状態はプロセス終了とともに失われ再開できないため。
    app.py はインポート時(モジュールロード時)に init_db() を1回呼び出す想定。

フレーズの保存について:
    create_job() 時点で処理対象のフレーズ一覧を phrases_json にスナップショットとして
    保存する(CSV由来・DB由来のどちらでも同じ形)。queued の間にCSVファイルが変更/削除
    されても、ディスパッチャーが実行時に取り出す内容は作成時点のまま安定する。
    DBの未使用フレーズから作成したジョブは phrase_ids_json にフレーズIDも保存し、
    動画化成功後に呼び出し側が phrase_db.mark_used() でDBを更新できるようにする
    (CSV由来のジョブは phrase_ids_json = NULL)。

読み上げ順(sequence)について:
    create_job() 時点で読み上げ順(例: ["en", "ja"])を sequence_json に保存する。
    未指定時は ["en"](英語のみ、従来通り)。video_pipeline.run_pipeline() の
    sequence 引数にそのまま渡す。
"""

import datetime
import json
import os
import sqlite3
import sys

DB_PATH = "data/jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    current INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    current_phrase TEXT,
    error TEXT,
    csv_path TEXT,
    phrases_json TEXT NOT NULL DEFAULT '[]',
    phrase_ids_json TEXT,
    sequence_json TEXT NOT NULL DEFAULT '["en"]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

INTERRUPTED_ERROR_MSG = "Interrupted by server restart"


def get_connection(db_path=DB_PATH):
    """DB接続を返す(保存先ディレクトリがなければ作成)。行はdict風にアクセスできる。"""
    out_dir = os.path.dirname(db_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=DB_PATH):
    """テーブルが無ければ作成し、前回プロセスから残った running ジョブを error にする"""
    conn = get_connection(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    conn.close()
    _recover_interrupted_jobs(db_path)


def _recover_interrupted_jobs(db_path=DB_PATH):
    """status="running" のまま残っているジョブを error に遷移させる(サーバー再起動時の後始末)"""
    conn = get_connection(db_path)
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "UPDATE jobs SET status = ?, error = ?, updated_at = ? WHERE status = ?",
        ("error", INTERRUPTED_ERROR_MSG, now, "running"),
    )
    conn.commit()
    conn.close()


def create_job(job_id, phrases, csv_path=None, phrase_ids=None, sequence=None, status="queued", db_path=DB_PATH):
    """
    新しいジョブ行を作成する。

    phrases: [(english, japanese), ...] — 処理対象フレーズのスナップショット
    csv_path: CSV由来の場合の元ファイルパス(表示用、DB由来ならNone)
    phrase_ids: DB由来の場合のフレーズID一覧(動画化成功後のmark_used用、CSV由来ならNone)
    sequence: 読み上げる言語の順番(例: ["en", "ja"])。省略時は ["en"](英語のみ)。
    """
    conn = get_connection(db_path)
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "INSERT INTO jobs (id, status, current, total, current_phrase, error, csv_path, "
        "phrases_json, phrase_ids_json, sequence_json, created_at, updated_at) "
        "VALUES (?, ?, 0, 0, '', NULL, ?, ?, ?, ?, ?, ?)",
        (
            job_id, status, csv_path,
            json.dumps(phrases),
            json.dumps(phrase_ids) if phrase_ids else None,
            json.dumps(sequence or ["en"]),
            now, now,
        ),
    )
    conn.commit()
    conn.close()


def get_phrases(job):
    """ジョブ行(dict)から処理対象フレーズを [(english, japanese), ...] で取り出す"""
    return [tuple(p) for p in json.loads(job["phrases_json"])]


def get_phrase_ids(job):
    """ジョブ行(dict)からDB由来のフレーズID一覧を取り出す(CSV由来ならNone)"""
    raw = job.get("phrase_ids_json")
    return json.loads(raw) if raw else None


def get_sequence(job):
    """ジョブ行(dict)から読み上げ順を取り出す(例: ["en", "ja"]、未指定なら["en"])"""
    raw = job.get("sequence_json")
    return json.loads(raw) if raw else ["en"]


def update_job(job_id, db_path=DB_PATH, **fields):
    """ジョブの状態を更新する(既存のset_job_statusと同等)。updated_atは自動更新。"""
    if not fields:
        return
    fields["updated_at"] = datetime.datetime.now().isoformat()
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [job_id]
    conn = get_connection(db_path)
    conn.execute(f"UPDATE jobs SET {columns} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_job(job_id, db_path=DB_PATH):
    """ジョブの状態をdictで取得する。存在しなければ{}を返す(既存のget_job_statusと同じ挙動)。"""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}


def list_jobs(status=None, db_path=DB_PATH):
    """ジョブ一覧を作成日時順で取得する。status指定で絞り込み可能。"""
    conn = get_connection(db_path)
    if status:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def claim_next_queued_job(db_path=DB_PATH):
    """
    最も古い status="queued" のジョブを running に遷移させて返す(なければNoneを返す)。
    ディスパッチャーが次に実行するジョブを取り出すために使う。
    """
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
    ).fetchone()
    if not row:
        conn.close()
        return None
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "UPDATE jobs SET status = 'running', updated_at = ? WHERE id = ?",
        (now, row["id"]),
    )
    conn.commit()
    conn.close()
    job = dict(row)
    job["status"] = "running"
    return job


def main():
    if len(sys.argv) < 2:
        print("使い方:")
        print("  python3 job_store.py init")
        print("  python3 job_store.py list")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        init_db()
        print(f"DB initialized: {DB_PATH}")
    elif command == "list":
        init_db()
        rows = list_jobs()
        if not rows:
            print("(ジョブがありません)")
        for row in rows:
            print(f"{row['id']}: {row['status']} ({row['current']}/{row['total']}) csv={row['csv_path']}")
    else:
        print(f"unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
