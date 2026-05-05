import os
import functools
from datetime import datetime


@functools.lru_cache(maxsize=64)
def get_abs_path(file_name: str) -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    for root, dirs, files in os.walk(project_root):
        if file_name in files:
            return os.path.join(root, file_name)
    return os.path.join(project_root, file_name)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def get_output_folder(file_path: str) -> str:
    """根据数据文件路径，创建隔离的输出目录（始终带时间戳避免覆盖）"""
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_root = get_abs_path("output")

    # 始终添加时间戳，确保每次运行都有独立的输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = os.path.join(output_root, f"{base_name}_{timestamp}")

    ensure_dir(output_folder)
    return output_folder


def make_output_path(file_path: str, output_folder: str, suffix: str, extension: str) -> str:
    """生成带前缀的输出文件完整路径"""
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    return os.path.join(output_folder, f"{base_name}{suffix}.{extension}")


def list_csv_files():
    """列出 storage 目录下所有 CSV 文件"""
    storage_dir = "storage"
    if not os.path.exists(storage_dir):
        print(f"目录不存在: {storage_dir}")
        return []

    files = [f for f in os.listdir(storage_dir) if f.endswith('.csv')]
    return files

if __name__ == "__main__":
    print(get_abs_path("earthquake_data_tsunami.csv"))