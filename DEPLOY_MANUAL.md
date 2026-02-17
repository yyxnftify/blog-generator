# 📝 Blog Article Generator クラウドデプロイ手順書
# Streamlit Community Cloud で無料公開する手順

## 📋 前提条件
- GitHubアカウント ✅（済み）
- GCPサービスアカウント ✅（credentials.json は既にお持ち）
- ブログ記事フォルダの全ファイル

---

## Step 1: GitHubリポジトリを作成

### 1-1. GitHub で新しいリポジトリを作成
1. https://github.com/new にアクセス
2. リポジトリ名: `blog-generator` （お好みで変更OK）
3. **Private（プライベート）** を選択 ← 大事！
4. 「Create repository」をクリック

### 1-2. ローカルから push
コマンドプロンプトまたはPowerShellで以下を実行：

```powershell
cd "c:\Users\rokuz\OneDrive\デスクトップ\農関係\八ヶ岳ガーデン\AI\antigravityFILE\ブログ記事"

# Gitリポジトリ初期化
git init
git add .
git commit -m "初回コミット: ブログ記事自動生成システム"

# GitHubリモートを追加（YOUR_USERNAMEは自分のGitHubユーザー名に置き換え）
git remote add origin https://github.com/YOUR_USERNAME/blog-generator.git
git branch -M main
git push -u origin main
```

⚠️ `.gitignore` で `credentials.json` はプッシュされないので安全です。

---

## Step 2: Streamlit Community Cloud にデプロイ

### 2-1. Streamlit Cloud にサインイン
1. https://share.streamlit.io にアクセス
2. 「Sign in with GitHub」でGitHubアカウントでログイン

### 2-2. 新しいアプリをデプロイ
1. 「New app」をクリック
2. 以下を設定：
   - **Repository**: `YOUR_USERNAME/blog-generator`
   - **Branch**: `main`
   - **Main file path**: `blog_app.py`
3. 「Deploy!」をクリック

---

## Step 3: Secrets（シークレット）を設定

デプロイ後、アプリの設定画面で **Secrets** を設定します。
これは Streamlit Cloud がクラウド上で `credentials.json` の代わりに使う情報です。

### 3-1. 設定画面を開く
1. アプリのURL右上「⋮」メニュー → 「Settings」
2. 「Secrets」タブを開く

### 3-2. 以下の内容を貼り付ける

```toml
[gcp_service_account]
type = "service_account"
project_id = "あなたのプロジェクトID"
private_key_id = "あなたのキーID"
private_key = "-----BEGIN PRIVATE KEY-----\nあなたの秘密鍵\n-----END PRIVATE KEY-----\n"
client_email = "あなたのサービスアカウントメール"
client_id = "あなたのクライアントID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "あなたの証明書URL"
```

💡 `credentials.json` の中身をそのまま TOML形式に変換して貼ればOKです。
   Xポスト記事の Secrets_To_Copy.txt の内容を流用できます。

---

## Step 4: 動作確認

1. デプロイが完了すると、URLが発行されます
   例: `https://your-app-name.streamlit.app`
2. ブラウザでアクセスして動作確認
3. サイドバーに「☁️ クラウドモード（Google Sheets）」と表示されればOK！
4. スマホからも同じURLでアクセス可能

---

## 📱 使い方（デプロイ後）

### PC or スマホから
1. ブラウザで `https://your-app-name.streamlit.app` にアクセス
2. サイドバーで Gemini API Key を入力
3. キーワードを入力して記事生成！

### ソース共有について
- 「ソース管理」タブからファイルをアップロード → Google Sheets に保存
- 別のPCやスマホからも同じソースが参照可能！
- Instagramの投稿もどのデバイスからでも追加可能

---

## 🔄 更新方法

コードを変更した場合：
```powershell
cd "c:\Users\rokuz\OneDrive\デスクトップ\農関係\八ヶ岳ガーデン\AI\antigravityFILE\ブログ記事"
git add .
git commit -m "更新内容のメモ"
git push
```
→ Streamlit Cloud が自動的に再デプロイされます（1-2分）

---

## 🔒 パスワード保護（後から追加可能）

Secrets に以下を追記するだけ：
```toml
[passwords]
password = "あなたのパスワード"
```
blog_app.py の先頭に認証コードを追加します（必要になったら言ってください）。
