"""Cached singleton for the compiled LangGraph application.

The compiled graph can't be pickled (LangGraph uses internal closures), so this
module keeps the graph in a module-level variable for in-process reuse and
writes a lightweight marker file (llm_cache/app_cache.json) to track when the
cache was last built for diagnostic purposes.
"""

import os
import json
import hashlib
from datetime import datetime, timezone

CACHE_FILE_NAME = "app_cache.json"

_app_graph = None


def _get_cache_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, "llm_cache", CACHE_FILE_NAME)


def _compute_code_hash() -> str:
    """Hash relevant source files to detect code changes between restarts."""
    hasher = hashlib.sha256()
    files = ["agent/graph.py", "agent/nodes.py", "agent/states.py"]
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel_path in files:
        path = os.path.join(project_root, rel_path)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                hasher.update(fh.read())
    return hasher.hexdigest()


def get_cached_app():
    """Return the compiled graph, building once and reusing across calls."""
    global _app_graph
    if _app_graph is not None:
        return _app_graph

    from agent.graph import build_agent_graph
    _app_graph = build_agent_graph()

    # Write diagnostic marker (graph itself can't be pickled)
    cache_path = _get_cache_path()
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({
                "built_at": datetime.now(timezone.utc).isoformat(),
                "code_hash": _compute_code_hash(),
            }, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # Non-critical

    return _app_graph


def clear_cache():
    """Clear the cached graph (in-memory and marker file)."""
    global _app_graph
    _app_graph = None
    cache_path = _get_cache_path()
    if os.path.exists(cache_path):
        os.remove(cache_path)
