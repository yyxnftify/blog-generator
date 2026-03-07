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
import re
import time
from datetime import datetime

import web_researcher
import source_loader
import prompts

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


def generate_content_api(api_key, system_prompt, user_prompt, temperature=0.7, max_retries=3):
    """
    現在のバックエンド設定に応じてAPIを叩く（統一インターフェース）
    ★エラー時の自動リトライ機能付き
    """
    
    # APIキーからバックエンドを自動判定（安全策）
    backend = AI_BACKEND
    if api_key:
        if api_key.startswith("gsk_"):
            backend = "groq"
        elif api_key.startswith("AIza"):
            backend = "gemini"
            
    for attempt in range(max_retries):
        if backend == "groq":
            if attempt == 0:
                print(f"🤖 API Call: Groq (Key: {api_key[:4]}...)")
            groq_key = api_key if api_key else GROQ_API_KEY
            result, error = generate_content_groq(groq_key, system_prompt, user_prompt, temperature)
        else:
            key_to_use = api_key if api_key else GOOGLE_API_KEY
            if attempt == 0:
                print(f"🤖 API Call: Gemini (Key: {key_to_use[:4]}...)")
            result, error = generate_content_gemini(key_to_use, system_prompt, user_prompt, temperature)
            
        if not error:
            return result, None
            
        # 429エラーなどの場合、少し待ってからリトライ
        if "429" in error or "Quota" in error or "Too Many Requests" in error:
            wait_time = (attempt + 1) * 3  # 3秒, 6秒, 9秒と待機時間を増やす
            print(f"    ⚠ API制限に到達 (Attempt {attempt+1}/{max_retries}). {wait_time}秒後にリトライします...")
            time.sleep(wait_time)
            continue
        else:
            # 429以外の致命的なエラーはすぐ返す
            return None, error
            
    return None, f"APIの呼び出しに{max_retries}回失敗しました。最新のエラー: {error}"


# ==========================================
# 記事構成の生成
# ==========================================

def generate_article_outline(keyword, research_data, api_key, custom_sources_text="", target_product=""):
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
        
    # 独自ソースから関連情報を抽出（トークン節約＆構成案への反映）
    relevant_custom_info = extract_relevant_info(keyword, custom_sources_text, max_chars=3000)

    # configのプロンプトを使用
    system_prompt = prompts.OUTLINE_SYSTEM_PROMPT

    user_prompt = f"""## ターゲットキーワード
{keyword}

## 競合サイトの見出し構造（参考。ただし見出しの数は5〜6個に厳選すること）
{existing_headings}

## 独自ソース（今回書きたい内容の最重要ベース情報）
{relevant_custom_info}

## 取り扱い商品情報
{product_info[:3000]}
"""

    if target_product:
        user_prompt += f"\n## 推し商品（記事のどこかで自然に紹介する目標）\n{target_product}\n"

    user_prompt += "\n## 出力形式\nJSONのみ出力してください。各H2の中にH3を必ず入れてください。\n"

    result, error = generate_content_api(current_api_key, system_prompt, user_prompt, temperature=0.6)

    if error:
        return None, error

    try:
        # JSON部分を抽出
        cleaned = result.replace("```json", "").replace("```", "").strip()
        
        # サニタイズ: 最後のカンマ（,）の後に閉じ括弧が来るパターン（LLMの常見ミス）を自己修復
        cleaned = re.sub(r',\s*([\]}])', r'\1', cleaned)
        # 制御文字の除去
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)
        
        outline_data = json.loads(cleaned)
        return outline_data, None
    except json.JSONDecodeError as e:
        print(f"⚠ JSON自己修復を試みましたが失敗しました: {e}")
        # さらに強力な修復を試みる（最後の手段）
        try:
             import ast
             outline_data = ast.literal_eval(cleaned)
             return outline_data, None
        except Exception as eval_e:
             return None, f"構成案のJSON解析に完全に失敗しました: {e}\n生データ: {result[:500]}"


def extract_relevant_info(query, text, max_chars=4000):
    """
    指定されたクエリ（見出しなど）に関連する段落だけをテキスト全体から抽出する。
    これにより、LLMに不要なノイズを与えず、トークン数の節約と精度の向上を図る。
    """
    if not text or not query:
        return text[:max_chars] if text else "(情報なし)"
        
    # 日本語のクエリから重要そうな単語を抽出（記号で分割し、2文字以上を対象）
    words = [w for w in re.split(r'[\s、。！？,.\-「」『』()（）]+', query) if len(w) >= 2]
    if not words:
        return text[:max_chars]
        
    # 古い実装: paragraphs = text.split('\n\n') は改行1個の段落を捉えられない
    # 新しい実装: 1個以上の改行で確実に分割する
    paragraphs = re.split(r'\n+', text)
    scored_paragraphs = []
    
    for i, p in enumerate(paragraphs):
        p = p.strip()
        if len(p) < 15:
            continue
        score = 0
        p_lower = p.lower()
        for w in words:
            if w.lower() in p_lower:
                score += len(w) * 2
        
        # 最初の数段落（ソースの冒頭や要約など）はボーナス点
        if i < 3:
            score += 5
            
        scored_paragraphs.append((score, i, p))
        
    # スコアの高い順にソート
    scored_paragraphs.sort(key=lambda x: x[0], reverse=True)
    
    top_paragraphs = []
    current_len = 0
    for score, i, p in scored_paragraphs:
        if current_len + len(p) > max_chars:
            break
        # 全く関連しない（score=0）段落は、すでにある程度データが集まっていれば捨てる
        if score == 0 and current_len > max_chars / 2:
            break
            
        top_paragraphs.append((i, p))
        current_len += len(p) + 2
        
    # 抽出した段落を元のファイル上の出現順序に戻す（自然な文脈を保つため）
    top_paragraphs.sort(key=lambda x: x[0])
    
    result_text = "\n\n".join([p for i, p in top_paragraphs])
    if not result_text.strip():
        return "(該当する詳細情報は見つかりませんでした)"
        
    return result_text


# ==========================================
# 記事本文の生成
# ==========================================

def generate_article_body(keyword, outline_data, research_data, api_key, custom_sources_text="", progress_callback=None, target_product=""):
    """
    構成案に基づいてSEOブログ記事の本文を生成する。
    【Ver2.0】見出し（H2）ごとに個別にAIを呼び出し、内容を限界まで濃く・深くする方式に変更。
    """
    current_api_key = api_key if api_key else (GROQ_API_KEY if AI_BACKEND == "groq" else GOOGLE_API_KEY)
    product_info = load_product_info()

    # リサーチデータ全体と独自ソース全体を保持（ここではまだ切り詰めない）
    full_source_data = ""
    if research_data and research_data.get("combined_content"):
        full_source_data = research_data["combined_content"]
        
    full_custom_sources = custom_sources_text if custom_sources_text else ""

    full_article_html = ""
    
    # 構成案の見出し（H2）ごとにループして生成
    sections = outline_data.get("outline", [])
    
    for index, section in enumerate(sections):
        h2_title = section['h2']
        h3_list = section.get('h3_list', [])
        
        # この章専用の構成テキストを作成
        section_outline = f"## {h2_title}\n"
        for h3 in h3_list:
            section_outline += f"### {h3}\n"
            
        # 前のセクションの文脈（不自然な繋がりを防ぐため）
        if index == 0:
            previous_context = "これは記事の【最初のセクション】です。読者の興味を強く惹きつける「導入（リード文）」の役割も兼ねて、魅力的に書き出してください。"
        elif index == len(sections) - 1:
            previous_context = f"これは記事の【最後のセクション（まとめ等）】です。全体を総括しつつ、読者の次の行動（CTA）を自然に促してください。直前のH2は「{sections[index-1]['h2']}」でした。"
        else:
            previous_context = f"直前のH2は「{sections[index-1]['h2']}」でした。前の文脈を自然に引き継ぎながら本文を展開してください。"

        # スマート抽出（RAG風）：このH2/H3に関連する情報だけを抽出
        query_text = f"{keyword} {h2_title} " + " ".join(h3_list)
        section_custom_sources = extract_relevant_info(query_text, full_custom_sources, max_chars=3000)
        section_web_sources = extract_relevant_info(query_text, full_source_data, max_chars=4000)

        # プロンプトを専用ファイルから読み込み
        import affiliate_manager
        affiliate_list_prompt = affiliate_manager.format_affiliate_list_for_prompt()
        
        system_prompt = prompts.BODY_SYSTEM_PROMPT.format(
            affiliate_list_prompt=affiliate_list_prompt,
            product_info=product_info[:2000]
        )

        user_prompt = prompts.BODY_USER_PROMPT_TEMPLATE.format(
            keyword=keyword,
            section_outline=section_outline,
            previous_context=previous_context,
            section_custom_sources=section_custom_sources,
            section_web_sources=section_web_sources,
            h2_title=h2_title
        )
        
        if target_product:
            user_prompt += f"\n\n※特に、今回は「{target_product}」を読者に自然に紹介・おすすめすることを意識してください。"
        
        # API呼び出し（進捗がわかるようにprint & callback）
        msg = f"✍️ 第{index+1}章を執筆中 ({index+1}/{len(sections)}): {h2_title[:15]}..."
        print(f"  └ {msg}")
        if progress_callback:
            progress_callback(msg)
            
        result, error = generate_content_api(current_api_key, system_prompt, user_prompt, temperature=0.7)
        
        if error:
            print(f"    ⚠ この章の生成でエラー発生: {error}")
            full_article_html += f"<h2>{h2_title}</h2>\n<p>※生成エラーにより本文をスキップしました。</p>\n\n"
            continue
            
        # HTMLの整形（不要なマークダウン記法の除去）
        html_chunk = result.strip()
        if html_chunk.startswith("```html"):
            html_chunk = html_chunk[7:]
        if html_chunk.startswith("```"):
            html_chunk = html_chunk[3:]
        if html_chunk.endswith("```"):
            html_chunk = html_chunk[:-3]
            
        full_article_html += html_chunk.strip() + "\n\n"

    if not full_article_html.strip():
         return None, "すべての章の生成に失敗しました"
         
    # ▼【自動化】AIが出力した [AFF_LINK: 商品名] を、実際のアフィリエイトタグに完全自動置換する
    import affiliate_manager
    full_article_html = affiliate_manager.replace_affiliate_placeholders(full_article_html)
         
    return full_article_html, None


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
