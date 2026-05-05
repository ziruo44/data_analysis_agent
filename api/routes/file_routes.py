"""File management endpoints."""
from fastapi import APIRouter, UploadFile, HTTPException
from pathlib import Path

from utils.path_tool import get_abs_path

router = APIRouter()

STORAGE_DIR = Path(get_abs_path("storage"))


@router.get("/api/files")
async def list_files():
    """List available CSV files in storage directory"""
    if not STORAGE_DIR.exists():
        return []
    files = [f.name for f in STORAGE_DIR.iterdir() if f.suffix == ".csv"]
    return files


@router.post("/api/upload")
async def upload_file(file: UploadFile):
    """Upload a CSV file to storage"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files allowed")
    file_path = STORAGE_DIR / file.filename
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    return {"filename": file.filename, "path": str(file_path)}