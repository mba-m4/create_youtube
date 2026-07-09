"""
phrase_image_generator.py
--------------------------
英語フレーズ + 日本語訳の画像を一括生成するモジュール。

使い方(モジュールとしてimportする場合):
    from phrase_image_generator import generate_all, load_phrases_from_csv

    phrases = [
        ("Break a leg!", "頑張ってね!"),
        ("It's a piece of cake.", "それは朝飯前だよ。"),
    ]
    generate_all(phrases, output_dir="output_images")

    # CSVから読み込む場合 (1列目=英語, 2列目=日本語)
    phrases = load_phrases_from_csv("phrases.csv")
    generate_all(phrases, output_dir="output_images")

コマンドラインから直接実行する場合:
    python3 phrase_image_generator.py                 # サンプルフレーズで生成
    python3 phrase_image_generator.py phrases.csv      # CSVを指定して生成
"""

import os
import csv
import sys
from PIL import Image, ImageDraw, ImageFont

# ---- デザイン設定(必要に応じて呼び出し側から上書き可能) ----
WIDTH, HEIGHT = 1280, 720
BG_COLOR_TOP = (25, 30, 45)
BG_COLOR_BOTTOM = (45, 55, 90)
EN_COLOR = (255, 255, 255)
JP_COLOR = (255, 210, 90)

EN_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
JP_FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
EN_FONT_SIZE = 64
JP_FONT_SIZE = 48


def load_fonts(en_size=EN_FONT_SIZE, jp_size=JP_FONT_SIZE):
    """英語フォントと日本語フォントを読み込んで返す"""
    en_font = ImageFont.truetype(EN_FONT_PATH, en_size)
    jp_font = ImageFont.truetype(JP_FONT_PATH, jp_size)
    return en_font, jp_font


def make_gradient_background(
    width=WIDTH, height=HEIGHT, top_color=BG_COLOR_TOP, bottom_color=BG_COLOR_BOTTOM
):
    """縦グラデーションの背景画像を1枚生成する"""
    base = Image.new("RGB", (width, height), top_color)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return base


def draw_centered_text(draw, text, font, y, color, width=WIDTH):
    """指定したy座標に、横方向中央揃えでテキストを描画する"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = (width - text_w) / 2
    draw.text((x, y), text, font=font, fill=color)
    return bbox


def generate_phrase_image(
    en_text,
    jp_text,
    en_font=None,
    jp_font=None,
    width=WIDTH,
    height=HEIGHT,
):
    """1フレーズ分の画像(PIL.Image)を生成して返す"""
    if en_font is None or jp_font is None:
        en_font, jp_font = load_fonts()

    img = make_gradient_background(width, height)
    draw = ImageDraw.Draw(img)

    # 区切り線
    draw.line(
        [(100, height // 2), (width - 100, height // 2)],
        fill=(255, 255, 255, 80),
        width=2,
    )

    draw_centered_text(draw, en_text, en_font, height // 2 - 120, EN_COLOR, width)
    draw_centered_text(draw, jp_text, jp_font, height // 2 + 40, JP_COLOR, width)

    return img


def generate_all(phrases, output_dir="phrase_images", filename_prefix="phrase"):
    """
    フレーズのリストから画像を一括生成し、ファイルに保存する。

    Args:
        phrases: [(英語フレーズ, 日本語訳), ...] のリスト
        output_dir: 保存先ディレクトリ
        filename_prefix: ファイル名の接頭辞 (例: phrase_01.png)

    Returns:
        生成したファイルパスのリスト
    """
    os.makedirs(output_dir, exist_ok=True)
    en_font, jp_font = load_fonts()

    saved_paths = []
    for i, (en, jp) in enumerate(phrases, start=1):
        img = generate_phrase_image(en, jp, en_font, jp_font)
        out_path = os.path.join(output_dir, f"{filename_prefix}_{i:02d}.png")
        img.save(out_path)
        saved_paths.append(out_path)
        print(f"saved: {out_path}")

    return saved_paths


def load_phrases_from_csv(csv_path, has_header=False):
    """
    CSVファイルからフレーズを読み込む。
    1列目=英語フレーズ, 2列目=日本語訳 を想定。

    Args:
        csv_path: CSVファイルのパス
        has_header: 1行目がヘッダーの場合はTrue

    Returns:
        [(英語フレーズ, 日本語訳), ...] のリスト
    """
    phrases = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
        if has_header and rows:
            rows = rows[1:]
        for row in rows:
            if len(row) >= 2 and row[0].strip():
                phrases.append((row[0].strip(), row[1].strip()))
    return phrases


# ---- サンプルフレーズ(直接実行した際のデフォルト) ----
SAMPLE_PHRASES = [
    ("Break a leg!", "頑張ってね!(舞台などの本番前の決まり文句)"),
    ("It's a piece of cake.", "それは朝飯前だよ。"),
    ("I'm on the fence about it.", "それについてはまだ迷ってる。"),
]


def main():
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        phrases = load_phrases_from_csv(csv_path)
        print(f"loaded {len(phrases)} phrases from {csv_path}")
    else:
        phrases = SAMPLE_PHRASES
        print("using sample phrases (CSVを指定する場合は引数にパスを渡してください)")

    generate_all(phrases)


if __name__ == "__main__":
    main()
