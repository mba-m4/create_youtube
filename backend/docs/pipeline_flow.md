# パイプライン処理フロー(詳細)

概要・ロードマップは `README.md`、開発ルールは `CLAUDE.md` を参照。
このドキュメントは「実際にコードが何をどの順番で処理するか」だけをまとめる。

## 全体の流れ

```
[フレーズ入力]                          [変換]                              [結合]
CSV or SAMPLE_PHRASES                                                    final_video.mp4
      |                                                                        ^
      v                                                                        |
load_phrases_from_csv()                                                        |
  -> [(en, jp), ...] を全件メモリに読み込む                                       |
      |                                                                        |
      v                                                                        |
run_pipeline(phrases)  ---- 1件ずつ for ループ -------------------------+       |
      |                                                                |       |
      | 各フレーズ (en, jp) について:                                    |       |
      |   1. generate_audio(en)      -> audio/phrase_XX.mp3 (ElevenLabs TTS)   |
      |   2. generate_phrase_image(en, jp) -> images/phrase_XX.png (Pillow)    |
      |   3. make_clip(image, audio) -> clips/phrase_XX.mp4 (ffmpeg)           |
      |      duration = 音声長 + 1.0秒(SILENCE_AFTER_SEC)                      |
      +------------------------------------------------------------------------+
                                                                         |
                                          全クリップ生成が終わったら1回だけ ---+
                                          concat_clips(clip_paths) -> final_video.mp4
                                          (ffmpeg -f concat -c copy, 再エンコードなし)
```

## モジュール別の役割

- `phrase_image_generator.py`
  - `load_phrases_from_csv(path, has_header)`: CSVを1回で全行読み込み、`[(english, japanese), ...]` を返す(ストリーミングではない)。
  - `generate_phrase_image(en, jp)`: 1フレーズ分の画像を`PIL.Image`として生成して返す(保存はしない)。
- `tts_elevenlabs.py`
  - `generate_audio(text, out_path, language_code)`: ElevenLabs APIにテキストを渡し、返ってきた音声を`out_path`に保存。
- `video_pipeline.py`
  - `tts_elevenlabs.generate_audio()`を呼び出して音声を生成(`video_pipeline.py`自体にはTTS実装を持たない)。
  - `make_clip(image_path, audio_path, out_path)`: `ffprobe`で音声長を取得 → `ffmpeg`で「画像1枚を音声長+1秒ぶんループさせた動画」を作る。
  - `concat_clips(clip_paths, out_path)`: 全クリップのパスを`filelist.txt`に書き出し、`ffmpeg -f concat -c copy`でストリームコピー結合(再エンコードなしなので高速)。
  - `run_pipeline(phrases)`: 上記を「1フレーズ=音声→画像→クリップ」の順で1件ずつ実行し、最後に全クリップを結合。
- `phrase_db.py`(現状`video_pipeline.py`とは未接続)
  - `get_unused_phrases(n)` で未使用フレーズを取得 → 呼び出し側で`run_pipeline()`に渡す → `mark_used(ids)`で使用済みにする、という流れを想定しているが、この配線はまだ書かれていない。

## ご質問: CSVが100件ある場合、1件ずつ読み取って変換して結合する?

**「1件ずつ変換」は Yes、「結合」は全件変換後に1回だけ、というのが正確な動きです。**

1. **読み込みは一括**: `load_phrases_from_csv()`はCSV100行を最初に全部読み込み、100件のタプルのリストをメモリに持つ(ストリーミングで1件ずつ読むわけではない)。
2. **変換(音声・画像・クリップ化)は1件ずつ逐次**: `run_pipeline()`の`for`ループで、100件を順番に処理する。
   - フレーズ1件ごとに「TTS APIコール1回 → 画像生成1回 → ffmpeg実行1回(クリップ化)」という3ステップが完結してから、次のフレーズに進む。
   - 並列処理はしていない(README記載の設計方針どおり、音声長=画像表示時間の対応を壊さないため)。
   - 結果として、100件なら音声ファイル100個・画像100個・クリップ100個ができる。
3. **結合は最後にまとめて1回**: 100個のクリップが全部揃ってから、`concat_clips()`が最後に1回だけ呼ばれ、`ffmpeg -f concat`で全クリップを1本の`final_video.mp4`に結合する(逐次結合ではなく、最後にバッチで結合)。

### 実運用上の注意点(100件クラスの場合)

- **API呼び出し回数**: TTS APIコールが100回発生する(ElevenLabsへの課金・レート制限に注意)。
- **処理時間**: 直列実行なので、1件あたりの処理時間 × 100件がそのまま総時間になる。
- **途中失敗時の再開機能はまだない**: 例えば57件目でエラーが起きると`run_pipeline()`はそこで例外停止する。既存の`audio/`・`images/`・`clips/`ファイルはディスクに残るが、`generate_audio`/`generate_phrase_image`/`make_clip`のどれも「既にファイルがあればスキップ」という判定をしていないため、再実行すると1件目からすべて作り直しになる(現状は未実装、必要になったら対応を検討)。

## 未実装の連携(README/CLAUDE.md記載の既知事項)

- `phrase_db.get_unused_phrases()` → `video_pipeline.run_pipeline()` → `phrase_db.mark_used()` の自動連携は未実装(手動で繋ぐ想定)。
- `phrase_generator.py`が生成したフレーズをDBに直接INSERTする経路は未実装(CSV経由でのみ`phrase_db.import_csv()`に渡せる)。
