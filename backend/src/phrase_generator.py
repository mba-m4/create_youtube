"""
phrase_generator.py
--------------------
Claude API を使ってテーマから英語フレーズ+日本語訳を自動生成するモジュール。

使い方(モジュールとしてimportする場合):
    from phrase_generator import generate_phrases, save_phrases_to_csv

    phrases = generate_phrases("レストランでの会話", count=100)
    save_phrases_to_csv(phrases, "data/generated/restaurant.csv")

コマンドラインから直接実行する場合:
    python3 phrase_generator.py "テーマ" [生成数(デフォルト100)] [出力先CSVパス(省略時は自動生成)]

APIキーは backend/.env に ANTHROPIC_API_KEY として設定しておくこと(.env.example参照)。
モデルは環境変数 PHRASE_GEN_MODEL で上書き可能(未設定時は DEFAULT_MODEL を使用)。
優先順位: 関数引数 > 環境変数 > デフォルト値(CLAUDE.md参照)。
"""

import csv
import datetime
import json
import os
import sys

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5"
OUTPUT_DIR = "data/generated"

PHRASE_SCHEMA = {
    "type": "object",
    "properties": {
        "phrases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "english": {"type": "string", "description": "英語フレーズ"},
                    "japanese": {
                        "type": "string",
                        "description": "自然な日本語訳(補足があれば括弧書きで添える)",
                    },
                },
                "required": ["english", "japanese"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["phrases"],
    "additionalProperties": False,
}


def resolve_model(model=None):
    """使用するモデル名を決定する。優先順位: 引数 > 環境変数 PHRASE_GEN_MODEL > デフォルト"""
    return model or os.environ.get("PHRASE_GEN_MODEL") or DEFAULT_MODEL


def generate_phrases(theme, count=100, model=None):
    """
    テーマに沿った英語フレーズ+日本語訳をClaude APIで生成する。

    Args:
        theme: フレーズのテーマ(例: "レストランでの会話", "ビジネスメール")
        count: 生成するフレーズ数
        model: 使用するClaudeモデル(省略時は resolve_model() のルールに従う)

    Returns:
        [(英語フレーズ, 日本語訳), ...] のリスト
    """
    client = Anthropic()
    resolved_model = resolve_model(model)
    max_tokens = min(max(count * 100 + 1000, 4096), 64000)

    prompt = (
        f"「{theme}」というテーマに沿った、日常英会話でよく使われる実用的な英語フレーズを"
        f"{count}個作成してください。\n"
        "各フレーズには自然な日本語訳を付けてください。"
        "同じ意味・似た表現のフレーズが重複しないようにしてください。"
    )

    request = dict(
        model=resolved_model,
        max_tokens=max_tokens,
        output_config={"format": {"type": "json_schema", "schema": PHRASE_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )

    if max_tokens > 16000:
        with client.messages.stream(**request) as stream:
            response = stream.get_final_message()
    else:
        response = client.messages.create(**request)

    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)

    return [(p["english"], p["japanese"]) for p in data["phrases"]]


def save_phrases_to_csv(phrases, csv_path):
    """
    フレーズのリストをCSVに保存する(1列目=英語, 2列目=日本語, ヘッダーあり)。
    保存先ディレクトリが存在しない場合は作成する。

    Args:
        phrases: [(英語フレーズ, 日本語訳), ...] のリスト
        csv_path: 保存先パス
    """
    out_dir = os.path.dirname(csv_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["english", "japanese"])
        writer.writerows(phrases)

    print(f"saved: {csv_path} ({len(phrases)} phrases)")


def default_output_path(theme):
    """テーマと今日の日付から data/generated/ 配下の出力パスを組み立てる"""
    date_str = datetime.date.today().strftime("%Y%m%d")
    return os.path.join(OUTPUT_DIR, f"{theme}_{date_str}.csv")


def main():
    if len(sys.argv) < 2:
        print("使い方: python3 phrase_generator.py <テーマ> [生成数] [出力先CSVパス]")
        sys.exit(1)

    theme = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    output_path = sys.argv[3] if len(sys.argv) > 3 else default_output_path(theme)

    print(f"テーマ「{theme}」で{count}個のフレーズを生成中... (model={resolve_model()})")
    phrases = generate_phrases(theme, count=count)
    save_phrases_to_csv(phrases, output_path)


if __name__ == "__main__":
    main()
