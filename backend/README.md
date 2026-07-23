# English Phrase Video Pipeline

英語フレーズ+日本語訳の動画を自動生成するパイプライン。
「フレーズ集 → 音声(TTS) → 画像 → 動画」までを自動化する。

## 現状できていること

- `phrase_image_generator.py`
  - フレーズ(英語+日本語)を1枚の画像にする
  - CSVからフレーズを読み込む機能あり
- `video_pipeline.py`
  - フレーズを1つずつ処理し、音声生成→画像生成→動画クリップ化→全体連結まで自動で行う
  - TTSは `tts_elevenlabs.py`(ElevenLabs API)を使用
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

# 日本語表示用フォント(Noto Sans CJK)
sudo apt-get install fonts-noto-cjk
```

## セットアップ(必要な依存関係)

### システムコマンド

#### Linux (Ubuntu等)
```bash
# ffmpeg (動画結合)
sudo apt-get install ffmpeg

# 日本語表示用フォント(Noto Sans CJK)
sudo apt-get install fonts-noto-cjk
```

#### macOS
```bash
# ffmpeg (Homebrew でインストール)
brew install ffmpeg

# 日本語フォント(オプション。デフォルトは AppleSDGothicNeo を使用)
# より良い日本語表示を望む場合:
brew install --cask font-noto-sans-cjk-jp
```

### Pythonパッケージ
`uv sync`(または`pip install -e .`)で`pyproject.toml`記載の依存関係(pillow, elevenlabs, fastapi等)を導入する。

### ElevenLabs APIキー
`.env`に`ELEVENLABS_API_KEY`を設定する(`.env.example`参照)。

### フォントパス(環境によって変わるので要確認)

`phrase_image_generator.py` は環境変数 `EN_FONT_PATH` / `JP_FONT_PATH` で指定されたパスを優先し、
未設定ならLinux用のデフォルトパスを使用します。

**macOS の場合は `.env` に以下を設定してください:**
```bash
# オプション 1: 自動インストール済みの AppleSDGothicNeo を使用(デフォルト、OK)
JP_FONT_PATH=/System/Library/Fonts/AppleSDGothicNeo.ttc

# オプション 2: 高品質な Noto Sans CJK JP をインストール済みの場合
JP_FONT_PATH=/Library/Fonts/NotoSansCJK-Regular.ttc
```

英語フォント(`EN_FONT_PATH`)は、多くの環境ではデフォルト(`/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`)
が自動で検索されるため、通常は設定不要です。必要に応じて `.env` で上書きしてください。

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

2. **フレーズ管理をDB化**(実装済み・Web UIとの自動連携も実装済み)
   - `phrase_db.py` で実装済み。SQLite(`data/phrases.db`、`.gitignore`済み)。
   - スキーマ: `phrases(id, english, japanese, theme, created_at, used_at, times_used)`
   - 実装済みの運用:
     - `get_unused_phrases(n)` — 未使用のフレーズをN個取得
     - `get_review_phrases(n, days_ago)` — N日以上前に使ったフレーズを復習用に取得
     - `mark_used(ids)` — 使用済みにマーク(`used_at`更新、`times_used`+1)
     - `stats_by_theme()` / `python3 src/phrase_db.py stats` — テーマ別在庫数の確認
     - `import_csv(path, theme)` / `python3 src/phrase_db.py import <csv> [theme]` — 既存CSVの取り込み
   - Web UI (`app.py`) との連携:
     - `POST /api/phrases/generate` — `phrase_generator.py`で生成したフレーズをCSV保存に加えてDBにも直接INSERT
     - `POST /api/generate` (`source: "db"`) — DBから未使用フレーズを取得→動画化→成功時に`mark_used()`まで自動化

3. **Web UIのジョブ管理を永続化・複数ジョブ対応**(実装済み)
   - `job_store.py` で実装済み。ジョブ状態をSQLite(`data/jobs.db`、`.gitignore`済み)に永続化し、サーバー再起動をまたいで保持する
   - 動画生成の同時実行は常に1件までとし、それ以外のリクエストは`queued`として自動的にキューイングされる(完了後に自動で次のジョブが起動する)

4. **TTSを高品質化**(実装済み)
   - `tts_elevenlabs.py` でElevenLabs APIに差し替え済み(`video_pipeline.py`から呼び出し)
   - 英語だけでなく日本語音声も追加する場合、読み上げ順(英語→間→日本語)と、その合計時間に合わせた画像表示時間の計算が必要(未実装)

5. **cronで定期実行**
   - 1〜4が固まってから着手
   - 例: 毎日決まった時間にテーマを1つ選んで動画を自動生成

6. **Slack連携 / YouTube自動アップロード**
   - 運用が固まってからの最終フェーズ
   - Slack Bot(`slack_bolt`)でスマホから起動 → 完成後の動画をSlackに返す、などを想定
   - YouTube Data APIでアップロードまで自動化可能

## ファイル一覧

- `phrase_image_generator.py` — フレーズ画像生成モジュール
- `video_pipeline.py` — 音声・画像・動画結合の一括パイプライン
- `tts_elevenlabs.py` — ElevenLabs APIによるTTS(音声生成)モジュール
- `phrase_generator.py` — Claude APIによるフレーズ自動生成モジュール
- `phrase_db.py` — フレーズのSQLite管理モジュール
- `app.py` — FastAPI による Web UI サーバー
- `sample_phrases.csv` — CSVフォーマットのサンプル(1列目=英語, 2列目=日本語, ヘッダー行あり)

## Web UI での使用

### 起動

```bash
cd backend
uv sync                    # 依存関係をインストール
python3 src/app.py         # または: uv run python3 src/app.py
```

ブラウザで `http://localhost:8000` を開く。

### 操作

1. **(任意)新しいフレーズを生成** — テーマと件数を指定して「Generate」をクリックすると、
   Claude APIでフレーズを自動生成し、CSV保存 + フレーズDB登録まで行う
2. **CSV を選択またはアップロード** — `data/` 配下のCSVファイルをドロップダウンから選択、
   または新しいCSVをアップロード。あるいは「Or Generate From Phrase Bank」でDB内の
   未使用フレーズをテーマ・件数指定して直接動画化することもできる
3. **フレーズをプレビュー** — 選択したCSVの内容を確認
4. **「Generate Video」をクリック** — 動画生成を開始(進捗をリアルタイム表示)。既に別の
   ジョブが実行中の場合は自動的にキューイングされ、完了後に順番に処理される
5. **完成後、ダウンロード** — 動画をプレイヤーで再生またはMP4をダウンロード

動画生成ジョブの状態はサーバー再起動をまたいで保持される(`data/jobs.db`)。