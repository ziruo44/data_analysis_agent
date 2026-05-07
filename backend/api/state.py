"""API 路由间共享的状态管理模块。

提供工作流元数据的内存存储与磁盘持久化，确保服务重启后线程信息不丢失。

磁盘持久化文件: output/.thread_state.json

数据结构:
    {
        thread_id: {
            "output_folder": str,   # 工作流输出目录路径
            "session_name": str     # 从用户第一句话生成的简短会话名
        }
    }
"""

import json
from pathlib import Path

from utils.path_tool import get_abs_path

# 磁盘持久化文件路径
_STATE_FILE = Path(get_abs_path("output")) / ".thread_state.json"


def _load_thread_state() -> dict:
    """从磁盘加载线程元数据。

    支持新旧两种数据格式兼容：
    - 新格式：{thread_id: {"output_folder": str, "session_name": str}}
    - 旧格式：{thread_id: str}（仅 output_folder，用于兼容已存在的数据）
    """
    try:
        if _STATE_FILE.exists():
            with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 检测是否为旧格式（值为字符串而非字典）
            if data and isinstance(next(iter(data.values())), str):
                converted = {}
                for tid, folder in data.items():
                    converted[tid] = {"output_folder": folder, "session_name": ""}
                return converted
            return data
    except Exception:
        pass
    return {}


def _save_thread_state(state: dict) -> None:
    """将线程元数据持久化到磁盘。"""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _generate_session_name(user_prompt: str, max_len: int = 30) -> str:
    """根据用户的第一条指令生成简短的会话名称。

    Args:
        user_prompt: 用户的原始指令。
        max_len: 会话名最大长度，超过则截断并加省略号。

    Returns:
        处理后的会话名称，如 "请分析该数据并生成可视..."。
    """
    name = user_prompt.strip().replace('\n', ' ')
    if len(name) > max_len:
        name = name[:max_len].rstrip() + '...'
    return name or "未命名会话"


# -----------------------------------------------------------
# 内存存储（进程级别）
# -----------------------------------------------------------
# 结构: {thread_id: {"output_folder": str, "session_name": str}}
thread_output_map: dict = _load_thread_state()

# 工作流执行结果缓存 {thread_id: result_dict}
workflow_results: dict = {}

# 工作流执行状态 {thread_id: "running"|"completed"|"error"}
workflow_status: dict = {}

# 当前正在执行的节点名称 {thread_id: node_name}
workflow_current_node: dict = {}


def register_thread(thread_id: str, output_folder: str, session_name: str = "") -> None:
    """注册一个线程的元数据（输出目录 + 会话名），并持久化到磁盘。

    Args:
        thread_id: 线程唯一标识符（UUID）。
        output_folder: 该线程工作流的输出目录路径。
        session_name: 可选的会话名称。
    """
    if thread_id not in thread_output_map:
        thread_output_map[thread_id] = {}
    thread_output_map[thread_id]["output_folder"] = output_folder
    if session_name:
        thread_output_map[thread_id]["session_name"] = session_name
    _save_thread_state(thread_output_map)


def unregister_thread(thread_id: str) -> None:
    """Remove persisted metadata for a thread."""
    if thread_id in thread_output_map:
        del thread_output_map[thread_id]
        _save_thread_state(thread_output_map)


def set_thread_session_name(thread_id: str, session_name: str) -> None:
    """更新已有线程的会话名称。

    Args:
        thread_id: 线程唯一标识符。
        session_name: 新的会话名称。
    """
    if thread_id not in thread_output_map:
        thread_output_map[thread_id] = {"output_folder": "", "session_name": ""}
    thread_output_map[thread_id]["session_name"] = session_name
    _save_thread_state(thread_output_map)


def get_thread_output_folder(thread_id: str) -> str:
    """获取指定线程的输出目录路径。

    Args:
        thread_id: 线程唯一标识符。

    Returns:
        输出目录的绝对路径字符串。
    """
    meta = thread_output_map.get(thread_id)
    if isinstance(meta, dict):
        return meta.get("output_folder", "")
    return meta if isinstance(meta, str) else ""


def get_thread_session_name(thread_id: str) -> str:
    """获取指定线程的会话名称。

    Args:
        thread_id: 线程唯一标识符。

    Returns:
        会话名称字符串。
    """
    meta = thread_output_map.get(thread_id)
    if isinstance(meta, dict):
        return meta.get("session_name", "")
    return ""
