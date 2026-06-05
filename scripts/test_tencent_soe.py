#!/usr/bin/env python3
"""Run a real Tencent Cloud SOE pronunciation test with local fixture audio.

By default this script reads .env, picks a pronunciation fixture from
fixtures/generated/speechocean762_subset.json, uploads the WAV file to Tencent
SOE, and prints the returned assessment summary.
"""

from __future__ import annotations

import argparse
import base64
import hmac
import hashlib
import json
import os
import secrets
import socket
import ssl
import struct
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlsplit


DEFAULT_WS_URL = "wss://soe.cloud.tencent.com/soe/api"
DEFAULT_MANIFEST = Path("fixtures/generated/speechocean762_subset.json")


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
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        os.environ[key] = value


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


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


def load_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        raise RuntimeError(
            f"Fixture manifest not found: {path}. "
            "Run `python scripts/extract_fixtures.py` or pass --audio and --ref-text."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_manifest_audio(manifest_path: Path, item: dict[str, object]) -> Path:
    audio_file = item.get("audio_file")
    if not isinstance(audio_file, str) or not audio_file:
        raise RuntimeError(f"Manifest item {item.get('id')} has no audio_file")
    if audio_file.startswith("fixtures/"):
        return Path(audio_file)
    return manifest_path.parent.parent / audio_file


def select_manifest_item(
    manifest_path: Path,
    item_id: str | None,
) -> tuple[dict[str, object], Path]:
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
) -> tuple[dict[str, object], str] | None:
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


def build_signed_url(args: argparse.Namespace) -> tuple[str, str]:
    app_id = require_env("TENCENT_APP_ID")
    secret_id = require_env("TENCENT_SECRET_ID")
    secret_key = require_env("TENCENT_SECRET_KEY")

    base_url = os.environ.get("TENCENT_SOE_WS_URL", DEFAULT_WS_URL).strip()
    if not base_url.startswith("wss://"):
        base_url = DEFAULT_WS_URL

    parsed = urlsplit(base_url)
    host = parsed.netloc
    path = parsed.path.rstrip("/")
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

    canonical_query = "&".join(
        f"{key}={params[key]}" for key in sorted(params.keys())
    )
    sign_text = f"{host}{path_with_appid}?{canonical_query}"
    signature = base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            sign_text.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")

    request_query = urlencode({**params, "signature": signature})
    return f"wss://{host}{path_with_appid}?{request_query}", voice_id


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
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))

        response = self._recv_until(b"\r\n\r\n", limit=65536)
        status_line = response.split(b"\r\n", 1)[0].decode("ascii", "replace")
        if not status_line.startswith("HTTP/1.1 101"):
            raise RuntimeError(
                "WebSocket upgrade failed: "
                + response.decode("utf-8", "replace").split("\r\n\r\n", 1)[0]
            )

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
        while True:
            header = self._recv_exact(2)
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

            if opcode == 0x9:
                self.send_frame(bytes(payload), opcode=0xA)
                continue
            return opcode, bytes(payload)

    def recv_json(self) -> dict[str, object]:
        opcode, payload = self.recv_message()
        if opcode == 0x8:
            raise RuntimeError("Server closed WebSocket connection")
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

    def send_text(self, payload: dict[str, object]) -> None:
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


def print_assessment(result: object, raw_result: bool) -> None:
    if raw_result:
        print("raw_result=" + json.dumps(result, ensure_ascii=False, indent=2))

    if not isinstance(result, dict):
        print("result=" + str(result)[:1000])
        return

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
        lowest = sorted(scored_words)[:5]
        print("  lowest_words:")
        for accuracy, text in lowest:
            print(f"    {text}: {accuracy:.2f}")


def summarize_response(
    label: str,
    message: dict[str, object],
    raw_result: bool = False,
) -> None:
    code = message.get("code")
    status = "OK" if code == 0 else "ERROR"
    print(f"{label}: {status} code={code} message={message.get('message')}")
    if "voice_id" in message:
        print(f"voice_id={message['voice_id']}")
    if "final" in message:
        print(f"final={message['final']}")
    if "result" in message and message.get("final") == 1:
        print_assessment(message["result"], raw_result=raw_result)


def prepare_audio_args(args: argparse.Namespace) -> None:
    if args.handshake_only:
        args.ref_text = args.ref_text or "hello"
        args.voice_format = args.voice_format or 1
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
        args.rec_mode = 1


def run(args: argparse.Namespace) -> int:
    load_dotenv(args.env_file)

    if args.server_engine_type is None:
        args.server_engine_type = os.environ.get(
            "TENCENT_SOE_SERVER_ENGINE_TYPE", "16k_en"
        )
    if args.eval_mode is None:
        args.eval_mode = int(os.environ.get("TENCENT_SOE_EVAL_MODE", "1") or 1)
    if args.score_coeff is None:
        args.score_coeff = os.environ.get("TENCENT_SOE_SCORE_COEFF", "3.0")

    try:
        prepare_audio_args(args)
        url, voice_id = build_signed_url(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("Connecting to Tencent SOE WebSocket...")
    print(f"host=soe.cloud.tencent.com voice_id={voice_id}")
    if not args.handshake_only:
        if args.fixture_id:
            print(f"fixture_id={args.fixture_id}")
        print(f"audio={args.audio}")
        print(f"ref_text={args.ref_text}")

    try:
        with MinimalWebSocket(url, timeout=args.timeout) as ws:
            handshake = ws.recv_json()
            summarize_response("handshake", handshake)
            if handshake.get("code") != 0:
                return 1
            if args.handshake_only:
                print("Handshake-only test passed.")
                return 0

            audio_bytes = args.audio.read_bytes()
            print(f"Uploading audio bytes={len(audio_bytes)}")
            ws.send_binary(audio_bytes)
            ws.send_text({"type": "end"})

            deadline = time.monotonic() + args.result_timeout
            while time.monotonic() < deadline:
                message = ws.recv_json()
                summarize_response("result", message, raw_result=args.raw_result)
                if message.get("code") not in {0, None}:
                    return 1
                if message.get("final") == 1:
                    print("Audio assessment test passed.")
                    return 0
            print("Timed out waiting for final assessment result.", file=sys.stderr)
            return 1
    except (OSError, ssl.SSLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Tencent SOE test failed: {exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real Tencent Cloud SOE pronunciation test from .env"
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to local env file. Default: .env",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Pronunciation fixture manifest. Default: {DEFAULT_MANIFEST}",
    )
    parser.add_argument(
        "--item-id",
        help="Optional manifest item id. Default: first existing fixture audio.",
    )
    parser.add_argument(
        "--audio",
        type=Path,
        help="Optional WAV/MP3/PCM/Speex file to upload for assessment.",
    )
    parser.add_argument(
        "--ref-text",
        default=None,
        help="Reference text for custom audio. Defaults to manifest transcript.",
    )
    parser.add_argument(
        "--handshake-only",
        action="store_true",
        help="Only verify credentials and WebSocket connection; do not upload audio.",
    )
    parser.add_argument(
        "--raw-result",
        action="store_true",
        help="Print the full Tencent assessment result JSON.",
    )
    parser.add_argument(
        "--server-engine-type",
        default=None,
        help="Tencent SOE engine type. Default: env or 16k_en",
    )
    parser.add_argument(
        "--eval-mode",
        type=int,
        default=None,
        help="Evaluation mode. Default: env or 1 sentence mode",
    )
    parser.add_argument(
        "--score-coeff",
        default=None,
        help="Score coefficient, usually 1.0-4.0. Default: env or 3.0",
    )
    parser.add_argument("--text-mode", type=int, default=0)
    parser.add_argument("--sentence-info-enabled", type=int, default=1)
    parser.add_argument("--voice-format", type=int, default=None)
    parser.add_argument("--rec-mode", type=int, default=None)
    parser.add_argument("--expire-seconds", type=int, default=86400)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--result-timeout", type=float, default=30.0)
    parser.set_defaults(fixture_id=None)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))
