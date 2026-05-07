"""
配置 matplotlib 中文字体，解决图表中文显示方块问题。
"""
import os
import glob
from utils.path_tool import get_abs_path
from utils.logger import get_logger
import matplotlib
matplotlib.use('Agg')  # 非 GUI 后端，避免 WSL/Tkinter 报错
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

_logger = get_logger()


def _clear_font_cache():
    """清除 matplotlib 字体缓存，强制下次启动时重新扫描。"""
    try:
        cache_dir = matplotlib.get_cachedir()
        for cache_file in glob.glob(os.path.join(cache_dir, "fontlist-*.json")):
            os.remove(cache_file)
    except Exception:
        pass


def setup_chinese_font():
    font_dir = os.path.join(os.path.dirname(get_abs_path("path_tool.py")), "fonts")

    # 候选字体文件（按优先级排列）
    CANDIDATES = [
        ("NotoSansCJKsc.otf",  "Noto Sans CJK SC"),
        ("SourceHanSansSC.otf", "Source Han Sans SC"),
    ]

    # 先清缓存再注册，确保字体名能被正确识别
    _clear_font_cache()
    fm._load_fontmanager(try_read_cache=False)

    for filename, expected_name in CANDIDATES:
        font_path = os.path.join(font_dir, filename)
        if not os.path.exists(font_path):
            continue

        try:
            # 注册字体到 fontManager
            fm.fontManager.addfont(font_path)

            # 尝试多个可能的字体名
            font_names_to_try = list(dict.fromkeys([
                expected_name,
                filename.replace(".otf", ""),
                filename.replace(".otf", "").replace("SC", " SC"),
            ]))

            for name in font_names_to_try:
                if name in [f.name for f in fm.fontManager.ttflist]:
                    # 插入到 font.sans-serif 首位
                    current = list(plt.rcParams.get('font.sans-serif', []))
                    if name in current:
                        current.remove(name)
                    plt.rcParams['font.sans-serif'] = [name] + current
                    plt.rcParams['axes.unicode_minus'] = False
                    _logger.info(f"matplotlib 中文字体配置完成! (family: {name})")
                    return
        except Exception as e:
            _logger.warning(f"字体注册失败: {font_path} - {e}")
            continue

    _logger.warning("未找到中文字体文件，跳过字体配置")


if __name__ == "__main__":
    setup_chinese_font()
