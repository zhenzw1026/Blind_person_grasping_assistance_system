from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from backend_api.bridge import GraspAssistBridge
from backend_api.models import (
    SessionResponse,
    SessionSettingsRequest,
    SessionStartRequest,
    VoiceCommandRequest,
    VoiceCommandResponse,
    VisionFrameRequest,
    VisionFrameResponse,
)
from backend_api.session_manager import SessionManager

router = APIRouter(prefix="/api")
sessions = SessionManager()
bridge = GraspAssistBridge()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/session/start", response_model=SessionResponse)
def start_session(payload: SessionStartRequest) -> SessionResponse:
    ctx = sessions.create(payload.target_label)
    bridge.apply_target(ctx.target_label)
    sessions.update(ctx)
    return SessionResponse(
        session_id=ctx.session_id,
        target_label=ctx.target_label,
        state=ctx.state,
        current_instruction=ctx.instruction,
    )


@router.post("/session/{session_id}/settings", status_code=status.HTTP_204_NO_CONTENT)
def update_settings(session_id: str, payload: SessionSettingsRequest) -> Response:
    ctx = sessions.get(session_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="session not found")

    ctx.speech_rate = payload.speech_rate
    ctx.offline_mode = payload.offline_mode
    sessions.update(ctx)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/vision/frame", response_model=VisionFrameResponse)
def process_frame(payload: VisionFrameRequest) -> VisionFrameResponse:
    ctx = sessions.get(payload.session_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="session not found")

    try:
        result = bridge.process_frame(ctx, payload.image_b64, payload.mirror_x)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sessions.update(ctx)
    return result


@router.post("/voice/command", response_model=VoiceCommandResponse)
def process_voice(payload: VoiceCommandRequest) -> VoiceCommandResponse:
    ctx = sessions.get(payload.session_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="session not found")

    result = bridge.process_voice(ctx, payload.transcript)
    sessions.update(ctx)
    return result


@router.post("/session/{session_id}/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_session(session_id: str) -> Response:
    ctx = sessions.reset(session_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="session not found")

    bridge.apply_target(ctx.target_label)
    sessions.update(ctx)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
