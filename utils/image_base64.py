"""
图片 Base64 编码工具
===================
将图片文件转换为 Base64 数据 URI 格式，支持单张和批量处理
"""

import base64
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List, Union


def encode_image_to_base64(image_path: str) -> str:
    """
    将单张图片编码为 Base64 数据 URI 格式

    参数:
        image_path: 图片文件的绝对路径

    返回:
        str: 格式为 "data:image/{type};base64,..." 的完整数据 URI 字符串
    """
    ext = os.path.splitext(image_path)[1].lower()

    mime_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }

    mime_type = mime_map.get(ext, 'application/octet-stream')

    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode('utf-8')
        return f"data:{mime_type};base64,{encoded}"


def encode_images_to_base64(image_paths: Union[str, List[str]]) -> List[str]:
    """
    将单张或多张图片编码为 Base64 数据 URI 列表

    参数:
        image_paths: 单个图片路径(字符串)或多个路径(列表)

    返回:
        List[str]: Base64 数据 URI 字符串列表
    """
    if isinstance(image_paths, str):
        image_paths = [image_paths]
    with ThreadPoolExecutor(max_workers=min(4, len(image_paths))) as pool:
        return list(pool.map(encode_image_to_base64, image_paths))


def find_images_in_dir(directory: str) -> List[str]:
    """
    查找目录下所有图片

    参数:
        directory: 目录路径

    返回:
        List[str]: 图片绝对路径列表
    """
    try:
        files = os.listdir(directory)
    except FileNotFoundError:
        return []

    image_paths = []
    for file in files:
        if file.endswith(('.png', '.jpg', '.jpeg')):
            image_paths.append(os.path.join(directory, file))
    return image_paths


if __name__ == "__main__":
    print("=" * 60)
    print("图片 Base64 编码工具")
    print("=" * 60)

    # 示例：给定目录转 base64
    test_dir = "/mnt/d/ziruo_project/data_analysis_agent/output/earthquake_data_tsunami"
    images = find_images_in_dir(test_dir)
    print(f"\n{test_dir} 下的图片:")
    for img in images:
        print(f"  - {img}")

    base64_list = encode_images_to_base64(images)
    print(f"\n已编码 {len(base64_list)} 张图片为 Base64")
