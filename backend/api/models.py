"""Pydantic 模型定义，用于 API 请求/响应的数据校验。

所有请求/响应模型均继承自 BaseModel，FastAPI 会自动进行：
- 类型检查与自动转换
- JSON 序列化/反序列化
- OpenAPI 文档生成
"""

from pydantic import BaseModel


class WorkflowRequest(BaseModel):
    """启动新工作流的请求体。

    Attributes:
        file_path: CSV 数据文件的绝对路径或相对于项目根目录的路径。
        user_prompt: 用户指令，描述希望执行的数据分析任务。
    """
    file_path: str
    user_prompt: str = "请分析该数据并生成可视化图表"


class ContinueRequest(BaseModel):
    """继续已有工作流的请求体。

    Attributes:
        user_prompt: 用户的追加指令，用于在已有分析结果基础上继续提问。
    """
    user_prompt: str = "请继续分析"