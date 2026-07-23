# CLAUDE.md

このリポジトリで作業する際の開発方針・ルール。実装前に必ず確認すること。
プロジェクトの概要・ロードマップは README.md を参照。

## コーディング規約

- 1ファイル1モジュールの単純な関数ベース設計を維持する。クラス化やフレームワーク導入はしない。
- 過剰な抽象化・エラーハンドリングを避ける。バグ修正や単発処理のためにヘルパー関数を作らない。
- 既存モジュール(`phrase_image_generator.py`, `video_pipeline.py`)と同じスタイルに合わせる:
  - モジュール先頭の docstring に使い方(import する場合 / CLI実行する場合)を書く
  - `python3 xxx.py` で直接実行できる `main()` を用意する

## Claude APIキーの管理

- APIキーは `.env` に `ANTHROPIC_API_KEY=...` として保存し、`python-dotenv` で読み込む。
- `.env` はコミットしない(`.gitignore` 済み)。キーなしのテンプレートは `.env.example` を参照・更新する。

## フレーズ生成のモデル選択

- デフォルトはコスト優先で `claude-sonnet-5`。
- 環境変数 `PHRASE_GEN_MODEL` で上書き可能にする(未設定時はデフォルト値を使う)。
- 関数の引数でも明示的に指定できるようにし、優先順位は「関数引数 > 環境変数 > デフォルト値」とする。
- 高品質が必要な場合は呼び出し側で `claude-opus-4-8` 等を指定すればよく、コード変更は不要な設計にする。

## 生成フレーズCSVの保存規約

- 保存先は `data/generated/` に統一する。
- ファイル名は `<テーマ>_<日付>.csv` 形式で自動生成する(例: `data/generated/レストラン_20260710.csv`)。

## フレーズDB(SQLite)

- `src/phrase_db.py` が担当。DB本体は `data/phrases.db`(`.gitignore`済み、環境ごとにローカルで持つ)。
- スキーマ: `phrases(id, english, japanese, theme, created_at, used_at, times_used)`。
- 重複判定は `english` の完全一致(`UNIQUE`制約 + `INSERT OR IGNORE`)。
- 読み取り系(`get_unused_phrases`/`get_review_phrases`/`mark_used`/`stats_by_theme`)も
  書き込み系(`insert_phrases`/`import_csv`)と同様に呼び出し時に `init_db()` するので、
  DBファイル未作成の状態から呼んでも安全。
- `phrase_generator.py` の出力(CSV保存)に加えて、Web UI (`app.py` の
  `POST /api/phrases/generate`)から呼んだ場合は生成結果を `phrase_db.insert_phrases()` で
  DBにも登録する(CSV出力は単独運用でも使えるよう引き続き併存)。
- 動画化との連携(`get_unused_phrases()` → `video_pipeline.run_pipeline()` → `mark_used()`)は
  `app.py` の `POST /api/generate`(`{"source": "db", "theme": ..., "count": ...}`)と
  `job_store.py` に組み込み済み。`video_pipeline.py` 自体はフレーズ由来を意識しない設計のまま。

## ジョブ管理(Web UI)

- `src/job_store.py` が担当。ジョブ状態は `data/jobs.db`(`.gitignore`済み)に永続化し、
  サーバー再起動をまたいで保持する。起動時に `status="running"` のまま残ったジョブは
  `error`(`"Interrupted by server restart"`)に遷移させる。
- 同時に実行できる動画生成ジョブは常に1件のみ(`video_pipeline.py` の出力先が
  `AUDIO_DIR`/`IMAGE_DIR`/`CLIP_DIR`/`FINAL_VIDEO` の固定パスで、ジョブごとに分離されて
  いないため)。2件目以降は `queued` として登録し、`app.py` のディスパッチャーが
  実行中ジョブの完了を検知して自動的に起動する。
- ジョブ作成時点の処理対象フレーズは `phrases_json` にスナップショットとして保存する
  (CSV由来・DB由来を同じ形で扱うため)。DB由来ジョブは `phrase_ids_json` も保存し、
  動画化成功後に `mark_used()` を呼ぶ。

## TTS(音声生成)

- `src/tts_elevenlabs.py` が担当。ElevenLabs APIを使用し、`video_pipeline.py`から呼び出す。
- APIキーは `.env` に `ELEVENLABS_API_KEY` として保存する(`.env.example`参照)。
- 読み上げ順(`sequence`、例: `["en", "ja"]`)は `video_pipeline.run_pipeline()` の引数で
  指定する(省略時は `["en"]` で従来通り英語のみ)。`build_sequence_audio()` が
  同じ言語の音声をAPIで1回だけ生成し(重複排除)、`sequence`の順に無音(`SILENCE_BETWEEN_SEC`)
  を挟んで結合する。
- Web UI経由の場合は `job_store.py` の `sequence_json` カラムにジョブ作成時点で
  スナップショットされ、`app.py` の `POST /api/generate` が `"en"`/`"ja"` 以外の値を
  弾く(APIバウンダリでのバリデーション)。

## 未確定事項(今後決める)

- ElevenLabsの音声品質基準(voice_id/model_idの最終選定)
