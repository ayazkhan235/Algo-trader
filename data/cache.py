import json
import os
import time
from typing import Any, Optional

CACHE_DIR = ".cache"


def _key_to_path(key: str) -> str:
    safe = key.replace("/", "_").replace(":", "_")
    return os.path.join(CACHE_DIR, f"{safe}.json")


def get(key: str, ttl_hours: float = 24) -> Optional[Any]:
    path = _key_to_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            entry = json.load(f)
        if time.time() - entry["ts"] > ttl_hours * 3600:
            return None
        return entry["data"]
    except Exception:
        return None


def set(key: str, value: Any) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _key_to_path(key)
    with open(path, "w") as f:
        json.dump({"ts": time.time(), "data": value}, f)


def invalidate(key: str) -> None:
    path = _key_to_path(key)
    if os.path.exists(path):
        os.remove(path)


def clear_all() -> None:
    if os.path.isdir(CACHE_DIR):
        for fname in os.listdir(CACHE_DIR):
            os.remove(os.path.join(CACHE_DIR, fname))
