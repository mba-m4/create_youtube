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
- `phrase_generator.py` の出力(CSV)は `phrase_db.import_csv()` で取り込む。今のところ
  `phrase_generator.py`がDBに直接INSERTする経路は作っていない(CSV出力は単独でも使えるようにするため)。
- 動画化との連携(`get_unused_phrases()` → `video_pipeline.run_pipeline()` → `mark_used()`)は
  まだ`video_pipeline.py`側に組み込んでいない。呼び出し側で手動で繋ぐ想定。

## TTS(音声生成)

- `src/tts_elevenlabs.py` が担当。ElevenLabs APIを使用し、`video_pipeline.py`から呼び出す。
- APIキーは `.env` に `ELEVENLABS_API_KEY` として保存する(`.env.example`参照)。

## 未確定事項(今後決める)

- ElevenLabsの音声品質基準(voice_id/model_idの最終選定)
- `video_pipeline.py`をDB連携(未使用フレーズの自動取得→動画化→used_at更新)に対応させるか
