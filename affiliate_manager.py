import os
import json
import uuid

AFFILIATE_DATA_DIR = "blog_data"
AFFILIATE_DATA_FILE = os.path.join(AFFILIATE_DATA_DIR, "affiliate_links.json")

def _ensure_dir():
    if not os.path.exists(AFFILIATE_DATA_DIR):
        os.makedirs(AFFILIATE_DATA_DIR, exist_ok=True)

def load_affiliate_links():
    """
    登録されている全アフィリエイト商品のリストを取得する。
    戻り値の例: [{"id": "...", "name": "...", "feature": "...", "tag": "..."}, ...]
    """
    _ensure_dir()
    if not os.path.exists(AFFILIATE_DATA_FILE):
        return []
    
    try:
        with open(AFFILIATE_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"アフィリエイトデータ読み込みエラー: {e}")
        return []

def save_affiliate_links(links):
    """
    アフィリエイト商品のリストを保存する。
    """
    _ensure_dir()
    try:
        with open(AFFILIATE_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(links, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"アフィリエイトデータ保存エラー: {e}")
        return False

def add_affiliate_link(name, feature, tag):
    """
    新しいアフィリエイト商品を登録する。
    """
    links = load_affiliate_links()
    
    # 既存の同名商品があれば更新、なければ追加
    for link in links:
        if link["name"] == name:
            link["feature"] = feature
            link["tag"] = tag
            return save_affiliate_links(links)
    
    # 新規追加
    new_link = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "feature": feature,
        "tag": tag
    }
    links.append(new_link)
    return save_affiliate_links(links)

def delete_affiliate_link(link_id):
    """
    指定したIDのアフィリエイト商品を削除する。
    """
    links = load_affiliate_links()
    new_links = [l for l in links if l.get("id") != link_id]
    if len(links) != len(new_links):
        return save_affiliate_links(new_links)
    return False

def format_affiliate_list_for_prompt():
    """
    AIのプロンプトに注入するための、事前登録されたアフィリエイト商品リスト文字列を生成する。
    """
    links = load_affiliate_links()
    if not links:
        return ""
        
    prompt_text = "【以下は、あなたが記事内で自然にお勧めできるアフィリエイト商品のリストです】\n"
    for link in links:
        prompt_text += f"- 商品名: {link['name']}\n"
        prompt_text += f"  特徴・おすすめする読者層: {link['feature']}\n\n"
        
    return prompt_text

def replace_affiliate_placeholders(article_html):
    """
    生成されたHTML記事内の `[AFF_LINK: 商品名]` というプレースホルダーを、
    実際のアフィリエイトタグ（HTMLまたはWPショートコード）に自動置換する。
    """
    links = load_affiliate_links()
    if not links:
        return article_html
        
    for link in links:
        name = link["name"]
        tag = link["tag"]
        # プロンプトの指示により [AFF_LINK: 商品名] で出力されることを想定
        placeholder = f"[AFF_LINK: {name}]"
        
        # 実際に置き換える処理
        if placeholder in article_html:
            # HTML要素として自然に機能するよう、pタグやdivタグの中で置換される場合も考慮しつつ直接置換
            # または単独行にある場合は前後に少しマージンを取るなど。今回はシンプルに直接文字列置換
            article_html = article_html.replace(placeholder, tag)
            
    return article_html
