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

1. **Issue を作成** — 作業内容に応じて GitHub Issue を立てる。後述の「粒度」ガイドを参照
2. **feature ブランチを切る** — `git checkout -b feature/xxx` または `git checkout -b fix/xxx`
3. **実装 + テスト** — 小さく分けたタスク単位で実装する
4. **コミット** — `git commit -m "..."`。以下の方針に従う:
   - 1コミット = 1つの独立した変更 (アトミック・単一責任)
   - メッセージは英語で簡潔に。詳細は本文に記載
   - 差分行数は 100-300 行程度が目安
5. **複数コミットで PR を作成** — 関連する複数のコミットをまとめて PR にする
6. **レビュー + マージ** — PR がマージされたら feature ブランチは削除

## コミット・PR・Issue の粒度ガイドライン

このプロジェクトでは、変更を細かく分割することを重視します。

### Issue（チケット）の粒度

**1つの Issue = 1週間以内に完結する単一の作業**

例：
- ❌ 大きすぎる: "Build Web UI" (複数の機能が含まれる)
- ✅ 適切: "Add CSV upload feature to Web UI"
- ✅ 適切: "Add progress display to Web UI"
- ✅ 適切: "Implement `/api/generate` FastAPI endpoint"

### コミットの粒度

**1つのコミット = 1つの独立した変更。差分 100-300 行程度が目安**

例：
- ❌ 大きすぎる: app.py + index.html + README を同時にコミット (差分 1000+ 行)
- ✅ 適切: "backend: Add FastAPI app.py with core endpoints"
- ✅ 適切: "frontend: Create index.html Web UI page"
- ✅ 適切: "docs: Update README with Web UI setup"
- ✅ 適切: "backend: Add on_progress callback to video_pipeline"

### PR の粒度

**1つの PR = 1つの Issue。複数の関連コミットで構成**

例：
- ❌ 大きすぎる: 14 ファイル、1000+ 行の変更を 1 PR で
- ✅ 適切: Issue「Web UI の CSV アップロード機能」に対して、複数のコミット:
  1. "backend: Add /api/upload endpoint"
  2. "frontend: Add CSV upload form"
  3. "docs: Update README"

### Git / GitHub 操作の言語ルール

**PR タイトル・Issue タイトルは英語で統一する**（コミットメッセージも同様に英語）。本文・説明は日本語で構わない。

例：
- ✅ PR タイトル: "Add Web UI for video generation"
- ✅ Issue タイトル: "Add DB integration to Web UI for unused phrases"
- ✅ コミットメッセージ: "fix: sanitize filename in CSV upload endpoint"
- Issue 本文・PR 本文（Summary/Test plan など）は日本語で詳細を書いてよい

### 実装時のチェックリスト

- [ ] Issue を先に作成した
- [ ] 1 コミット = 1 つの独立した変更か確認
- [ ] 1 コミット差分が 100-300 行程度か確認（大きければ分割）
- [ ] PR 説明に Issue 番号を記載（`Closes #123` など）
- [ ] 関連するドキュメント更新も別コミットで含める

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
