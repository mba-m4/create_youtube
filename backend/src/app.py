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
    POST /api/generate   — 動画生成開始
    GET  /api/status/{id} — 進捗確認
    GET  /api/video/{id} — 完成動画ダウンロード
"""

import os
import sys
import glob
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

from phrase_image_generator import load_phrases_from_csv
from video_pipeline import run_pipeline

WORK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline_output")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
FINAL_VIDEO = os.path.join(WORK_DIR, "final_video.mp4")
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

app = FastAPI(title="Video Generator")

# ジョブ管理(単一ジョブのみサポート)
JOBS = {}
JOB_LOCK = threading.Lock()


def get_job_status(job_id: str):
    """ジョブの状態を取得"""
    return JOBS.get(job_id, {})


def set_job_status(job_id: str, **kwargs):
    """ジョブの状態を更新"""
    with JOB_LOCK:
        if job_id not in JOBS:
            JOBS[job_id] = {}
        JOBS[job_id].update(kwargs)


def on_progress_callback(job_id: str):
    """run_pipeline の on_progress コールバック工場"""
    def callback(current, total, phrase):
        set_job_status(job_id, current=current, total=total, current_phrase=phrase)
    return callback


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

    filepath = os.path.join(upload_dir, file.filename or "uploaded.csv")
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"filename": file.filename, "path": filepath}


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


@app.post("/api/generate")
async def generate_video(request: dict):
    """動画生成を開始(バックグラウンドで実行)"""
    csv_path = request.get("csv_path")
    if not csv_path or not os.path.exists(csv_path):
        raise HTTPException(status_code=400, detail="CSV file path required and must exist")

    # 既に実行中のジョブがあるかチェック
    with JOB_LOCK:
        for job in JOBS.values():
            if job.get("status") == "running":
                raise HTTPException(status_code=409, detail="Another job is already running")

    job_id = uuid.uuid4().hex[:8]
    set_job_status(job_id, status="running", current=0, total=0, current_phrase="", error=None)

    def run_job():
        try:
            phrases = load_phrases_from_csv(csv_path, has_header=True)
            set_job_status(job_id, total=len(phrases))

            run_pipeline(phrases, on_progress=on_progress_callback(job_id))

            set_job_status(job_id, status="completed", current=len(phrases))
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            set_job_status(job_id, status="error", error=error_msg)

    thread = threading.Thread(target=run_job, daemon=True)
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
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
