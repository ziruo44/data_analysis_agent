import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.app_cache import get_cached_app
from agent.states import AgentState
from memory.session import get_session_config
from utils.path_tool import get_output_folder, get_abs_path
from utils.thread_check import browse_history, delete_thread




def build_graph():
    """编译图，返回 app 实例（缓存复用）"""
    app = get_cached_app()
    print(f"图编译成功: {app}")
    return app


def run_workflow(file_path: str, user_prompt: str = "请分析该数据并生成可视化图表"):
    """执行完整工作流（供 Web 前端调用）

    Args:
        file_path: CSV 文件路径
        user_prompt: 用户提示词

    Returns:
        执行结果 dict，包含所有 state 字段
    """
    app = get_cached_app()

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    output_folder = get_output_folder(file_path)

    config = get_session_config(str(uuid.uuid4()))

    initial_state: AgentState = {
        "file_path": file_path,
        "cleaned_file_path": "",
        "user_prompt": user_prompt,
        "data_profile": "",
        "cleaning_policy": {},
        "generated_code": "",
        "execution_log": "",
        "visualization_paths": [],
        "chart_insights": [],
        "review_feedback": "",
        "retry_count": 0,
        "output_folder": output_folder,
        "image_analysis_results": [],
        "thread_id": config["configurable"]["thread_id"],
    }

    print("开始执行工作流...")
    print(f"输出目录: {output_folder}")
    result = app.invoke(initial_state, config=config)

    print("\n=== 执行结果 ===")
    print(f"data_profile 长度: {len(result.get('data_profile', ''))}")
    print(f"cleaned_file_path: {result.get('cleaned_file_path')}")
    print(f"generated_code 长度: {len(result.get('generated_code', ''))}")
    print(f"execution_log 长度: {len(result.get('execution_log', ''))}")
    print(f"visualization_paths: {result.get('visualization_paths', [])}")
    print(f"review_feedback: {result.get('review_feedback')}")

    print("\n=== 检查点信息 ===")
    state = app.get_state(config)
    print(f"checkpoint_id: {state.config['configurable']['checkpoint_id']}")
    print(f"step: {state.metadata.get('step')}")
    print(f"next: {state.next}")

    print("\n=== 历史检查点 ===")
    history = list(app.get_state_history(config))
    print(f"共 {len(history)} 个检查点")
    for i, h in enumerate(history):
        checkpoint_id = h.config['configurable']['checkpoint_id']
        print(f"\n  [{i}] step={h.metadata.get('step')}, id={checkpoint_id[:20]}...")
        print(f"      next: {h.next}")
        for key in h.values:
            val = h.values[key]
            if isinstance(val, str) and len(val) > 80:
                print(f"      values['{key}']: {val[:80]}...")
            elif isinstance(val, list) and len(val) > 3:
                print(f"      values['{key}']: [{val[0]}, ... (共{len(val)}项)]")
            else:
                print(f"      values['{key}']: {val}")

    print("\n工作流执行完成!")
    return result


def continue_workflow(thread_id: str):
    """继续已有对话

    Args:
        thread_id: 继续执行的线程 ID
    """
    app = get_cached_app()

    config = get_session_config(thread_id)

    # 获取当前状态（从 checkpoint 恢复）
    state = app.get_state(config)
    if not state or not state.values:
        print(f"线程 {thread_id} 没有找到历史记录")
        return

    print(f"\n=== 继续已有对话 ===")
    print(f"Thread ID: {thread_id}")
    print(f"当前 step: {state.metadata.get('step')}")

    # 获取当前文件路径和数据概况
    file_path = state.values.get("file_path", "")
    cleaned_file_path = state.values.get("cleaned_file_path", "")
    data_profile = state.values.get("data_profile", "")

    # 验证 cleaned_file_path 是否存在，不存在则回退到原始文件
    if cleaned_file_path and not os.path.exists(cleaned_file_path):
        print(f"警告: 清洗后的文件不存在: {cleaned_file_path}")
        print(f"   将回退到原始文件重新清洗: {file_path}")
        cleaned_file_path = ""  # 清空以触发重新清洗

    print(f"数据文件: {file_path}")
    print(f"已清洗: {cleaned_file_path or '(将重新清洗)'}")
    print(f"数据概况: {'有' if data_profile else '无'}")

    # 获取已有图片
    viz_paths = state.values.get("visualization_paths", [])
    image_results = state.values.get("image_analysis_results", [])
    print(f"已有图表: {len(viz_paths)} 张")
    print(f"已有分析: {len(image_results)} 条")

    print("\n请输入新的分析指令 (如: '再画一个帕累托图'):")
    user_prompt = input("> ").strip()

    if not user_prompt:
        print("请输入分析指令")
        return

    # 复用原来的输出目录，不要创建新的时间戳目录
    output_folder = state.values.get("output_folder", get_abs_path("output"))

    # 从 checkpoint 恢复完整状态，只更新 user_prompt 和 output_folder
    # current_visualization_paths 设为空列表，新图表会追加到 visualization_paths
    continue_state = dict(state.values)
    continue_state["user_prompt"] = user_prompt
    continue_state["output_folder"] = output_folder
    continue_state["current_visualization_paths"] = []
    # 继续对话时清理上一轮的 review_feedback，避免沿用旧状态
    continue_state["review_feedback"] = ""
    continue_state["generated_code"] = ""
    continue_state["execution_log"] = ""
    # retry_count 重置，因为是新的一轮
    continue_state["retry_count"] = 0

    # 如果 cleaned_file_path 有效，更新 continue_state；否则清空让工作流重新清洗
    if cleaned_file_path and os.path.exists(cleaned_file_path):
        continue_state["cleaned_file_path"] = cleaned_file_path
        print(f"\n继续执行工作流...")
        print(f"输出目录: {output_folder}")
        print(f"检测到已清洗文件存在: {cleaned_file_path}，将跳过数据清洗")
    else:
        continue_state["cleaned_file_path"] = ""  # 触发重新清洗
        print(f"\n继续执行工作流...")
        print(f"输出目录: {output_folder}")
        print(f"清洗文件不存在或无效，将重新执行数据清洗")

    # 从 checkpoint 恢复状态后继续执行
    result = app.invoke(continue_state, config=config)

    print("\n=== 执行结果 ===")
    print(f"data_profile 长度: {len(result.get('data_profile', ''))}")
    print(f"cleaned_file_path: {result.get('cleaned_file_path')}")
    print(f"generated_code 长度: {len(result.get('generated_code', ''))}")
    print(f"visualization_paths: {result.get('visualization_paths', [])}")
    print(f"current_visualization_paths: {result.get('current_visualization_paths', [])}")
    print(f"review_feedback: {result.get('review_feedback')}")

    print("\n=== 历史检查点 ===")
    history = list(app.get_state_history(config))
    print(f"共 {len(history)} 个检查点")

    print("\n继续对话执行完成!")
    return result
