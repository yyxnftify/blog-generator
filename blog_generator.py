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
    model = "llama-3.3-70b-versatile"
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
    
    # APIキーからバックエンドを自動判定（安全策）
    backend = AI_BACKEND
    if api_key:
        if api_key.startswith("gsk_"):
            backend = "groq"
        elif api_key.startswith("AIza"):
            backend = "gemini"
            
    if backend == "groq":
        print(f"🤖 API Call: Groq (Key: {api_key[:4]}...)")
        groq_key = api_key if api_key else GROQ_API_KEY
        return generate_content_groq(groq_key, system_prompt, user_prompt, temperature)
    else:
        key_to_use = api_key if api_key else GOOGLE_API_KEY
        print(f"🤖 API Call: Gemini (Key: {key_to_use[:4]}...)")
        return generate_content_gemini(key_to_use, system_prompt, user_prompt, temperature)


# ==========================================
# 記事構成の生成
# ==========================================

def generate_article_outline(keyword, research_data, api_key):
    """
    記事の構成案（見出し構造）を先に生成する。
    これにより、記事全体の流れを制御しやすくする。
    """
    current_api_key = api_key if api_key else (GROQ_API_KEY if AI_BACKEND == "groq" else GOOGLE_API_KEY)
    product_info = load_product_info()

    # リサーチで取得した見出しを参考データとして追加
    existing_headings = ""
    if research_data and research_data.get("combined_headings"):
        headings_list = research_data["combined_headings"][:30]
        existing_headings = "\n".join(headings_list)

    system_prompt = """あなたはSEOに精通したプロのWebライター兼編集者です。
指定されたキーワードに対して、Google検索1位を狙える記事の構成案を作成してください。

## ★最重要：構成ルール
1. **H2見出しは最大5個まで**（厳選する）
2. **各H2の下に必ずH3見出しを2〜3個作る**（読みやすさのため小見出しを入れる）
3. H2見出しは「読者が思わずクリックしたくなる」キャッチーな表現にする
   - 良い例: 「フィンガーライム、知っていますか？」「実は○○だった！」「プロが教える○○のコツ」
   - 悪い例: 「フィンガーライムとは」「フィンガーライムの栽培方法」（←これは退屈）
4. 見出しのパターン例:
   - 読者への呼びかけ型: 「○○で困っていませんか？」
   - 驚き・発見型: 「意外と知らない○○の真実」
   - まとめ・提案型: 「○○を始めるなら、まずはここから」
5. 構成の流れ: 導入（読者の興味を引く）→ 本題（2〜3セクション）→ まとめ・CTA
6. FAQは見出しとしてではなく、最後のH2セクションとしてまとめる

## 出力形式
以下のJSON形式で出力してください。
{{
    "title": "SEO最適化されたタイトル（32文字以内。キャッチーに）",
    "meta_description": "メタディスクリプション（120文字以内）",
    "outline": [
        {{
            "h2": "キャッチーなH2見出し",
            "h3_list": ["具体的な小見出し1", "具体的な小見出し2"]
        }},
        ...
    ],
    "target_audience": "想定読者",
    "search_intent": "検索意図の分析"
}}"""

    user_prompt = f"""## ターゲットキーワード
{keyword}

## 競合サイトの見出し構造（参考。ただし見出しの数は5個以下に絞る）
{existing_headings}

## 取り扱い商品情報
{product_info[:3000]}

## 出力形式
JSONのみ出力してください。H2は最大5個、各H2の中にH3を必ず入れてください。
"""

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
    current_api_key = api_key if api_key else (GROQ_API_KEY if AI_BACKEND == "groq" else GOOGLE_API_KEY)
    product_info = load_product_info()

    # リサーチデータを整形
    source_data = ""
    if research_data and research_data.get("combined_content"):
        # 文字数制限（Groq対策: 15000 -> 5000）
        source_data = research_data["combined_content"][:5000]

    # 構成案をテキスト化
    outline_text = ""
    for section in outline_data.get("outline", []):
        outline_text += f"\n## {section['h2']}\n"
        for h3 in section.get("h3_list", []):
            outline_text += f"### {h3}\n"

    system_prompt = f"""あなたは、SEOライティングのプロフェッショナルです。
以下の指示に従って、WordPressブログ用のSEO記事を執筆してください。
参考サイト: https://jetb.co.jp のブログ記事のような、読み応えがあり中身の濃い記事を目指します。

## ★最重要：記事構成ルール
1. **見出し構造**: <h2>見出しの下に、必ず<h3>見出し（小見出し）を2〜3個入れること。
   - 悪い例：<h2>の下に長文がダラダラ続く（読みづらい）
   - 良い例：<h2>の下に短い導入 → <h3>小見出し → 本文 → <h3>小見出し → 本文
2. **情報の絞り込み**: 全てを網羅しようとせず、ターゲットキーワードに関連する重要なポイントに絞って深く書く。
3. **重複禁止**: 同じ内容（特に「品種確定苗の重要性」など）を何度も繰り返さない。一度詳しく書けばOK。
4. **冒頭リード文**: 読者の興味を引く「問いかけ」から始める。

## ★最重要：文体ルール（これがこの記事の命）
1. **AI臭を完全排除する**:
   - 「〜と言えるでしょう」「〜ではないでしょうか」禁止
   - 「いかがでしたでしょうか」禁止
   - 同じ語尾（〜ます。）の3連続禁止
2. **人間味のある自然な文体**:
   - 「実は〜」「ここだけの話ですが〜」のような表現を使う
   - 著者の感想「個人的には〜が好きです」を2〜3箇所入れる
   - 読者への呼びかけ「〜だと思いませんか？」を入れる

## ★SEOライティングの技術ルール
1. **段落は3〜4文で改行**する
2. **太字（<strong>）**で重要ポイントを強調する
3. **画像挿入ポイント**を<!-- 画像: 説明 -->で示す

## ★HTML出力形式（厳守）
- 記事の全体をHTMLタグで構成する
- `<h2>` タグで大見出し
- `<h3>` タグで小見出し
- `<p>` タグで本文
- `<ul><li>` タグで箇条書き
- **`[]` や `**` などのMarkdown記法はHTMLの中に混ぜないこと**

## 商品情報（CTA挿入用）
{product_info[:3000]}
"""

    user_prompt = f"""## ターゲットキーワード
{keyword}

## 記事タイトル
{outline_data.get('title', keyword)}

## 記事構成（この構成案に従うこと）
{outline_text}

## 独自ソース（最優先）
{custom_sources_text[:5000] if custom_sources_text else '（独自ソースなし）'}

## Web参考ソース（補助情報）
{source_data}

## ★執筆開始
SEO最適化されたブログ記事をHTML形式のみで出力してください。
`<h2>` から書き始めてください。
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
    # バックエンドに応じてAPIキーを選択
    if AI_BACKEND == "groq":
        current_api_key = api_key if api_key else GROQ_API_KEY
    else:
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
    print(f"  → ファイル: {sources_summary['total_file_count']}件 / Instagram: {sources_summary['instagram_count']}件 / Web・YouTube: {sources_summary['web_count']}件")

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
