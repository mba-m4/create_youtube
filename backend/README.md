# English Phrase Video Pipeline

英語フレーズ+日本語訳の動画を自動生成するパイプライン。
「フレーズ集 → 音声(TTS) → 画像 → 動画」までを自動化する。

## 現状できていること

- `phrase_image_generator.py`
  - フレーズ(英語+日本語)を1枚の画像にする
  - CSVからフレーズを読み込む機能あり
- `video_pipeline.py`
  - フレーズを1つずつ処理し、音声生成→画像生成→動画クリップ化→全体連結まで自動で行う
  - TTSは現状 `espeak-ng`(オフライン・棒読み)でプロトタイプ済み。ElevenLabs等に差し替え予定
- `phrase_generator.py`
  - Claude APIでテーマからフレーズ(英語+日本語)を自動生成し、CSVに保存する
  - まだAPI課金未設定のため実際の生成テストは未実施(構文・CSV保存ロジックのみ確認済み)
- `phrase_db.py`
  - フレーズをSQLiteで永続管理(未使用フレーズの取得・使用済みマーク・テーマ別在庫確認)
  - CSVからのインポート機能あり。動作確認済み

3フレーズのサンプルで、実際に音声付きmp4が生成できることを確認済み。

## セットアップ(必要な依存関係)

### システムコマンド
```bash
# ffmpeg (動画結合)
sudo apt-get install ffmpeg

# espeak-ng (プロトタイプ用オフラインTTS。本番はAPIに差し替え予定)
sudo apt-get install espeak-ng

# 日本語表示用フォント(Noto Sans CJK)
sudo apt-get install fonts-noto-cjk
```

### Pythonパッケージ
```bash
pip install pillow
```

### フォントパス(環境によって変わるので要確認)
`phrase_image_generator.py` 内で下記を指定している。環境が変わったらパスを見直すこと。
```python
EN_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
JP_FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
```

## 設計方針(重要)

- **フレーズは1つずつ処理する。まとめて音声だけ100個作る、はやらない。**
  理由: 音声の長さがそのまま画像の表示時間になるため、1フレーズ=1音声ファイル=1クリップの対応関係を保つ方が事故が少ない。
- **TTSはAPIに簡単に差し替えられる設計にしてある。**
  `video_pipeline.py` の `generate_audio()` 関数の中身だけ変更すればいい。他の処理(画像生成・ffmpeg結合)には影響しない。
- **司令塔はローカルのPythonスクリプト。** Claudeは開発時のコード作成/修正の補助であって、実行時に関与するわけではない(ただしフレーズ自動生成にClaude APIを組み込む場合は例外)。

## 今後のロードマップ(優先順位順)

1. **フレーズ自動生成**(実装済み・実APIでの動作確認は未実施)
   - `phrase_generator.py` で実装済み。Claude APIに「テーマ→フレーズN個(英語+日本語)」を投げて生成し、CSVに保存する
   - API課金が有効になったら `python3 src/phrase_generator.py "テーマ" [件数]` で実地確認する

2. **フレーズ管理をDB化**(実装済み・`video_pipeline.py`との自動連携は未実装)
   - `phrase_db.py` で実装済み。SQLite(`data/phrases.db`、`.gitignore`済み)。
   - スキーマ: `phrases(id, english, japanese, theme, created_at, used_at, times_used)`
   - 実装済みの運用:
     - `get_unused_phrases(n)` — 未使用のフレーズをN個取得
     - `get_review_phrases(n, days_ago)` — N日以上前に使ったフレーズを復習用に取得
     - `mark_used(ids)` — 使用済みにマーク(`used_at`更新、`times_used`+1)
     - `stats_by_theme()` / `python3 src/phrase_db.py stats` — テーマ別在庫数の確認
     - `import_csv(path, theme)` / `python3 src/phrase_db.py import <csv> [theme]` — 既存CSVの取り込み
   - 未実装: `phrase_generator.py`からDBへの直接INSERT、`video_pipeline.py`側での
     「DBから取得→動画化→used_at更新」の自動連携(現状は呼び出し側で手動で繋ぐ)

3. **TTSを高品質化**
   - `generate_audio()` を ElevenLabs API 等に差し替える
   - 英語だけでなく日本語音声も追加する場合、読み上げ順(英語→間→日本語)と、その合計時間に合わせた画像表示時間の計算が必要

4. **cronで定期実行**
   - 1〜3が固まってから着手
   - 例: 毎日決まった時間にテーマを1つ選んで動画を自動生成

5. **Slack連携 / YouTube自動アップロード**
   - 運用が固まってからの最終フェーズ
   - Slack Bot(`slack_bolt`)でスマホから起動 → 完成後の動画をSlackに返す、などを想定
   - YouTube Data APIでアップロードまで自動化可能

## ファイル一覧

- `phrase_image_generator.py` — フレーズ画像生成モジュール
- `video_pipeline.py` — 音声・画像・動画結合の一括パイプライン
- `phrase_generator.py` — Claude APIによるフレーズ自動生成モジュール
- `phrase_db.py` — フレーズのSQLite管理モジュール
- `sample_phrases.csv` — CSVフォーマットのサンプル(1列目=英語, 2列目=日本語, ヘッダー行あり)