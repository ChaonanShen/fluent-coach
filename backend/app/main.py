import asyncio
import base64
import binascii
import json
import os
import time

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
    TurnSpeaker,
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
    _ensure_known_session(request.session_id)
    try:
        assessment = pronunciation_provider.assess(
            reference_text=request.reference_text,
            audio_file=request.audio_file,
            fixture_id=request.fixture_id,
        )
    except RuntimeError as exc:
        error = _provider_analysis_error(
            stage=AnalysisStage.PRONUNCIATION,
            exc=exc,
            provider_name=_provider_name(pronunciation_provider),
            fallback_applied=False,
        )
        _record_analysis_error_for_session(request.session_id, error)
        raise _analysis_http_error(error) from exc
    if assessment is None:
        raise HTTPException(status_code=404, detail="Pronunciation fixture not found")
    log_store.save_pronunciation_assessment(assessment)
    _record_pronunciation_for_session(request.session_id, assessment)
    mistake_service.add_from_pronunciation(assessment)
    return assessment


@app.post("/api/pronunciation/assess/upload", response_model=PronunciationAssessment)
def assess_uploaded_pronunciation(request: PronunciationUploadRequest) -> PronunciationAssessment:
    _ensure_known_session(request.session_id)
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
        error = _provider_analysis_error(
            stage=AnalysisStage.PRONUNCIATION,
            exc=exc,
            provider_name=_provider_name(pronunciation_provider),
            fallback_applied=False,
        )
        _record_analysis_error_for_session(request.session_id, error)
        raise _analysis_http_error(error) from exc
    if assessment is None:
        raise HTTPException(status_code=404, detail="Pronunciation assessment failed")
    log_store.save_pronunciation_assessment(assessment)
    _record_pronunciation_for_session(request.session_id, assessment)
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
        pronunciation_results=analysis_store.pronunciation_results(session_id),
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
                turn_timing_started = time.perf_counter()
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
                timings = {
                    "audio_write_ms": stored_audio.raw_write_ms,
                    "audio_transcode_ms": stored_audio.transcode_ms,
                    "audio_total_ms": stored_audio.total_ms,
                }
                if stored_audio.conversion_error and _provider_name(asr_provider) != "fake":
                    timings["end_turn_to_error_ms"] = _elapsed_ms(turn_timing_started)
                    error = _provider_analysis_error(
                        stage=AnalysisStage.ASR,
                        exc=RuntimeError(stored_audio.conversion_error),
                        provider_name=_provider_name(asr_provider),
                        fallback_applied=False,
                    )
                    analysis_store.add_error(session.id, error)
                    await websocket.send_json(
                        {
                            "type": "debug.timing",
                            "stage": "asr",
                            "timings": timings,
                        }
                    )
                    await websocket.send_json(
                        {
                            "type": "analysis.error",
                            "stage": "asr",
                            "error": error.model_dump(mode="json"),
                        }
                    )
                    audio.clear()
                    expected_text = None
                    audio_mime_type = None
                    force_analysis_error = False
                    continue
                try:
                    asr_started = time.perf_counter()
                    transcript = asr_provider.transcribe_file(stored_audio.preferred_path, expected_text)
                    timings["asr_ms"] = _elapsed_ms(asr_started)
                except RuntimeError as exc:
                    timings["end_turn_to_error_ms"] = _elapsed_ms(turn_timing_started)
                    error = _provider_analysis_error(
                        stage=AnalysisStage.ASR,
                        exc=exc,
                        provider_name=_provider_name(asr_provider),
                        fallback_applied=False,
                    )
                    analysis_store.add_error(session.id, error)
                    await websocket.send_json(
                        {
                            "type": "debug.timing",
                            "stage": "asr",
                            "timings": timings,
                        }
                    )
                    await websocket.send_json(
                        {
                            "type": "analysis.error",
                            "stage": "asr",
                            "error": error.model_dump(mode="json"),
                        }
                    )
                    audio.clear()
                    expected_text = None
                    audio_mime_type = None
                    force_analysis_error = False
                    continue
                if not transcript.strip():
                    timings["end_turn_to_error_ms"] = _elapsed_ms(turn_timing_started)
                    error = AnalysisError(
                        stage=AnalysisStage.ASR,
                        code="asr_no_speech",
                        user_message_zh="没有识别到有效语音，请重新录制这一句。",
                        severity=AnalysisErrorSeverity.WARNING,
                        fallback_applied=False,
                        provider=_provider_name(asr_provider),
                    )
                    analysis_store.add_error(session.id, error)
                    await websocket.send_json(
                        {
                            "type": "debug.timing",
                            "stage": "asr",
                            "timings": timings,
                        }
                    )
                    await websocket.send_json(
                        {
                            "type": "analysis.error",
                            "stage": "asr",
                            "error": error.model_dump(mode="json"),
                        }
                    )
                    audio.clear()
                    expected_text = None
                    audio_mime_type = None
                    force_analysis_error = False
                    continue
                await websocket.send_json({"type": "asr.final", "text": transcript})
                timings["end_turn_to_asr_final_ms"] = _elapsed_ms(turn_timing_started)
                dialogue_started = time.perf_counter()
                stream_reply = dialogue_service.generate_reply_stream(
                    session=session,
                    scenario=scenario,
                    user_text=transcript,
                )
                if stream_reply is None:
                    user_turn, ai_turn, reply = dialogue_service.add_text_turns(
                        session=session,
                        scenario=scenario,
                        user_text=transcript,
                        user_mode="audio",
                        user_audio_path=str(stored_audio.preferred_path),
                    )
                    timings["dialogue_reply_ms"] = _elapsed_ms(dialogue_started)
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
                else:
                    user_turn = session.add_turn(
                        speaker=TurnSpeaker.USER,
                        text=transcript,
                        mode="audio",
                        audio_path=str(stored_audio.preferred_path),
                    )
                    reply_text_parts: list[str] = []
                    first_delta = True
                    try:
                        for chunk in stream_reply.chunks:
                            if not chunk:
                                continue
                            if first_delta:
                                timings["reply_first_delta_ms"] = _elapsed_ms(dialogue_started)
                                first_delta = False
                            reply_text_parts.append(chunk)
                            await websocket.send_json(
                                {
                                    "type": "reply.delta",
                                    "text": chunk,
                                    "user_turn_id": user_turn.id,
                                    "current_goal": stream_reply.current_goal,
                                    "next_intent": stream_reply.next_intent,
                                }
                            )
                    except Exception:
                        fallback = dialogue_service.generate_reply(
                            session=session,
                            scenario=scenario,
                            user_text=transcript,
                        )
                        reply_text_parts = [fallback.text]
                        stream_reply.current_goal = fallback.current_goal
                        stream_reply.next_intent = fallback.next_intent

                    reply_text = "".join(reply_text_parts).strip()
                    if not reply_text:
                        fallback = dialogue_service.generate_reply(
                            session=session,
                            scenario=scenario,
                            user_text=transcript,
                        )
                        reply_text = fallback.text
                        stream_reply.current_goal = fallback.current_goal
                        stream_reply.next_intent = fallback.next_intent
                    ai_turn = session.add_turn(speaker=TurnSpeaker.AI, text=reply_text)
                    timings["dialogue_reply_ms"] = _elapsed_ms(dialogue_started)
                    session_store.save(session)
                    await websocket.send_json(
                        {
                            "type": "reply.done",
                            "text": ai_turn.text,
                            "turn_id": ai_turn.id,
                            "user_turn_id": user_turn.id,
                            "current_goal": stream_reply.current_goal,
                            "next_intent": stream_reply.next_intent,
                        }
                    )
                timings["end_turn_to_reply_text_ms"] = _elapsed_ms(turn_timing_started)
                await websocket.send_json(
                    {
                        "type": "debug.timing",
                        "stage": "reply",
                        "timings": timings,
                    }
                )
                analysis_stages = ["grammar"]
                assess_audio_pronunciation = _should_assess_audio_turn_pronunciation()
                if assess_audio_pronunciation:
                    analysis_stages.append("pronunciation")
                await websocket.send_json({"type": "analysis.pending", "stages": analysis_stages})
                asyncio.create_task(
                    _run_ws_grammar_analysis(
                        websocket=websocket,
                        session_id=session.id,
                        scenario_id=scenario.id,
                        user_text=transcript,
                        conversation_context=[turn.text for turn in session.turns],
                        force_analysis_error=force_analysis_error,
                        timings=dict(timings),
                    )
                )
                if assess_audio_pronunciation:
                    asyncio.create_task(
                        _run_ws_pronunciation_analysis(
                            websocket=websocket,
                            session_id=session.id,
                            reference_text=transcript,
                            audio_file=str(stored_audio.preferred_path.resolve()),
                            timings=dict(timings),
                        )
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


async def _run_ws_grammar_analysis(
    *,
    websocket: WebSocket,
    session_id: str,
    scenario_id: str,
    user_text: str,
    conversation_context: list[str],
    force_analysis_error: bool,
    timings: dict[str, float],
) -> None:
    grammar_started = time.perf_counter()
    if force_analysis_error:
        error = AnalysisError(
            stage=AnalysisStage.GRAMMAR,
            code="forced_analysis_error",
            user_message_zh="语法分析暂时不可用，已保留本轮对话。",
            severity=AnalysisErrorSeverity.WARNING,
            fallback_applied=True,
        )
        analysis_store.add_error(session_id, error)
        timings["grammar_ms"] = _elapsed_ms(grammar_started)
        await _safe_send_json(
            websocket,
            {
                "type": "debug.timing",
                "stage": "grammar",
                "timings": timings,
            },
        )
        await _safe_send_json(
            websocket,
            {
                "type": "analysis.error",
                "error": error.model_dump(mode="json"),
            },
        )
        return

    correction = await asyncio.to_thread(
        grammar_service.check,
        scenario_id=scenario_id,
        user_text=user_text,
        conversation_context=conversation_context,
    )
    log_store.save_grammar_correction(correction)
    mistake_service.add_from_grammar(correction)
    analysis_store.add_grammar_result(session_id, correction)
    timings["grammar_ms"] = _elapsed_ms(grammar_started)
    await _safe_send_json(
        websocket,
        {
            "type": "debug.timing",
            "stage": "grammar",
            "timings": timings,
        },
    )
    await _safe_send_json(
        websocket,
        {
            "type": "analysis.result",
            "stage": "grammar",
            "result": correction.model_dump(mode="json"),
        },
    )


async def _run_ws_pronunciation_analysis(
    *,
    websocket: WebSocket,
    session_id: str,
    reference_text: str,
    audio_file: str,
    timings: dict[str, float],
) -> None:
    pronunciation_started = time.perf_counter()
    try:
        assessment = await asyncio.to_thread(
            pronunciation_provider.assess,
            reference_text=reference_text,
            audio_file=audio_file,
        )
    except RuntimeError as exc:
        error = _provider_analysis_error(
            stage=AnalysisStage.PRONUNCIATION,
            exc=exc,
            provider_name=_provider_name(pronunciation_provider),
            fallback_applied=False,
        )
        analysis_store.add_error(session_id, error)
        timings["pronunciation_ms"] = _elapsed_ms(pronunciation_started)
        await _safe_send_json(
            websocket,
            {
                "type": "debug.timing",
                "stage": "pronunciation",
                "timings": timings,
            },
        )
        await _safe_send_json(
            websocket,
            {
                "type": "analysis.error",
                "stage": "pronunciation",
                "error": error.model_dump(mode="json"),
            },
        )
        return

    timings["pronunciation_ms"] = _elapsed_ms(pronunciation_started)
    await _safe_send_json(
        websocket,
        {
            "type": "debug.timing",
            "stage": "pronunciation",
            "timings": timings,
        },
    )
    if assessment is None:
        error = AnalysisError(
            stage=AnalysisStage.PRONUNCIATION,
            code="pronunciation_unavailable",
            user_message_zh="本轮语音暂时无法生成发音评测，已保留对话结果。",
            severity=AnalysisErrorSeverity.INFO,
            fallback_applied=True,
            provider=_provider_name(pronunciation_provider),
        )
        analysis_store.add_error(session_id, error)
        await _safe_send_json(
            websocket,
            {
                "type": "analysis.error",
                "stage": "pronunciation",
                "error": error.model_dump(mode="json"),
            },
        )
        return

    log_store.save_pronunciation_assessment(assessment)
    analysis_store.add_pronunciation_result(session_id, assessment)
    mistake_service.add_from_pronunciation(assessment)
    await _safe_send_json(
        websocket,
        {
            "type": "analysis.result",
            "stage": "pronunciation",
            "result": assessment.model_dump(mode="json"),
        },
    )


async def _safe_send_json(websocket: WebSocket, payload: dict[str, object]) -> bool:
    try:
        await websocket.send_json(payload)
    except (RuntimeError, WebSocketDisconnect):
        return False
    return True


def _provider_analysis_error(
    *,
    stage: AnalysisStage,
    exc: RuntimeError,
    provider_name: str | None = None,
    fallback_applied: bool,
) -> AnalysisError:
    code, user_message_zh = _classify_provider_error(
        stage=stage,
        provider_name=provider_name,
        exc=exc,
    )
    return AnalysisError(
        stage=stage,
        code=code,
        user_message_zh=user_message_zh,
        severity=AnalysisErrorSeverity.WARNING,
        fallback_applied=fallback_applied,
        provider=provider_name or stage.value,
        raw_code=type(exc).__name__,
    )


def _analysis_http_error(error: AnalysisError) -> HTTPException:
    return HTTPException(status_code=502, detail=error.model_dump(mode="json"))


def _provider_name(provider: object) -> str | None:
    value = getattr(provider, "provider_name", None)
    return value if isinstance(value, str) and value else None


def _ensure_known_session(session_id: str | None) -> None:
    if session_id is None:
        return
    if session_store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="Unknown session")


def _record_pronunciation_for_session(
    session_id: str | None,
    assessment: PronunciationAssessment,
) -> None:
    if session_id is None:
        return
    analysis_store.add_pronunciation_result(session_id, assessment)


def _record_analysis_error_for_session(
    session_id: str | None,
    error: AnalysisError,
) -> None:
    if session_id is None:
        return
    analysis_store.add_error(session_id, error)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 1)


def _should_assess_audio_turn_pronunciation() -> bool:
    configured = os.environ.get("PRON_ASSESS_AUDIO_TURNS", "").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    return _provider_name(pronunciation_provider) not in {None, "mock"}


def _classify_provider_error(
    *,
    stage: AnalysisStage,
    provider_name: str | None,
    exc: RuntimeError,
) -> tuple[str, str]:
    if stage == AnalysisStage.PRONUNCIATION and provider_name == "tencent_soe":
        return _classify_tencent_soe_error(exc)
    if stage == AnalysisStage.ASR:
        return _classify_asr_error(exc)
    return "provider_request_failed", "外部服务暂时不可用，请稍后重试。"


def _classify_asr_error(exc: RuntimeError) -> tuple[str, str]:
    message = str(exc).lower()
    if "faster-whisper" in message or "not installed" in message:
        return "provider_dependency_missing", "本地语音识别依赖缺失，请安装 faster-whisper 后重试。"
    if "ffmpeg_missing" in message or "ffmpeg" in message:
        return "provider_dependency_missing", "音频转码工具 ffmpeg 缺失，请安装后重试。"
    if "transcode_failed" in message or any(token in message for token in ["decode", "codec", "invalid audio"]):
        return "invalid_audio", "音频格式暂时无法识别，请重新录音后再试。"
    if "model" in message or "no such file" in message or "not found" in message:
        return "provider_model_unavailable", "本地 ASR 模型不可用，请检查模型路径。"
    if "timeout" in message or "timed out" in message:
        return "provider_timeout", "语音识别超时，请稍后重试。"
    return "provider_request_failed", "语音识别暂时不可用，请稍后重试。"


def _classify_tencent_soe_error(exc: RuntimeError) -> tuple[str, str]:
    message = str(exc).lower()
    if "missing required env var" in message:
        return "provider_config_missing", "腾讯云发音评测配置缺失，请检查服务配置。"
    if any(token in message for token in ["auth", "signature", "secret", "unauthorized", "forbidden", "401", "403"]):
        return "provider_auth_failed", "腾讯云发音评测鉴权失败，请检查密钥和签名配置。"
    if any(token in message for token in ["rate limit", "rate_limited", "too many", "throttle", "limit exceeded"]):
        return "provider_rate_limited", "腾讯云发音评测请求过于频繁，请稍后重试。"
    if any(token in message for token in ["timeout", "timed out"]):
        return "provider_timeout", "腾讯云发音评测超时，请稍后重试。"
    if any(token in message for token in ["audio", "voice_format", "format", "codec"]):
        return "invalid_audio", "音频格式暂时无法评测，请重新录音后再试。"
    if any(token in message for token in ["handshake", "websocket upgrade", "connection closed"]):
        return "provider_handshake_failed", "腾讯云发音评测连接失败，请稍后重试。"
    return "provider_request_failed", "腾讯云发音评测暂时不可用，请稍后重试。"
