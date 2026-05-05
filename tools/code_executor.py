import pandas as pd
import os
import sys
import io
import traceback
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from contextlib import redirect_stdout

# 这里假设 utils 模块在项目的正确位置，根据你的实际路径引入
from utils.logger import logger
from utils.path_tool import get_abs_path, ensure_dir

# 初始化中文字体（下载到 utils/fonts/ 目录）
from utils.setup_font import setup_chinese_font

# 预先应用中文字体，并拦截会重置 rcParams 的调用
setup_chinese_font()
try:
    import seaborn as sns
    _sns_original_set_style = sns.set_style

    def _patched_set_style(*args, **kwargs):
        _sns_original_set_style(*args, **kwargs)
        setup_chinese_font()

    sns.set_style = _patched_set_style
except ImportError:
    sns = None  # seaborn 未安装时跳过

_mpl_original_style_use = plt.style.use

def _patched_style_use(*args, **kwargs):
    _mpl_original_style_use(*args, **kwargs)
    setup_chinese_font()

plt.style.use = _patched_style_use


def execute_code(code: str, data_file: str, output_dir: str) -> tuple:
    """
    执行生成的 Pandas 代码，捕获控制台输出并自动收集图表

    Args:
        code: 要执行的Python代码
        data_file: 数据文件路径
        output_dir: 输出目录

    Returns:
        (执行结果文本/报错信息, 生成的图表路径列表)
    """
    try:
        # 再次确保字体已配置（应对多轮执行后 rcParams 被覆盖的情况）
        setup_chinese_font()

        logger.info(f"开始执行大模型生成的代码，目标文件: {data_file}")

        ensure_dir(output_dir)

        files_before_execution = set(os.listdir(output_dir))

        full_code = code

        # 准备执行环境 (注入常用的库，防止 LLM 忘记 import)
        exec_globals = {
            'pd': pd,
            'plt': plt,
            'sns': sns,
            'os': os,
            'output_dir': output_dir,
            'data_file': data_file
        }

        original_show = plt.show
        plt.show = lambda *args, **kwargs: logger.warning(
            "已拦截代码中的 plt.show() 调用。在服务端生成图表应仅使用 plt.savefig()")

        captured_output = io.StringIO()

        with redirect_stdout(captured_output):
            # 执行代码（含注入的字体初始化）
            exec(full_code, exec_globals)

        # 获取 LLM print 的所有数据结论
        execution_result = captured_output.getvalue()

        if not execution_result.strip():
            execution_result = "代码执行成功，但没有产生终端输出内容(print)。"

        logger.info("代码执行成功并捕获输出")

        # 收集新生成的图表
        visualization_paths = []
        files_after_execution = set(os.listdir(output_dir))
        new_files = files_after_execution - files_before_execution

        for file in new_files:
            if file.endswith(('.png', '.jpg', '.jpeg', '.html')):
                file_path = os.path.join(output_dir, file)
                visualization_paths.append(file_path)
                logger.info(f"成功收集到新生成的图表: {file_path}")

        return execution_result, visualization_paths

    except Exception as e:
        error_msg = f"执行代码时出错: {str(e)}\n"
        error_msg += traceback.format_exc()
        logger.error(f"代码执行失败:\n{error_msg}")
        return error_msg, []

    finally:
        plt.show = original_show
        plt.close('all')

