# phase1_extract.py

import os
import time
import pdf2image
import google.genai as genai          # ← 新しいライブラリに変更
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

# ── 新しい書き方でクライアントを初期化 ──────────────
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def extract_text_from_page(image: Image.Image, page_num: int) -> str:
    """1ページの画像をGeminiに渡してテキストを抽出する（リトライ付き）"""

    prompt = """
    この画像はマニュアルの1ページです。
    記載されているテキストを全て抽出し、Markdown形式で出力してください。
    - 見出しは # や ## で表現してください
    - 表は Markdown の表形式で再現してください
    - 図・イラスト・フローチャートは [図: 〇〇の説明] と記載してください
    - 縦書きのテキストも正確に読み取ってください
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # ── 新しい呼び出し方法 ──────────────────
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[prompt, image],
            )
            return response.text

        except Exception as e:
            if "429" in str(e) or "ResourceExhausted" in str(type(e).__name__):
                wait_time = 60 * (attempt + 1)
                print(f"  レート制限 (429)。{wait_time}秒待機後リトライ... ({attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise

    raise RuntimeError(f"ページ {page_num} の処理が {max_retries} 回失敗しました。")


def extract_pdf(pdf_path: str, output_txt_path: str = None, return_text: bool = False) -> str | None:
    """
    PDFを全ページ処理してテキストを返す or ファイルに保存する

    引数:
        pdf_path:        PDFファイルのパス
        output_txt_path: 保存先テキストファイルのパス（省略可）
        return_text:     Trueにするとテキストを戻り値として返す（app.pyから呼ぶときに使用）
    """

    print(f"PDFを読み込み中: {pdf_path}")
    pages = pdf2image.convert_from_path(pdf_path, dpi=200)
    print(f"総ページ数: {len(pages)}")

    all_text = []

    for i, page_image in enumerate(pages):
        print(f"  処理中... {i+1}/{len(pages)} ページ")

        text = extract_text_from_page(page_image, i + 1)
        all_text.append(f"\n\n--- ページ {i+1} ---\n\n{text}")

        if i < len(pages) - 1:
            print(f"  60秒待機中... (API呼び出し間隔調整)")
            time.sleep(60)

    full_text = "\n".join(all_text)

    # ファイル保存（パスが指定されている場合）
    if output_txt_path:
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"\n完了！保存先: {output_txt_path}")

    # テキストを返す（app.pyから呼ばれる場合）
    if return_text:
        return full_text


# ── 単体実行用 ────────────────────────────────────
if __name__ == "__main__":
    PDF_PATH    = r"C:\Users\Kameda Ryu\OneDrive\デスクトップ\venv_claude\assessment_tool\saigaiyobouhenn.pdf"
    OUTPUT_PATH = "output_text.txt"

    extract_pdf(PDF_PATH, output_txt_path=OUTPUT_PATH)