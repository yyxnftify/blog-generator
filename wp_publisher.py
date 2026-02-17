"""
WordPress Publisher モジュール（スタブ版）
WordPress REST APIを使って記事を下書き投稿する。

※現在はスタブ（仮実装）。WordPress準備ができたら有効化する。
"""

import requests
import json
import base64

# ==========================================
# WordPress 接続設定
# ==========================================

# TODO: WordPress準備ができたら以下を設定する
WP_SITE_URL = ""  # 例: "https://sasayoshi-garden.com"
WP_USERNAME = ""  # WordPressのユーザー名
WP_APP_PASSWORD = ""  # アプリケーションパスワード


def configure(site_url, username, app_password):
    """WordPress接続情報を設定する"""
    global WP_SITE_URL, WP_USERNAME, WP_APP_PASSWORD
    WP_SITE_URL = site_url.rstrip("/")
    WP_USERNAME = username
    WP_APP_PASSWORD = app_password


def is_configured():
    """WordPress接続情報が設定されているか確認"""
    return bool(WP_SITE_URL and WP_USERNAME and WP_APP_PASSWORD)


def _get_auth_header():
    """Basic認証ヘッダーを生成する"""
    credentials = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def test_connection():
    """
    WordPress への接続をテストする。

    Returns:
        tuple: (成功フラグ, メッセージ)
    """
    if not is_configured():
        return False, "WordPress接続情報が設定されていません。"

    try:
        url = f"{WP_SITE_URL}/wp-json/wp/v2/posts?per_page=1"
        headers = _get_auth_header()
        headers["Content-Type"] = "application/json"

        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return True, "WordPress接続成功！"
        elif response.status_code == 401:
            return False, "認証エラー: ユーザー名またはアプリケーションパスワードが正しくありません。"
        else:
            return False, f"接続エラー: ステータスコード {response.status_code}"

    except Exception as e:
        return False, f"接続例外: {e}"


def create_draft(title, content, meta_description="", categories=None, tags=None):
    """
    WordPressに下書き記事を作成する。

    Args:
        title: 記事タイトル
        content: 記事の本文HTML
        meta_description: メタディスクリプション（Yoast/RankMath用）
        categories: カテゴリIDのリスト
        tags: タグIDのリスト

    Returns:
        tuple: (成功フラグ, 投稿データ or エラーメッセージ)
    """
    if not is_configured():
        return False, "WordPress接続情報が設定されていません。WordPress管理画面で設定してください。"

    try:
        url = f"{WP_SITE_URL}/wp-json/wp/v2/posts"
        headers = _get_auth_header()
        headers["Content-Type"] = "application/json"

        post_data = {
            "title": title,
            "content": content,
            "status": "draft",  # 常に下書きとして作成
        }

        # カテゴリとタグの設定
        if categories:
            post_data["categories"] = categories
        if tags:
            post_data["tags"] = tags

        # Yoast SEO / RankMath 用のメタデータ
        if meta_description:
            post_data["meta"] = {
                "_yoast_wpseo_metadesc": meta_description,
                "rank_math_description": meta_description,
            }

        response = requests.post(url, headers=headers, json=post_data, timeout=30)

        if response.status_code in [200, 201]:
            post_info = response.json()
            return True, {
                "id": post_info.get("id"),
                "title": post_info.get("title", {}).get("rendered", ""),
                "link": post_info.get("link", ""),
                "edit_link": f"{WP_SITE_URL}/wp-admin/post.php?post={post_info.get('id')}&action=edit",
                "status": post_info.get("status"),
            }
        else:
            return False, f"投稿エラー: {response.status_code} - {response.text[:500]}"

    except Exception as e:
        return False, f"投稿例外: {e}"


def get_categories():
    """WordPressのカテゴリ一覧を取得する"""
    if not is_configured():
        return []

    try:
        url = f"{WP_SITE_URL}/wp-json/wp/v2/categories?per_page=100"
        headers = _get_auth_header()
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return [
                {"id": cat["id"], "name": cat["name"], "slug": cat["slug"]}
                for cat in response.json()
            ]
    except Exception:
        pass

    return []


def get_tags():
    """WordPressのタグ一覧を取得する"""
    if not is_configured():
        return []

    try:
        url = f"{WP_SITE_URL}/wp-json/wp/v2/tags?per_page=100"
        headers = _get_auth_header()
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            return [
                {"id": tag["id"], "name": tag["name"], "slug": tag["slug"]}
                for tag in response.json()
            ]
    except Exception:
        pass

    return []
