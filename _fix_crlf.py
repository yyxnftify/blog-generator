"""改行コードをLFに変換するスクリプト"""
import os

files = [
    'blog_app.py',
    'blog_generator.py',
    'blog_sheet_manager.py',
    'source_loader.py',
    'web_researcher.py',
    'wp_publisher.py',
    'requirements.txt',
    'DEPLOY_MANUAL.md',
    '.gitignore',
    '.gitattributes',
    os.path.join('.streamlit', 'config.toml'),
    os.path.join('blog_data', 'product_info.txt'),
]

count = 0
for f in files:
    if os.path.exists(f):
        data = open(f, 'rb').read()
        new = data.replace(b'\r\n', b'\n')
        if data != new:
            open(f, 'wb').write(new)
            count += 1
            print(f'Fixed: {f}')
        else:
            print(f'OK: {f}')
    else:
        print(f'Skip: {f}')

print(f'\nTotal fixed: {count}')
