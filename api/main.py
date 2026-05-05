"""FastAPI application entry point."""
from pathlib import Path

from fastapi import FastAPI
from utils.path_tool import get_abs_path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes.file_routes import router as file_router
from api.routes.thread_routes import router as thread_router
from api.routes.workflow_routes import router as workflow_router

app = FastAPI(title="Data Analysis Agent API")


# 在模块加载时预编译 LangGraph（在 uvicorn 开始监听之前完成）
# 避免后台线程中的 get_cached_app() 首次导入失败
from agent.app_cache import get_cached_app as _warm_cache
_warm_cache()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path(get_abs_path("output"))
STORAGE_DIR = Path(get_abs_path("storage"))

STORAGE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app.include_router(file_router)
app.include_router(thread_router)
app.include_router(workflow_router)

app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
app.mount("/", StaticFiles(directory=str(Path(get_abs_path("static"))), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)