"""
video_pipeline.py
------------------
フレーズ集(英語+日本語)から、音声・画像・動画まで一括生成するパイプライン。

流れ:
  1. フレーズごとに音声(TTS)をsequence通りに生成・結合  -> audio/phrase_XX.mp3
  2. フレーズごとに画像を生成                            -> images/phrase_XX.png
  3. 画像+音声を1クリップに結合                          -> clips/phrase_XX.mp4
  4. 全クリップを連結して1本の動画にする                  -> final_video.mp4

TTSについて:
  ElevenLabs API(`tts_elevenlabs.py`)を使用。
  APIキーは .env の ELEVENLABS_API_KEY を使う(.env.example参照)。

読み上げ順(sequence)について:
  run_pipeline() の sequence 引数で読み上げる言語の順番を指定できる
  (例: ["en", "ja"] や ["en", "en", "ja"])。省略時は ["en"](英語のみ)。
  同じ言語が複数回出てきても、その言語の音声はAPIで1回しか生成しない
  (生成した音声ファイルを使い回して結合する)。

使い方:
  python3 video_pipeline.py phrases.csv
  python3 video_pipeline.py phrases.csv en,ja   # 読み上げ順を指定(カンマ区切り)
  python3 video_pipeline.py                     # 引数なしならサンプルフレーズを使用
"""

import os
import sys
import subprocess
import shutil

from dotenv import load_dotenv

from phrase_image_generator import generate_phrase_image, load_phrases_from_csv
from tts_elevenlabs import generate_audio

load_dotenv()

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
SILENCE_BETWEEN_SEC = 0.5  # sequence内の音声同士の間に挟む無音の秒数
DEFAULT_SEQUENCE = ["en"]


def setup_dirs():
    for d in [AUDIO_DIR, IMAGE_DIR, CLIP_DIR]:
        os.makedirs(d, exist_ok=True)


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


def make_silence(out_path, duration_sec):
    """無音のmp3ファイルを作る(sequence内の音声同士をつなぐ間として使う)"""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(duration_sec),
            "-c:a", "libmp3lame",
            out_path,
        ],
        check=True,
        capture_output=True,
    )


def concat_audio(audio_paths, out_path):
    """複数の音声ファイルを1本に連結する(concat_clipsの音声版)"""
    filelist_path = os.path.join(WORK_DIR, "audio_filelist.txt")
    with open(filelist_path, "w") as f:
        for p in audio_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    # 入力ファイル(ElevenLabs出力 + ffmpeg生成の無音)でビットレート等が
    # 揃っていない可能性があるため、-c copy ではなく再エンコードして繋ぐ
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", filelist_path,
            "-c:a", "libmp3lame", "-b:a", "128k",
            out_path,
        ],
        check=True,
        capture_output=True,
    )


def build_sequence_audio(en, jp, sequence, audio_dir, tag):
    """
    sequence(例: ["en", "en", "ja"])の順に読み上げ音声を結合した1本のmp3を作る。
    同じ言語は音声APIで1回しか生成せず(重複排除)、結合時に使い回す。
    """
    texts = {"en": en, "ja": jp}
    lang_paths = {}
    for lang in set(sequence):
        lang_path = os.path.join(audio_dir, f"phrase_{tag}_{lang}.mp3")
        generate_audio(texts[lang], lang_path, language_code=lang)
        lang_paths[lang] = lang_path

    if len(sequence) == 1:
        return lang_paths[sequence[0]]

    silence_path = os.path.join(audio_dir, "_silence.mp3")
    if not os.path.exists(silence_path):
        make_silence(silence_path, SILENCE_BETWEEN_SEC)

    parts = []
    for i, lang in enumerate(sequence):
        if i > 0:
            parts.append(silence_path)
        parts.append(lang_paths[lang])

    final_path = os.path.join(audio_dir, f"phrase_{tag}.mp3")
    concat_audio(parts, final_path)
    return final_path


def run_pipeline(phrases, sequence=None, on_progress=None):
    """
    sequence: 読み上げる言語の順番(例: ["en", "ja"])。省略時は ["en"](英語のみ)。
    on_progress: 各フレーズのクリップ完成時に on_progress(i, total, en) の形で呼ばれる(省略可)。
    """
    sequence = sequence or DEFAULT_SEQUENCE
    setup_dirs()
    clip_paths = []
    total = len(phrases)

    for i, (en, jp) in enumerate(phrases, start=1):
        tag = f"{i:02d}"
        print(f"[{tag}] processing: {en}")

        # 1. 音声生成(sequence通りに結合)
        audio_path = build_sequence_audio(en, jp, sequence, AUDIO_DIR, tag)

        # 2. 画像生成
        img = generate_phrase_image(en, jp)
        image_path = os.path.join(IMAGE_DIR, f"phrase_{tag}.png")
        img.save(image_path)

        # 3. クリップ結合
        clip_path = os.path.join(CLIP_DIR, f"phrase_{tag}.mp4")
        make_clip(image_path, audio_path, clip_path)
        clip_paths.append(clip_path)

        print(f"[{tag}] clip done: {clip_path}")
        if on_progress:
            on_progress(i, total, en)

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

    sequence = sys.argv[2].split(",") if len(sys.argv) > 2 else None

    run_pipeline(phrases, sequence=sequence)


if __name__ == "__main__":
    main()
