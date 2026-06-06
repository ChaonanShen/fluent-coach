#!/usr/bin/env python3
"""Standalone Tencent Cloud SOE WebSocket diagnostic script.

This script intentionally does not import backend application code and does not
require third-party websocket packages. It tests the Tencent SOE service itself:

1. load Tencent credentials from .env or the process environment
2. build the signed SOE WebSocket URL
3. open a raw WebSocket connection
4. upload one local audio file
5. print the handshake, final result, and safe diagnostics
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import ssl
import struct
import sys
import time
import uuid
import wave
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit


DEFAULT_WS_URL = "wss://soe.cloud.tencent.com/soe/api"
DEFAULT_MANIFEST = Path("fixtures/generated/speechocean762_subset.json")
DEFAULT_REF_TEXT = "hello"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(
            f"Fixture manifest not found: {path}. "
            "Run `python3 scripts/extract_fixtures.py` or pass --audio and --ref-text."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_manifest_audio(manifest_path: Path, item: dict[str, Any]) -> Path:
    audio_file = item.get("audio_file")
    if not isinstance(audio_file, str) or not audio_file:
        raise RuntimeError(f"Manifest item {item.get('id')} has no audio_file")
    if audio_file.startswith("fixtures/"):
        return Path(audio_file)
    return manifest_path.parent.parent / audio_file


def select_manifest_item(
    manifest_path: Path,
    item_id: str | None,
) -> tuple[dict[str, Any], Path]:
    manifest = load_manifest(manifest_path)
    items = manifest.get("items")
    if not isinstance(items, list):
        raise RuntimeError(f"Manifest has no items list: {manifest_path}")

    for item in items:
        if not isinstance(item, dict):
            continue
        if item_id and item.get("id") != item_id:
            continue
        audio_path = resolve_manifest_audio(manifest_path, item)
        if audio_path.exists():
            return item, audio_path

    if item_id:
        raise RuntimeError(f"No existing audio found for manifest item: {item_id}")
    raise RuntimeError(f"No existing audio files found in manifest: {manifest_path}")


def find_manifest_text_for_audio(
    manifest_path: Path,
    audio_path: Path,
) -> tuple[dict[str, Any], str] | None:
    try:
        manifest = load_manifest(manifest_path)
    except RuntimeError:
        return None

    items = manifest.get("items")
    if not isinstance(items, list):
        return None
    target = audio_path.resolve()
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = resolve_manifest_audio(manifest_path, item)
        if candidate.exists() and candidate.resolve() == target:
            transcript = item.get("transcript")
            if isinstance(transcript, str) and transcript.strip():
                return item, transcript.strip()
    return None


def infer_voice_format(audio_path: Path | None) -> int:
    if audio_path is None:
        return 1
    suffix = audio_path.suffix.lower()
    if suffix == ".wav":
        return 1
    if suffix == ".mp3":
        return 2
    if suffix in {".sp", ".speex"}:
        return 4
    return 0


def wav_diagnostics(audio_path: Path) -> dict[str, Any]:
    if audio_path.suffix.lower() != ".wav":
        return {"is_wav": False}
    try:
        with wave.open(str(audio_path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            return {
                "is_wav": True,
                "channels": wav.getnchannels(),
                "sample_width_bytes": wav.getsampwidth(),
                "sample_rate_hz": rate,
                "frames": frames,
                "duration_seconds": round(frames / rate, 3) if rate else None,
            }
    except wave.Error as exc:
        return {"is_wav": True, "error": str(exc)}


def build_signed_url(args: argparse.Namespace) -> tuple[str, str, dict[str, str]]:
    app_id = require_env("TENCENT_APP_ID")
    secret_id = require_env("TENCENT_SECRET_ID")
    secret_key = require_env("TENCENT_SECRET_KEY")

    base_url = args.ws_url or os.environ.get("TENCENT_SOE_WS_URL", DEFAULT_WS_URL).strip()
    if not base_url:
        base_url = DEFAULT_WS_URL
    if not base_url.startswith("wss://"):
        raise RuntimeError(f"TENCENT_SOE_WS_URL must start with wss://, got: {base_url}")

    parsed = urlsplit(base_url)
    host = parsed.netloc
    path = parsed.path.rstrip("/")
    if not host or not path:
        raise RuntimeError(f"Invalid Tencent SOE WebSocket URL: {base_url}")

    path_with_appid = f"{path}/{app_id}"
    now = int(time.time())
    voice_id = str(uuid.uuid4())
    params = {
        "eval_mode": str(args.eval_mode),
        "expired": str(now + args.expire_seconds),
        "nonce": str(secrets.randbelow(9_999_999_999) + 1),
        "ref_text": args.ref_text,
        "score_coeff": str(args.score_coeff),
        "secretid": secret_id,
        "sentence_info_enabled": str(args.sentence_info_enabled),
        "server_engine_type": args.server_engine_type,
        "text_mode": str(args.text_mode),
        "timestamp": str(now),
        "voice_format": str(args.voice_format),
        "voice_id": voice_id,
    }
    if args.rec_mode is not None:
        params["rec_mode"] = str(args.rec_mode)

    canonical_query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    sign_text = f"{host}{path_with_appid}?{canonical_query}"
    signature = base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            sign_text.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")
    request_query = urlencode({**params, "signature": signature})
    return f"wss://{host}{path_with_appid}?{request_query}", voice_id, params


def signed_url_diagnostics(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)

    def first(name: str) -> str | None:
        values = query.get(name)
        return values[0] if values else None

    return {
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "path_shape": redact_appid_path(parsed.path),
        "query_keys": sorted(query.keys()),
        "has_secretid": bool(first("secretid")),
        "has_signature": bool(first("signature")),
        "signature_chars": len(first("signature") or ""),
        "ref_text_chars": len(first("ref_text") or ""),
        "server_engine_type": first("server_engine_type"),
        "eval_mode": first("eval_mode"),
        "text_mode": first("text_mode"),
        "rec_mode": first("rec_mode"),
        "voice_format": first("voice_format"),
        "score_coeff": first("score_coeff"),
        "sentence_info_enabled": first("sentence_info_enabled"),
        "timestamp_present": bool(first("timestamp")),
        "expired_present": bool(first("expired")),
        "nonce_present": bool(first("nonce")),
        "voice_id_present": bool(first("voice_id")),
    }


def redact_appid_path(path: str) -> str:
    parts = path.strip("/").split("/")
    if not parts:
        return "/"
    if parts[-1].isdigit():
        parts[-1] = "<appid>"
    return "/" + "/".join(parts)


class MinimalWebSocket:
    def __init__(self, url: str, timeout: float) -> None:
        self.url = url
        self.timeout = timeout
        self.sock: ssl.SSLSocket | None = None

    def __enter__(self) -> "MinimalWebSocket":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def connect(self) -> None:
        parsed = urlsplit(self.url)
        host = parsed.hostname
        if not host:
            raise RuntimeError("Invalid WebSocket URL: missing host")
        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        raw_sock = socket.create_connection((host, port), timeout=self.timeout)
        raw_sock.settimeout(self.timeout)
        context = ssl.create_default_context()
        self.sock = context.wrap_socket(raw_sock, server_hostname=host)

        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.netloc}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "User-Agent: fluent-coach-tencent-soe-standalone-test/1.0\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))

        response = self._recv_until(b"\r\n\r\n", limit=65536)
        header_text = response.decode("utf-8", "replace").split("\r\n\r\n", 1)[0]
        status_line = header_text.split("\r\n", 1)[0]
        if not status_line.startswith("HTTP/1.1 101"):
            raise RuntimeError(f"WebSocket upgrade failed: {header_text}")

    def _recv_until(self, marker: bytes, limit: int) -> bytes:
        if self.sock is None:
            raise RuntimeError("WebSocket is not connected")
        chunks = bytearray()
        while marker not in chunks:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            chunks.extend(chunk)
            if len(chunks) > limit:
                raise RuntimeError("Response exceeded read limit")
        return bytes(chunks)

    def _recv_exact(self, size: int) -> bytes:
        if self.sock is None:
            raise RuntimeError("WebSocket is not connected")
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self.sock.recv(size - len(chunks))
            if not chunk:
                raise RuntimeError("Connection closed while reading frame")
            chunks.extend(chunk)
        return bytes(chunks)

    def recv_message(self) -> tuple[int, bytes]:
        message_opcode: int | None = None
        message_payload = bytearray()

        while True:
            header = self._recv_exact(2)
            fin = bool(header[0] & 0x80)
            opcode = header[0] & 0x0F
            masked = bool(header[1] & 0x80)
            payload_len = header[1] & 0x7F
            if payload_len == 126:
                payload_len = struct.unpack("!H", self._recv_exact(2))[0]
            elif payload_len == 127:
                payload_len = struct.unpack("!Q", self._recv_exact(8))[0]

            mask_key = self._recv_exact(4) if masked else b""
            payload = bytearray(self._recv_exact(payload_len))
            if masked:
                for idx in range(payload_len):
                    payload[idx] ^= mask_key[idx % 4]

            if opcode == 0x8:
                return opcode, bytes(payload)
            if opcode == 0x9:
                self.send_frame(bytes(payload), opcode=0xA)
                continue
            if opcode == 0xA:
                continue
            if opcode in {0x1, 0x2}:
                message_opcode = opcode
                message_payload = bytearray(payload)
            elif opcode == 0x0 and message_opcode is not None:
                message_payload.extend(payload)
            else:
                raise RuntimeError(f"Unsupported WebSocket opcode: {opcode}")

            if fin:
                if message_opcode is None:
                    raise RuntimeError("Received fragmented frame without message opcode")
                return message_opcode, bytes(message_payload)

    def recv_json(self) -> dict[str, Any]:
        opcode, payload = self.recv_message()
        if opcode == 0x8:
            reason = payload.decode("utf-8", "replace")
            raise RuntimeError(f"Server closed WebSocket connection: {reason}")
        if opcode != 0x1:
            raise RuntimeError(f"Expected text frame, got opcode {opcode}")
        return json.loads(payload.decode("utf-8"))

    def send_frame(self, payload: bytes, opcode: int) -> None:
        if self.sock is None:
            raise RuntimeError("WebSocket is not connected")

        first = 0x80 | opcode
        length = len(payload)
        if length < 126:
            header = struct.pack("!BB", first, 0x80 | length)
        elif length <= 0xFFFF:
            header = struct.pack("!BBH", first, 0x80 | 126, length)
        else:
            header = struct.pack("!BBQ", first, 0x80 | 127, length)

        mask_key = secrets.token_bytes(4)
        masked = bytearray(payload)
        for idx in range(length):
            masked[idx] ^= mask_key[idx % 4]
        self.sock.sendall(header + mask_key + bytes(masked))

    def send_binary(self, payload: bytes) -> None:
        self.send_frame(payload, opcode=0x2)

    def send_text(self, payload: dict[str, Any]) -> None:
        self.send_frame(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            opcode=0x1,
        )

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            self.send_frame(b"", opcode=0x8)
        except OSError:
            pass
        try:
            self.sock.close()
        finally:
            self.sock = None


def summarize_response(label: str, message: dict[str, Any], raw_json: bool) -> None:
    code = message.get("code")
    status = "OK" if code == 0 else "ERROR"
    print(f"{label}: {status} code={code} message={message.get('message')}")
    if "voice_id" in message:
        print(f"voice_id={message['voice_id']}")
    if "final" in message:
        print(f"final={message['final']}")
    if raw_json:
        print(f"{label}_json=" + json.dumps(message, ensure_ascii=False, indent=2))
    result = message.get("result")
    if message.get("final") == 1 and isinstance(result, dict):
        print_assessment(result)


def print_assessment(result: dict[str, Any]) -> None:
    print("assessment_summary:")
    for key in ["SuggestedScore", "PronAccuracy", "PronFluency", "PronCompletion"]:
        if key in result:
            print(f"  {key}: {result[key]}")

    words = result.get("Words")
    if not isinstance(words, list):
        return

    scored_words: list[tuple[float, str]] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        text = str(word.get("Word") or word.get("ReferenceWord") or "")
        try:
            accuracy = float(word.get("PronAccuracy"))
        except (TypeError, ValueError):
            continue
        scored_words.append((accuracy, text))

    if scored_words:
        print("  lowest_words:")
        for accuracy, text in sorted(scored_words)[:5]:
            print(f"    {text}: {accuracy:.2f}")


def print_safe_diagnostics(
    *,
    url: str,
    args: argparse.Namespace,
    params: dict[str, str],
) -> None:
    audio = None
    if args.audio is not None:
        audio = {
            "path": str(args.audio),
            "exists": args.audio.exists(),
            "bytes": args.audio.stat().st_size if args.audio.exists() else None,
            "suffix": args.audio.suffix.lower(),
            "wav": wav_diagnostics(args.audio),
        }
    diagnostics = {
        "mode": args.mode,
        "signed_url": signed_url_diagnostics(url),
        "audio": audio,
        "fixture_id": args.fixture_id,
        "selected_params": {
            "eval_mode": params.get("eval_mode"),
            "rec_mode": params.get("rec_mode"),
            "voice_format": params.get("voice_format"),
            "server_engine_type": params.get("server_engine_type"),
            "score_coeff": params.get("score_coeff"),
            "sentence_info_enabled": params.get("sentence_info_enabled"),
            "text_mode": params.get("text_mode"),
        },
        "timeouts": {
            "connect_seconds": args.timeout,
            "result_seconds": args.result_timeout,
        },
    }
    print("safe_diagnostics=" + json.dumps(diagnostics, ensure_ascii=False, indent=2))


def prepare_args(args: argparse.Namespace) -> None:
    if args.server_engine_type is None:
        args.server_engine_type = os.environ.get("TENCENT_SOE_SERVER_ENGINE_TYPE", "16k_en")
    if args.eval_mode is None:
        args.eval_mode = int(os.environ.get("TENCENT_SOE_EVAL_MODE", "1") or 1)
    if args.score_coeff is None:
        args.score_coeff = os.environ.get("TENCENT_SOE_SCORE_COEFF", "3.0") or "3.0"

    if args.mode == "handshake":
        args.ref_text = args.ref_text or DEFAULT_REF_TEXT
        args.voice_format = args.voice_format if args.voice_format is not None else 1
        if args.rec_mode is None:
            args.rec_mode = 1
        return

    if args.audio is None:
        item, audio_path = select_manifest_item(args.manifest, args.item_id)
        transcript = item.get("transcript")
        if not isinstance(transcript, str) or not transcript.strip():
            raise RuntimeError(f"Manifest item {item.get('id')} has no transcript")
        args.fixture_id = item.get("id")
        args.audio = audio_path
        args.ref_text = args.ref_text or transcript.strip()
    else:
        args.audio = args.audio.expanduser()
        if args.ref_text is None:
            manifest_match = find_manifest_text_for_audio(args.manifest, args.audio)
            if manifest_match is not None:
                item, transcript = manifest_match
                args.fixture_id = item.get("id")
                args.ref_text = transcript

    if args.audio is None:
        raise RuntimeError("No audio selected. Pass --audio or provide fixture manifest data.")
    if not args.audio.exists():
        raise RuntimeError(f"Audio file not found: {args.audio}")
    if not args.ref_text:
        raise RuntimeError("Missing reference text. Pass --ref-text for custom audio.")
    if args.voice_format is None:
        args.voice_format = infer_voice_format(args.audio)
    if args.rec_mode is None:
        args.rec_mode = 1 if args.mode == "recorded" else 0


def send_audio(ws: MinimalWebSocket, args: argparse.Namespace) -> None:
    if args.audio is None:
        return
    audio_bytes = args.audio.read_bytes()
    if args.mode == "recorded":
        print(f"Uploading one recorded audio frame bytes={len(audio_bytes)}")
        ws.send_binary(audio_bytes)
        ws.send_text({"type": "end"})
        return

    print(
        "Uploading stream audio "
        f"bytes={len(audio_bytes)} chunk_size={args.chunk_size} "
        f"interval_ms={args.chunk_interval_ms}"
    )
    sent = 0
    for offset in range(0, len(audio_bytes), args.chunk_size):
        chunk = audio_bytes[offset : offset + args.chunk_size]
        ws.send_binary(chunk)
        sent += len(chunk)
        if args.chunk_interval_ms > 0:
            time.sleep(args.chunk_interval_ms / 1000.0)
    print(f"Finished stream upload bytes={sent}")
    ws.send_text({"type": "end"})


def print_failure_hints(text: str) -> None:
    lowered = text.lower()
    hints: list[str] = []
    if "signature" in lowered or "auth" in lowered or "401" in lowered:
        hints.append("check TENCENT_APP_ID, TENCENT_SECRET_ID, TENCENT_SECRET_KEY, and CAM SOE permission")
    if "4000" in lowered or "parameter" in lowered or "param" in lowered:
        hints.append("check eval_mode, ref_text requirements, server_engine_type, voice_format, and rec_mode")
    if "4008" in lowered or "too fast" in lowered:
        hints.append("for streaming mode, slow down chunks; for complete files, use --mode recorded with rec_mode=1")
    if "audio" in lowered or "format" in lowered:
        hints.append("use 16 kHz, 16-bit, mono WAV and voice_format=1 for the safest recorded-mode test")
    if "timed out" in lowered or "timeout" in lowered:
        hints.append("increase --result-timeout or try --mode stream for longer audio")
    if hints:
        print("failure_hints:")
        for hint in dict.fromkeys(hints):
            print(f"  - {hint}")


def run(args: argparse.Namespace) -> int:
    load_dotenv(args.env_file)
    try:
        prepare_args(args)
        url, voice_id, params = build_signed_url(args)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.verbose_safe:
        print_safe_diagnostics(url=url, args=args, params=params)

    print("Connecting to Tencent SOE WebSocket...")
    print(f"host=soe.cloud.tencent.com voice_id={voice_id}")
    if args.fixture_id:
        print(f"fixture_id={args.fixture_id}")
    if args.audio is not None:
        print(f"audio={args.audio}")
    print(f"ref_text={args.ref_text}")

    try:
        with MinimalWebSocket(url, timeout=args.timeout) as ws:
            handshake = ws.recv_json()
            summarize_response("handshake", handshake, raw_json=args.raw_json)
            if handshake.get("code") != 0:
                print_failure_hints(json.dumps(handshake, ensure_ascii=False))
                return 1
            if args.mode == "handshake":
                print("Handshake test passed.")
                return 0

            send_audio(ws, args)
            deadline = time.monotonic() + args.result_timeout
            while time.monotonic() < deadline:
                message = ws.recv_json()
                summarize_response("result", message, raw_json=args.raw_json)
                if message.get("code") not in {0, None}:
                    print_failure_hints(json.dumps(message, ensure_ascii=False))
                    return 1
                if message.get("final") == 1:
                    print("Tencent SOE audio assessment test passed.")
                    return 0
            message = "Timed out waiting for final assessment result."
            print(message, file=sys.stderr)
            print_failure_hints(message)
            return 1
    except (OSError, ssl.SSLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        message = f"Tencent SOE test failed: {exc}"
        print(message, file=sys.stderr)
        print_failure_hints(message)
        return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone Tencent Cloud SOE WebSocket pronunciation test"
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--ws-url", default=None, help="Default: env TENCENT_SOE_WS_URL or Tencent official URL")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--item-id", help="Fixture item id. Default: first existing SpeechOcean audio.")
    parser.add_argument("--audio", type=Path, help="Custom local WAV/MP3/PCM/Speex audio file.")
    parser.add_argument("--ref-text", default=None, help="Reference text. Required for custom audio unless manifest matches.")
    parser.add_argument(
        "--mode",
        choices=["recorded", "stream", "handshake"],
        default="recorded",
        help="recorded sends one complete audio frame with rec_mode=1. stream sends chunks with rec_mode=0.",
    )
    parser.add_argument("--raw-json", action="store_true", help="Print full Tencent JSON messages.")
    parser.add_argument("--verbose-safe", action="store_true", help="Print redacted URL/audio diagnostics.")
    parser.add_argument("--server-engine-type", default=None)
    parser.add_argument("--eval-mode", type=int, default=None)
    parser.add_argument("--score-coeff", default=None)
    parser.add_argument("--text-mode", type=int, default=0)
    parser.add_argument("--sentence-info-enabled", type=int, default=1)
    parser.add_argument("--voice-format", type=int, default=None)
    parser.add_argument("--rec-mode", type=int, default=None)
    parser.add_argument("--expire-seconds", type=int, default=86400)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--result-timeout", type=float, default=30.0)
    parser.add_argument("--chunk-size", type=int, default=3200)
    parser.add_argument("--chunk-interval-ms", type=float, default=100.0)
    parser.set_defaults(fixture_id=None)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))
