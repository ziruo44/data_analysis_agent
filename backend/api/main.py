"""FastAPI 应用入口文件。

整个 API 服务的启动点，负责：
- 创建 FastAPI 应用实例
- 注册所有路由（文件、线程、工作流）
- 配置 CORS 中间件
- 挂载 output/ 静态目录（生成的图表和报告）

注意：前端已分离到独立的 Vue 3 项目（frontend/），由 Vite 开发服务器托管。
"""
from pathlib import Path

from fastapi import FastAPI
from utils.path_tool import get_abs_path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 导入各模块的路由处理器
from api.routes.file_routes import router as file_router      # 文件上传与列表
from api.routes.thread_routes import router as thread_router    # 线程/会话管理
from api.routes.workflow_routes import router as workflow_router # 工作流执行

# 创建 FastAPI 应用实例
app = FastAPI(title="Data Analysis Agent API")

# -----------------------------------------------------------
# 启动预热：提前编译 LangGraph 计算图
# -----------------------------------------------------------
# 在 uvicorn 开始接收请求之前完成 LangGraph 的缓存加载，
# 避免后续后台线程中首次调用 get_cached_app() 时因 GIL 或
# 导入顺序问题导致失败。
from agent.app_cache import get_cached_app as _warm_cache
_warm_cache()

# -----------------------------------------------------------
# CORS 中间件配置
# -----------------------------------------------------------
# 允许所有来源（前后端分离后前端运行在不同端口）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------
# 目录初始化
# -----------------------------------------------------------
OUTPUT_DIR = Path(get_abs_path("output"))   # 工作流输出目录（图表、报告等）
STORAGE_DIR = Path(get_abs_path("storage")) # CSV 文件存储目录

STORAGE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# -----------------------------------------------------------
# 注册路由
# -----------------------------------------------------------
app.include_router(file_router)      # /api/files, /api/upload
app.include_router(thread_router)    # /api/threads, /api/threads/{id}
app.include_router(workflow_router) # /api/workflow, /api/workflow/{id}/status 等

# -----------------------------------------------------------
# 静态文件服务（仅 output/ 目录，供前端访问生成的图表/报告）
# -----------------------------------------------------------
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


# -----------------------------------------------------------
# 直接运行入口
# -----------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # 监听所有网络接口，端口 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)