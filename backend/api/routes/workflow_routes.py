"""Workflow execution related API routes."""

import os
import sqlite3
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.models import ContinueRequest, WorkflowRequest
from api.state import (
    _generate_session_name,
    get_thread_output_folder,
    get_thread_session_name,
    register_thread,
    workflow_current_node,
    workflow_results,
    workflow_status,
)
from utils.path_tool import ensure_dir, get_abs_path

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = Path(get_abs_path("output"))
DB_PATH = Path(get_abs_path("checkpoints.db"))

sys.path.insert(0, str(PROJECT_ROOT))


def _mark_workflow_running(thread_id: str) -> None:
    """Initialize in-memory workflow state before the worker starts."""
    workflow_status[thread_id] = "running"
    workflow_results.pop(thread_id, None)
    workflow_current_node.pop(thread_id, None)


def _build_workflow_result(
    thread_id: str,
    user_prompt: str,
    file_path: str,
    result: dict,
    output_folder: str,
) -> dict:
    """Normalize the workflow payload returned to the frontend."""
    return {
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


def _resolve_existing_session_name(thread_id: str) -> str:
    """Keep any pre-registered session name when the output folder becomes available."""
    return get_thread_session_name(thread_id)


def run_workflow_sync(file_path: str, user_prompt: str, thread_id: str):
    """Run a brand new workflow in a background thread."""
    try:
        from agent.app_cache import get_cached_app
        from agent.states import AgentState
        from memory.session import get_session_config

        app_graph = get_cached_app()
        output_folder = str(OUTPUT_DIR / f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        ensure_dir(output_folder)
        register_thread(thread_id, output_folder, session_name=_resolve_existing_session_name(thread_id))

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

        result = app_graph.invoke(initial_state, config=config)
        workflow_results[thread_id] = _build_workflow_result(
            thread_id=thread_id,
            user_prompt=user_prompt,
            file_path=file_path,
            result=result,
            output_folder=output_folder,
        )
        workflow_status[thread_id] = "completed"
        workflow_current_node.pop(thread_id, None)
    except Exception as exc:
        import traceback

        workflow_status[thread_id] = "error"
        workflow_current_node.pop(thread_id, None)
        workflow_results[thread_id] = {"error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"}


@router.post("/api/workflow")
async def start_workflow(req: WorkflowRequest):
    """Start a new workflow."""
    file_path = req.file_path
    if not os.path.isabs(file_path):
        file_path = get_abs_path(file_path)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File not found: {file_path}")

    thread_id = str(uuid.uuid4())
    user_prompt = req.user_prompt
    session_name = _generate_session_name(user_prompt)

    register_thread(thread_id, "", session_name=session_name)
    _mark_workflow_running(thread_id)

    thread = threading.Thread(
        target=run_workflow_sync,
        args=(file_path, user_prompt, thread_id),
        daemon=True,
    )
    thread.start()

    return {"thread_id": thread_id, "status": "started"}


@router.get("/api/workflow/{thread_id}/status")
async def get_workflow_status(thread_id: str):
    """Return workflow progress and any available result."""
    return {
        "status": workflow_status.get(thread_id, "not_found"),
        "result": workflow_results.get(thread_id),
        "output_folder": get_thread_output_folder(thread_id),
        "current_node": workflow_current_node.get(thread_id, ""),
    }


def _restore_existing_thread_state(thread_id: str):
    """Load the latest persisted LangGraph state for a thread."""
    from agent.app_cache import get_cached_app
    from memory.session import get_session_config

    app_graph = get_cached_app()
    config = get_session_config(thread_id)
    state = app_graph.get_state(config)
    return app_graph, config, state


def _resolve_continue_paths(state_values: dict, thread_id: str) -> tuple[str, str, str]:
    """Resolve output, source, and cleaned file paths for a continued workflow."""
    raw_output_folder = state_values.get("output_folder", "")
    folder_name = os.path.basename(raw_output_folder) if raw_output_folder else thread_id
    if not folder_name or folder_name == "output":
        folder_name = f"workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_folder = os.path.join(get_abs_path("output"), folder_name)
    ensure_dir(output_folder)
    register_thread(thread_id, output_folder, session_name=_resolve_existing_session_name(thread_id))

    file_path = state_values.get("file_path", "")
    if file_path and not os.path.exists(file_path):
        resolved = get_abs_path(os.path.basename(file_path))
        file_path = resolved if os.path.exists(resolved) else file_path

    cleaned_file_path = state_values.get("cleaned_file_path", "")
    if cleaned_file_path and not os.path.exists(cleaned_file_path):
        resolved = get_abs_path(os.path.basename(cleaned_file_path))
        cleaned_file_path = resolved if os.path.exists(resolved) else ""

    return output_folder, file_path, cleaned_file_path


def _build_continue_state(
    state_values: dict,
    user_prompt: str,
    output_folder: str,
    file_path: str,
    cleaned_file_path: str,
) -> dict:
    """Reset the transient state fields for a continued run."""
    continue_state = dict(state_values)
    continue_state["user_prompt"] = user_prompt
    continue_state["output_folder"] = output_folder
    continue_state["file_path"] = file_path
    continue_state["current_visualization_paths"] = []
    continue_state["review_feedback"] = ""
    continue_state["generated_code"] = ""
    continue_state["execution_log"] = ""
    continue_state["retry_count"] = 0
    continue_state["cleaned_file_path"] = cleaned_file_path if cleaned_file_path and os.path.exists(cleaned_file_path) else ""
    return continue_state


@router.post("/api/workflow/{thread_id}/continue")
async def continue_workflow(thread_id: str, req: ContinueRequest):
    """Continue an existing workflow from the latest checkpoint."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database not found")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,))
    if cursor.fetchone()[0] == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Thread not found")
    conn.close()

    app_graph, config, state = _restore_existing_thread_state(thread_id)
    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Thread state not found")

    output_folder, file_path, cleaned_file_path = _resolve_continue_paths(state.values, thread_id)
    continue_state = _build_continue_state(
        state_values=state.values,
        user_prompt=req.user_prompt,
        output_folder=output_folder,
        file_path=file_path,
        cleaned_file_path=cleaned_file_path,
    )

    def run_in_thread():
        try:
            result = app_graph.invoke(continue_state, config=config)
            workflow_results[thread_id] = _build_workflow_result(
                thread_id=thread_id,
                user_prompt=req.user_prompt,
                file_path=file_path,
                result=result,
                output_folder=output_folder,
            )
            workflow_status[thread_id] = "completed"
            workflow_current_node.pop(thread_id, None)
        except Exception as exc:
            import traceback

            workflow_status[thread_id] = "error"
            workflow_current_node.pop(thread_id, None)
            workflow_results[thread_id] = {"error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"}

    _mark_workflow_running(thread_id)
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    return {"thread_id": thread_id, "status": "continued"}


@router.get("/api/workflow/{thread_id}/report")
async def get_workflow_report(thread_id: str):
    """Return the split markdown report for a workflow."""
    output_folder = get_thread_output_folder(thread_id)

    if not output_folder and DB_PATH.exists():
        try:
            _, config, state = _restore_existing_thread_state(thread_id)
            if state and state.values:
                raw_output_folder = state.values.get("output_folder", "")
                if raw_output_folder:
                    folder_name = os.path.basename(raw_output_folder)
                    if folder_name and folder_name != "output":
                        output_folder = str(OUTPUT_DIR / folder_name)
        except Exception:
            pass

    if not output_folder:
        raise HTTPException(status_code=404, detail="Output folder not found for this thread")

    from utils.info_loader import get_report_path, split_report_by_turns

    report_path = get_report_path(output_folder)
    if not report_path:
        raise HTTPException(status_code=404, detail="Report not found")

    with open(report_path, "r", encoding="utf-8") as file:
        content = file.read()

    report_data = split_report_by_turns(content)
    return {
        "html": "",
        "turns": report_data["turns"],
        "exists": True,
        "output_folder": output_folder,
    }
