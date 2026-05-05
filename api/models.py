"""Pydantic models for API requests/responses."""
from pydantic import BaseModel


class WorkflowRequest(BaseModel):
    file_path: str
    user_prompt: str = "请分析该数据并生成可视化图表"


class ContinueRequest(BaseModel):
    user_prompt: str = "请继续分析"