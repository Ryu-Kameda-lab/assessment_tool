# question_spec.py

import openpyxl

SPEC_FILE = "QuestionSpec_地域防災計画確認票.xlsx"

def load_question_spec(filepath: str = SPEC_FILE) -> list[dict]:
    """
    QuestionSpecのExcelを読み込んで、
    質問ごとの辞書リストを返す
    """
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb["QuestionSpec"]

    questions = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        # 空行スキップ
        if not row[0]:
            continue

        questions.append({
            "qid":          row[0],   # 質問番号
            "text":         row[1],   # 質問テキスト
            "category":     row[2],   # カテゴリ
            "answer_type":  row[4],   # 回答型
            "scope":        row[5],   # 対象（風水害/地震/共通）
            "query_must":   row[6],   # 必須キーワード
            "query_should": row[7],   # 加点キーワード
            "output_rule":  row[10],  # 回答の書き方
        })

    print(f"✅ QuestionSpec読み込み完了: {len(questions)}問")
    return questions


def make_search_query(q: dict) -> str:
    """
    QuestionSpecのMust+Shouldを結合して
    ChromaDB検索用クエリ文字列を作る
    """
    must   = q.get("query_must", "") or ""
    should = q.get("query_should", "") or ""

    # カンマ区切りを空白区切りに変換して結合
    parts = (must + " " + should).replace(",", " ")
    return " ".join(parts.split())   # 余分なスペース除去


if __name__ == "__main__":
    # 動作確認
    questions = load_question_spec()
    for q in questions[:3]:
        print(f"\nQ{q['qid']}: {q['text'][:30]}...")
        print(f"  検索クエリ: {make_search_query(q)}")