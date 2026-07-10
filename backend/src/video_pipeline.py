"""
video_pipeline.py
------------------
フレーズ集(英語+日本語)から、音声・画像・動画まで一括生成するパイプライン。

流れ:
  1. フレーズごとに英語音声(TTS)を生成          -> audio/phrase_XX.wav
  2. フレーズごとに画像を生成                    -> images/phrase_XX.png
  3. 画像+音声を1クリップに結合                  -> clips/phrase_XX.mp4
  4. 全クリップを連結して1本の動画にする          -> final_video.mp4

TTSについて:
  Higgsfield の text2speech_v2 モデル(REST API経由、higgsfield-client SDK)を使用。
  声質は環境変数 HIGGSFIELD_VOICE_ID で切り替え可能(利用可能な声は `higgsfield voices list` で確認)。
  認証情報は .env の HF_KEY (または HF_API_KEY + HF_API_SECRET) を使う(.env.example参照)。

使い方:
  python3 video_pipeline.py phrases.csv
  python3 video_pipeline.py            # 引数なしならサンプルフレーズを使用
"""

import os
import sys
import subprocess
import shutil

import higgsfield_client
import requests
from dotenv import load_dotenv

from phrase_image_generator import generate_phrase_image, load_phrases_from_csv

load_dotenv()

# Tallulah(プリセット音声)をデフォルトに使用。優先順位: 引数 > 環境変数 > デフォルト値
DEFAULT_VOICE_ID = "f32c8f51-449e-4ddf-bdf7-1527e11df917"
DEFAULT_TTS_VARIANT = "elevenlabs"

WORK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline_output")
AUDIO_DIR = os.path.join(WORK_DIR, "audio")
IMAGE_DIR = os.path.join(WORK_DIR, "images")
CLIP_DIR = os.path.join(WORK_DIR, "clips")
FINAL_VIDEO = os.path.join(WORK_DIR, "final_video.mp4")

SAMPLE_PHRASES = [
    ("Break a leg!", "頑張ってね!(舞台などの本番前の決まり文句)"),
    ("It's a piece of cake.", "それは朝飯前だよ。"),
    ("I'm on the fence about it.", "それについてはまだ迷ってる。"),
]

SILENCE_AFTER_SEC = 1.0  # 音声の後に画像だけ表示しておく余白の秒数


def setup_dirs():
    for d in [AUDIO_DIR, IMAGE_DIR, CLIP_DIR]:
        os.makedirs(d, exist_ok=True)


def generate_audio(text, out_path, voice_id=None, variant=None):
    """
    Higgsfield(text2speech_v2)でTTS音声を生成し、out_pathに保存する。

    Args:
        text: 読み上げるテキスト
        out_path: 保存先パス
        voice_id: Higgsfieldのプリセット音声ID(省略時は環境変数 HIGGSFIELD_VOICE_ID
                  → DEFAULT_VOICE_ID の順で解決)
        variant: TTSエンジンのバリアント(elevenlabs/minimax/seed_speech/vibe_voice/cozy_voice。
                 省略時は環境変数 HIGGSFIELD_TTS_VARIANT → DEFAULT_TTS_VARIANT の順で解決)
    """
    resolved_voice_id = voice_id or os.environ.get("HIGGSFIELD_VOICE_ID") or DEFAULT_VOICE_ID
    resolved_variant = variant or os.environ.get("HIGGSFIELD_TTS_VARIANT") or DEFAULT_TTS_VARIANT

    result = higgsfield_client.subscribe(
        "text2speech_v2",
        arguments={
            "prompt": text,
            "variant": resolved_variant,
            "voice_type": "preset",
            "voice_id": resolved_voice_id,
        },
    )

    try:
        audio_url = result["audios"][0]["url"]
    except (KeyError, IndexError, TypeError) as e:
        # Higgsfieldの音声生成レスポンスの正確なキー名は未検証(ドキュメントに記載なし)。
        # 実際に課金・実行して確認できたら、ここのキー名を確定させること。
        raise RuntimeError(
            f"Higgsfieldのレスポンス形式が想定(result['audios'][0]['url'])と異なります。"
            f"実際のresult: {result}"
        ) from e

    response = requests.get(audio_url, timeout=60)
    response.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(response.content)


def get_audio_duration(path):
    """ffprobeで音声の長さ(秒)を取得する"""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def make_clip(image_path, audio_path, out_path, extra_seconds=SILENCE_AFTER_SEC):
    """画像1枚+音声1つを、音声の長さ+余白ぶんの動画クリップにする"""
    duration = get_audio_duration(audio_path) + extra_seconds
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1280:720",
            "-shortest",
            out_path,
        ],
        check=True,
        capture_output=True,
    )


def concat_clips(clip_paths, out_path):
    """複数の動画クリップを1本に連結する"""
    filelist_path = os.path.join(WORK_DIR, "filelist.txt")
    with open(filelist_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", filelist_path,
            "-c", "copy",
            out_path,
        ],
        check=True,
        capture_output=True,
    )


def run_pipeline(phrases):
    setup_dirs()
    clip_paths = []

    for i, (en, jp) in enumerate(phrases, start=1):
        tag = f"{i:02d}"
        print(f"[{tag}] processing: {en}")

        # 1. 音声生成
        audio_path = os.path.join(AUDIO_DIR, f"phrase_{tag}.wav")
        generate_audio(en, audio_path)

        # 2. 画像生成
        img = generate_phrase_image(en, jp)
        image_path = os.path.join(IMAGE_DIR, f"phrase_{tag}.png")
        img.save(image_path)

        # 3. クリップ結合
        clip_path = os.path.join(CLIP_DIR, f"phrase_{tag}.mp4")
        make_clip(image_path, audio_path, clip_path)
        clip_paths.append(clip_path)

        print(f"[{tag}] clip done: {clip_path}")

    # 4. 全クリップ連結
    concat_clips(clip_paths, FINAL_VIDEO)
    print(f"\n完成: {FINAL_VIDEO}")
    return FINAL_VIDEO


def main():
    if len(sys.argv) > 1:
        phrases = load_phrases_from_csv(sys.argv[1], has_header=True)
        print(f"loaded {len(phrases)} phrases from {sys.argv[1]}")
    else:
        phrases = SAMPLE_PHRASES
        print("using sample phrases")

    run_pipeline(phrases)


if __name__ == "__main__":
    main()
