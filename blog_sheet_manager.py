"""
Blog Sheet Manager モジュール
Google Sheetsを使って、ブログ記事のソース・Instagram投稿・記事履歴を
クラウド上で管理する。

既存のXポスト用sheet_manager.pyと同じGCPサービスアカウントを使用し、
同じスプレッドシート内に別シートとして管理する。
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import datetime

import streamlit as st

# ==========================================
# 設定
# ==========================================

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# 認証ファイル（ローカル用）
CREDENTIALS_FILE = "credentials.json"

# 既存のXポスト用と同じスプレッドシートID
SHEET_ID = "1d4f4G11VFLSl13dbrHT2ALDpd5cxzfvP_C_Yy0qV8jI"

# ブログ用シート名（Xポスト用は sheet1 = 既存のまま）
SHEET_NAME_SOURCES = "ブログソース"
SHEET_NAME_INSTAGRAM = "Instagram"
SHEET_NAME_ARTICLES = "記事履歴"

# シートのヘッダー定義
HEADERS_SOURCES = [
    "ID", "ファイル名", "ファイル種類", "内容", "文字数", "登録日時"
]
HEADERS_INSTAGRAM = [
    "ID", "アカウント名", "キャプション", "投稿URL", "タグ", "登録日時"
]
HEADERS_ARTICLES = [
    "ID", "キーワード", "タイトル", "メタディスクリプション",
    "記事HTML", "ソース数", "文字数", "生成日時", "ステータス"
]


# ==========================================
# 認証・接続
# ==========================================

def get_client():
    """GCPサービスアカウントで認証する（Streamlit Cloud / ローカル両対応）"""
    # 1. Streamlit Cloud (Secrets) から読み込み
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
            return gspread.authorize(creds)
    except Exception:
        pass

    # 2. ローカルファイル (credentials.json) から読み込み
    # ブログ記事フォルダ内 または Xポスト記事フォルダ内を探す
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # まずブログ記事フォルダ内を確認
    local_creds = os.path.join(base_dir, CREDENTIALS_FILE)
    if not os.path.exists(local_creds):
        # Xポスト記事フォルダのcredentials.jsonを探す
        parent_dir = os.path.dirname(base_dir)
        xpost_creds = os.path.join(parent_dir, "Xポスト記事", CREDENTIALS_FILE)
        if os.path.exists(xpost_creds):
            local_creds = xpost_creds

    if not os.path.exists(local_creds):
        print("⚠ credentials.json が見つかりません")
        return None

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(local_creds, SCOPE)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"GCP認証エラー: {e}")
        return None


def get_spreadsheet():
    """スプレッドシートを取得する"""
    client = get_client()
    if not client:
        return None
    try:
        return client.open_by_key(SHEET_ID)
    except Exception as e:
        print(f"スプレッドシート取得エラー: {e}")
        return None


def get_or_create_sheet(sheet_name, headers):
    """
    指定名のシートを取得する。存在しない場合は新規作成する。
    """
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return None

    try:
        # 既存シートを探す
        worksheet = spreadsheet.worksheet(sheet_name)
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        # シートが存在しない場合は作成
        try:
            worksheet = spreadsheet.add_worksheet(
                title=sheet_name, rows=1000, cols=len(headers)
            )
            # ヘッダー行を追加
            worksheet.append_row(headers)
            print(f"✅ シート「{sheet_name}」を新規作成しました")
            return worksheet
        except Exception as e:
            print(f"シート作成エラー: {e}")
            return None
    except Exception as e:
        print(f"シート取得エラー ({sheet_name}): {e}")
        return None


def is_connected():
    """Google Sheetsに接続できるか確認する"""
    try:
        spreadsheet = get_spreadsheet()
        return spreadsheet is not None
    except Exception:
        return False


# ==========================================
# ソース管理（テキスト/PDF/Excel）
# ==========================================

def get_all_sources():
    """全ソースデータを取得する"""
    sheet = get_or_create_sheet(SHEET_NAME_SOURCES, HEADERS_SOURCES)
    if not sheet:
        return []
    try:
        records = sheet.get_all_records()
        return records
    except Exception as e:
        print(f"ソース取得エラー: {e}")
        return []


def add_source(filename, file_type, content):
    """ソースデータを追加する"""
    sheet = get_or_create_sheet(SHEET_NAME_SOURCES, HEADERS_SOURCES)
    if not sheet:
        return False

    try:
        # 次のIDを取得
        records = sheet.get_all_records()
        next_id = len(records) + 1

        # 内容が長すぎる場合はトリム（セルの文字数制限対策）
        if len(content) > 45000:
            content = content[:45000] + "\n...(以下省略)"

        row = [
            next_id,
            filename,
            file_type,
            content,
            len(content),
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ]
        sheet.append_row(row, value_input_option='RAW')
        print(f"✅ ソースを保存: {filename}")
        return True
    except Exception as e:
        print(f"ソース保存エラー: {e}")
        return False


def delete_source(source_id):
    """指定IDのソースを削除する"""
    sheet = get_or_create_sheet(SHEET_NAME_SOURCES, HEADERS_SOURCES)
    if not sheet:
        return False

    try:
        records = sheet.get_all_records()
        for i, record in enumerate(records):
            if record.get("ID") == source_id:
                # ヘッダー行(1) + データ行のインデックス(0始まり → +2)
                sheet.delete_rows(i + 2)
                print(f"✅ ソース削除: ID={source_id}")
                return True
        return False
    except Exception as e:
        print(f"ソース削除エラー: {e}")
        return False


def get_sources_text(keyword=""):
    """
    全ソースの内容を統合テキストとして返す。
    キーワードが指定された場合はマッチするものを優先。
    """
    sources = get_all_sources()
    if not sources:
        return ""

    parts = []
    for s in sources:
        content = s.get("内容", "")
        if content:
            parts.append(f"【{s.get('ファイル種類', 'ファイル')}: {s.get('ファイル名', '')}】\n{content}")

    return "\n\n===\n\n".join(parts)


# ==========================================
# Instagram管理
# ==========================================

def get_all_instagram():
    """全Instagramソースを取得する"""
    sheet = get_or_create_sheet(SHEET_NAME_INSTAGRAM, HEADERS_INSTAGRAM)
    if not sheet:
        return []
    try:
        records = sheet.get_all_records()
        return records
    except Exception as e:
        print(f"Instagram取得エラー: {e}")
        return []


def add_instagram(account_name, caption, post_url="", tags=""):
    """Instagramソースを追加する"""
    sheet = get_or_create_sheet(SHEET_NAME_INSTAGRAM, HEADERS_INSTAGRAM)
    if not sheet:
        return False

    try:
        records = sheet.get_all_records()
        next_id = len(records) + 1

        row = [
            next_id,
            account_name.strip(),
            caption.strip(),
            post_url.strip(),
            tags.strip(),
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ]
        sheet.append_row(row, value_input_option='RAW')
        print(f"✅ Instagramソース保存: @{account_name}")
        return True
    except Exception as e:
        print(f"Instagram保存エラー: {e}")
        return False


def delete_instagram(insta_id):
    """指定IDのInstagramソースを削除する"""
    sheet = get_or_create_sheet(SHEET_NAME_INSTAGRAM, HEADERS_INSTAGRAM)
    if not sheet:
        return False

    try:
        records = sheet.get_all_records()
        for i, record in enumerate(records):
            if record.get("ID") == insta_id:
                sheet.delete_rows(i + 2)
                print(f"✅ Instagram削除: ID={insta_id}")
                return True
        return False
    except Exception as e:
        print(f"Instagram削除エラー: {e}")
        return False


def get_instagram_text(keyword=""):
    """
    Instagramソースの内容を統合テキストとして返す。
    """
    sources = get_all_instagram()
    if not sources:
        return ""

    relevant = []
    for s in sources:
        if not keyword:
            relevant.append(s)
        else:
            search_text = (str(s.get("キャプション", "")) + str(s.get("タグ", ""))).lower()
            if any(kw.lower() in search_text for kw in keyword.split()):
                relevant.append(s)

    if not relevant:
        relevant = sources  # 関連なければ全部返す

    parts = []
    for s in relevant:
        part = f"【Instagram @{s.get('アカウント名', '')}】\n{s.get('キャプション', '')}"
        if s.get("投稿URL"):
            part += f"\n(出典: {s['投稿URL']})"
        parts.append(part)

    return "\n\n---\n\n".join(parts)


# ==========================================
# 記事履歴管理
# ==========================================

def save_article_record(article_data):
    """生成した記事をスプレッドシートに記録する"""
    sheet = get_or_create_sheet(SHEET_NAME_ARTICLES, HEADERS_ARTICLES)
    if not sheet:
        return False

    try:
        records = sheet.get_all_records()
        next_id = len(records) + 1

        import re
        article_html = article_data.get("article_html", "")
        plain_text = re.sub(r'<[^>]+>', '', article_html)

        # 記事HTMLが長い場合はトリム
        html_to_save = article_html
        if len(html_to_save) > 45000:
            html_to_save = html_to_save[:45000] + "\n<!-- 以下省略 -->"

        row = [
            next_id,
            article_data.get("keyword", ""),
            article_data.get("title", ""),
            article_data.get("meta_description", ""),
            html_to_save,
            article_data.get("custom_sources_summary", {}).get("total_count", 0) if article_data.get("custom_sources_summary") else 0,
            len(plain_text),
            article_data.get("generated_at", ""),
            "生成済み"
        ]
        sheet.append_row(row, value_input_option='RAW')
        print(f"✅ 記事をスプレッドシートに保存: {article_data.get('title', '')}")
        return True
    except Exception as e:
        print(f"記事保存エラー: {e}")
        return False


def get_all_articles():
    """全記事履歴を取得する"""
    sheet = get_or_create_sheet(SHEET_NAME_ARTICLES, HEADERS_ARTICLES)
    if not sheet:
        return []
    try:
        records = sheet.get_all_records()
        return records
    except Exception as e:
        print(f"記事履歴取得エラー: {e}")
        return []


# ==========================================
# 統合: 全ソーステキスト取得
# ==========================================

def get_all_cloud_sources_text(keyword=""):
    """
    全クラウドソース（ファイル + Instagram）を統合してテキストとして返す。
    記事生成プロンプトに直接渡せる形式。
    """
    parts = []

    # ファイルソース
    file_text = get_sources_text(keyword)
    if file_text:
        parts.append("## ★ ファイルソース（独自情報）\n" + file_text)

    # Instagramソース
    insta_text = get_instagram_text(keyword)
    if insta_text:
        parts.append("## ★ Instagramソース（専門家投稿）\n" + insta_text)

    combined = "\n\n" + "=" * 40 + "\n\n".join(parts)

    # 長すぎる場合はトリム
    if len(combined) > 80000:
        combined = combined[:80000] + "\n...(以下省略)"

    return combined


def get_cloud_source_summary():
    """クラウドソースの状況サマリーを返す"""
    sources = get_all_sources()
    insta = get_all_instagram()

    text_count = sum(1 for s in sources if s.get("ファイル種類") == "text")
    pdf_count = sum(1 for s in sources if s.get("ファイル種類") == "pdf")
    excel_count = sum(1 for s in sources if s.get("ファイル種類") == "excel")
    image_count = sum(1 for s in sources if s.get("ファイル種類") == "image")

    return {
        "text_count": text_count,
        "pdf_count": pdf_count,
        "excel_count": excel_count,
        "image_count": image_count,
        "instagram_count": len(insta),
        "total_file_count": len(sources),
        "total_count": len(sources) + len(insta),
    }


# テスト用
if __name__ == "__main__":
    print("=== Blog Sheet Manager テスト ===")
    if is_connected():
        print("✅ Google Sheets接続成功！")
        summary = get_cloud_source_summary()
        print(f"ソース: {summary['total_file_count']}件")
        print(f"Instagram: {summary['instagram_count']}件")
    else:
        print("❌ Google Sheets接続失敗")
