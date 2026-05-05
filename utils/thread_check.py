import json
import os
import sqlite3
from pathlib import Path

from utils.path_tool import get_abs_path

DB_PATH = get_abs_path("checkpoints.db")
THREAD_STATE_PATH = Path(get_abs_path("output")) / ".thread_state.json"


def _load_session_names() -> dict:
    """Load session_name map from thread state file."""
    try:
        if THREAD_STATE_PATH.exists():
            with open(THREAD_STATE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            names = {}
            for tid, meta in data.items():
                if isinstance(meta, dict):
                    name = meta.get("session_name", "")
                else:
                    name = ""
                names[tid] = name
            return names
    except Exception:
        pass
    return {}


def list_threads():
    """列出数据库中所有 thread_id 及其检查点数量"""
    if not os.path.exists(DB_PATH):
        print("数据库不存在")
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT thread_id, COUNT(*) as checkpoint_count
        FROM checkpoints
        GROUP BY thread_id
        ORDER BY MAX(checkpoint_id) DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    return [(row[0], row[1]) for row in rows]


def show_thread_history(thread_id: str, app=None):
    """打印指定 thread 的完整检查点历史"""
    if app is None:
        from agent.graph import build_agent_graph
        app = build_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        history = list(app.get_state_history(config))
    except Exception as e:
        print(f"读取失败: {e}")
        return

    if not history:
        print("无历史记录")
        return

    print(f"\n=== Thread: {thread_id} ===")
    print(f"共 {len(history)} 个检查点\n")

    for i, h in enumerate(reversed(history)):
        checkpoint_id = h.config["configurable"]["checkpoint_id"]
        print(f"[{len(history)-1-i}] step={h.metadata.get('step')}, id={checkpoint_id[:20]}...")
        print(f"    next: {h.next}")
        for key, val in h.values.items():
            if isinstance(val, str) and len(val) > 80:
                print(f"    values['{key}']: {val[:80]}...")
            elif isinstance(val, list) and len(val) > 3:
                print(f"    values['{key}']: [{val[0]}, ... (共{len(val)}项)]")
            elif val:
                print(f"    values['{key}']: {val}")
        print()


def delete_thread(thread_id: str, app=None) -> bool:
    """删除指定线程的所有检查点、写入记录及关联的输出文件夹"""
    if not os.path.exists(DB_PATH):
        print("数据库不存在")
        return False

    conn = sqlite3.connect(DB_PATH)

    # 先查该 thread 是否存在
    cursor = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,))
    count = cursor.fetchone()[0]
    if count == 0:
        print(f"线程 {thread_id} 不存在")
        conn.close()
        return False

    # 从最新检查点获取 output_folder
    output_folder = None
    if app is None:
        from agent.graph import build_agent_graph
        app = build_agent_graph()
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = app.get_state(config)
        if state and state.values:
            output_folder = state.values.get("output_folder")
    except Exception:
        pass

    # 删除数据库记录
    conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
    conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
    conn.commit()
    conn.close()

    # 清理关联文件夹
    if output_folder and os.path.exists(output_folder):
        print(f"关联文件夹: {output_folder}")
        confirm = input("   是否删除此文件夹? (y/N): ").strip().lower()
        if confirm == "y":
            import shutil
            shutil.rmtree(output_folder)
            print(f"已删除关联文件夹: {output_folder}")
        else:
            print("   已跳过文件夹删除")

    print(f"已删除线程 {thread_id}（共 {count} 个检查点）")
    return True


def browse_history(app=None):
    """交互式浏览所有线程的历史记录"""
    if app is None:
        from agent.graph import build_agent_graph
        app = build_agent_graph()

    threads = list_threads()

    if not threads:
        print("暂无任何历史记录")
        return

    session_names = _load_session_names()

    print("\n=== 所有会话线程 ===")
    for i, (tid, count) in enumerate(threads, 1):
        name = session_names.get(tid, "")
        if name:
            print(f"  {i}. {name}  ({count} 步)  [{tid[:16]}...]")
        else:
            print(f"  {i}. {tid}  ({count} 个检查点)")

    print("\n输入编号查看详情，输入 q 返回:")
    choice = input("> ").strip()

    if choice.lower() == "q":
        return

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(threads):
            show_thread_history(threads[idx][0], app)
        else:
            print("无效编号")
