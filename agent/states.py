from typing import TypedDict, List, Annotated
import operator

# 路由常量（统一在此定义，供 nodes.py / graph.py 导入）
SAFE = "safe"
UNSAFE = "unsafe"
RETRY = "retry"
PASS = "pass"
ERROR_FEEDBACK = "error"
FAIL_FEEDBACK = "fail"


class AgentState(TypedDict):
    # 基础信息
    file_path: str  # 原始文件路径
    cleaned_file_path: str  # 清洗后的本地文件路径
    data_profile: str  # 数据概况（列名、类型、统计信息等）

    # 用户提示词
    user_prompt: str  # 存放用户在控制台输入的话

    # 清洗策略
    cleaning_policy: dict  # 清洗策略配置

    # 计划与代码
    generated_code: str  # 生成的分析/绘图代码

    # 执行结果
    execution_log: str  # 捕获的控制台打印内容

    # 使用 Annotated 和 operator.add 可以让图片路径在重试循环中”追加”而不是”覆盖”
    visualization_paths: Annotated[List[str], operator.add]

    # 视觉洞察
    image_analysis_results: List[dict]  # Node 7 图片分析的完整结果
    chart_insights: List[str]  # 图表分析洞察摘要

    # 仅保留当前轮次生成的图片路径（覆盖模式，每轮清零）
    current_visualization_paths: List[str]

    # 自评反馈
    review_feedback: str  # Node 9 生成的报错或修改建议

    # 记录重试次数以便后面终止
    retry_count: int  # 记录当前在 Node 5 重试了多少次

    # 输出目录（按数据文件名隔离）
    output_folder: str  # 例如 output/test_sales_data/

    # 用于中断机制的线程标识（非状态流转内容，仅运行时使用）
    thread_id: str

    # 对话历史（累积所有轮次的摘要记录）
    chat_history: Annotated[List[dict], operator.add]

