"""
Web Researcher モジュール
キーワードからネット上の関連情報を自動収集し、
記事生成のソースデータとして提供する。
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import random
import concurrent.futures

# ユーザーエージェント一覧（ブロック回避用）
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def get_headers():
    """ランダムなユーザーエージェントでヘッダーを生成"""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
    }


def search_google(keyword, num_results=8):
    """
    Google検索でキーワードの上位ページURLを取得する。
    ※Google検索APIの代わりに簡易スクレイピングを使用。
    制限がかかる場合はDuckDuckGoにフォールバック。
    """
    urls = []

    # まずDuckDuckGoで検索（レート制限が緩い）
    urls = _search_duckduckgo(keyword, num_results)

    if not urls:
        # フォールバック: Google検索
        urls = _search_google_direct(keyword, num_results)

    return urls


def _search_duckduckgo(keyword, num_results=8):
    """DuckDuckGo HTMLから検索結果を取得"""
    try:
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(keyword)}"
        response = requests.get(url, headers=get_headers(), timeout=15)

        if response.status_code != 200:
            print(f"  DuckDuckGo検索失敗: ステータス {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        # DuckDuckGo HTML版の結果リンクを取得
        for link in soup.find_all("a", class_="result__a"):
            href = link.get("href", "")
            # DuckDuckGoのリダイレクトURLからactualのURLを抽出
            if "uddg=" in href:
                import urllib.parse
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                if "uddg" in parsed:
                    actual_url = parsed["uddg"][0]
                    if _is_valid_url(actual_url):
                        results.append(actual_url)
            elif href.startswith("http") and _is_valid_url(href):
                results.append(href)

            if len(results) >= num_results:
                break

        print(f"  DuckDuckGo検索: {len(results)}件のURL取得")
        return results

    except Exception as e:
        print(f"  DuckDuckGo検索エラー: {e}")
        return []


def _search_google_direct(keyword, num_results=8):
    """Google検索から結果URLを取得（フォールバック）"""
    try:
        url = f"https://www.google.co.jp/search?q={requests.utils.quote(keyword)}&hl=ja&num={num_results}"
        response = requests.get(url, headers=get_headers(), timeout=15)

        if response.status_code != 200:
            print(f"  Google検索失敗: ステータス {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/url?q=" in href:
                actual_url = href.split("/url?q=")[1].split("&")[0]
                if _is_valid_url(actual_url):
                    results.append(actual_url)

            if len(results) >= num_results:
                break

        print(f"  Google検索: {len(results)}件のURL取得")
        return results

    except Exception as e:
        print(f"  Google検索エラー: {e}")
        return []


def _is_valid_url(url):
    """有効な記事URLかチェック（広告やSNSを除外）"""
    exclude_domains = [
        "google.", "youtube.", "twitter.", "facebook.",
        "instagram.", "amazon.", "rakuten.", "yahoo.",
        "pinterest.", "tiktok.", "linkedin.",
    ]
    for domain in exclude_domains:
        if domain in url.lower():
            return False
    return url.startswith("http")


def extract_page_content(url, max_chars=5000):
    """
    指定URLのページ本文を抽出する。
    HTML構造からメインコンテンツを取得し、テキストに変換する。
    """
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        response.encoding = response.apparent_encoding

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # 不要な要素を除去
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        # タイトル取得
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # メタディスクリプション取得
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")

        # 見出し構造を取得
        headings = []
        for h_tag in soup.find_all(["h1", "h2", "h3"]):
            text = h_tag.get_text(strip=True)
            if text and len(text) > 2:
                headings.append(f"[{h_tag.name.upper()}] {text}")

        # 本文テキストを取得
        # articleタグ優先、なければmain、なければbody
        content_area = soup.find("article") or soup.find("main") or soup.find("body")

        if not content_area:
            return None

        # パラグラフを優先的に取得
        paragraphs = content_area.find_all("p")
        if paragraphs:
            text_content = "\n".join([
                p.get_text(strip=True) for p in paragraphs
                if len(p.get_text(strip=True)) > 15  # 短すぎるものは除外
            ])
        else:
            text_content = content_area.get_text(separator="\n", strip=True)

        # テキストの整形
        text_content = re.sub(r'\n{3,}', '\n\n', text_content)
        text_content = text_content[:max_chars]

        return {
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "headings": headings[:20],  # 上位20見出しまで
            "content": text_content,
        }

    except Exception as e:
        print(f"  ページ取得エラー ({url[:60]}...): {e}")
        return None


def research_keyword(keyword, max_sources=5):
    """
    キーワードに関するWeb情報を包括的に収集する。
    複数ソースから情報を集め、記事生成に使えるデータを返す。

    Returns:
        dict: {
            "keyword": str,
            "sources": list[dict],  # 取得した各ページの情報
            "combined_headings": list[str],  # 全ソースの見出し一覧
            "combined_content": str,  # 全ソースの内容を統合
            "source_count": int,
        }
    """
    print(f"\n🔍 リサーチ開始: 「{keyword}」")

    # 検索実行
    urls = search_google(keyword, num_results=max_sources + 3)

    if not urls:
        print("  ⚠ 検索結果が取得できませんでした")
        return {
            "keyword": keyword,
            "sources": [],
            "combined_headings": [],
            "combined_content": "",
            "source_count": 0,
        }

    # 各ページの内容を並列で取得（超高速化）
    sources = []
    all_headings = []
    all_content_parts = []
    
    urls_to_fetch = urls[:max_sources + 3]
    print(f"  🚀 {len(urls_to_fetch)}件のURLを並列処理で取得中...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(extract_page_content, url): url for url in urls_to_fetch}
        for future in concurrent.futures.as_completed(future_to_url):
            if len(sources) >= max_sources:
                break
                
            url = future_to_url[future]
            try:
                page_data = future.result()
                if page_data and page_data["content"] and len(page_data["content"]) > 100:
                    print(f"  ✅ 取得成功: {page_data['title'][:40]}...")
                    sources.append(page_data)
                    all_headings.extend(page_data["headings"])
                    all_content_parts.append(
                        f"【出典: {page_data['title'][:60]}】\n{page_data['content'][:3000]}"
                    )
                else:
                    print(f"  ⚠ コンテンツ不足: {url[:40]}...")
            except Exception as e:
                print(f"  ❌ 取得エラー {url[:40]}...: {e}")

    # 結果を統合
    combined_content = "\n\n---\n\n".join(all_content_parts)

    # 内容が多すぎる場合はトリム
    if len(combined_content) > 30000:
        combined_content = combined_content[:30000] + "\n...(以下略)"

    result = {
        "keyword": keyword,
        "sources": sources,
        "combined_headings": list(set(all_headings)),  # 重複除去
        "combined_content": combined_content,
        "source_count": len(sources),
    }

    print(f"  ✅ リサーチ完了: {len(sources)}件のソースを取得")
    return result


def research_multiple_keywords(keywords, max_sources_per_keyword=3):
    """
    複数キーワードでリサーチを実行し、結果を統合する。
    例: ["フィンガーライム 育て方", "フィンガーライム 冬越し"]
    """
    all_results = []
    for kw in keywords:
        result = research_keyword(kw, max_sources=max_sources_per_keyword)
        all_results.append(result)
        time.sleep(2)  # キーワード間の待ち時間

    return all_results


# テスト用
if __name__ == "__main__":
    result = research_keyword("フィンガーライム 育て方", max_sources=3)
    print(f"\n=== リサーチ結果 ===")
    print(f"キーワード: {result['keyword']}")
    print(f"ソース数: {result['source_count']}")
    for s in result['sources']:
        print(f"  - {s['title'][:50]}")
    print(f"見出し数: {len(result['combined_headings'])}")
    print(f"統合テキスト長: {len(result['combined_content'])}文字")
