import os, json, time, uuid
from typing import Any, Dict

SESS_DIR = os.path.join("backend", "data", "sessions")

def _mkdir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def new_session() -> str:
    _mkdir(SESS_DIR)
    sid = str(uuid.uuid4())
    path = os.path.join(SESS_DIR, f"{sid}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"session_id": sid, "created": time.time(), "reading": None, "chat": []}, f, indent=2)
    return sid

def load_session(session_id: str) -> Dict[str, Any]:
    path = os.path.join(SESS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(session_id)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_session(session_id: str, data: Dict[str, Any]) -> None:
    _mkdir(SESS_DIR)
    path = os.path.join(SESS_DIR, f"{session_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def append_chat(session_id: str, role: str, content: str) -> None:
    s = load_session(session_id)
    s["chat"].append({"role": role, "content": content, "ts": time.time()})
    save_session(session_id, s)

def set_reading(session_id: str, reading: Dict[str, Any]) -> None:
    s = load_session(session_id)
    s["reading"] = reading
    save_session(session_id, s)
