import os
from functools import partial
from utils.path_tool import get_abs_path
from utils.logger import logger


def load_prompt(file_name: str, fallback: str = '{"strategies": []}') -> str:
    """通用提示词加载器"""
    logger.debug(f"准备加载提示词文件: {file_name}")
    prompt_path = get_abs_path(file_name)

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        logger.info(f"成功加载提示词 [{file_name}]，共计 {len(content)} 字符")
        return content
    except FileNotFoundError:
        logger.warning(f"找不到提示词文件: {prompt_path}，启动兜底提示词。")
        return fallback
    except Exception as e:
        logger.error(f"读取提示词文件时发生未知异常: {str(e)}")
        return fallback


load_data_clean_prompt = partial(load_prompt, "data_clean_prompt.txt")
load_data_analysis_prompt = partial(load_prompt, "data_analysis_prompt.txt")
load_code_healing_prompt = partial(load_prompt, "code_healing_prompt.txt")
load_image_analysis_prompt = partial(load_prompt, "image_analysis_prompt.txt")
