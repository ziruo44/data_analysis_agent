"""下载中文字体到本地"""
import os
import urllib.request

from utils.path_tool import get_abs_path

font_dir = os.path.join(os.path.dirname(get_abs_path("path_tool.py")), "fonts")
os.makedirs(font_dir, exist_ok=True)

urls = [
    ("https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf", "NotoSansCJKsc.otf"),
    ("https://github.com/adobe-fonts/source-han-sans/raw/release/OTF/SimplifiedChinese/SourceHanSansSC-Regular.otf", "SourceHanSansSC.otf"),
]

for url, filename in urls:
    font_path = os.path.join(font_dir, filename)
    if os.path.exists(font_path):
        print(f"字体已存在: {font_path}")
        continue
    try:
        print(f"正在下载: {url}")
        urllib.request.urlretrieve(url, font_path)
        print(f"下载成功: {font_path}")
    except Exception as e:
        print(f"失败: {e}")
