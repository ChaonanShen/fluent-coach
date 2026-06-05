import base64
import binascii
import json

from backend.app.core.env import load_dotenv, provider_status

load_dotenv()

from fastapi import FastAPI, HTTPException
from starlette.websockets import WebSocket, WebSocketDisconnect

from backend.app.api import (
    CreateSessionRequest,
    GrammarCheckRequest,
    MistakeListResponse,
    ProgressResponse,
    PronunciationAssessRequest,
    PronunciationUploadRequest,
    ScenarioListResponse,
    SessionAnalysisResponse,
    SessionResponse,
    TextTurnRequest,
    TextTurnResponse,
    TTSRequest,
    TTSResponse,
)
from backend.app.core.fixtures import get_fixture_status
from backend.app.models import (
    AnalysisError,
    AnalysisErrorSeverity,
    AnalysisStage,
    GrammarCorrection,
    MistakeItem,
    PronunciationAssessment,
    SessionSummary,
)
from backend.app.services.analysis import analysis_store
from backend.app.services.asr import asr_provider
from backend.app.services.audio import save_turn_audio
from backend.app.services.dialogue import dialogue_service
from backend.app.services.grammar import grammar_service
from backend.app.services.mistakes import mistake_service
from backend.app.services.pronunciation import pronunciation_provider
from backend.app.services.progress import progress_service
from backend.app.services.scenarios import get_scenario, list_scenarios
from backend.app.services.sessions import session_store
from backend.app.services.storage import log_store
from backend.app.services.summary import summary_service
from backend.app.services.tts import tts_provider

app = FastAPI(title="XEngineer AI English Speaking Coach", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "fixtures": get_fixture_status(),
        "providers": provider_status(),
    }


@app.get("/api/scenarios", response_model=ScenarioListResponse)
def scenarios() -> ScenarioListResponse:
    return ScenarioListResponse(scenarios=list(list_scenarios()))


@app.post("/api/sessions", response_model=SessionResponse, status_code=201)
def create_session(request: CreateSessionRequest) -> SessionResponse:
    scenario = get_scenario(request.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Unknown scenario")
    session = session_store.create(scenario)
    return SessionResponse(
        session=session,
        scenario=scenario,
        opening_line=scenario.opening_line,
        conversation_goals=scenario.conversation_goals,
        target_expressions=scenario.target_expressions,
    )


@app.post("/api/sessions/{session_id}/end", response_model=SessionResponse)
def end_session(session_id: str) -> SessionResponse:
    session = session_store.end(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    scenario = get_scenario(session.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=500, detail="Session references an unknown scenario")
    return SessionResponse(
        session=session,
        scenario=scenario,
        opening_line=scenario.opening_line,
        conversation_goals=scenario.conversation_goals,
        target_expressions=scenario.target_expressions,
    )


@app.post("/api/grammar/check", response_model=GrammarCorrection)
def check_grammar(request: GrammarCheckRequest) -> GrammarCorrection:
    scenario = get_scenario(request.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Unknown scenario")
    correction = grammar_service.check(
        scenario_id=request.scenario_id,
        user_text=request.user_text,
        conversation_context=request.conversation_context,
    )
    log_store.save_grammar_correction(correction)
    mistake_service.add_from_grammar(correction)
    return correction


@app.post("/api/sessions/{session_id}/turns/text", response_model=TextTurnResponse)
def add_text_turn(session_id: str, request: TextTurnRequest) -> TextTurnResponse:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    scenario = get_scenario(session.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=500, detail="Session references an unknown scenario")
    user_turn, ai_turn, reply = dialogue_service.add_text_turns(
        session=session,
        scenario=scenario,
        user_text=request.text,
    )
    correction = grammar_service.check(
        scenario_id=scenario.id,
        user_text=request.text,
        conversation_context=[turn.text for turn in session.turns],
    )
    log_store.save_grammar_correction(correction)
    mistake_service.add_from_grammar(correction)
    analysis_store.add_grammar_result(session.id, correction)
    session_store.save(session)
    return TextTurnResponse(
        session=session,
        user_turn=user_turn,
        ai_turn=ai_turn,
        current_goal=reply.current_goal,
        next_intent=reply.next_intent,
        grammar_result=correction,
    )


@app.post("/api/pronunciation/assess", response_model=PronunciationAssessment)
def assess_pronunciation(request: PronunciationAssessRequest) -> PronunciationAssessment:
    try:
        assessment = pronunciation_provider.assess(
            reference_text=request.reference_text,
            audio_file=request.audio_file,
            fixture_id=request.fixture_id,
        )
    except RuntimeError as exc:
        raise _provider_http_error(stage=AnalysisStage.PRONUNCIATION, exc=exc) from exc
    if assessment is None:
        raise HTTPException(status_code=404, detail="Pronunciation fixture not found")
    log_store.save_pronunciation_assessment(assessment)
    mistake_service.add_from_pronunciation(assessment)
    return assessment


@app.post("/api/pronunciation/assess/upload", response_model=PronunciationAssessment)
def assess_uploaded_pronunciation(request: PronunciationUploadRequest) -> PronunciationAssessment:
    try:
        audio_bytes = base64.b64decode(request.audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid audio_base64") from exc
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty")

    stored_audio = save_turn_audio(
        session_id="pronunciation",
        audio_bytes=audio_bytes,
        mime_type=request.mime_type,
    )
    try:
        assessment = pronunciation_provider.assess(
            reference_text=request.reference_text,
            audio_file=str(stored_audio.preferred_path.resolve()),
        )
    except RuntimeError as exc:
        raise _provider_http_error(stage=AnalysisStage.PRONUNCIATION, exc=exc) from exc
    if assessment is None:
        raise HTTPException(status_code=404, detail="Pronunciation assessment failed")
    log_store.save_pronunciation_assessment(assessment)
    mistake_service.add_from_pronunciation(assessment)
    return assessment


@app.get("/api/sessions/{session_id}/summary", response_model=SessionSummary)
def get_session_summary(session_id: str) -> SessionSummary:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    scenario = get_scenario(session.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=500, detail="Session references an unknown scenario")
    return summary_service.summarize(session=session, scenario=scenario)


@app.get("/api/sessions/{session_id}/analysis", response_model=SessionAnalysisResponse)
def get_session_analysis(session_id: str) -> SessionAnalysisResponse:
    if session_store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return SessionAnalysisResponse(
        session_id=session_id,
        grammar_results=analysis_store.grammar_results(session_id),
        errors=analysis_store.errors(session_id),
    )


@app.get("/api/mistakes", response_model=MistakeListResponse)
def list_mistakes() -> MistakeListResponse:
    return MistakeListResponse(mistakes=mistake_service.list())


@app.post("/api/mistakes/{mistake_id}/review", response_model=MistakeItem)
def review_mistake(mistake_id: str) -> MistakeItem:
    mistake = mistake_service.review(mistake_id)
    if mistake is None:
        raise HTTPException(status_code=404, detail="Unknown mistake")
    return mistake


@app.get("/api/progress", response_model=ProgressResponse)
def get_progress() -> ProgressResponse:
    return progress_service.get_progress()


@app.post("/api/tts/synthesize", response_model=TTSResponse)
def synthesize_tts(request: TTSRequest) -> TTSResponse:
    result = tts_provider.synthesize(request.text)
    return TTSResponse(
        provider=result.provider,
        text=result.text,
        audio_url=result.audio_url,
        fallback_applied=result.fallback_applied,
    )


@app.websocket("/ws/sessions/{session_id}/audio")
async def session_audio(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session = session_store.get(session_id)
    if session is None:
        await websocket.send_json({"type": "error", "code": "unknown_session", "message": "Unknown session"})
        await websocket.close()
        return
    scenario = get_scenario(session.scenario_id)
    if scenario is None:
        await websocket.send_json(
            {
                "type": "error",
                "code": "unknown_scenario",
                "message": "Session references an unknown scenario",
            }
        )
        await websocket.close()
        return

    expected_text: str | None = None
    audio_mime_type: str | None = None
    force_analysis_error = False
    audio = bytearray()
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                audio.extend(message["bytes"])
                continue
            raw_text = message.get("text")
            if raw_text is None:
                continue
            event = json.loads(raw_text)
            event_type = event.get("type")
            if event_type == "start_turn":
                expected_text = event.get("expected_text")
                audio_mime_type = event.get("mime_type")
                force_analysis_error = bool(event.get("force_analysis_error", False))
                audio.clear()
                await websocket.send_json({"type": "asr.partial", "text": asr_provider.partial(expected_text)})
            elif event_type == "end_turn":
                if not audio:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "empty_audio",
                            "message": "No audio was received for this turn.",
                        }
                    )
                    expected_text = None
                    audio_mime_type = None
                    force_analysis_error = False
                    continue
                stored_audio = save_turn_audio(
                    session_id=session.id,
                    audio_bytes=bytes(audio),
                    mime_type=audio_mime_type,
                )
                transcript = asr_provider.transcribe_file(stored_audio.preferred_path, expected_text)
                await websocket.send_json({"type": "asr.final", "text": transcript})
                user_turn, ai_turn, reply = dialogue_service.add_text_turns(
                    session=session,
                    scenario=scenario,
                    user_text=transcript,
                    user_mode="audio",
                    user_audio_path=str(stored_audio.preferred_path),
                )
                session_store.save(session)
                await websocket.send_json(
                    {
                        "type": "reply.text",
                        "text": ai_turn.text,
                        "turn_id": ai_turn.id,
                        "user_turn_id": user_turn.id,
                        "current_goal": reply.current_goal,
                        "next_intent": reply.next_intent,
                    }
                )
                await websocket.send_json({"type": "analysis.pending", "stages": ["grammar"]})
                if force_analysis_error:
                    error = AnalysisError(
                        stage=AnalysisStage.GRAMMAR,
                        code="forced_analysis_error",
                        user_message_zh="语法分析暂时不可用，已保留本轮对话。",
                        severity=AnalysisErrorSeverity.WARNING,
                        fallback_applied=True,
                    )
                    analysis_store.add_error(session.id, error)
                    await websocket.send_json(
                        {
                            "type": "analysis.error",
                            "error": error.model_dump(mode="json"),
                        }
                    )
                else:
                    correction = grammar_service.check(
                        scenario_id=scenario.id,
                        user_text=transcript,
                        conversation_context=[turn.text for turn in session.turns],
                    )
                    log_store.save_grammar_correction(correction)
                    mistake_service.add_from_grammar(correction)
                    analysis_store.add_grammar_result(session.id, correction)
                    await websocket.send_json(
                        {
                            "type": "analysis.result",
                            "stage": "grammar",
                            "result": correction.model_dump(mode="json"),
                        }
                    )
                audio.clear()
                expected_text = None
                audio_mime_type = None
                force_analysis_error = False
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "unknown_event",
                        "message": f"Unknown event type: {event_type}",
                    }
                )
    except (WebSocketDisconnect, json.JSONDecodeError):
        return


def _provider_http_error(*, stage: AnalysisStage, exc: RuntimeError) -> HTTPException:
    error = AnalysisError(
        stage=stage,
        code="provider_request_failed",
        user_message_zh="外部服务暂时不可用，请稍后重试。",
        severity=AnalysisErrorSeverity.WARNING,
        fallback_applied=False,
        provider=stage.value,
        raw_code=type(exc).__name__,
    )
    return HTTPException(status_code=502, detail=error.model_dump(mode="json"))
