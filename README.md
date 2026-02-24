# 🛡️ 防災計画アセスメント自動化ツール

> 地域防災計画の確認票（105問）に対し、PDFマニュアルを根拠にAIが自動回答するWebアプリケーションです。

---

## 📋 目次

1. [背景・目的](#背景目的)
2. [システム概要](#システム概要)
3. [技術スタック](#技術スタック)
4. [ファイル構成](#ファイル構成)
5. [処理フロー詳細](#処理フロー詳細)
6. [セットアップ手順](#セットアップ手順)
7. [使い方](#使い方)
8. [QuestionSpecの設計](#questionspecの設計)
9. [カスタマイズ・チューニング](#カスタマイズチューニング)
10. [既知の制限・注意事項](#既知の制限注意事項)

---

## 背景・目的

### これまでの課題

地域防災計画のアセスメント業務では、**300ページ超のPDFマニュアル複数**を担当者が手作業で読み込み、**105問の確認票**に1問ずつ回答する必要がありました。

| 従来の方法 | 課題 |
|---|---|
| 担当者が手動でPDFを参照 | 1件あたり数日〜1週間の作業時間 |
| 根拠ページを手作業で探す | 読み落とし・記載箇所の見落としリスク |
| 回答をExcelに手入力 | ヒューマンエラーの発生 |

### このツールで解決すること

- **PDFをアップロードするだけ**で105問に自動回答
- 根拠ページ番号も合わせて出力（ダブルチェックが容易）
- 作業時間を**数日 → 数十分**に短縮

---

## システム概要

```
┌──────────────────────────────────────────────────────────┐
│                    Streamlit Web UI                       │
│   Step1: PDF入力  →  Step2: RAG構築  →  Step3: 回答生成   │
└──────────────┬───────────────┬───────────────┬───────────┘
               │               │               │
               ▼               ▼               ▼
        ┌─────────────┐ ┌───────────────┐ ┌──────────────┐
        │  Gemini     │ │   ChromaDB    │ │ QuestionSpec │
        │ Vision API  │ │（ベクトルDB）  │ │  (.xlsx)     │
        │ テキスト抽出 │ │  意味検索      │ │ 105問の仕様   │
        └─────────────┘ └───────────────┘ └──────────────┘
               │               │               │
               └───────────────┴───────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │    Gemini API    │
                    │  （回答生成）     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  回答済みExcel    │
                    │  （根拠ページ付） │
                    └──────────────────┘
```

---

## 技術スタック

| カテゴリ | ライブラリ/サービス | 用途 |
|---|---|---|
| UI | Streamlit | Webアプリ画面 |
| PDF処理 | pdf2image, Pillow, Poppler | PDF→画像変換 |
| テキスト抽出 | Gemini Vision API (1.5 Flash) | 画像→Markdownテキスト |
| ベクトル化 | sentence-transformers | テキスト→数値ベクトル変換 |
| ベクトルDB | ChromaDB | 意味検索データベース（ローカル） |
| 回答生成 | Gemini API (1.5 Flash) | RAG経由の回答生成 |
| Excel操作 | openpyxl | 質問票への書き込み |
| 言語 | Python 3.11 | ※3.14非対応（後述） |

---

## ファイル構成

```
assessment_tool/
│
├── app.py                          # Streamlit Webアプリ（エントリーポイント）
│
├── phase1_extract.py               # Step1: PDF → テキスト化
│                                   #   pdf2imageでページ画像化
│                                   #   Gemini Vision APIでテキスト抽出
│                                   #   → output_text.txt に保存
│
├── phase2_build_rag.py             # Step2: RAG構築
│                                   #   テキストをチャンク分割（400文字/80文字重複）
│                                   #   sentence-transformersでベクトル化
│                                   #   → ChromaDBに保存
│
├── phase2_test_search.py           # Step2: 検索テスト（開発・検証用）
│
├── phase3_answer_engine.py         # Step3: 回答生成エンジン
│                                   #   QuestionSpecのクエリでChromaDB検索
│                                   #   10問バッチでGemini APIに投げる
│                                   #   → 回答辞書を返す
│
├── phase3_excel_writer.py          # Step3: Excel書き込み
│                                   #   回答と根拠ページをテンプレートに書き込み
│
├── question_spec.py                # QuestionSpec読み込み・クエリ生成ユーティリティ
│
├── QuestionSpec_地域防災計画確認票.xlsx   # 105問の検索仕様定義ファイル
│
├── 地域防災計画確認票.xlsm               # 回答出力テンプレート（元ファイル）
│
├── .env                            # APIキー（Gitに含めない）
├── requirements.txt                # 依存ライブラリ一覧
│
├── output_text.txt                 # [生成物] Step1の出力テキスト
├── chroma_db/                      # [生成物] ChromaDBのデータフォルダ
└── output_answered_YYYYMMDD.xlsx   # [生成物] 回答済みExcel
```

---

## 処理フロー詳細

### Step1：PDF → テキスト化

```
PDFファイル
    ↓ pdf2image（Popplerを使用）
各ページを画像（PNG）に変換
    ↓ Gemini Vision API（1.5 Flash）
画像1枚ずつMarkdown形式でテキスト化
    ↓
output_text.txt に結合して保存
    形式: --- ページ XX ---
          （本文テキスト）
```

**ポイント：** 表・箇条書きなどの構造をMarkdownで保持することで、後のRAG検索精度が向上します。

---

### Step2：RAG構築

```
output_text.txt
    ↓ ページ区切りで分割 → さらに400文字で分割（80文字重複）
チャンク群（約1,000〜1,500個）
    ↓ paraphrase-multilingual-mpnet-base-v2（ローカル動作）
各チャンクがベクトル（数値の配列）に変換される
    ↓ ChromaDB（コサイン類似度）
chroma_db/ フォルダに永続保存
```

**チャンク設定値（`phase2_build_rag.py` 内）：**

| パラメータ | デフォルト値 | 説明 |
|---|---|---|
| CHUNK_SIZE | 400文字 | 1チャンクの最大文字数 |
| CHUNK_OVERLAP | 80文字 | 前チャンクとの重複文字数 |

---

### Step3：回答生成

```
QuestionSpec（105問の仕様）
    ↓ query_must + query_should を結合
検索クエリ文字列
    ↓ ChromaDB（上位4チャンクを取得）
関連テキスト（根拠候補）
    ↓ 10問バッチ × 約11回 → Gemini API（1.5 Flash）
JSON形式の回答
    ↓ openpyxl
回答済みExcel（根拠ページ番号付き）
```

**Gemini API呼び出し回数（105問の場合）：**
- バッチサイズ10問 → 11回のAPI呼び出し
- 処理時間目安：約3〜5分

---

## セットアップ手順

### 前提条件

- **Python 3.11**（3.14はChromaDBの依存ライブラリ `pydantic v1` が非対応）
- **Poppler**（pdf2imageの依存ツール）
- **Gemini APIキー**

### 1. Popplerのインストール（Windows）

[Popplerダウンロードページ](https://github.com/oschwartz10612/poppler-windows/releases)から最新版をダウンロードし、解凍後に `bin/` フォルダをシステムのPATHに追加してください。

### 2. 仮想環境の作成

```bash
py -3.11 -m venv venv_311
venv_311\Scripts\activate   # Windows
# または
source venv_311/bin/activate  # Mac/Linux
```

### 3. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

`requirements.txt` の内容：

```
chromadb
sentence-transformers
langchain
langchain-community
pdf2image
Pillow
google-generativeai
python-dotenv
openpyxl
streamlit
```

### 4. APIキーの設定

`.env` ファイルをプロジェクトルートに作成してください：

```
GEMINI_API_KEY=your_api_key_here
```

### 5. 動作確認

```bash
# ChromaDB・sentence-transformersの確認
python check_install.py

# QuestionSpec読み込みの確認
python question_spec.py

# 検索テスト（Step2まで完了後）
python phase2_test_search.py
```

---

## 使い方

### Webアプリの起動

```bash
streamlit run app.py
```

ブラウザで `http://localhost:8501` が自動的に開きます。

### 操作手順

**Step1 タブ：PDF → テキスト化**
1. PDFファイルを1つ以上アップロード
2. 「テキスト抽出を開始」ボタンをクリック
3. 完了メッセージが出たら次へ

**Step2 タブ：RAG構築**
1. 「RAG構築を開始」ボタンをクリック
2. 初回はモデルダウンロードが走るため数分かかります
3. サイドバーに「✅ RAGデータベース：構築済み」と表示されたら次へ

**Step3 タブ：回答生成**
1. 「回答生成を開始」ボタンをクリック
2. プログレスバーで進捗を確認（約3〜5分）
3. 完了後に「回答済みExcelをダウンロード」ボタンが表示されます

---

## QuestionSpecの設計

`QuestionSpec_地域防災計画確認票.xlsx` は、RAG検索の精度を高めるための**質問ごとの検索仕様書**です。

### 列の説明

| 列名 | 説明 | 例（Q1：本部員の定め） |
|---|---|---|
| QID | 質問番号 | 1 |
| 質問テキスト | 確認票の質問文 | 本部員はあらかじめ定められているか |
| カテゴリ | 12カテゴリに分類 | 指揮統制（本部） |
| AnswerType | 回答の型 | 体制/責任者 |
| Scope | 対象災害種別 | 共通 |
| QueryMust | 必ず含めるキーワード | 本部員,任命,指名 |
| QueryShould | 検索精度を上げるキーワード | 災害対策本部,構成,役割,班,体制 |
| SectionHints | マニュアルの章・節名のヒント | 災害対策本部,本部体制,組織体制 |
| EvidenceRule | 根拠文章の特徴パターン | 本部員は〜,〜をもって充てる |
| OutputRule | 回答の書き方指示 | 本部員の定め方・リスト有無を一文で |

### 12カテゴリ一覧

| コード | カテゴリ名 | 対象質問 |
|---|---|---|
| CAT_01 | 指揮統制（本部） | Q1-5, Q20-24 |
| CAT_02 | 職員の安否・参集 | Q6-14, Q18-19 |
| CAT_03 | 情報連携・本部機能 | Q15-17 |
| CAT_04 | 地域連携・防災教育 | Q25-27 |
| CAT_05 | 受援・応援協定 | Q28-38 |
| CAT_06 | 通信（手段/冗長化） | Q39-44 |
| CAT_07 | ハザード・被害情報収集 | Q45-54 |
| CAT_08 | 広報・住民情報発信 | Q55-65 |
| CAT_09 | 帰宅困難者 | Q66-70 |
| CAT_10 | 避難所・要配慮者 | Q71-81 |
| CAT_11 | 物資（備蓄・調達・運搬） | Q82-91 |
| CAT_12 | インフラ・危険物情報収集 | Q92-105 |

---

## カスタマイズ・チューニング

### 回答精度を上げたい場合

**① チャンクサイズの調整（`phase2_build_rag.py`）**

```python
CHUNK_SIZE    = 400   # 小さくすると精度↑、件数↑
CHUNK_OVERLAP = 80    # 大きくすると文脈の連続性↑
```

**② 取得チャンク数の調整（`phase3_answer_engine.py`）**

```python
TOP_K = 4   # 増やすと根拠の網羅性↑、ただしトークン消費↑
```

**③ QuestionSpecのクエリ改善**

`QueryMust` や `QueryShould` を実際のマニュアル用語に合わせて編集することで検索精度が向上します。

### 別のマニュアルに対応させる場合

1. 新しいPDFをStep1でテキスト化
2. Step2でRAGを再構築（既存DBは上書き）
3. Step3で回答生成

QuestionSpecの変更は不要です（質問票が同じ場合）。

---

## 既知の制限・注意事項

| 項目 | 内容 |
|---|---|
| **Pythonバージョン** | Python 3.14はChromaDBが非対応。**必ず3.11を使用**すること |
| **PDF品質** | スキャンPDFや手書きが多いページはOCR精度が下がる |
| **マクロ付きExcel** | `.xlsm`（マクロ付き）はopenpyxlでマクロが失われる。出力は `.xlsx` 形式になる |
| **APIコスト** | Gemini Vision APIはページ数に比例してコスト増。300ページ×複数ファイルは事前に見積もりを |
| **根拠ページの精度** | RAGは完全ではないため、重要な回答は必ず根拠ページを人間が確認すること |
| **ChromaDB保存先** | `chroma_db/` フォルダはローカルのみ。チームで共有する場合は別途共有ストレージへの移行が必要 |

---

## ライセンス・問い合わせ

社内利用限定。外部共有・再配布は禁止。

問い合わせ先：**[担当者名・チーム名をここに記載]**
