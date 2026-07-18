"""
tts_elevenlabs.py
-------------------
ElevenLabs API を使ったTTS(テキスト読み上げ)モジュール。
sample/tts.py の実装を、既存モジュールと同じ関数ベースのスタイルに合わせて移植したもの。

使い方(モジュールとしてimportする場合):
    from tts_elevenlabs import generate_audio

    generate_audio("Break a leg!", "output_en.mp3", language_code="en")
    generate_audio("頑張ってね!", "output_ja.mp3", language_code="ja")

コマンドラインから直接実行する場合:
    python3 tts_elevenlabs.py "読み上げたいテキスト" [出力先パス] [言語コード(en/ja、デフォルトen)]

APIキーは backend/.env に ELEVENLABS_API_KEY として設定しておくこと(.env.example参照)。
まだ video_pipeline.py には接続していない(呼び出し側で必要に応じて使う想定)。
"""

import os
import sys

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_MODEL_ID = "eleven_v3"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


def generate_audio(
    text,
    out_path,
    language_code="en",
    voice_id=None,
    model_id=None,
    output_format=None,
):
    """
    ElevenLabs APIでTTS音声を生成し、out_pathに保存する。

    Args:
        text: 読み上げるテキスト
        out_path: 保存先パス
        language_code: 言語コード("en" / "ja" など)
        voice_id: 声のID(省略時はDEFAULT_VOICE_ID)
        model_id: 使用するモデル(省略時はDEFAULT_MODEL_ID)
        output_format: 出力フォーマット(省略時はDEFAULT_OUTPUT_FORMAT)
    """
    client = ElevenLabs(api_key=os.environ.get("ELEVENLABS_API_KEY"))

    audio_stream = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id or DEFAULT_VOICE_ID,
        model_id=model_id or DEFAULT_MODEL_ID,
        language_code=language_code,
        output_format=output_format or DEFAULT_OUTPUT_FORMAT,
    )

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "wb") as f:
        for chunk in audio_stream:
            f.write(chunk)


def main():
    if len(sys.argv) < 2:
        print("使い方: python3 tts_elevenlabs.py <テキスト> [出力先パス] [言語コード]")
        sys.exit(1)

    text = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "output.mp3"
    language_code = sys.argv[3] if len(sys.argv) > 3 else "en"

    generate_audio(text, out_path, language_code=language_code)
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
