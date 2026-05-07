"""文件管理相关 API 路由。

提供以下功能：
- GET /api/files: 列出 storage/ 目录下所有可用的 CSV 文件
- POST /api/upload: 上传 CSV 文件到 storage/ 目录

storage/ 目录用于存放用户上传的原始数据文件，工作流从这里读取数据。
"""

from fastapi import APIRouter, UploadFile, HTTPException
from pathlib import Path

from utils.path_tool import get_abs_path

router = APIRouter()

# CSV 文件存储目录（相对于项目根目录）
STORAGE_DIR = Path(get_abs_path("storage"))


@router.get("/api/files")
async def list_files():
    """列出 storage/ 目录中所有 CSV 文件。

    Returns:
        文件名列表（不含路径），例如 ["data1.csv", "sales.csv"]
    """
    if not STORAGE_DIR.exists():
        return []
    # 过滤只保留 .csv 后缀的文件
    files = [f.name for f in STORAGE_DIR.iterdir() if f.suffix == ".csv"]
    return files


@router.post("/api/upload")
async def upload_file(file: UploadFile):
    """上传 CSV 文件到 storage/ 目录。

    Args:
        file: 上传的文件（FastAPI 自动解析 multipart/form-data）。

    Returns:
        {"filename": str, "path": str} 上传后的文件名和路径。

    Raises:
        HTTPException 400: 文件类型不是 CSV。
    """
    # 仅允许 CSV 文件
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files allowed")

    file_path = STORAGE_DIR / file.filename
    content = await file.read()

    with open(file_path, "wb") as f:
        f.write(content)

    return {"filename": file.filename, "path": str(file_path)}