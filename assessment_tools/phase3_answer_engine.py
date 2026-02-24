# phase3_answer_engine.py

import os
import json
import time
import chromadb
import google.generativeai as genai
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from question_spec import load_question_spec, make_search_query

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ===================================================
# 設定
# ===================================================
CHROMA_DB_PATH  = "./chroma_db"
COLLECTION_NAME = "manual_chunks"
EMBED_MODEL     = "paraphrase-multilingual-mpnet-base-v2"
TOP_K              = 4    # 1問あたり何チャンク取得するか
BATCH_SIZE         = 10   # 何問まとめてAPIに投げるか
GEMINI_MODEL       = "gemini-2.0-flash"
BATCH_INTERVAL_SEC = 10   # バッチ間の待機秒数（API rate limit対策）
MAX_RETRIES        = 3    # エラー時の最大リトライ回数
RETRY_BASE_SEC     = 30   # リトライ待機の基準秒数（指数バックオフ: 30→60→120）


# ===================================================
# ChromaDB検索
# ===================================================
def search_chunks(query: str, collection, model, top_k: int = TOP_K) -> list[dict]:
    """
    クエリに近いチャンクを検索して返す
    """
    vector  = model.encode([query]).tolist()
    results = collection.query(
        query_embeddings = vector,
        n_results        = top_k,
        include          = ["documents", "metadatas", "distances"]
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text":     doc,
            "page_num": meta["page_num"],
            "score":    round(1 - dist, 3),
        })
    return chunks


# ===================================================
# バッチ回答生成
# ===================================================
def answer_batch(questions: list[dict], collection, embed_model) -> dict:
    """
    10問分の質問を受け取り、
    各質問に対して検索→Gemini呼び出しで回答を返す

    返り値: { QID: {"answer": "...", "evidence_pages": [12, 13]} }
    """

    # 各質問の検索結果をまとめる
    context_blocks = []
    for q in questions:
        query  = make_search_query(q)
        chunks = search_chunks(query, collection, embed_model)

        # 検索結果をテキストに整形
        refs = "\n".join([
            f"  [ページ{c['page_num']}] {c['text']}"
            for c in chunks
        ])
        context_blocks.append(
            f"【Q{q['qid']}の参考情報】\n{refs}"
        )

    # 質問リストを整形
    q_list = "\n".join([
        f"Q{q['qid']}: {q['text']}\n  ※回答指示: {q['output_rule']}"
        for q in questions
    ])

    # Geminiへのプロンプト
    prompt = f"""
あなたは地域防災計画のアセスメント担当者です。
以下の【参考情報】は防災マニュアルから抽出した文章です。
この情報を根拠にして、各質問に日本語で回答してください。

ルール：
- 参考情報に記載がある場合は、その内容を簡潔にまとめて回答する
- 参考情報に記載がない場合は「記載なし」と回答する
- 回答はJSON形式のみで返す（他の文章は一切不要）
- 根拠ページ番号も必ず含める

{'='*50}
【参考情報】
{'='*50}
{chr(10).join(context_blocks)}

{'='*50}
【質問リスト】
{'='*50}
{q_list}

{'='*50}
【出力形式（このJSONのみ返すこと）】
{'='*50}
{{
  "Q1": {{"answer": "回答内容", "evidence_pages": [12, 15]}},
  "Q2": {{"answer": "回答内容", "evidence_pages": [20]}},
  ...
}}
"""

    # Gemini API呼び出し（リトライ付き）
    model_gemini = genai.GenerativeModel(GEMINI_MODEL)
    response = None
    for attempt in range(MAX_RETRIES):
        try:
            response = model_gemini.generate_content(prompt)
            break  # 成功したらループを抜ける
        except Exception as e:
            is_rate_limit = (
                "429" in str(e)
                or "ResourceExhausted" in str(type(e).__name__)
                or "quota" in str(e).lower()
            )
            if is_rate_limit and attempt < MAX_RETRIES - 1:
                wait_sec = RETRY_BASE_SEC * (2 ** attempt)  # 30→60→120秒
                print(f"  ⚠️  レート制限エラー。{wait_sec}秒待機後にリトライ... "
                      f"({attempt+1}/{MAX_RETRIES})")
                time.sleep(wait_sec)
            else:
                print(f"  ❌ Gemini API呼び出し失敗 (attempt {attempt+1}): {e}")
                # リトライ上限 or 予期しないエラー → 全問エラー埋め
                return {
                    f"Q{q['qid']}": {"answer": "取得エラー", "evidence_pages": []}
                    for q in questions
                }

    # JSONパース
    raw = response.text.strip()
    # コードブロックが含まれる場合を除去
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # パース失敗時は全問「取得エラー」で埋める
        result = {
            f"Q{q['qid']}": {"answer": "取得エラー", "evidence_pages": []}
            for q in questions
        }

    return result


# ===================================================
# 105問すべてに回答する
# ===================================================
def answer_all(collection=None, progress_callback=None) -> dict:
    """
    全105問に回答して結果を返す

    collection:        ChromaDBのコレクションオブジェクト（省略時はディスクから読み込む）
    progress_callback: Streamlitのプログレスバー更新用
    返り値: { QID(int): {"answer": "...", "evidence_pages": [...]} }
    """
    embed_model = SentenceTransformer(EMBED_MODEL)

    if collection is None:
        print("📂 ChromaDB読み込み中...")
        client     = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collection = client.get_collection(COLLECTION_NAME)

    questions = load_question_spec()
    all_answers = {}
    total_batches = (len(questions) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end   = min(start + BATCH_SIZE, len(questions))
        batch = questions[start:end]

        qids = [q['qid'] for q in batch]
        print(f"  バッチ {batch_idx+1}/{total_batches}: Q{qids[0]}〜Q{qids[-1]} 処理中...")

        result = answer_batch(batch, collection, embed_model)

        # QIDを整数キーで統一して格納
        for q in batch:
            key = f"Q{q['qid']}"
            if key in result:
                all_answers[q['qid']] = result[key]
            else:
                all_answers[q['qid']] = {"answer": "取得エラー", "evidence_pages": []}

        # Streamlitプログレスバーの更新
        if progress_callback:
            progress_callback((batch_idx + 1) / total_batches)

        # 最後のバッチ以外は待機（API呼び出し間隔調整）
        if batch_idx < total_batches - 1:
            print(f"  ⏳ 次のバッチまで {BATCH_INTERVAL_SEC}秒待機...")
            time.sleep(BATCH_INTERVAL_SEC)

    print(f"✅ 全{len(all_answers)}問の回答生成完了")
    return all_answers


# ===================================================
# 動作確認（単体テスト用）
# ===================================================
if __name__ == "__main__":
    print("=== 回答エンジン 動作テスト ===")
    print("最初の10問だけ回答生成します...\n")

    client      = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection  = client.get_collection(COLLECTION_NAME)
    embed_model = SentenceTransformer(EMBED_MODEL)

    questions = load_question_spec()[:10]   # 最初の10問だけテスト
    result    = answer_batch(questions, collection, embed_model)

    for qid, val in result.items():
        print(f"{qid}: {val['answer'][:60]}...")
        print(f"   根拠ページ: {val['evidence_pages']}")