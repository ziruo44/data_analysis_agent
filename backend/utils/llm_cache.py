"""LLM response caching — exact hash match only, no semantic search."""
import os
import json
import hashlib
import tempfile
from datetime import datetime, timezone
from threading import Lock

from utils.logger import logger
from utils.path_tool import ensure_dir

CACHE_DIR_NAME = "llm_cache"
CACHE_FILE_NAME = "cache.json"

_write_lock = Lock()


def _get_project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_cache_path() -> str:
    cache_dir = os.path.join(_get_project_root(), CACHE_DIR_NAME)
    ensure_dir(cache_dir)
    return os.path.join(cache_dir, CACHE_FILE_NAME)


def _compute_key(*parts: str) -> str:
    raw = "||".join(p.strip() for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_cache() -> dict:
    path = _get_cache_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Corrupt cache file, resetting: {path} ({e})")
        os.remove(path)
        return {}


def _write_cache(data: dict) -> None:
    path = _get_cache_path()
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def get_cached_response(user_prompt: str) -> str | None:
    """Look up cached LLM response — exact hash match only."""
    cache = _read_cache()
    if not cache:
        return None

    exact_key = _compute_key(user_prompt)
    entry = cache.get(exact_key)
    if entry is not None:
        logger.info("LLM cache HIT (exact match)")
        return entry.get("response")

    return None


def store_cached_response(user_prompt: str, response: str) -> None:
    """Store an LLM response with its key."""
    if not response or not response.strip():
        return

    key = _compute_key(user_prompt)

    with _write_lock:
        cache = _read_cache()
        cache[key] = {
            "response": response,
            "user_prompt": user_prompt,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "node": "code_generator",
        }
        _write_cache(cache)
    logger.info(f"LLM response cached (key={key[:12]}...)")


def get_cached_image_response(user_prompt: str, chart_path: str) -> str | None:
    """Look up cached image analysis — exact hash match only."""
    cache = _read_cache()
    if not cache:
        return None

    exact_key = _compute_key(user_prompt, chart_path)
    entry = cache.get(exact_key)
    if entry is not None:
        logger.info("Image cache HIT (exact match)")
        return entry.get("response")

    return None


def store_cached_image_response(user_prompt: str, chart_path: str, response: str) -> None:
    """Store an image analysis response with its key."""
    if not response or not response.strip():
        return

    key = _compute_key(user_prompt, chart_path)

    with _write_lock:
        cache = _read_cache()
        cache[key] = {
            "response": response,
            "user_prompt": user_prompt,
            "chart_path": chart_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "node": "image_analysis",
        }
        _write_cache(cache)
    logger.info(f"Image analysis cached (key={key[:12]}...)")