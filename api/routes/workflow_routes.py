"""Workflow execution endpoints."""
import os
import sys
import uuid
import threading
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException

from api.models import WorkflowRequest, ContinueRequest
from api.state import thread_output_map, workflow_results, workflow_status, workflow_current_node, register_thread, get_thread_output_folder, _generate_session_name

router = APIRouter()

from utils.path_tool import get_abs_path, ensure_dir

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = Path(get_abs_path("output"))
DB_PATH = Path(get_abs_path("checkpoints.db"))

sys.path.insert(0, str(PROJECT_ROOT))


def run_workflow_sync(file_path: str, user_prompt: str, thread_id: str):
    """Synchronous workflow execution to run in thread pool"""
    try:

        from agent.app_cache import get_cached_app
        from agent.states import AgentState
        from memory.session import get_session_config

        app_graph = get_cached_app()
        output_folder = str(OUTPUT_DIR / f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        ensure_dir(output_folder)
        # Preserve existing session_name (set in start_workflow) while updating output_folder
        from api.state import thread_output_map as tom
        existing_name = ""
        if thread_id in tom and isinstance(tom[thread_id], dict):
            existing_name = tom[thread_id].get("session_name", "")
        register_thread(thread_id, output_folder, session_name=existing_name)

        config = get_session_config(thread_id)

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
            "chat_history": [],
            "thread_id": config["configurable"]["thread_id"],
        }
        workflow_status[thread_id] = "running"

        # 后台线程运行 graph
        result = app_graph.invoke(initial_state, config=config)
        workflow_results[thread_id] = {
            "thread_id": thread_id,
            "user_prompt": user_prompt,
            "data_profile": result.get("data_profile", ""),
            "cleaned_file_path": result.get("cleaned_file_path", ""),
            "generated_code": result.get("generated_code", ""),
            "execution_log": result.get("execution_log", ""),
            "visualization_paths": result.get("visualization_paths", []),
            "current_visualization_paths": result.get("current_visualization_paths", []),
            "review_feedback": result.get("review_feedback", ""),
            "file_path": file_path,
            "chart_insights": result.get("chart_insights", []),
            "chat_history": result.get("chat_history", []),
            "output_folder": output_folder,
        }
        workflow_status[thread_id] = "completed"
        workflow_current_node.pop(thread_id, None)
    except Exception as e:
        import traceback
        workflow_status[thread_id] = "error"
        workflow_current_node.pop(thread_id, None)
        workflow_results[thread_id] = {"error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}


@router.post("/api/workflow")
async def start_workflow(req: WorkflowRequest):
    """Start a new workflow"""
    file_path = req.file_path
    # 使用 path_tool 解析为绝对路径，避免受 CWD 或项目搬迁影响
    if not os.path.isabs(file_path):
        file_path = get_abs_path(file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File not found: {file_path}")

    thread_id = str(uuid.uuid4())
    user_prompt = req.user_prompt
    session_name = _generate_session_name(user_prompt)

    # Register session name immediately so sidebar shows it before workflow completes
    from api.state import thread_output_map
    thread_output_map[thread_id] = {"output_folder": "", "session_name": session_name}

    thread = threading.Thread(target=run_workflow_sync, args=(file_path, user_prompt, thread_id))
    thread.start()

    return {"thread_id": thread_id, "status": "started"}


@router.get("/api/workflow/{thread_id}/status")
async def get_workflow_status(thread_id: str):
    """Get workflow status"""
    status = workflow_status.get(thread_id, "not_found")
    result = workflow_results.get(thread_id)
    return {
        "status": status,
        "result": result,
        "output_folder": get_thread_output_folder(thread_id),
        "current_node": workflow_current_node.get(thread_id, "")
    }


@router.post("/api/workflow/{thread_id}/continue")
async def continue_workflow(thread_id: str, req: ContinueRequest):
    """Continue an existing workflow"""
    import sqlite3
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database not found")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,))
    if cursor.fetchone()[0] == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Thread not found")
    conn.close()

    from agent.app_cache import get_cached_app
    from memory.session import get_session_config

    app_graph = get_cached_app()
    config = get_session_config(thread_id)
    state = app_graph.get_state(config)

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Thread state not found")

    # Normalize output_folder to current project (stale after project relocation)
    raw_output_folder = state.values.get("output_folder", "")
    folder_name = os.path.basename(raw_output_folder) if raw_output_folder else thread_id
    if not folder_name or folder_name == "output":
        folder_name = f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_folder = os.path.join(get_abs_path("output"), folder_name)

    ensure_dir(output_folder)
    register_thread(thread_id, output_folder)

    # Normalize file_path via project-tree search if relocated
    orig_file_path = state.values.get("file_path", "")
    if orig_file_path and not os.path.exists(orig_file_path):
        resolved = get_abs_path(os.path.basename(orig_file_path))
        orig_file_path = resolved if os.path.exists(resolved) else orig_file_path

    # Normalize cleaned_file_path the same way
    cleaned_file_path = state.values.get("cleaned_file_path", "")
    if cleaned_file_path and not os.path.exists(cleaned_file_path):
        resolved = get_abs_path(os.path.basename(cleaned_file_path))
        cleaned_file_path = resolved if os.path.exists(resolved) else ""

    continue_state = dict(state.values)
    continue_state["user_prompt"] = req.user_prompt
    continue_state["output_folder"] = output_folder
    continue_state["file_path"] = orig_file_path
    continue_state["current_visualization_paths"] = []
    continue_state["review_feedback"] = ""
    continue_state["generated_code"] = ""
    continue_state["execution_log"] = ""
    continue_state["retry_count"] = 0

    if cleaned_file_path and os.path.exists(cleaned_file_path):
        continue_state["cleaned_file_path"] = cleaned_file_path
    else:
        continue_state["cleaned_file_path"] = ""

    def run_in_thread():
        try:
            workflow_status[thread_id] = "running"
            result = app_graph.invoke(continue_state, config=config)
            workflow_results[thread_id] = {
                "thread_id": thread_id,
                "user_prompt": req.user_prompt,
                "data_profile": result.get("data_profile", ""),
                "cleaned_file_path": result.get("cleaned_file_path", ""),
                "generated_code": result.get("generated_code", ""),
                "execution_log": result.get("execution_log", ""),
                "visualization_paths": result.get("visualization_paths", []),
                "current_visualization_paths": result.get("current_visualization_paths", []),
                "review_feedback": result.get("review_feedback", ""),
                "file_path": orig_file_path,
                "chart_insights": result.get("chart_insights", []),
                "chat_history": result.get("chat_history", []),
                "output_folder": output_folder,
            }
            workflow_status[thread_id] = "completed"
            workflow_current_node.pop(thread_id, None)
        except Exception as e:
            import traceback
            workflow_status[thread_id] = "error"
            workflow_current_node.pop(thread_id, None)
            workflow_results[thread_id] = {"error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}

    thread = threading.Thread(target=run_in_thread)
    thread.start()

    return {
        "thread_id": thread_id,
        "status": "continued"
    }


@router.get("/api/workflow/{thread_id}/report")
async def get_workflow_report(thread_id: str):
    """Get the rendered final report HTML for a workflow."""
    from utils.info_loader import load_report_html

    output_folder = get_thread_output_folder(thread_id)
    if not output_folder and DB_PATH.exists():
        try:
            from agent.app_cache import get_cached_app
            from memory.session import get_session_config
            app = get_cached_app()
            config = get_session_config(thread_id)
            state = app.get_state(config)
            if state and state.values:
                raw = state.values.get("output_folder", "")
                if raw:
                    folder_name = os.path.basename(raw)
                    if folder_name and folder_name != "output":
                        output_folder = str(OUTPUT_DIR / folder_name)
        except Exception:
            pass

    if not output_folder:
        raise HTTPException(status_code=404, detail="Output folder not found for this thread")

    from utils.info_loader import split_report_by_turns, get_report_path

    report_path = get_report_path(output_folder)
    if not report_path:
        raise HTTPException(status_code=404, detail="Report not found")

    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()

    report_data = split_report_by_turns(content)

    return {
        "html": "",
        "turns": report_data["turns"],
        "exists": True,
        "output_folder": output_folder
    }