@echo off
chcp 65001 >nul
echo ========================================
echo   Blog Article Generator 起動中...
echo   八ヶ岳ガーデンSHOP ブログ記事生成システム
echo ========================================
echo.

REM このバッチファイルのあるディレクトリに移動
cd /d "%~dp0"

REM 必要なライブラリがなければインストール
pip install streamlit requests beautifulsoup4 --quiet 2>nul

echo.
echo Streamlitを起動します...
echo ブラウザが自動で開きます。開かない場合は http://localhost:8501 にアクセスしてください。
echo.

streamlit run blog_app.py --server.port 8502

pause
