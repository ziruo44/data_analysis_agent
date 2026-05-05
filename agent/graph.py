import os
from langgraph.graph import StateGraph, END, START

from agent.states import AgentState, SAFE, UNSAFE, RETRY, PASS
from memory.checkpointer import checkpointer
from utils.logger import logger
from api.state import workflow_current_node

# 引入所有节点
from agent.nodes import (
    data_clean_node,
    code_generator_node,
    sanity_checker_node,
    code_executor_node,
    self_reviewer_node,
    report_output_node,
    imag_analysis_code,
)


def _track_node(node_name: str, node_func):
    """Wrap a node function to report current execution progress."""
    def wrapper(state: AgentState):
        thread_id = state.get("thread_id", "")
        if thread_id:
            workflow_current_node[thread_id] = node_name
        return node_func(state)
    return wrapper

# 3. 入口路由：根据是否已有清洗后的文件，决定是否跳过 data_clean
def route_from_start(state: AgentState) -> str:
    if state.get("cleaned_file_path"):
        logger.info("[路由] 检测到已清洗数据，跳过 data_clean，直接生成代码")
        return "skip_data_clean"
    logger.info("[路由] 新会话，执行数据清洗")
    return "data_clean"

# [条件路由 1]：安全审查是否通过？
def route_after_sanity_check(state: AgentState):
    feedback = state.get("review_feedback", "")
    if UNSAFE in feedback.lower():
        logger.warning("[路由控制] 检测到危险指令，打回 [代码生成] 节点重写！")
        return UNSAFE
    return SAFE

def route_after_execution(state: AgentState):
    feedback = state.get("review_feedback", "")
    if "error" in feedback.lower() or "fail" in feedback.lower():
        logger.warning("[路由控制] 代码执行报错，将 Traceback 发回 [代码生成] 节点进行自愈！")
        return RETRY
    return PASS


def build_agent_graph():
    """
    组装全量智能体工作流：包含数据清洗、代码生成、安全检查、本地执行与结果反思闭环
    """
    logger.info("正在初始化 LangGraph 全量状态机...")

    # 1. 初始化状态图
    workflow = StateGraph(AgentState)

    # 2. 注册所有节点 (声明打工人)，每个节点包裹进度追踪
    workflow.add_node("data_clean", _track_node("data_clean", data_clean_node))
    workflow.add_node("code_generator", _track_node("code_generator", code_generator_node))
    workflow.add_node("sanity_checker", _track_node("sanity_checker", sanity_checker_node))
    workflow.add_node("code_executor", _track_node("code_executor", code_executor_node))
    workflow.add_node("self_reviewer", _track_node("self_reviewer", self_reviewer_node))
    workflow.add_node("image_analysis", _track_node("image_analysis", imag_analysis_code))
    workflow.add_node("report_output", _track_node("report_output", report_output_node))


    workflow.add_conditional_edges(START, route_from_start, {
        "data_clean": "data_clean",
        "skip_data_clean": "code_generator"
    })

    # 数据清洗完成后，直接进入代码生成
    workflow.add_edge("data_clean", "code_generator")

    # 代码生成后，必须先进行安全审查
    workflow.add_edge("code_generator", "sanity_checker")

    # 执行完代码后，必须进入自我审查环节
    workflow.add_edge("code_executor", "self_reviewer")

    #审查完后，进入图片分析环节
    workflow.add_edge("image_analysis", "report_output")

    # 报告输出后，流程彻底结束
    workflow.add_edge("report_output", END)

    # 4. 编排条件边 (动态分叉与自愈循环)


    workflow.add_conditional_edges(
        "sanity_checker",
        route_after_sanity_check,
        {
            SAFE: "code_executor",
            UNSAFE: "code_generator"
        }
    )

    workflow.add_conditional_edges(
        "self_reviewer",
        route_after_execution,
        {
            PASS: "image_analysis",
            RETRY: "code_generator"
        }
    )


    # 5. 编译成可执行的程序
    app = workflow.compile(checkpointer=checkpointer)
    logger.info("全量状态机编译完成！拥有安全拦截与自愈能力的 Agent 已就绪。")

    return app


# 根据你最新的节点逻辑，我为你重写了 graph.py。这份代码在原来前三个节点的基础上，
# 引入了 LangGraph 的条件边（Conditional Edges），完美实现了**“拦截打回”与“报错重试”**的闭环循环。