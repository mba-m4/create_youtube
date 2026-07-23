# 使い方ガイド(日本語)

English Phrase Video Pipeline — 英語フレーズ+日本語訳から、音声・画像入りの動画を自動生成するツール。

このドキュメントは「動かし方」だけをまとめたものです。設計方針や開発ルールは `README.md` / `CLAUDE.md` を、
処理の内部フローは `docs/pipeline_flow.md` を参照してください。

## これは何ができるツールか

- CSVまたはフレーズDBに登録した「英語フレーズ+日本語訳」を1件ずつ、
  - 音声(TTS)
  - 画像(フレーズ+訳を1枚にレイアウト)
  - 動画クリップ(画像+音声)

  にして、最後に1本のMP4に連結します。
- Claude APIでテーマから英語フレーズを自動生成することもできます。
- ブラウザから操作できるWeb UIがあり、CLIを使わずに一通りの操作が可能です。

**現状のスコープ**: ローカルで動画を生成するところまでが対象です。cronでの定期実行やSlack通知、
YouTubeへの自動アップロードはまだ実装されていません(今後のロードマップ、`README.md` 参照)。

## 必要なもの(セットアップ)

### 1. システムコマンド

- **ffmpeg**(動画結合に必須)
  ```bash
  # macOS
  brew install ffmpeg
  # Linux (Ubuntu等)
  sudo apt-get install ffmpeg
  ```
- **日本語フォント**(画像に日本語訳を描画するため)
  - macOSはデフォルトで `AppleSDGothicNeo` を使うため追加インストール不要(そのままでOK)。
    より綺麗な表示を望む場合は `brew install --cask font-noto-sans-cjk-jp`
  - Linuxは `sudo apt-get install fonts-noto-cjk` が必要

### 2. Pythonパッケージ

```bash
cd backend
uv sync
```

### 3. APIキー(`.env` を作成)

`backend/.env.example` を `backend/.env` にコピーし、値を埋めます。

| 変数名 | 用途 | 必須? |
|---|---|---|
| `ELEVENLABS_API_KEY` | 音声生成(TTS) | 動画生成に必須 |
| `ANTHROPIC_API_KEY` | Claude APIでのフレーズ自動生成 | フレーズ自動生成機能を使う場合のみ必須 |
| `PHRASE_GEN_MODEL` | フレーズ生成に使うモデル名の上書き | 任意(未設定なら `claude-sonnet-5`) |
| `EN_FONT_PATH` / `JP_FONT_PATH` | 画像描画に使うフォントの明示指定 | 任意(未設定ならOS標準のパスを自動使用) |

**`.env` は絶対にコミットしないでください**(`.gitignore` 済み)。

## 使い方: Web UI(おすすめ)

### 起動

```bash
cd backend
python3 src/app.py
# または: uv run python3 src/app.py
```

ブラウザで `http://localhost:8000` を開きます。

### 画面の操作

1. **(任意)新しいフレーズを生成** — テーマ(例: "レストランでの会話")と件数を入力して
   「Generate」をクリックすると、Claude APIでフレーズを自動生成し、CSV保存とフレーズDBへの
   登録が同時に行われます。
2. **CSVを選択/アップロード、またはフレーズDBから生成**
   - 既存のCSVファイル(`data/` 配下)をドロップダウンから選ぶか、手元のCSVをアップロード
   - もしくは「Or Generate From Phrase Bank」で、DBに溜まっている未使用フレーズをテーマと
     件数を指定して直接動画化(動画化が成功すると自動的に「使用済み」としてマークされ、
     次回以降は選ばれなくなります)
3. **フレーズをプレビュー** — 選んだCSVの中身を確認できます。
4. **「Generate Video」をクリック** — 動画生成が始まり、進捗がリアルタイムで表示されます。
   すでに別の動画生成が進行中の場合は自動的に順番待ち(キュー)に入り、完了後に自動で
   処理が始まります。
5. **完成したら再生・ダウンロード** — ブラウザ内で再生するか、MP4をダウンロードできます。

途中でサーバーを再起動しても、ジョブの状態(実行中/待機中/完了/エラー)は保持されます。

### CSVフォーマット

1列目=英語フレーズ、2列目=日本語訳、1行目はヘッダー行。`data/sample_phrases.csv` を参照。

```csv
english,japanese
Break a leg!,頑張ってね!(舞台などの本番前の決まり文句)
It's a piece of cake.,それは朝飯前だよ。
```

## 使い方: コマンドラインから直接実行する場合

Web UIを使わず、スクリプトを直接叩くこともできます。

```bash
# 動画生成パイプラインをCSVから実行
python3 src/video_pipeline.py data/sample_phrases.csv
# 引数なしなら3フレーズのサンプルを使用
python3 src/video_pipeline.py

# Claude APIでフレーズを自動生成(結果は data/generated/ にCSV保存)
python3 src/phrase_generator.py "レストランでの会話" 50

# フレーズDBの管理
python3 src/phrase_db.py init                       # DB初期化
python3 src/phrase_db.py stats                       # テーマ別の在庫(未使用/合計)を表示
python3 src/phrase_db.py import data/sample_phrases.csv レストラン   # CSVをDBに取り込み

# ジョブ(動画生成の実行履歴)の確認
python3 src/job_store.py list
```

## トラブルシューティング

- **日本語が文字化け/豆腐(□)になる** → `JP_FONT_PATH` を `.env` で明示的に設定してください。
  macOSでは `/System/Library/Fonts/AppleSDGothicNeo.ttc` がデフォルトで使えるはずです。
- **`ffmpeg: command not found`** → 上記の「システムコマンド」の手順でインストールしてください。
- **フレーズ自動生成が失敗する** → `.env` の `ANTHROPIC_API_KEY` が設定されているか確認してください。
- **「Another job is already running」的なエラーは出ない** → 同時に2件以上リクエストしても
  エラーにはならず、自動的にキューイングされます(2件目以降は `queued` 状態として表示されます)。
