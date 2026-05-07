"""Thread and session related API routes."""

import os
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.state import (
    get_thread_output_folder,
    get_thread_session_name,
    unregister_thread,
)
from utils.path_tool import get_abs_path
from utils.thread_check import list_threads as _list_threads

router = APIRouter()

DB_PATH = Path(get_abs_path("checkpoints.db"))


def list_threads() -> list[dict]:
    """Return all thread ids with their checkpoint counts."""
    raw_threads = _list_threads()
    return [{"thread_id": thread_id, "checkpoint_count": count} for thread_id, count in raw_threads]


def get_latest_output_folder(thread_id: str) -> Optional[str]:
    """Restore the latest output folder from the checkpoint state."""
    if not DB_PATH.exists():
        return None

    try:
        from agent.app_cache import get_cached_app
        from memory.session import get_session_config

        app = get_cached_app()
        state = app.get_state(get_session_config(thread_id))
        if state and state.values:
            return state.values.get("output_folder")
    except Exception:
        pass

    return None


def _resolve_session_name(thread_id: str) -> str:
    """Prefer the persisted session name and fall back to a short thread id."""
    session_name = get_thread_session_name(thread_id)
    if session_name:
        return session_name
    return thread_id[:16] + "..."


@router.get("/api/threads")
async def get_threads():
    """Return lightweight thread metadata for the sidebar."""
    items = []
    for thread in list_threads():
        thread_id = thread["thread_id"]
        output_folder = get_thread_output_folder(thread_id) or get_latest_output_folder(thread_id)
        items.append(
            {
                "thread_id": thread_id,
                "session_name": _resolve_session_name(thread_id),
                "checkpoint_count": thread["checkpoint_count"],
                "output_folder": output_folder,
            }
        )
    return items


@router.get("/api/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Return details for a single thread."""
    for thread in list_threads():
        if thread["thread_id"] != thread_id:
            continue

        output_folder = get_thread_output_folder(thread_id) or get_latest_output_folder(thread_id)
        return {
            "thread_id": thread_id,
            "session_name": _resolve_session_name(thread_id),
            "checkpoint_count": thread["checkpoint_count"],
            "output_folder": output_folder,
        }

    raise HTTPException(status_code=404, detail="Thread not found")


@router.get("/api/threads/{thread_id}/state")
async def get_thread_state(thread_id: str):
    """Return the full restored AgentState for a thread."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database not found")

    from agent.app_cache import get_cached_app
    from memory.session import get_session_config

    app = get_cached_app()

    try:
        state = app.get_state(get_session_config(thread_id))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Failed to get state: {exc}") from exc

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
    """Delete a thread, its checkpoints, and any output folder."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database not found")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,))
    if cursor.fetchone()[0] == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Thread not found")

    output_folder = get_thread_output_folder(thread_id) or get_latest_output_folder(thread_id)

    conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
    conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
    conn.commit()
    conn.close()

    if output_folder and os.path.exists(output_folder):
        shutil.rmtree(output_folder)

    unregister_thread(thread_id)

    return {"success": True, "thread_id": thread_id}
