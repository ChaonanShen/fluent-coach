from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from backend.app.core.fixtures import load_generated_manifest, resolve_fixture_audio
from backend.app.models import (
    GrammarSeverity,
    PhonemeScore,
    PronunciationAssessment,
    PronunciationIssue,
    PronunciationWordScore,
)


def _scale_0_10(value: object) -> float:
    return max(0.0, min(100.0, float(value) * 10.0))


def _scale_phone(value: object) -> float:
    return max(0.0, min(100.0, float(value) * 50.0))


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


@lru_cache(maxsize=1)
def _speechocean_items() -> tuple[dict[str, Any], ...]:
    return tuple(load_generated_manifest("speechocean762")["items"])


class MockPronunciationProvider:
    provider_name = "mock"

    def assess(
        self,
        *,
        reference_text: str | None = None,
        audio_file: str | None = None,
        fixture_id: str | None = None,
    ) -> PronunciationAssessment | None:
        item = self._find_item(
            reference_text=reference_text,
            audio_file=audio_file,
            fixture_id=fixture_id,
        )
        if item is None:
            return None
        sentence_scores = item["sentence_scores"]
        words = [self._word_score(word) for word in item["word_scores"]]
        issues = [
            PronunciationIssue(
                kind="word_accuracy",
                target=word.word,
                message_zh=f"`{word.word}` 发音准确度偏低，建议单独跟读。",
                severity=GrammarSeverity.MAJOR if word.accuracy < 50 else GrammarSeverity.MINOR,
            )
            for word in words
            if word.accuracy < 60
        ]
        return PronunciationAssessment(
            provider=self.provider_name,
            reference_text=reference_text or item["transcript"],
            audio_file=audio_file or item["audio_file"],
            overall=_scale_0_10(sentence_scores["total"]),
            accuracy=_scale_0_10(sentence_scores["accuracy"]),
            fluency=_scale_0_10(sentence_scores["fluency"]),
            prosody=_scale_0_10(sentence_scores["prosodic"]),
            completeness=_scale_0_10(sentence_scores["completeness"]),
            words=words,
            issues=issues,
        )

    def _find_item(
        self,
        *,
        reference_text: str | None,
        audio_file: str | None,
        fixture_id: str | None,
    ) -> dict[str, Any] | None:
        for item in _speechocean_items():
            if fixture_id and item["id"] == fixture_id:
                return item
            if audio_file and item["audio_file"] == audio_file:
                return item
            if reference_text and _normalize(item["transcript"]) == _normalize(reference_text):
                return item
        return None

    def _word_score(self, word: dict[str, Any]) -> PronunciationWordScore:
        return PronunciationWordScore(
            word=word["text"],
            accuracy=_scale_0_10(word["accuracy"]),
            phonemes=[
                PhonemeScore(phoneme=phone, accuracy=_scale_phone(score))
                for phone, score in zip(word["phones"], word["phones-accuracy"], strict=True)
            ],
            issue="low_accuracy" if _scale_0_10(word["accuracy"]) < 60 else None,
        )


class TencentSOEProvider:
    provider_name = "tencent_soe"
    default_ws_url = "wss://soe.cloud.tencent.com/soe/api"

    def assess(
        self,
        *,
        reference_text: str | None = None,
        audio_file: str | None = None,
        fixture_id: str | None = None,
    ) -> PronunciationAssessment | None:
        item = MockPronunciationProvider()._find_item(
            reference_text=reference_text,
            audio_file=audio_file,
            fixture_id=fixture_id,
        )
        if item is not None:
            reference_text = reference_text or item["transcript"]
            audio_file = audio_file or item["audio_file"]
        if not reference_text or not audio_file:
            return None

        audio_path = resolve_fixture_audio(audio_file)
        if not audio_path.exists():
            return None

        url = build_tencent_signed_url(
            ref_text=reference_text,
            voice_format=infer_voice_format(audio_path),
        )
        result = self._request_assessment(url=url, audio_bytes=audio_path.read_bytes())
        return self.map_result(
            result=result,
            reference_text=reference_text,
            audio_file=audio_file,
        )

    def _request_assessment(self, *, url: str, audio_bytes: bytes) -> dict[str, Any]:
        try:
            from websockets.sync.client import connect
        except ImportError as exc:  # pragma: no cover - dependency comes from uvicorn[standard].
            raise RuntimeError("websockets package is required for Tencent SOE provider") from exc

        timeout = float(os.environ.get("TENCENT_SOE_TIMEOUT", "30") or 30)
        with connect(url, open_timeout=timeout, close_timeout=timeout) as websocket:
            handshake = json.loads(websocket.recv(timeout=timeout))
            if handshake.get("code") != 0:
                raise RuntimeError(f"Tencent SOE handshake failed: {handshake}")
            websocket.send(audio_bytes)
            websocket.send(json.dumps({"type": "end"}, ensure_ascii=False))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                message = json.loads(websocket.recv(timeout=timeout))
                if message.get("code") not in {0, None}:
                    raise RuntimeError(f"Tencent SOE assessment failed: {message}")
                if message.get("final") == 1:
                    result = message.get("result")
                    if isinstance(result, dict):
                        return result
                    raise RuntimeError(f"Tencent SOE final result missing result object: {message}")
        raise RuntimeError("Tencent SOE timed out waiting for final assessment result")

    def map_result(
        self,
        *,
        result: dict[str, Any],
        reference_text: str,
        audio_file: str | None,
    ) -> PronunciationAssessment:
        words = [self._map_word(word) for word in result.get("Words", []) if isinstance(word, dict)]
        issues = [
            PronunciationIssue(
                kind="word_accuracy",
                target=word.word,
                message_zh=f"`{word.word}` 发音准确度偏低，建议单独跟读。",
                severity=GrammarSeverity.MAJOR if word.accuracy < 50 else GrammarSeverity.MINOR,
            )
            for word in words
            if word.accuracy < 60
        ]
        accuracy = normalize_tencent_score(result.get("PronAccuracy"))
        return PronunciationAssessment(
            provider=self.provider_name,
            reference_text=reference_text,
            audio_file=audio_file,
            overall=normalize_tencent_score(result.get("SuggestedScore", accuracy)),
            accuracy=accuracy,
            fluency=normalize_tencent_score(result.get("PronFluency")),
            completeness=normalize_tencent_score(result.get("PronCompletion")),
            words=words,
            issues=issues,
        )

    def _map_word(self, word: dict[str, Any]) -> PronunciationWordScore:
        text = str(word.get("Word") or word.get("ReferenceWord") or "").strip()
        if not text:
            text = "unknown"
        phone_infos = word.get("PhoneInfos", [])
        phonemes = [
            PhonemeScore(
                phoneme=str(phone.get("Phone") or phone.get("ReferencePhone") or "").strip() or "unknown",
                accuracy=normalize_tencent_score(phone.get("PronAccuracy")),
            )
            for phone in phone_infos
            if isinstance(phone, dict)
        ]
        accuracy = normalize_tencent_score(word.get("PronAccuracy"))
        return PronunciationWordScore(
            word=text,
            accuracy=accuracy,
            phonemes=phonemes,
            issue="low_accuracy" if accuracy < 60 else None,
        )


def infer_voice_format(audio_path: Path) -> int:
    suffix = audio_path.suffix.lower()
    if suffix == ".wav":
        return 1
    if suffix == ".mp3":
        return 2
    if suffix in {".sp", ".speex"}:
        return 4
    return 0


def normalize_tencent_score(raw: object) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if 0.0 <= value <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, value))


def build_tencent_signed_url(
    *,
    ref_text: str,
    voice_format: int,
    timestamp: int | None = None,
    nonce: int | None = None,
    voice_id: str | None = None,
) -> str:
    app_id = require_env("TENCENT_APP_ID")
    secret_id = require_env("TENCENT_SECRET_ID")
    secret_key = require_env("TENCENT_SECRET_KEY")
    base_url = os.environ.get("TENCENT_SOE_WS_URL", TencentSOEProvider.default_ws_url).strip()
    if not base_url.startswith("wss://"):
        base_url = TencentSOEProvider.default_ws_url
    parsed = urlsplit(base_url)
    host = parsed.netloc
    path = parsed.path.rstrip("/")
    path_with_appid = f"{path}/{app_id}"
    now = timestamp if timestamp is not None else int(time.time())

    params = {
        "eval_mode": os.environ.get("TENCENT_SOE_EVAL_MODE", "1") or "1",
        "expired": str(now + int(os.environ.get("TENCENT_SOE_EXPIRE_SECONDS", "86400") or 86400)),
        "nonce": str(nonce if nonce is not None else secrets.randbelow(9_999_999_999) + 1),
        "ref_text": ref_text,
        "score_coeff": os.environ.get("TENCENT_SOE_SCORE_COEFF", "3.0") or "3.0",
        "secretid": secret_id,
        "sentence_info_enabled": os.environ.get("TENCENT_SOE_SENTENCE_INFO_ENABLED", "1") or "1",
        "server_engine_type": os.environ.get("TENCENT_SOE_SERVER_ENGINE_TYPE", "16k_en") or "16k_en",
        "text_mode": os.environ.get("TENCENT_SOE_TEXT_MODE", "0") or "0",
        "timestamp": str(now),
        "voice_format": str(voice_format),
        "voice_id": voice_id or str(uuid.uuid4()),
    }
    rec_mode = os.environ.get("TENCENT_SOE_REC_MODE")
    if rec_mode:
        params["rec_mode"] = rec_mode

    canonical_query = "&".join(f"{key}={params[key]}" for key in sorted(params.keys()))
    sign_text = f"{host}{path_with_appid}?{canonical_query}"
    signature = base64.b64encode(
        hmac.new(secret_key.encode("utf-8"), sign_text.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    request_query = urlencode({**params, "signature": signature})
    return f"wss://{host}{path_with_appid}?{request_query}"


def tencent_signed_url_diagnostics(url: str) -> dict[str, object]:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)

    def first(name: str) -> str | None:
        values = query.get(name)
        return values[0] if values else None

    return {
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "path_shape": _redact_appid_path(parsed.path),
        "query_keys": sorted(query.keys()),
        "has_signature": bool(first("signature")),
        "signature_chars": len(first("signature") or ""),
        "has_secretid": bool(first("secretid")),
        "ref_text_chars": len(first("ref_text") or ""),
        "server_engine_type": first("server_engine_type"),
        "eval_mode": first("eval_mode"),
        "text_mode": first("text_mode"),
        "voice_format": first("voice_format"),
        "score_coeff": first("score_coeff"),
        "timestamp_present": bool(first("timestamp")),
        "expired_present": bool(first("expired")),
        "nonce_present": bool(first("nonce")),
        "voice_id_present": bool(first("voice_id")),
    }


def _redact_appid_path(path: str) -> str:
    parts = path.strip("/").split("/")
    if not parts:
        return "/"
    if parts[-1].isdigit():
        parts[-1] = "<appid>"
    return "/" + "/".join(parts)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def create_pronunciation_provider() -> MockPronunciationProvider | TencentSOEProvider:
    if os.environ.get("PRON_PROVIDER", "mock").strip().lower() == "tencent_soe":
        return TencentSOEProvider()
    return MockPronunciationProvider()


pronunciation_provider = create_pronunciation_provider()
