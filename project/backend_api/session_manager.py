from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import time
from uuid import uuid4

from backend_api.models import GuideState


@dataclass
class SessionContext:
    session_id: str
    target_label: str
    state: GuideState = GuideState.searching
    instruction: str = "请说出你要找的物品"
    speech_rate: str = "medium"
    offline_mode: bool = False
    done_latched: bool = False
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionContext] = {}
        self._lock = Lock()

    def create(self, target_label: str) -> SessionContext:
        sid = uuid4().hex
        ctx = SessionContext(
            session_id=sid,
            target_label=target_label.strip(),
            state=GuideState.searching,
            instruction=f"收到，开始搜索{target_label.strip()}",
        )
        with self._lock:
            self._sessions[sid] = ctx
        return ctx

    def get(self, session_id: str) -> SessionContext | None:
        with self._lock:
            return self._sessions.get(session_id)

    def update(self, ctx: SessionContext) -> None:
        ctx.updated_at = time()
        with self._lock:
            self._sessions[ctx.session_id] = ctx

    def reset(self, session_id: str) -> SessionContext | None:
        with self._lock:
            ctx = self._sessions.get(session_id)
            if ctx is None:
                return None
            ctx.state = GuideState.searching
            ctx.instruction = f"开始重新搜索{ctx.target_label}"
            ctx.done_latched = False
            ctx.updated_at = time()
            return ctx

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
