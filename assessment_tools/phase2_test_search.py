# phase2_test_search.py

import chromadb
from sentence_transformers import SentenceTransformer

# ===================================================
# 設定（build_ragと同じ値にする）
# ===================================================
CHROMA_DB_PATH  = "./chroma_db"
COLLECTION_NAME = "manual_chunks"
EMBED_MODEL     = "paraphrase-multilingual-mpnet-base-v2"
TOP_K           = 5   # 上位何件取得するか


# ===================================================
# 検索関数
# ===================================================
def search(query: str, collection, model, top_k: int = TOP_K):
    """
    クエリ文字列に近いチャンクをChromaDBから検索して返す
    """
    # クエリをベクトル化
    query_vector = model.encode([query]).tolist()

    # ChromaDBで類似チャンクを検索
    results = collection.query(
        query_embeddings = query_vector,
        n_results        = top_k,
        include          = ["documents", "metadatas", "distances"]
    )

    return results


def show_results(query: str, results: dict):
    """
    検索結果を見やすく表示する
    """
    print(f"\n{'='*60}")
    print(f"🔍 検索クエリ: {query}")
    print(f"{'='*60}")

    docs      = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for i, (doc, meta, dist) in enumerate(zip(docs, metadatas, distances)):
        similarity = 1 - dist   # コサイン距離→類似度に変換
        print(f"\n--- 結果 {i+1} (類似度: {similarity:.3f}, ページ: {meta['page_num']}) ---")
        print(doc[:300] + "..." if len(doc) > 300 else doc)

    print(f"\n{'='*60}")


# ===================================================
# メイン処理
# ===================================================
if __name__ == "__main__":
    print("ChromaDB読み込み中...")
    client     = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_collection(COLLECTION_NAME)
    model      = SentenceTransformer(EMBED_MODEL)

    print(f"✅ 読み込み完了（総チャンク数: {collection.count()} 件）")
    print("\n検索クエリを入力してください。終了するには 'q' を入力。\n")

    # ===================================================
    # テスト用クエリ（質問票から抜粋した5問）
    # ===================================================
    test_queries = [
        "本部員 任命 災害対策本部 構成",              # Q1
        "本部 設置 基準 風水害 地震 警戒レベル",       # Q2
        "安否確認 実施 基準 対象者 タイミング",         # Q6
        "避難所 開設 基準 風水害 地震",                # Q71
        "電力 ガス 通信 石油 情報収集 ライフライン",    # Q102
    ]

    for query in test_queries:
        results = search(query, collection, model)
        show_results(query, results)

    # ===================================================
    # 対話モード（自分でクエリを打ち込んで試せる）
    # ===================================================
    print("\n\n💬 対話モード開始（自由に検索できます）")
    while True:
        query = input("\n検索クエリを入力 > ").strip()
        if query.lower() == "q":
            print("終了します。")
            break
        if not query:
            continue
        results = search(query, collection, model)
        show_results(query, results)