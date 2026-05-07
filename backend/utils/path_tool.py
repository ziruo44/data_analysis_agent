import functools
import os
from datetime import datetime


@functools.lru_cache(maxsize=64)
def get_abs_path(file_name: str) -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    for root, _, files in os.walk(project_root):
        if file_name in files:
            return os.path.join(root, file_name)
    return os.path.join(project_root, file_name)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def get_output_folder(file_path: str) -> str:
    """Create a timestamped output directory for a workflow run."""
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_root = get_abs_path("output")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = os.path.join(output_root, f"{base_name}_{timestamp}")
    ensure_dir(output_folder)
    return output_folder


def list_csv_files():
    """List CSV files under the storage directory."""
    storage_dir = "storage"
    if not os.path.exists(storage_dir):
        print(f"目录不存在: {storage_dir}")
        return []

    return [file_name for file_name in os.listdir(storage_dir) if file_name.endswith(".csv")]


if __name__ == "__main__":
    print(get_abs_path("earthquake_data_tsunami.csv"))
