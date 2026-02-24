# app.py

import streamlit as st
import os
import time

st.set_page_config(
    page_title="防災計画アセスメント自動化ツール",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ 防災計画アセスメント自動化ツール")
st.caption("PDFマニュアルをアップロードするだけで、105問の質問票に自動回答します")

# ===================================================
# サイドバー：設定
# ===================================================
with st.sidebar:
    st.header("⚙️ 設定")
    st.info("APIキーは .env ファイルで管理しています")

    st.markdown("---")
    st.markdown("**処理ステータス**")

    if os.path.exists("./chroma_db"):
        st.success("✅ RAGデータベース：構築済み")
    else:
        st.warning("⚠️ RAGデータベース：未構築")

    if os.path.exists("output_text.txt"):
        st.success("✅ テキスト抽出：完了")
    else:
        st.warning("⚠️ テキスト抽出：未実施")

# ===================================================
# タブで3ステップに分ける
# ===================================================
tab1, tab2, tab3 = st.tabs([
    "📄 Step1：PDF → テキスト化",
    "🗄️ Step2：RAG構築",
    "💬 Step3：回答生成 → Excel出力"
])


# ─── Tab1：PDF → テキスト化 ───────────────────────
with tab1:
    st.subheader("PDFをアップロードしてテキストを抽出します")
    st.info("複数のPDFをまとめてアップロードできます。処理時間はページ数に比例します（300ページ：約10〜15分）")

    uploaded_pdfs = st.file_uploader(
        "PDFファイルをアップロード",
        type=["pdf"],
        accept_multiple_files=True
    )

    if uploaded_pdfs:
        st.success(f"{len(uploaded_pdfs)} ファイルがアップロードされました")
        for f in uploaded_pdfs:
            st.write(f"  - {f.name}")

    if st.button("▶️ テキスト抽出を開始", disabled=not uploaded_pdfs):
        from phase1_extract import extract_pdf
        import tempfile

        all_text = ""
        progress = st.progress(0)
        status   = st.empty()

        for i, pdf_file in enumerate(uploaded_pdfs):
            status.write(f"処理中: {pdf_file.name} ({i+1}/{len(uploaded_pdfs)})")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_file.read())
                tmp_path = tmp.name

            text = extract_pdf(tmp_path, return_text=True)   # ← 後で修正
            all_text += f"\n\n=== ファイル: {pdf_file.name} ===\n\n{text}"
            os.unlink(tmp_path)

            progress.progress((i + 1) / len(uploaded_pdfs))

        with open("output_text.txt", "w", encoding="utf-8") as f:
            f.write(all_text)

        status.success(f"✅ 完了！総文字数: {len(all_text):,} 文字")
        st.balloons()


# ─── Tab2：RAG構築 ────────────────────────────────
with tab2:
    st.subheader("抽出したテキストからRAGデータベースを構築します")
    st.info("Step1完了後に実施してください。初回のモデルダウンロードが含まれる場合は数分かかります")

    if not os.path.exists("output_text.txt"):
        st.warning("先にStep1でテキスト抽出を完了させてください")
    else:
        if st.button("▶️ RAG構築を開始"):
            from phase2_build_rag import load_text, split_into_chunks, build_chroma_db

            with st.spinner("RAGデータベースを構築中..."):
                text   = load_text("output_text.txt")
                chunks = split_into_chunks(text, chunk_size=400, overlap=80)
                build_chroma_db(chunks)

            st.success(f"✅ RAG構築完了！（{len(chunks)} チャンク）")
            st.rerun()


# ─── Tab3：回答生成 ───────────────────────────────
with tab3:
    st.subheader("105問の質問票に自動回答してExcelを出力します")

    if not os.path.exists("./chroma_db"):
        st.warning("先にStep2でRAGを構築してください")
    else:
        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown("""
            **処理の流れ：**
            1. QuestionSpecの検索クエリでChromaDBを検索
            2. 105問を10問ずつバッチ化してGemini APIへ投げる（約11回）
            3. 回答をExcelに書き込んで返却
            """)

        with col2:
            st.metric("API呼び出し回数（目安）", "約11回")
            st.metric("処理時間（目安）", "約3〜5分")

        if st.button("▶️ 回答生成を開始", type="primary"):
            from phase3_answer_engine import answer_all
            from phase3_excel_writer import write_answers_to_excel

            progress_bar  = st.progress(0)
            status_text   = st.empty()

            status_text.write("🔄 回答生成中...")

            def update_progress(ratio):
                progress_bar.progress(ratio)
                batch_num  = int(ratio * 11)
                status_text.write(f"🔄 バッチ処理中... {batch_num}/11")

            answers = answer_all(progress_callback=update_progress)

            status_text.write("📝 Excelに書き込み中...")
            output_path = write_answers_to_excel(answers)

            progress_bar.progress(1.0)
            status_text.success("✅ 完了！")

            # ダウンロードボタン
            with open(output_path, "rb") as f:
                st.download_button(
                    label     = "📥 回答済みExcelをダウンロード",
                    data      = f.read(),
                    file_name = output_path,
                    mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            st.balloons()