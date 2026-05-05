"""Thread/session management endpoints."""
import os
import shutil
import sqlite3
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException

from utils.path_tool import get_abs_path

router = APIRouter()

DB_PATH = Path(get_abs_path("checkpoints.db"))
OUTPUT_DIR = Path(get_abs_path("output"))

from api.state import thread_output_map, get_thread_output_folder, get_thread_session_name
from utils.thread_check import list_threads as _list_threads


def list_threads():
    """List all threads from checkpoints database"""
    raw = _list_threads()
    return [{"thread_id": tid, "checkpoint_count": count} for tid, count in raw]


def get_latest_output_folder(thread_id: str) -> Optional[str]:
    """Try to find output folder for a thread using LangGraph's get_state"""
    if not DB_PATH.exists():
        return None
    try:
        from agent.app_cache import get_cached_app
        from memory.session import get_session_config
        app = get_cached_app()
        config = get_session_config(thread_id)
        state = app.get_state(config)
        if state and state.values:
            return state.values.get("output_folder")
    except Exception:
        pass
    return None


def _resolve_session_name(thread_id: str) -> str:
    """Get session name from metadata, falling back to truncated thread_id."""
    name = get_thread_session_name(thread_id)
    if name:
        return name
    return thread_id[:16] + "..."


@router.get("/api/threads")
async def get_threads():
    """Get all sessions/threads (lightweight, no graph build)"""
    threads = list_threads()
    result = []
    for t in threads:
        thread_id = t["thread_id"]
        output_folder = get_thread_output_folder(thread_id)
        result.append({
            "thread_id": thread_id,
            "session_name": _resolve_session_name(thread_id),
            "checkpoint_count": t["checkpoint_count"],
            "output_folder": output_folder,
        })
    return result


@router.get("/api/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Get thread details"""
    threads = list_threads()
    for t in threads:
        if t["thread_id"] == thread_id:
            output_folder = get_thread_output_folder(thread_id) or get_latest_output_folder(thread_id)
            return {
                "thread_id": thread_id,
                "session_name": _resolve_session_name(thread_id),
                "checkpoint_count": t["checkpoint_count"],
                "output_folder": output_folder
            }
    raise HTTPException(status_code=404, detail="Thread not found")


@router.get("/api/threads/{thread_id}/state")
async def get_thread_state(thread_id: str):
    """Get the full state of a thread from checkpoints database"""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database not found")

    from agent.app_cache import get_cached_app
    from memory.session import get_session_config

    app = get_cached_app()
    config = get_session_config(thread_id)

    try:
        state = app.get_state(config)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to get state: {str(e)}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Thread state not found")

    values = state.values

    return {
        "thread_id": thread_id,
        "file_path": values.get("file_path"),
        "output_folder": values.get("output_folder"),
        "user_prompt": values.get("user_prompt"),
        "data_profile": values.get("data_profile"),
        "generated_code": values.get("generated_code"),
        "execution_log": values.get("execution_log"),
        "visualization_paths": values.get("visualization_paths", []),
        "current_visualization_paths": values.get("current_visualization_paths", []),
        "cleaned_file_path": values.get("cleaned_file_path"),
        "review_feedback": values.get("review_feedback"),
        "chart_insights": values.get("chart_insights", []),
        "chat_history": values.get("chat_history", []),
    }


@router.delete("/api/workflow/{thread_id}")
async def delete_workflow(thread_id: str):
    """Delete a workflow thread"""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database not found")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,))
    if cursor.fetchone()[0] == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Thread not found")

    output_folder = get_thread_output_folder(thread_id)
    if not output_folder:
        output_folder = get_latest_output_folder(thread_id)

    conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
    conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
    conn.commit()
    conn.close()

    if output_folder and os.path.exists(output_folder):
        shutil.rmtree(output_folder)

    if thread_id in thread_output_map:
        del thread_output_map[thread_id]

    return {"success": True, "thread_id": thread_id}