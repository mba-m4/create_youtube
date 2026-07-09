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

1. **フレーズ自動生成**(未着手・最優先)
   - Claude APIに「テーマ→フレーズ100個(英語+日本語)」を投げて自動生成する
   - これが解決すると「ネタが尽きる」問題が解消される
   - 実装イメージ: テーマを渡す→Claude APIがCSV相当のフレーズリストを返す→そのまま`video_pipeline.py`に渡す

2. **フレーズ管理をDB化**(CSVからの移行)
   - CSVは1回きりのバッチ処理には十分だが、継続運用するなら「もう動画化したか」「いつ使ったか」を管理する必要が出てくる
   - 最初はSQLite(ファイル1個で完結、サーバー不要)で十分。将来的に必要ならPostgres等に移行
   - 想定スキーマ例:
     ```
     phrases テーブル
     - id
     - english
     - japanese
     - theme       (例: レストラン、ビジネス、日常会話)
     - created_at
     - used_at     (動画化した日付。NULLなら未使用)
     - times_used  (復習用に再利用した回数)
     ```
   - これにより以下のような運用ができる:
     - 「今日は未使用のフレーズをN個取得して動画にする」
     - 「N日前に出したフレーズを復習用に再度動画化する」
     - 「テーマ別の在庫数を確認する」
   - フレーズ自動生成(1)と合わせて実装すると効率的
     (生成したフレーズをそのままDBにINSERT → 動画化タイミングでSELECT)

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
- `sample_phrases.csv` — CSVフォーマットのサンプル(1列目=英語, 2列目=日本語, ヘッダー行あり)