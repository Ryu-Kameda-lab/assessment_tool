# phase2_build_rag.py

import os
import re
import chromadb
from sentence_transformers import SentenceTransformer

# ===================================================
# 設定（ここだけ変更すればOK）
# ===================================================
INPUT_TEXT_FILE = "output_text.txt"   # フェーズ1で作ったテキストファイル
CHROMA_DB_PATH  = "./chroma_db"       # ChromaDBの保存先フォルダ
COLLECTION_NAME = "manual_chunks"     # DB内のコレクション名（テーブル名のようなもの）

CHUNK_SIZE    = 400   # チャンク1つあたりの最大文字数
CHUNK_OVERLAP = 80    # 前のチャンクと重複させる文字数（文脈を切らさないため）

# 埋め込みモデル（日本語対応・無料・ローカル動作）
EMBED_MODEL = "paraphrase-multilingual-mpnet-base-v2"


# ===================================================
# Step1: テキストファイルを読み込む
# ===================================================
def load_text(filepath: str) -> str:
    print(f"📄 テキスト読み込み中: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    print(f"   → 総文字数: {len(text):,} 文字")
    return text


# ===================================================
# Step2: テキストをチャンクに分割する
# ===================================================
def split_into_chunks(text: str, chunk_size: int, overlap: int) -> list[dict]:
    """
    テキストを小さな塊（チャンク）に分割する。
    ページ区切り「--- ページ XX ---」を手がかりに、
    まずページ単位に分けてからさらに細かく分割する。
    """
    print(f"\n✂️  チャンク分割中（1チャンク={chunk_size}文字, 重複={overlap}文字）")

    # ページ区切りで分割
    page_pattern = re.compile(r"--- ページ (\d+) ---")
    parts = page_pattern.split(text)

    # parts は [前テキスト, ページ番号, 本文, ページ番号, 本文, ...] の形になる
    chunks = []
    chunk_id = 0

    # ページ番号と本文をペアにする
    pages = []
    i = 1
    while i < len(parts) - 1:
        page_num = int(parts[i])
        page_text = parts[i + 1].strip()
        if page_text:
            pages.append((page_num, page_text))
        i += 2

    print(f"   → 検出ページ数: {len(pages)} ページ")

    # 各ページをさらに細かく分割
    for page_num, page_text in pages:
        start = 0
        while start < len(page_text):
            end = start + chunk_size
            chunk_text = page_text[start:end]

            if chunk_text.strip():   # 空白だけのチャンクはスキップ
                chunks.append({
                    "id":       f"chunk_{chunk_id:04d}",
                    "text":     chunk_text,
                    "page_num": page_num,
                })
                chunk_id += 1

            # 次の開始位置（overlapぶん戻す）
            start = end - overlap
            if start >= len(page_text):
                break

    print(f"   → 生成チャンク数: {len(chunks)} 個")
    return chunks


# ===================================================
# Step3: ChromaDBにチャンクを保存する
# ===================================================
def build_chroma_db(chunks: list[dict], use_memory: bool = False):
    """
    チャンクをベクトル化してChromaDBに保存する。

    Args:
        chunks:     split_into_chunks() の返り値
        use_memory: True にするとディスクに書かずインメモリで動作（Streamlit Cloud向け）
    """
    print(f"\n🔧 ChromaDB構築中...")

    # 埋め込みモデルをロード（初回はダウンロードが走ります）
    print(f"   モデルロード中: {EMBED_MODEL}")
    print(f"   （初回は数分かかる場合があります）")
    model = SentenceTransformer(EMBED_MODEL)

    # ChromaDBクライアントを作成
    if use_memory:
        print(f"   インメモリモードで動作します（再起動で消去されます）")
        client = chromadb.Client()
    else:
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    # コレクションが既にあれば削除して作り直す（再実行時のため）
    existing = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing:
        print(f"   既存コレクション '{COLLECTION_NAME}' を削除して再作成します")
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}  # コサイン類似度で検索
    )

    # チャンクを100件ずつまとめてベクトル化・保存（メモリ節約）
    batch_size = 100
    total = len(chunks)

    for batch_start in range(0, total, batch_size):
        batch = chunks[batch_start : batch_start + batch_size]

        ids       = [c["id"]       for c in batch]
        texts     = [c["text"]     for c in batch]
        metadatas = [{"page_num": c["page_num"]} for c in batch]

        # テキスト→ベクトル変換
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        collection.add(
            ids        = ids,
            documents  = texts,
            embeddings = embeddings,
            metadatas  = metadatas,
        )

        done = min(batch_start + batch_size, total)
        print(f"   保存済み: {done}/{total} チャンク")

    print(f"\n✅ ChromaDB構築完了！")
    print(f"   保存先: {CHROMA_DB_PATH}")
    print(f"   総チャンク数: {collection.count()} 件")
    return collection


# ===================================================
# メイン処理
# ===================================================
if __name__ == "__main__":
    # 1. テキスト読み込み
    text = load_text(INPUT_TEXT_FILE)

    # 2. チャンク分割
    chunks = split_into_chunks(text, CHUNK_SIZE, CHUNK_OVERLAP)

    # 3. ChromaDB構築
    build_chroma_db(chunks)

    print("\n🎉 フェーズ2 Step1 完了！次は検索テストを実行してください。")