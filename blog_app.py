"""
Blog Article Generator - Streamlit管理UI
キーワードからSEOブログ記事を自動生成し、プレビュー・保存する。

起動方法: streamlit run blog_app.py
"""

import streamlit as st
import os
import json
import glob
from datetime import datetime

import blog_generator
import web_researcher
import wp_publisher
import source_loader

# ==========================================
# ページ設定
# ==========================================
st.set_page_config(
    page_title="📝 Blog Article Generator",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# カスタムCSS
# ==========================================
st.markdown("""
<style>
    /* 全体のフォント */
    .main { font-family: 'Noto Sans JP', 'Hiragino Sans', sans-serif; }
    
    /* サイドバーのスタイル */
    .css-1d391kg { background-color: #1a472a; }
    
    /* カードスタイル */
    .article-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid #2d7d46;
    }
    
    /* プレビューエリア */
    .preview-area {
        background: #fafafa;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 25px;
        margin: 15px 0;
        max-height: 600px;
        overflow-y: auto;
    }
    
    /* ステータスバッジ */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85em;
        font-weight: bold;
    }
    .status-draft { background: #fff3e0; color: #e65100; }
    .status-published { background: #e8f5e9; color: #2e7d32; }
    
    /* ヘッダー */
    .main-header {
        background: linear-gradient(135deg, #1a472a, #2d7d46);
        color: white;
        padding: 20px 30px;
        border-radius: 12px;
        margin-bottom: 25px;
    }
    
    /* プログレス */
    .step-indicator {
        background: #e8f5e9;
        padding: 10px 15px;
        border-radius: 8px;
        margin: 5px 0;
        font-size: 0.9em;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# サイドバー設定
# ==========================================
with st.sidebar:
    st.markdown("## ⚙️ 設定")
    
    # AIバックエンド選択
    ai_backend = st.selectbox(
        "🤖 AIモデル",
        ["Gemini", "Groq (LLaMA)"],
        help="Geminiが制限中の場合はGroqに切り替えてください"
    )
    
    # APIキー（Secretsから自動読み込み or 手入力）
    api_key = ""
    
    if ai_backend == "Gemini":
        # Gemini APIキー
        saved_key = ""
        try:
            for key_name in ["GEMINI_API_KEY", "GOOGLE_API_KEY"]:
                if key_name in st.secrets:
                    saved_key = st.secrets[key_name]
                    break
        except Exception:
            pass
        
        if saved_key:
            st.success("🔑 Gemini: Secretsから自動読み込み済み")
            api_key = saved_key
        else:
            api_key = st.text_input(
                "🔑 Gemini API Key", type="password",
                help="Google Gemini APIのキーを入力"
            )
        blog_generator.config_api(api_key, "gemini")
        
        if api_key and api_key.startswith("gsk_"):
            st.error("⚠️ 警告: 入力されたキーはGroq用のようです。Geminiを使うには `AIza...` で始まるGoogle APIキーが必要です。")
    
    else:
        # Groq APIキー
        saved_key = ""
        try:
            if "GROQ_API_KEY" in st.secrets:
                saved_key = st.secrets["GROQ_API_KEY"]
        except Exception:
            pass
        
        if saved_key:
            st.success("🔑 Groq: Secretsから自動読み込み済み")
            api_key = saved_key
        else:
            api_key = st.text_input(
                "🔑 Groq API Key", type="password",
                help="Groq APIのキーを入力"
            )
        blog_generator.config_api(api_key, "groq")

        if api_key and api_key.startswith("AIza"):
            st.error("⚠️ 警告: 入力されたキーはGemini用のようです。Groqを使うには `gsk_...` で始まるAPIキーが必要です。")
    
    if api_key:
        prefix = api_key[:6] + "..." if len(api_key) > 6 else "..."
        api_type = "Google (Gemini)" if api_key.startswith("AIza") else ("Groq" if api_key.startswith("gsk_") else "不明")
        st.caption(f"🗝️ 現在のキー種別: {api_type} (Key: {prefix})")

    st.markdown("---")
    
    # WordPress設定（将来用）
    st.markdown("### 🌐 WordPress設定")
    wp_enabled = st.checkbox("WordPress連携を有効にする", value=False)
    
    if wp_enabled:
        wp_url = st.text_input("サイトURL", placeholder="https://sasayoshi-garden.com")
        wp_user = st.text_input("ユーザー名")
        wp_pass = st.text_input("アプリケーションパスワード", type="password")
        
        if wp_url and wp_user and wp_pass:
            wp_publisher.configure(wp_url, wp_user, wp_pass)
            if st.button("🔌 接続テスト"):
                success, msg = wp_publisher.test_connection()
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
    
    st.markdown("---")
    
    # 記事生成設定
    st.markdown("### 📊 生成設定")
    max_sources = st.slider("参考ソース取得数", min_value=1, max_value=8, value=5,
                            help="Web検索で取得する参考記事の数")
    do_research = st.checkbox("Web情報収集を行う", value=True,
                              help="オフにすると商品情報のみで記事を生成します")
    
    st.markdown("---")
    
    # ソース状況サマリー
    st.markdown("### 📂 情報ソース状況")
    
    # クラウド接続状態表示
    if source_loader.is_cloud_mode():
        st.success("☁️ クラウドモード（Google Sheets）")
    else:
        st.info("💻 ローカルモード")
    
    src_summary = source_loader.get_source_summary()
    st.markdown(f"""
    - 📄 テキスト: **{src_summary['text_count']}**件
    - 📑 PDF: **{src_summary['pdf_count']}**件
    - 📊 Excel: **{src_summary['excel_count']}**件
    - 📸 画像: **{src_summary['image_count']}**件
    - 📷 Instagram: **{src_summary['instagram_count']}**件
    - **合計: {src_summary['total_count']}件**
    """)
    
    st.markdown("---")
    st.markdown("### 📦 商品カテゴリ")
    st.markdown("""
    - 🍋 フィンガーライム苗（29品種）
    - 🍋 斑入りフィンガーライム
    - 🍊 接ぎ木レモン苗
    - 🌲 ウッドチップ
    - 🔥 コナラ薪
    """)

# ==========================================
# メインヘッダー
# ==========================================
st.markdown("""
<div class="main-header">
    <h1 style="margin:0; color:white;">📝 Blog Article Generator</h1>
    <p style="margin:5px 0 0 0; opacity:0.9;">
        SEO最適化されたブログ記事を自動生成 | 八ヶ岳ガーデンSHOP
    </p>
</div>
""", unsafe_allow_html=True)


# ==========================================
# メインコンテンツ：タブ構成
# ==========================================
tab_generate, tab_sources, tab_history, tab_preview = st.tabs([
    "✍️ 記事生成",
    "📂 ソース管理",
    "📚 生成履歴",
    "👁️ プレビュー"
])


# ==========================================
# タブ1: 記事生成
# ==========================================
with tab_generate:
    col_input, col_info = st.columns([2, 1])
    
    with col_input:
        st.subheader("🎯 キーワード入力")
        
        keyword = st.text_input(
            "記事のターゲットキーワード",
            placeholder="例: フィンガーライム 育て方 冬越し",
            help="Google検索で上位表示を狙うキーワードを入力してください"
        )
        
        # 追加キーワード（サブ）
        sub_keywords = st.text_input(
            "関連キーワード（オプション）",
            placeholder="例: 耐寒性, 室内栽培, 初心者",
            help="カンマ区切りで関連キーワードを追加できます"
        )
        
        # 記事の方向性
        article_direction = st.text_area(
            "記事の方向性・追加指示（オプション）",
            placeholder="例: 初心者向けに分かりやすく書いてほしい / 商品の購入を促す内容にしてほしい",
            height=80
        )
        
        # キーワードの提案
        st.markdown("---")
        st.markdown("#### 💡 キーワード候補（コピペして使ってください）")
        
        keyword_suggestions = [
            "フィンガーライム 育て方",
            "フィンガーライム 苗 通販",
            "フィンガーライム 品種 おすすめ",
            "フィンガーライム 冬越し 寒冷地",
            "フィンガーライム 食べ方 レシピ",
            "フィンガーライム 実がならない 原因",
            "フィンガーライム 接ぎ木苗 実生苗 違い",
            "フィンガーライム 価格 相場",
            "フィンガーライム 鉢植え ベランダ",
            "フィンガーライム 剪定 時期",
            "フィンガーライム 肥料 おすすめ",
            "フィンガーライム 病気 害虫",
            "森のキャビア フィンガーライム とは",
            "フィンガーライム 栽培 日本",
            "ウッドチップ 庭 メリット デメリット",
            "ウッドチップ 敷き方 コツ",
            "レモン 苗 接ぎ木 育て方",
        ]
        
        # 3列で表示
        cols = st.columns(3)
        for i, suggestion in enumerate(keyword_suggestions):
            with cols[i % 3]:
                st.code(suggestion, language=None)
    
    with col_info:
        st.subheader("📋 生成の流れ")
        st.markdown("""
        **Step 1** 🔍 Web情報収集
        > キーワードで検索し、上位記事の情報を自動取得
        
        **Step 2** 📋 構成案の生成
        > AIが記事の見出し構造を設計
        
        **Step 3** ✍️ 記事本文の生成
        > SEO最適化された長文記事をHTML形式で生成
        
        **Step 4** 💾 保存
        > HTMLファイルとして保存（WPにコピペ可能）
        """)
        
        st.markdown("---")
        st.markdown("#### 📊 記事スペック")
        st.markdown("""
        - **文字数**: 3,000〜8,000文字
        - **見出し**: H2×5〜8 / H3×10〜20
        - **構成**: 導入→本文→FAQ→まとめ→CTA
        - **形式**: WordPress互換HTML
        - **文体**: AI臭排除の自然文体
        """)
    
    st.markdown("---")
    
    # 文頭・文末の定型文設定
    with st.expander("📝 文頭・文末の定型文を設定（任意）"):
        header_text = st.text_area(
            "文頭の定型文",
            placeholder="例: こんにちは！八ヶ岳ガーデンです。\n今回は...",
            height=100,
            help="記事の冒頭に必ず挿入されるテキスト",
            key="header_text"
        )
        footer_text = st.text_area(
            "文末の定型文",
            placeholder="例: 最後までお読みいただきありがとうございます。\nお問い合わせは...",
            height=100,
            help="記事の末尾に必ず挿入されるテキスト",
            key="footer_text"
        )
    
    st.markdown("---")
    
    # 生成実行ボタン
    if st.button("🚀 記事を生成する", type="primary", use_container_width=True):
        if not api_key:
            st.error("⚠️ サイドバーでGemini APIキーを設定してください")
        elif not keyword:
            st.error("⚠️ キーワードを入力してください")
        else:
            # API設定（サイドバーの選択に応じて）
            backend = "groq" if ai_backend == "Groq (LLaMA)" else "gemini"
            blog_generator.config_api(api_key, backend)
            
            # 追加キーワードをメインに統合
            full_keyword = keyword
            if sub_keywords:
                full_keyword += " " + sub_keywords.replace(",", " ").replace("、", " ")
            
            with st.status("📝 記事生成中...", expanded=True) as status:
                
                # ステップ0: 独自ソース読み込み
                st.write("📂 **Step 0:** 独自ソース読み込み中...")
                custom_sources_text = source_loader.get_all_sources_text(keyword)
                src_info = source_loader.get_source_summary()
                st.write(f"  ✅ ファイル: {src_info['total_file_count']}件 / Instagram: {src_info['instagram_count']}件")
                
                # ステップ1: Web情報収集
                st.write("🔍 **Step 1:** Web情報を収集中...")
                research_data = None
                if do_research:
                    research_data = web_researcher.research_keyword(keyword, max_sources=max_sources)
                    if research_data["source_count"] > 0:
                        st.write(f"  ✅ {research_data['source_count']}件のソースを取得")
                        with st.expander("📄 取得したソース一覧"):
                            for s in research_data["sources"]:
                                st.markdown(f"- [{s['title'][:60]}]({s['url']})")
                    else:
                        st.write("  ⚠️ ソースが取得できませんでした（商品情報のみで生成します）")
                else:
                    st.write("  ⏭️ Web情報収集をスキップ")
                
                # ステップ2: 構成案の生成
                st.write("📋 **Step 2:** 記事構成案を生成中...")
                outline_data, outline_error = blog_generator.generate_article_outline(
                    full_keyword, research_data, api_key
                )
                
                if outline_error:
                    st.error(f"構成案生成エラー: {outline_error}")
                    status.update(label="❌ エラー発生", state="error", expanded=True)
                    st.stop()
                
                st.write(f"  ✅ タイトル：「{outline_data.get('title', '')}」")
                st.write(f"  ✅ H2見出し数：{len(outline_data.get('outline', []))}個")
                
                with st.expander("📋 構成案の詳細"):
                    for section in outline_data.get("outline", []):
                        st.markdown(f"**{section['h2']}**")
                        for h3 in section.get("h3_list", []):
                            st.markdown(f"  └ {h3}")
                
                # ステップ3: 記事本文の生成（独自ソースも渡す）
                st.write("✍️ **Step 3:** 記事本文を生成中（APIを複数回呼び出すため数分かかります）")
                
                # 進捗表示用のプレースホルダー
                progress_placeholder = st.empty()
                
                def update_progress(msg):
                    progress_placeholder.info(msg)
                
                article_html, body_error = blog_generator.generate_article_body(
                    full_keyword, outline_data, research_data, api_key,
                    custom_sources_text=custom_sources_text,
                    progress_callback=update_progress
                )
                
                # 生成が終わったらプレースホルダーを消去または完了表示
                progress_placeholder.empty()
                
                if body_error:
                    st.error(f"本文生成エラー: {body_error}")
                    status.update(label="❌ エラー発生", state="error", expanded=True)
                    st.stop()
                
                # 文字数カウント（HTMLタグ除去）
                import re
                plain_text = re.sub(r'<[^>]+>', '', article_html)
                char_count = len(plain_text)
                st.write(f"  ✅ 記事生成完了！（約{char_count:,}文字）")
                
                # 結果をまとめる
                article_data = {
                    "keyword": keyword,
                    "title": outline_data.get("title", keyword),
                    "meta_description": outline_data.get("meta_description", ""),
                    "outline": outline_data,
                    "article_html": article_html,
                    "research_data": research_data,
                    "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "error": None
                }
                
                # 文頭・文末の定型文を挿入
                if header_text:
                    header_html = "<div class='custom-header'>" + header_text.replace('\n', '<br>') + "</div>\n\n"
                    article_html = header_html + article_html
                    article_data["article_html"] = article_html
                if footer_text:
                    footer_html = "\n\n<div class='custom-footer'>" + footer_text.replace('\n', '<br>') + "</div>"
                    article_html = article_html + footer_html
                    article_data["article_html"] = article_html
                
                # セッションに保存（プレビュー用）
                st.session_state["latest_article"] = article_data
                
                # ステップ4: ファイル保存
                st.write("💾 **Step 4:** ファイルを保存中...")
                html_path = blog_generator.save_article_html(article_data)
                wp_path = blog_generator.save_article_wp_content(article_data)
                json_path = blog_generator.save_article_json(article_data)
                
                if html_path:
                    st.write(f"  ✅ プレビュー用HTML: `{os.path.basename(html_path)}`")
                if wp_path:
                    st.write(f"  ✅ WPコピペ用HTML: `{os.path.basename(wp_path)}`")
                if json_path:
                    st.write(f"  ✅ JSONバックアップ: `{os.path.basename(json_path)}`")
                
                # クラウド保存（Google Sheets接続時）
                if source_loader.is_cloud_mode():
                    try:
                        import blog_sheet_manager
                        blog_sheet_manager.save_article_record(article_data)
                        st.write("  ✅ ☁️ クラウド（Google Sheets）にも保存")
                    except Exception as e:
                        st.write(f"  ⚠️ クラウド保存スキップ: {e}")
                
                status.update(label="✅ 記事生成完了！", state="complete", expanded=False)
            
            # 生成結果のプレビュー
            st.markdown("---")
            st.subheader("📄 生成された記事")
            
            # タイトルとメタ情報
            st.markdown(f"""
            <div class="article-card">
                <h2 style="margin:0 0 10px 0;">{article_data['title']}</h2>
                <p style="color:#666; font-size:0.9em;">{article_data['meta_description']}</p>
                <p style="color:#999; font-size:0.8em;">
                    📅 {article_data['generated_at']} | 📊 約{char_count:,}文字 | 🔑 {keyword}
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            # 記事本文プレビュー
            with st.expander("👁️ 記事プレビュー（クリックで展開）", expanded=True):
                st.markdown(article_html, unsafe_allow_html=True)
            
            # WP用HTMLソース
            with st.expander("📋 WordPress用HTMLソース（コピペ用）"):
                st.code(article_html, language="html")
            
            # WordPress下書き投稿
            if wp_publisher.is_configured():
                st.markdown("---")
                if st.button("📤 WordPressに下書き投稿する"):
                    success, result = wp_publisher.create_draft(
                        title=article_data["title"],
                        content=article_data["article_html"],
                        meta_description=article_data["meta_description"]
                    )
                    if success:
                        st.success(f"✅ 下書き投稿成功！ [編集画面を開く]({result['edit_link']})")
                    else:
                        st.error(f"❌ 投稿失敗: {result}")


# ==========================================
# タブ2: ソース管理
# ==========================================
with tab_sources:
    st.subheader("📂 情報ソースの管理")
    st.markdown("ここでファイルのアップロードやInstagram投稿の貼り付けができます。追加したソースは記事生成時に自動的に参照されます。")
    
    src_col1, src_col2 = st.columns(2)
    
    # --- 左カラム: ファイルアップロード ---
    with src_col1:
        st.markdown("### 📤 ファイルアップロード")
        st.markdown("対応形式: **テキスト** (.txt, .md, .csv) / **PDF** (.pdf) / **Excel** (.xlsx, .xls) / **画像** (.jpg, .png, .gif, .webp)")
        
        uploaded_files = st.file_uploader(
            "ファイルを選択（複数OK）",
            type=["txt", "md", "csv", "pdf", "xlsx", "xls", "jpg", "jpeg", "png", "gif", "webp"],
            accept_multiple_files=True,
            help="blog_data/sources/ フォルダに保存されます"
        )
        
        if uploaded_files:
            if st.button("💾 アップロードしたファイルを保存", type="primary"):
                for uploaded_file in uploaded_files:
                    saved_path = source_loader.save_uploaded_file(uploaded_file)
                    if saved_path:
                        st.success(f"✅ 保存: {uploaded_file.name}")
                    else:
                        st.error(f"❌ 保存失敗: {uploaded_file.name}")
                st.rerun()
        
        st.markdown("---")
        
        # 保存済みファイル一覧
        st.markdown("### 📋 保存済みファイル一覧")
        file_sources = source_loader.load_all_file_sources()
        
        all_sources = (
            file_sources["text_sources"] +
            file_sources["pdf_sources"] +
            file_sources["excel_sources"] +
            file_sources["image_sources"]
        )
        
        if all_sources:
            for src in all_sources:
                type_emoji = {"text": "📄", "pdf": "📑", "excel": "📊", "image": "📸"}.get(src["type"], "📁")
                with st.expander(f"{type_emoji} {src['filename']}（{src.get('char_count', 0):,}文字）"):
                    if src["type"] != "image":
                        st.text_area(
                            "内容プレビュー",
                            value=src.get("content", "")[:2000],
                            height=200,
                            disabled=True,
                            key=f"file_preview_{src['filename']}"
                        )
                    else:
                        st.markdown(f"画像ファイル: `{src['filepath']}`")
        else:
            st.info("📭 まだファイルがアップロードされていません。")
    
    # --- 右カラム: Instagram投稿の貼り付け ---
    with src_col2:
        st.markdown("### 📷 Instagram投稿ソース")
        st.markdown("専門家のInstagram投稿キャプション（文章）をここに貼り付けてください。")
        
        with st.form("instagram_form", clear_on_submit=True):
            insta_account = st.text_input(
                "アカウント名",
                placeholder="@fingerlime_expert",
                help="@付きでもなしでもOK"
            )
            
            insta_caption = st.text_area(
                "投稿キャプション（文章）",
                placeholder="ここにInstagramの投稿テキストをコピペしてください...",
                height=200
            )
            
            insta_url = st.text_input(
                "投稿URL（オプション）",
                placeholder="https://www.instagram.com/p/xxxxx/"
            )
            
            insta_tags = st.text_input(
                "タグ / カテゴリ（オプション）",
                placeholder="フィンガーライム, 育て方, 冬越し",
                help="関連キーワードを入れておくと、記事生成時にマッチングしやすくなります"
            )
            
            submitted = st.form_submit_button("💾 Instagramソースを保存", type="primary")
            if submitted:
                if not insta_account or not insta_caption:
                    st.error("⚠️ アカウント名とキャプションは必須です")
                else:
                    success = source_loader.save_instagram_source(
                        account_name=insta_account,
                        caption_text=insta_caption,
                        post_url=insta_url,
                        tags=insta_tags
                    )
                    if success:
                        st.success(f"✅ @{insta_account} の投稿を保存しました！")
                    else:
                        st.error("❌ 保存に失敗しました")
        
        st.markdown("---")
        
        # 保存済みInstagramソース一覧
        st.markdown("### 📋 保存済みInstagramソース")
        insta_sources = source_loader.load_instagram_sources()
        
        if insta_sources:
            for src in reversed(insta_sources):  # 新しい順
                with st.expander(f"📷 @{src['account_name']} ({src['saved_at'][:10]})"):
                    st.markdown(f"**キャプション:**")
                    st.text_area(
                        "内容",
                        value=src.get("caption", ""),
                        height=150,
                        disabled=True,
                        key=f"insta_{src['id']}"
                    )
                    if src.get("post_url"):
                        st.markdown(f"🔗 [投稿を見る]({src['post_url']})")
                    if src.get("tags"):
                        st.markdown(f"🏷️ タグ: `{src['tags']}`")
                    
                    if st.button(f"🗑️ 削除", key=f"del_insta_{src['id']}"):
                        source_loader.delete_instagram_source(src["id"])
                        st.rerun()
        else:
            st.info("📭 まだInstagramソースが登録されていません。")
    
    # --- Webページ / YouTubeソース（全幅） ---
    st.markdown("---")
    st.markdown("### 🌐 Web / YouTube ソース")
    st.markdown("WebページのURLまたはYouTube動画のURLを貼り付けると、内容を自動取得して情報ソースに追加します。")
    
    web_col1, web_col2 = st.columns([3, 1])
    
    with web_col1:
        web_url = st.text_input(
            "URL",
            placeholder="https://example.com/article  または  https://youtube.com/watch?v=xxxxx",
            help="WebページまたはYouTube動画のURLを入力",
            label_visibility="collapsed"
        )
    
    with web_col2:
        web_tags = st.text_input(
            "タグ",
            placeholder="タグ（任意）",
            help="関連キーワード",
            label_visibility="collapsed"
        )
    
    if web_url:
        # YouTube URL判定
        is_youtube = any(domain in web_url for domain in ["youtube.com", "youtu.be"])
        
        if is_youtube:
            # YouTube用ボタン
            st.info("🎬 YouTube動画が検出されました。字幕テキストを取得します。")
            if st.button("🎬 YouTube字幕を取得して保存", type="primary", use_container_width=True):
                with st.spinner("🔄 YouTube字幕を取得中..."):
                    result = source_loader.fetch_youtube_transcript(web_url)
                    
                    if result["success"]:
                        saved = source_loader.save_web_source(
                            url=web_url,
                            title=f"🎬 {result['title']}",
                            text=result["text"],
                            tags=web_tags
                        )
                        if saved:
                            lang_info = result.get("language", "不明")
                            st.success(f"✅ 保存完了: **{result['title']}**（{result['char_count']:,}文字 / 言語: {lang_info}）")
                            st.rerun()
                        else:
                            st.error("❌ 保存に失敗しました")
                    else:
                        st.error(f"❌ 取得失敗: {result.get('error', '不明なエラー')}")
        else:
            # Webページ用ボタン
            btn_col1, btn_col2 = st.columns(2)
            
            with btn_col1:
                single_page = st.button("📥 このページだけ取得", type="primary", use_container_width=True)
            with btn_col2:
                crawl_site_btn = st.button("🔍 サイト全体を取得（最大10ページ）", use_container_width=True)
            
            if single_page:
                with st.spinner("🔄 ページを取得中..."):
                    result = source_loader.fetch_web_page(web_url)
                    
                    if result["success"]:
                        saved = source_loader.save_web_source(
                            url=web_url,
                            title=result["title"],
                            text=result["text"],
                            tags=web_tags
                        )
                        if saved:
                            st.success(f"✅ 保存完了: **{result['title']}**（{result['char_count']:,}文字）")
                            st.rerun()
                        else:
                            st.error("❌ 保存に失敗しました")
                    else:
                        st.error(f"❌ 取得失敗: {result.get('error', '不明なエラー')}")
            
            if crawl_site_btn:
                with st.spinner("🔍 サイト内を巡回中...（最大10ページ、少し時間がかかります）"):
                    pages = source_loader.crawl_site(web_url, max_pages=10)
                    
                    if pages:
                        saved_count = 0
                        for page in pages:
                            if page.get("success"):
                                saved = source_loader.save_web_source(
                                    url=page["url"],
                                    title=page["title"],
                                    text=page["text"],
                                    tags=web_tags
                                )
                                if saved:
                                    saved_count += 1
                        
                        if saved_count > 0:
                            st.success(f"✅ サイト巡回完了！**{saved_count}ページ**を保存しました")
                            st.rerun()
                        else:
                            st.error("❌ ページの保存に失敗しました")
                    else:
                        st.error("❌ サイトからページを取得できませんでした")
    
    # 保存済みWebソース一覧
    web_sources = source_loader.load_web_sources()
    if web_sources:
        st.markdown(f"**保存済み: {len(web_sources)}件**")
        for src in reversed(web_sources):
            with st.expander(f"🌐 {src.get('title', src['url'])}（{src.get('char_count', 0):,}文字）"):
                st.markdown(f"🔗 [{src['url']}]({src['url']})")
                if src.get("tags"):
                    st.markdown(f"🏷️ タグ: `{src['tags']}`")
                st.text_area(
                    "内容プレビュー",
                    value=src.get("content", "")[:2000],
                    height=150,
                    disabled=True,
                    key=f"web_{src['id']}"
                )
                if st.button(f"🗑️ 削除", key=f"del_web_{src['id']}"):
                    source_loader.delete_web_source(src["id"])
                    st.rerun()


# ==========================================
# タブ3: 生成履歴
# ==========================================
with tab_history:
    st.subheader("📚 生成した記事の履歴")
    
    articles_dir = blog_generator.ARTICLES_DIR
    
    if os.path.exists(articles_dir):
        # JSONファイル一覧を取得（新しい順）
        json_files = sorted(
            glob.glob(os.path.join(articles_dir, "*.json")),
            key=os.path.getmtime,
            reverse=True
        )
        
        if json_files:
            for json_file in json_files:
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    filename = os.path.basename(json_file)
                    
                    with st.container():
                        st.markdown(f"""
                        <div class="article-card">
                            <h3 style="margin:0 0 5px 0;">{data.get('title', '無題')}</h3>
                            <p style="color:#666; margin:0;">
                                🔑 {data.get('keyword', '')} | 
                                📅 {data.get('generated_at', '')} | 
                                📄 {filename}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            if st.button(f"👁️ プレビュー", key=f"preview_{filename}"):
                                st.session_state["preview_article"] = data
                        with col2:
                            # 対応するWP用HTMLファイルのパス
                            wp_filename = filename.replace(".json", "_wp.html")
                            # 元のファイル名パターンから探す
                            base_name = filename.replace(".json", "")
                            wp_html_path = os.path.join(articles_dir, f"{base_name}_wp.html")
                            if not os.path.exists(wp_html_path):
                                # ファイル名に_wpが含まれていない場合
                                wp_html_path = os.path.join(articles_dir, wp_filename)
                            
                            if os.path.exists(wp_html_path):
                                st.markdown(f"📋 [WP用HTML]({wp_html_path})")
                        with col3:
                            if wp_publisher.is_configured():
                                if st.button(f"📤 WP投稿", key=f"wp_{filename}"):
                                    success, result = wp_publisher.create_draft(
                                        title=data.get("title", ""),
                                        content=data.get("article_html", ""),
                                        meta_description=data.get("meta_description", "")
                                    )
                                    if success:
                                        st.success(f"✅ 投稿成功！")
                                    else:
                                        st.error(f"❌ {result}")
                        
                        st.markdown("---")
                
                except Exception as e:
                    st.warning(f"ファイル読み込みエラー: {os.path.basename(json_file)} - {e}")
        else:
            st.info("📭 まだ記事が生成されていません。「記事生成」タブでキーワードを入力して始めましょう！")
    else:
        st.info("📭 まだ記事保存フォルダが作成されていません。")


# ==========================================
# タブ3: プレビュー
# ==========================================
with tab_preview:
    st.subheader("👁️ 記事プレビュー")
    
    # 最新の記事 or 選択した記事をプレビュー
    preview_data = st.session_state.get("preview_article") or st.session_state.get("latest_article")
    
    if preview_data:
        st.markdown(f"""
        <div class="article-card">
            <h2 style="margin:0 0 5px 0;">{preview_data.get('title', '無題')}</h2>
            <p style="color:#888; font-size:0.85em;">
                🔑 キーワード: {preview_data.get('keyword', '')} | 
                📅 {preview_data.get('generated_at', '')}
            </p>
            <p style="color:#666; font-size:0.9em;">
                {preview_data.get('meta_description', '')}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # プレビュー表示
        article_html = preview_data.get("article_html", "")
        if article_html:
            st.markdown(article_html, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # HTMLソースコピー用
            with st.expander("📋 HTMLソース（WPコピペ用）"):
                st.code(article_html, language="html")
            
            # 構成情報
            outline = preview_data.get("outline")
            if outline:
                with st.expander("📋 記事構成"):
                    st.json(outline)
            
            # リサーチ情報
            research = preview_data.get("research_data")
            if research and research.get("sources"):
                with st.expander("🔍 参考ソース"):
                    for s in research["sources"]:
                        st.markdown(f"- [{s.get('title', 'No Title')[:60]}]({s.get('url', '')})")
    else:
        st.info("📭 プレビューする記事がありません。「記事生成」タブで記事を生成してください。")


# ==========================================
# フッター
# ==========================================
st.markdown("---")
st.markdown("""
<div style="text-align:center; color:#888; font-size:0.8em; padding:10px;">
    📝 Blog Article Generator | 八ヶ岳ガーデンSHOP びたみん市場 | 
    Powered by Gemini AI × Streamlit
</div>
""", unsafe_allow_html=True)
