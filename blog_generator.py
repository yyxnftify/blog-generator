"""
Blog Generator モジュール（メインエンジン）
Gemini APIを使い、SEO最適化されたブログ記事を生成する。

特徴:
- JetBサイト風の構成（目次 / 見出し / FAQ / まとめ / CTA）
- AI臭のない自然な文体
- Web調査データに基づく根拠のある記事
- WordPress互換のHTML出力
"""

import os
import json
import random
import requests
from datetime import datetime

import web_researcher
import source_loader

# ==========================================
# グローバル設定
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCT_INFO_PATH = os.path.join(BASE_DIR, "blog_data", "product_info.txt")
ARTICLES_DIR = os.path.join(BASE_DIR, "generated_articles")

GOOGLE_API_KEY = ""
GROQ_API_KEY = ""

# AIバックエンド設定: "gemini" or "groq"
AI_BACKEND = "gemini"

# 記事保存ディレクトリが無ければ作成
os.makedirs(ARTICLES_DIR, exist_ok=True)


# ==========================================
# 商品情報ロード
# ==========================================

def load_product_info():
    """product_info.txt から商品データを読み込む"""
    if not os.path.exists(PRODUCT_INFO_PATH):
        print(f"⚠ 商品情報ファイルが見つかりません: {PRODUCT_INFO_PATH}")
        return ""
    try:
        with open(PRODUCT_INFO_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"商品情報読み込みエラー: {e}")
        return ""


# ==========================================
# AI API 関連
# ==========================================

def config_api(api_key, backend="gemini", groq_key=""):
    """APIキーとバックエンドを設定する"""
    global GOOGLE_API_KEY, GROQ_API_KEY, AI_BACKEND
    AI_BACKEND = backend
    if backend == "gemini":
        GOOGLE_API_KEY = api_key
    elif backend == "groq":
        GROQ_API_KEY = api_key if api_key else groq_key


def config_gemini(api_key):
    """APIキーを設定する（後方互換）"""
    config_api(api_key, "gemini")


def find_best_model(api_key):
    """利用可能なモデルの中からベストなものを自動選択する"""
    preferred = [
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.0-pro",
        "gemini-pro",
    ]

    for version in ["v1", "v1beta"]:
        url = f"https://generativelanguage.googleapis.com/{version}/models?key={api_key}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                available = []
                for m in models:
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        available.append(m.get("name", ""))

                for pref in preferred:
                    for avail in available:
                        if pref in avail:
                            model_id = avail.replace("models/", "")
                            return version, model_id

                if available:
                    model_id = available[0].replace("models/", "")
                    return version, model_id
        except:
            continue

    return None, None


def generate_content_gemini(api_key, system_prompt, user_prompt, temperature=0.7):
    """Gemini APIを叩いてテキストを生成する"""

    api_version, model_id = find_best_model(api_key)

    if not api_version or not model_id:
        return None, "API Error: 利用可能なGeminiモデルが見つかりません。APIキーを確認してください。"

    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model_id}:generateContent?key={api_key}"
    print(f"★ Using Gemini: {api_version}/models/{model_id}")

    headers = {"Content-Type": "application/json"}

    data = {
        "contents": [
            {
                "parts": [
                    {"text": system_prompt + "\n\n" + user_prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 16384  # ブログ記事用に大きめ
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=data)

        if response.status_code != 200:
            return None, f"Gemini API Error: {response.status_code} - {response.text[:500]}"

        result_json = response.json()

        if "candidates" in result_json and result_json["candidates"]:
            candidate = result_json["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                return candidate["content"]["parts"][0]["text"], None
            else:
                return None, f"API Blocked: {candidate}"
        else:
            return None, f"API Response Error: {json.dumps(result_json)[:500]}"

    except Exception as e:
        return None, f"Gemini API Exception: {e}"


def generate_content_groq(api_key, system_prompt, user_prompt, temperature=0.7):
    """Groq API（OpenAI互換）を叩いてテキストを生成する"""

    url = "https://api.groq.com/openai/v1/chat/completions"
    # ブログ記事向けに大きなコンテキストのモデルを使用
    model = "llama-3.1-70b-versatile"
    print(f"★ Using Groq: {model}")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
        "max_tokens": 8000,  # Groqのトークン制限に合わせる
        "top_p": 0.95,
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=120)

        if response.status_code != 200:
            return None, f"Groq API Error: {response.status_code} - {response.text[:500]}"

        result_json = response.json()

        if "choices" in result_json and result_json["choices"]:
            content = result_json["choices"][0].get("message", {}).get("content", "")
            if content:
                return content, None
            else:
                return None, "Groq API: 空のレスポンス"
        else:
            return None, f"Groq API Response Error: {json.dumps(result_json)[:500]}"

    except Exception as e:
        return None, f"Groq API Exception: {e}"


def generate_content_api(api_key, system_prompt, user_prompt, temperature=0.7):
    """現在のバックエンド設定に応じてAPIを叩く（統一インターフェース）"""
    if AI_BACKEND == "groq":
        groq_key = api_key if api_key else GROQ_API_KEY
        return generate_content_groq(groq_key, system_prompt, user_prompt, temperature)
    else:
        gemini_key = api_key if api_key else GOOGLE_API_KEY
        return generate_content_gemini(gemini_key, system_prompt, user_prompt, temperature)


# ==========================================
# 記事構成の生成
# ==========================================

def generate_article_outline(keyword, research_data, api_key):
    """
    記事の構成案（見出し構造）を先に生成する。
    これにより、記事全体の流れを制御しやすくする。
    """
    current_api_key = api_key if api_key else GOOGLE_API_KEY
    product_info = load_product_info()

    # リサーチで取得した見出しを参考データとして追加
    existing_headings = ""
    if research_data and research_data.get("combined_headings"):
        headings_list = research_data["combined_headings"][:30]
        existing_headings = "\n".join(headings_list)

    system_prompt = """あなたはSEOに精通したプロのWebライター兼編集者です。
指定されたキーワードに対して、Google検索1位を狙える記事の構成案を作成してください。

## 構成ルール
1. H2見出しを5〜8個、各H2の下にH3見出しを2〜4個設定
2. 最初のH2は「〇〇とは？」系の導入
3. 途中に実用的な情報（育て方、選び方、使い方など）を配置
4. 最後の方に「よくある質問（FAQ）」と「まとめ」を配置
5. 見出しにはキーワードを自然に含める（不自然な詰め込みはNG）
6. 読者の検索意図（知りたいこと）に応える構成にする
7. 競合サイトの見出しを参考にしつつ、独自の切り口を加える"""

    user_prompt = f"""## ターゲットキーワード
{keyword}

## 競合サイトの見出し構造（参考）
{existing_headings}

## 取り扱い商品情報（この商品に関連する記事の場合、CTA要素を組み込む想定で）
{product_info[:3000]}

## 出力形式
以下のJSON形式で出力してください:
{{
    "title": "SEO最適化されたタイトル（32文字以内）",
    "meta_description": "メタディスクリプション（120文字以内）",
    "outline": [
        {{
            "h2": "H2見出しテキスト",
            "h3_list": ["H3見出し1", "H3見出し2", "H3見出し3"]
        }},
        ...
    ],
    "target_audience": "想定読者",
    "search_intent": "検索意図の分析"
}}"""

    result, error = generate_content_api(current_api_key, system_prompt, user_prompt, temperature=0.6)

    if error:
        return None, error

    try:
        # JSON部分を抽出
        cleaned = result.replace("```json", "").replace("```", "").strip()
        outline_data = json.loads(cleaned)
        return outline_data, None
    except json.JSONDecodeError as e:
        return None, f"構成案のJSON解析エラー: {e}\n生データ: {result[:500]}"


# ==========================================
# 記事本文の生成
# ==========================================

def generate_article_body(keyword, outline_data, research_data, api_key, custom_sources_text=""):
    """
    構成案に基づいてSEOブログ記事の本文を生成する。
    JetBサイト風の読みやすい記事を目指す。
    custom_sources_text: source_loaderから取得した独自ソースのテキスト
    """
    current_api_key = api_key if api_key else GOOGLE_API_KEY
    product_info = load_product_info()

    # リサーチデータを整形
    source_data = ""
    if research_data and research_data.get("combined_content"):
        source_data = research_data["combined_content"][:15000]

    # 構成案をテキスト化
    outline_text = ""
    for section in outline_data.get("outline", []):
        outline_text += f"\n## {section['h2']}\n"
        for h3 in section.get("h3_list", []):
            outline_text += f"### {h3}\n"

    system_prompt = f"""あなたは、SEOライティングのプロフェッショナルです。
以下の指示に従って、WordPressブログ用のSEO記事を執筆してください。

## ★最重要：文体ルール（これがこの記事の命）
1. **AI臭を完全排除する**:
   - 「〜と言えるでしょう」「〜ではないでしょうか」「〜について解説します」のような定型フレーズを禁止
   - ChatGPTっぽい丁寧すぎる表現は使わない
   - 「いかがでしたでしょうか」は絶対に使うな
   - 同じ語尾が3回以上連続するのを禁止（「〜ます。〜ます。〜ます。」はNG）

2. **人間味のある自然な文体**:
   - 実際に詳しい人が友人に教えるような、温かみのある口調
   - 「実は〜」「ここがポイントで〜」「正直なところ〜」など、リアリティのある表現を使う
   - 体験談・実感を交えた表現（「やってみると分かるのですが〜」）
   - 適度にカジュアル、でも信頼感のある文体

3. **専門性と具体性**:
   - 数字やデータを積極的に引用する
   - 「なぜそうなのか」の理由を必ず添える
   - 曖昧な表現を避け、具体的な方法・手順を書く
   - 初心者でも分かるよう、専門用語にはカッコ書きで補足

## ★SEOライティングの技術ルール
1. **1文は40〜60文字以内**を目安に（長文は分割）
2. **段落は3〜4文で改行**する（読みやすさ重視）
3. **見出し（H2/H3）にキーワードを自然に含める**
4. **箇条書き・番号リスト**を効果的に使う
5. **太字（<strong>）**で重要ポイントを強調する
6. **内部リンク・外部リンク**の挿入ポイントを示す
7. **画像挿入ポイント**を【画像: 説明】で示す

## ★記事の構造ルール
1. 冒頭にリード文（100〜200文字）を入れる
2. 目次の後、本文に入る
3. 各H2セクションは300〜600文字
4. 記事全体で3000〜8000文字を目指す
5. 最後に「まとめ」セクションを入れる
6. FAQセクションにはSchema.org対応のマークアップを意識する

## ★商品への誘導（CTA）ルール
- 記事テーマに関連する商品がある場合、自然な流れで紹介する
- 「宣伝臭」を出さず、読者の課題解決として商品を提案する
- 購入リンクは「▶ 商品ページはこちら」などのテキストで設置
- 押し売りは絶対にしない、あくまで選択肢の一つとして提示

## ★出力形式
HTML形式で出力すること。WordPressに直接貼り付けられる形式。
- 見出し: <h2>, <h3>タグ
- 段落: <p>タグ
- 箇条書き: <ul><li>タグ
- 番号リスト: <ol><li>タグ
- 太字: <strong>タグ
- テーブル: <table>タグ（必要に応じて）
- 画像: <!-- 画像挿入: 説明 --> コメントで示す

## 商品情報（CTA挿入用）
{product_info[:5000]}
"""

    user_prompt = f"""## ターゲットキーワード
{keyword}

## 記事タイトル
{outline_data.get('title', keyword)}

## 記事構成（この見出し構造に従って執筆）
{outline_text}

## 想定読者
{outline_data.get('target_audience', '一般読者')}

## 検索意図
{outline_data.get('search_intent', 'キーワードに関する情報を知りたい')}

## 独自ソース（★最優先で参考にすること。専門家・社内資料の情報は信頼性が高い）
{custom_sources_text[:15000] if custom_sources_text else '（独自ソースなし）'}

## Web参考ソース（以下のデータを補助的な根拠として活用すること。ただしコピペ・丸写しは厳禁）
{source_data}

## 執筆開始
上記の構成に従い、SEO最適化されたブログ記事をHTML形式で執筆してください。
独自ソースの情報がある場合はそちらを優先的に活用し、正確で信頼性の高い記事にすること。
出力はHTMLのみ（<h2>から始まること。<html>や<body>タグは不要）。
"""

    result, error = generate_content_api(current_api_key, system_prompt, user_prompt, temperature=0.7)

    if error:
        return None, error

    # HTMLの整形
    article_html = result.strip()
    if article_html.startswith("```html"):
        article_html = article_html[7:]
    if article_html.startswith("```"):
        article_html = article_html[3:]
    if article_html.endswith("```"):
        article_html = article_html[:-3]
    article_html = article_html.strip()

    return article_html, None


# ==========================================
# 記事生成のメインフロー
# ==========================================

def generate_blog_article(keyword, api_key=None, do_research=True, max_sources=5):
    """
    キーワードからSEOブログ記事を一気通貫で生成する。

    Returns:
        dict: {
            "keyword": str,
            "title": str,
            "meta_description": str,
            "outline": dict,
            "article_html": str,
            "research_data": dict,
            "custom_sources_summary": dict,
            "generated_at": str,
            "error": str or None
        }
    """
    current_api_key = api_key if api_key else GOOGLE_API_KEY  

    print(f"\n{'='*60}")
    print(f"📝 ブログ記事生成開始: 「{keyword}」")
    print(f"{'='*60}")

    result = {
        "keyword": keyword,
        "title": "",
        "meta_description": "",
        "outline": None,
        "article_html": "",
        "research_data": None,
        "custom_sources_summary": None,
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "error": None
    }

    # ステップ0: 独自ソースの読み込み
    print("\n📂 ステップ0: 独自ソース読み込み...")
    custom_sources_text = source_loader.get_all_sources_text(keyword)
    sources_summary = source_loader.get_source_summary()
    result["custom_sources_summary"] = sources_summary
    print(f"  → ファイル: {sources_summary['total_file_count']}件 / Instagram: {sources_summary['instagram_count']}件")

    # ステップ1: Web情報収集
    research_data = None
    if do_research:
        print("\n📊 ステップ1: Web情報収集...")
        research_data = web_researcher.research_keyword(keyword, max_sources=max_sources)
        result["research_data"] = research_data
        print(f"  → {research_data['source_count']}件のソースを取得")
    else:
        print("\n📊 ステップ1: Web情報収集（スキップ）")

    # ステップ2: 構成案の生成
    print("\n📋 ステップ2: 記事構成案を生成中...")
    outline_data, outline_error = generate_article_outline(keyword, research_data, current_api_key)

    if outline_error:
        result["error"] = f"構成案生成エラー: {outline_error}"
        print(f"  ❌ {outline_error}")
        return result

    result["outline"] = outline_data
    result["title"] = outline_data.get("title", keyword)
    result["meta_description"] = outline_data.get("meta_description", "")
    print(f"  → タイトル: 「{result['title']}」")
    print(f"  → H2見出し数: {len(outline_data.get('outline', []))}個")

    # ステップ3: 記事本文の生成（独自ソースも渡す）
    print("\n✍️ ステップ3: 記事本文を生成中...")
    article_html, body_error = generate_article_body(
        keyword, outline_data, research_data, current_api_key,
        custom_sources_text=custom_sources_text
    )

    if body_error:
        result["error"] = f"本文生成エラー: {body_error}"
        print(f"  ❌ {body_error}")
        return result

    result["article_html"] = article_html
    print(f"  → 記事HTML: {len(article_html)}文字生成")

    print(f"\n✅ 記事生成完了!")
    return result


# ==========================================
# 記事の保存
# ==========================================

def save_article_html(article_data, filename=None):
    """
    生成した記事をHTMLファイルとして保存する。
    WordPressにコピペ可能な形式。
    """
    if not filename:
        # キーワードからファイル名を生成
        safe_keyword = article_data["keyword"].replace(" ", "_").replace("　", "_")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{safe_keyword}.html"

    filepath = os.path.join(ARTICLES_DIR, filename)

    # 完全なHTMLドキュメントとして保存（プレビュー用）
    full_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{article_data.get('title', '')}</title>
    <meta name="description" content="{article_data.get('meta_description', '')}">
    <style>
        body {{
            font-family: 'Hiragino Sans', 'Noto Sans JP', 'Meiryo', sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px 30px;
            line-height: 1.9;
            color: #333;
            background: #fafafa;
        }}
        h1 {{
            font-size: 1.8em;
            color: #1a1a1a;
            border-bottom: 3px solid #2d7d46;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        h2 {{
            font-size: 1.4em;
            color: #2d7d46;
            border-left: 4px solid #2d7d46;
            padding-left: 12px;
            margin-top: 40px;
            margin-bottom: 15px;
        }}
        h3 {{
            font-size: 1.15em;
            color: #444;
            margin-top: 25px;
            margin-bottom: 10px;
        }}
        p {{
            margin-bottom: 16px;
            font-size: 16px;
        }}
        ul, ol {{
            margin-bottom: 16px;
            padding-left: 28px;
        }}
        li {{
            margin-bottom: 6px;
        }}
        strong {{
            color: #c0392b;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 10px 14px;
            text-align: left;
        }}
        th {{
            background: #2d7d46;
            color: white;
        }}
        tr:nth-child(even) {{
            background: #f5f5f5;
        }}
        .meta-info {{
            background: #e8f5e9;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            font-size: 14px;
            color: #555;
        }}
        .cta-box {{
            background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
            border: 2px solid #2d7d46;
            border-radius: 10px;
            padding: 20px;
            margin: 25px 0;
            text-align: center;
        }}
        .cta-box a {{
            color: #2d7d46;
            font-weight: bold;
            text-decoration: none;
        }}
        blockquote {{
            border-left: 4px solid #2d7d46;
            padding: 10px 20px;
            background: #f9f9f9;
            margin: 15px 0;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="meta-info">
        <strong>キーワード:</strong> {article_data.get('keyword', '')}<br>
        <strong>生成日時:</strong> {article_data.get('generated_at', '')}<br>
        <strong>Meta Description:</strong> {article_data.get('meta_description', '')}
    </div>

    <h1>{article_data.get('title', '')}</h1>

    {article_data.get('article_html', '<p>記事の生成に失敗しました。</p>')}
</body>
</html>"""

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"💾 記事を保存しました: {filepath}")
        return filepath
    except Exception as e:
        print(f"保存エラー: {e}")
        return None


def save_article_wp_content(article_data, filename=None):
    """
    WordPressにコピペする用の本文HTMLのみを保存する。
    （<h2>〜のみ、<html>などは含まない）
    """
    if not filename:
        safe_keyword = article_data["keyword"].replace(" ", "_").replace("　", "_")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{safe_keyword}_wp.html"

    filepath = os.path.join(ARTICLES_DIR, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(article_data.get("article_html", ""))
        print(f"💾 WP用記事を保存しました: {filepath}")
        return filepath
    except Exception as e:
        print(f"保存エラー: {e}")
        return None


def save_article_json(article_data, filename=None):
    """記事データ全体をJSONで保存する（バックアップ・管理用）"""
    if not filename:
        safe_keyword = article_data["keyword"].replace(" ", "_").replace("　", "_")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{safe_keyword}.json"

    filepath = os.path.join(ARTICLES_DIR, filename)

    # research_dataは大きすぎる場合があるのでトリム
    save_data = article_data.copy()
    if save_data.get("research_data"):
        rd = save_data["research_data"].copy()
        # 統合テキストを圧縮
        if rd.get("combined_content") and len(rd["combined_content"]) > 5000:
            rd["combined_content"] = rd["combined_content"][:5000] + "...(略)"
        # ソースの詳細も圧縮
        if rd.get("sources"):
            for s in rd["sources"]:
                if s.get("content") and len(s["content"]) > 1000:
                    s["content"] = s["content"][:1000] + "...(略)"
        save_data["research_data"] = rd

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        print(f"💾 JSONバックアップ保存: {filepath}")
        return filepath
    except Exception as e:
        print(f"JSON保存エラー: {e}")
        return None


# テスト用
if __name__ == "__main__":
    import sys

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("環境変数 GEMINI_API_KEY を設定してください")
        sys.exit(1)

    keyword = "フィンガーライム 育て方"
    result = generate_blog_article(keyword, api_key=api_key)

    if result["error"]:
        print(f"エラー: {result['error']}")
    else:
        save_article_html(result)
        save_article_wp_content(result)
        save_article_json(result)
        print(f"\n記事タイトル: {result['title']}")
        print(f"文字数: {len(result['article_html'])}文字")
