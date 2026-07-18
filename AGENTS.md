# create_youtube プロジェクト開発ガイド

英語フレーズの動画を自動生成するパイプラインプロジェクト。

## プロジェクト構成

```
create_youtube/
├── backend/                    # メインの実装
│   ├── CLAUDE.md              # backend 固有の実装ルール
│   ├── README.md              # ビルド・実行方法
│   ├── pyproject.toml         # Python 依存関係(uv で管理)
│   ├── src/                   # モジュール
│   │   ├── video_pipeline.py  # メインのパイプライン(CSV→動画)
│   │   ├── phrase_image_generator.py  # フレーズ画像生成
│   │   ├── tts_elevenlabs.py  # 音声生成(ElevenLabs API)
│   │   ├── phrase_generator.py # フレーズ自動生成(Claude API、オプション)
│   │   ├── phrase_db.py       # フレーズ管理(SQLite)
│   │   └── app.py             # Web UI (FastAPI)
│   ├── static/
│   │   └── index.html         # Web UI フロントエンド
│   ├── data/
│   │   ├── sample_phrases.csv # サンプルフレーズ
│   │   ├── generated/         # 自動生成されたフレーズCSV
│   │   └── uploads/           # ユーザーアップロードのCSV
│   └── pipeline_output/       # 生成物(音声・画像・動画、一時)
└── frontend/                   # (未使用)
```

## 開発の流れ

1. **feature ブランチを切る** — `git checkout -b feature/xxx`
2. **実装 + テスト** — backend に変更を加える
3. **コミット** — `git commit -m "..."`。以下の方針に従う:
   - 1コミット = 1機能 or 1バグ修正 (アトミック)
   - メッセージは英語で簡潔に: "Add Web UI for video generation"
   - backend/ 内の変更であれば "backend: ..." で始めてもよい
4. **プッシュ** — `git push origin feature/xxx`
5. **PR作成** — GitHub Web UI から PR を作成
   - タイトル: コミットメッセージと同じで OK
   - 説明: 何をなぜ変更したのか、テスト方法など
6. **レビュー + マージ** — PR がマージされたら feature ブランチは削除

## Backend の開発

実装ルール・ベストプラクティスは `backend/CLAUDE.md` を参照。

### セットアップ

```bash
cd backend
uv sync                       # 依存関係をインストール
```

### 環境変数の設定

`.env` に以下を設定する(`.env.example` を参照):
- `ELEVENLABS_API_KEY` — ElevenLabs API キー(TTS用)
- `ANTHROPIC_API_KEY` — Claude API キー(phrase_generator.py 用、オプション)
- `EN_FONT_PATH` — 英語フォントパス(環境に応じて、オプション)
- `JP_FONT_PATH` — 日本語フォントパス(環境に応じて、オプション)

**注**: `.env` は絶対にコミットしない。`.env.example` のみ追跡する。

### ローカルテスト

```bash
# CLI パイプラインのテスト
python3 src/video_pipeline.py data/sample_phrases.csv

# Web UI のテスト
python3 src/app.py
# ブラウザで http://localhost:8000 を開く
```

## 主なコミット/PR 対象の区分

| 内容 | ブランチ名 | PR タイトル例 |
|---|---|---|
| 機能追加 | `feature/xxx` | "Add Web UI for video generation" |
| バグ修正 | `fix/xxx` | "Fix font path resolution on macOS" |
| ドキュメント | `docs/xxx` | "docs: Update README with Web UI setup" |
| リファクタリング | `refactor/xxx` | "Refactor video_pipeline for clarity" |

## コーディング規約

- 1ファイル1モジュール、関数ベース設計(クラス化・過剰抽象化は避ける)
- モジュール先頭に docstring で使い方を記載
- `python3 xxx.py` で直接実行できる `main()` を用意
- 既存モジュールと同じスタイルに合わせる

## Q & A

**Q: バックエンドだけ変更する場合、プッシュしてもいいの？**
A: はい。ブランチを切って PR を作ってください。backend/ の変更は frontend に影響しません。

**Q: .env ファイルを間違えてコミットした場合？**
A: `git rm --cached .env` してから、コミットをやり直してください。

**Q: 依存パッケージを追加した場合？**
A: `uv add パッケージ名` し、`uv.lock` ごとコミットしてください。

**Q: Mac 上で日本語フォントが見つからないエラーが出る場合？**
A: `backend/README.md` のセットアップセクションを参照し、`JP_FONT_PATH` を `.env` に設定してください。

## その他

- **質問 / 改善提案**: PR の説明に記載してください。
- **重大なバグ**: Issue を作成して共有してください。
