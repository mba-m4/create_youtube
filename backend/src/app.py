"""
app.py
------
FastAPI によるローカルWeb UI。CSV をアップロード/選択してフレーズ動画を生成する。

使い方:
    python3 src/app.py
    # ブラウザで http://localhost:8000 を開く

または

    uv run python3 src/app.py

API エンドポイント:
    GET  /               — HTML ページ
    GET  /api/csvs       — CSV ファイル一覧
    POST /api/upload     — CSV ファイルアップロード
    GET  /api/preview    — フレーズプレビュー
    GET  /api/phrases/stats — フレーズDBのテーマ別在庫(未使用/合計)
    POST /api/generate   — 動画生成開始(CSV指定 or DBから未使用フレーズ取得)
    GET  /api/status/{id} — 進捗確認
    GET  /api/video/{id} — 完成動画ダウンロード
"""

import os
import sys
import glob
import time
import uuid
import threading
import traceback
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import job_store
from phrase_image_generator import load_phrases_from_csv
from phrase_db import get_unused_phrases, mark_used, stats_by_theme
from video_pipeline import run_pipeline

WORK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline_output")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
FINAL_VIDEO = os.path.join(WORK_DIR, "final_video.mp4")
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
JOBS_DB_PATH = os.path.join(DATA_DIR, "jobs.db")

DISPATCH_POLL_SEC = 1  # キューの空き状況をチェックする間隔(秒)

app = FastAPI(title="Video Generator")

# ジョブ管理: 状態は job_store.py (SQLite, data/jobs.db) で永続化する。
# 起動時に前回プロセスから running のまま残ったジョブを error にする(再開不可のため)。
job_store.init_db(db_path=JOBS_DB_PATH)

# 重要: run_pipeline() が使う出力先(AUDIO_DIR/IMAGE_DIR/CLIP_DIR/FINAL_VIDEO)は
# video_pipeline.py 側でジョブ非依存の固定パスになっているため、同時に2つ以上の
# ジョブを走らせると ffmpeg/TTS の出力が競合して壊れる。そのため実行中ジョブは
# 常に最大1件までとし、それ以外は queued として待機させる(下記ディスパッチャー参照)。
DISPATCH_LOCK = threading.Lock()


def get_job_status(job_id: str):
    """ジョブの状態を取得"""
    return job_store.get_job(job_id, db_path=JOBS_DB_PATH)


def set_job_status(job_id: str, **kwargs):
    """ジョブの状態を更新"""
    job_store.update_job(job_id, db_path=JOBS_DB_PATH, **kwargs)


def on_progress_callback(job_id: str):
    """run_pipeline の on_progress コールバック工場"""
    def callback(current, total, phrase):
        set_job_status(job_id, current=current, total=total, current_phrase=phrase)
    return callback


def run_job(job_id: str):
    """
    1ジョブ分の動画生成を実行し、完了後にキューの次のジョブを起動する。
    処理対象フレーズは create_job() 時点でスナップショットされた phrases_json から読む
    (CSV由来・DB由来のどちらでも同じ経路)。DB由来ジョブは完了後に mark_used() で使用済みにする。
    """
    job = job_store.get_job(job_id, db_path=JOBS_DB_PATH)
    phrases = job_store.get_phrases(job)
    phrase_ids = job_store.get_phrase_ids(job)

    try:
        set_job_status(job_id, total=len(phrases))

        run_pipeline(phrases, on_progress=on_progress_callback(job_id))

        if phrase_ids:
            mark_used(phrase_ids)

        set_job_status(job_id, status="completed", current=len(phrases))
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        set_job_status(job_id, status="error", error=error_msg)
    finally:
        dispatch_next_job()


def dispatch_next_job():
    """
    実行中のジョブがなければ、最も古い queued ジョブを1件だけ取り出して起動する。
    (同時実行は常に1件までにする、というルールの実体化)
    """
    with DISPATCH_LOCK:
        if job_store.list_jobs(status="running", db_path=JOBS_DB_PATH):
            return
        next_job = job_store.claim_next_queued_job(db_path=JOBS_DB_PATH)
        if not next_job:
            return
    thread = threading.Thread(target=run_job, args=(next_job["id"],), daemon=True)
    thread.start()


def dispatcher_loop():
    """実行中ジョブが終わったタイミングを取りこぼさないための保険としてのポーリングループ"""
    while True:
        time.sleep(DISPATCH_POLL_SEC)
        dispatch_next_job()


threading.Thread(target=dispatcher_loop, daemon=True).start()


@app.get("/")
async def index():
    """HTML ページを返す"""
    try:
        with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>index.html not found</h1>", status_code=404)


@app.get("/api/csvs")
async def list_csvs():
    """data/ 以下の CSV ファイル一覧を返す"""
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    csv_files += glob.glob(os.path.join(DATA_DIR, "uploads", "*.csv"))

    result = []
    for path in csv_files:
        result.append({
            "path": path,
            "filename": os.path.basename(path),
        })
    return result


@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...)):
    """CSV ファイルをアップロード"""
    upload_dir = os.path.join(DATA_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    filename = os.path.basename(file.filename or "")
    if not filename or filename in (".", ".."):
        filename = "uploaded.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are allowed")

    filepath = os.path.join(upload_dir, filename)
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"filename": filename, "path": filepath}


@app.get("/api/preview")
async def preview_csv(path: str):
    """CSV ファイルからフレーズを読み込んでプレビュー"""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="CSV file not found")

    try:
        phrases = load_phrases_from_csv(path, has_header=True)
        return {
            "phrases": [{"english": en, "japanese": jp} for en, jp in phrases],
            "count": len(phrases),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading CSV: {str(e)}")


@app.get("/api/phrases/stats")
async def phrase_stats():
    """フレーズDBのテーマ別在庫(未使用件数/合計件数)を返す"""
    return stats_by_theme()


@app.post("/api/generate")
async def generate_video(request: dict):
    """
    動画生成ジョブを作成する。

    リクエストボディ:
      - {"csv_path": "..."}                          — CSVファイルを指定(従来通り)
      - {"source": "db", "theme": "...", "count": N}  — DBから未使用フレーズをN件取得
        (theme省略時は全テーマ横断で取得。動画化成功時にDB側で使用済みにマークする)

    既に実行中のジョブが無ければ即座に開始し、あれば queued として登録して
    実行中ジョブの完了後にディスパッチャーが自動的に起動する。
    """
    source = request.get("source", "csv")
    csv_path = None
    phrase_ids = None

    if source == "db":
        count = request.get("count")
        if not isinstance(count, int) or count <= 0:
            raise HTTPException(status_code=400, detail="count is required and must be a positive integer for source=db")
        theme = request.get("theme") or None

        db_phrases = get_unused_phrases(count, theme=theme)
        if not db_phrases:
            raise HTTPException(status_code=400, detail="No unused phrases available in the DB for the given theme")

        phrases = [(p["english"], p["japanese"]) for p in db_phrases]
        phrase_ids = [p["id"] for p in db_phrases]
    else:
        csv_path = request.get("csv_path")
        if not csv_path or not os.path.exists(csv_path):
            raise HTTPException(status_code=400, detail="CSV file path required and must exist")
        phrases = load_phrases_from_csv(csv_path, has_header=True)

    job_id = uuid.uuid4().hex[:8]

    with DISPATCH_LOCK:
        is_running = bool(job_store.list_jobs(status="running", db_path=JOBS_DB_PATH))
        status = "queued" if is_running else "running"
        job_store.create_job(
            job_id, phrases, csv_path=csv_path, phrase_ids=phrase_ids,
            status=status, db_path=JOBS_DB_PATH,
        )

    if status == "running":
        thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
        thread.start()

    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """ジョブの進捗を取得"""
    job = get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/video/{job_id}")
async def download_video(job_id: str):
    """完成した動画をダウンロード"""
    job = get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Video not ready yet")

    if not os.path.exists(FINAL_VIDEO):
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        path=FINAL_VIDEO,
        media_type="video/mp4",
        filename="output.mp4"
    )


def main():
    """開発用: uvicorn で起動"""
    print("Starting video generator Web UI...")
    print("Open http://localhost:8000 in your browser")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
