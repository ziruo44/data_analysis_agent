"""Shared state across API routes."""
import json
import os
from pathlib import Path

from utils.path_tool import get_abs_path

_STATE_FILE = Path(get_abs_path("output")) / ".thread_state.json"


def _load_thread_state() -> dict:
    """Load persisted thread metadata from disk.

    Supports both new format (thread_id -> dict) and legacy format
    (thread_id -> output_folder string) for backward compatibility.
    """
    try:
        if _STATE_FILE.exists():
            with open(_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Legacy format: values are plain strings (output_folder only)
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
    """Persist thread metadata to disk."""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _generate_session_name(user_prompt: str, max_len: int = 30) -> str:
    """Generate a concise session name from the first user prompt."""
    name = user_prompt.strip().replace('\n', ' ')
    if len(name) > max_len:
        name = name[:max_len].rstrip() + '...'
    return name or "未命名会话"


# Thread-safe storage for workflow metadata (backed by disk for restarts)
# Structure: {thread_id: {"output_folder": str, "session_name": str}}
thread_output_map: dict = _load_thread_state()
workflow_results: dict = {}
workflow_status: dict = {}
workflow_current_node: dict = {}


def register_thread(thread_id: str, output_folder: str, session_name: str = "") -> None:
    """Register a thread with its output folder and optional session name, then persist."""
    if thread_id not in thread_output_map:
        thread_output_map[thread_id] = {}
    thread_output_map[thread_id]["output_folder"] = output_folder
    if session_name:
        thread_output_map[thread_id]["session_name"] = session_name
    _save_thread_state(thread_output_map)


def set_thread_session_name(thread_id: str, session_name: str) -> None:
    """Update session name for an existing thread."""
    if thread_id not in thread_output_map:
        thread_output_map[thread_id] = {"output_folder": "", "session_name": ""}
    thread_output_map[thread_id]["session_name"] = session_name
    _save_thread_state(thread_output_map)


def get_thread_output_folder(thread_id: str) -> str:
    """Get the output folder for a thread."""
    meta = thread_output_map.get(thread_id)
    if isinstance(meta, dict):
        return meta.get("output_folder", "")
    return meta if isinstance(meta, str) else ""


def get_thread_session_name(thread_id: str) -> str:
    """Get the session name for a thread."""
    meta = thread_output_map.get(thread_id)
    if isinstance(meta, dict):
        return meta.get("session_name", "")
    return ""