from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_ROOT = PROJECT_ROOT / "fixtures"
GENERATED_ROOT = FIXTURES_ROOT / "generated"
AUDIO_ROOT = FIXTURES_ROOT / "audio" / "public"

GENERATED_MANIFESTS = {
    "librispeech": GENERATED_ROOT / "librispeech_subset.json",
    "speechocean762": GENERATED_ROOT / "speechocean762_subset.json",
    "l2_arctic": GENERATED_ROOT / "l2_arctic_subset.json",
    "jfleg": GENERATED_ROOT / "jfleg_subset.json",
}

TEXT_FIXTURES = {
    "scenarios": FIXTURES_ROOT / "scenarios.json",
    "grammar_expression_errors": FIXTURES_ROOT / "grammar_expression_errors.json",
    "dialogue_samples": FIXTURES_ROOT / "dialogue_samples.json",
}


class FixtureError(RuntimeError):
    """Raised when required fixture data is missing or malformed."""


@dataclass(frozen=True)
class FixtureStatus:
    ready: bool
    generated_manifests: dict[str, bool]
    text_fixtures: dict[str, bool]
    audio_root_exists: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "generated_manifests": self.generated_manifests,
            "text_fixtures": self.text_fixtures,
            "audio_root_exists": self.audio_root_exists,
        }


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FixtureError(
            f"Missing fixture file: {path.relative_to(PROJECT_ROOT)}. "
            "Run `python scripts/extract_fixtures.py` from the project root."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureError(f"Invalid JSON in fixture file: {path}") from exc


def get_fixture_status() -> dict[str, object]:
    generated = {name: path.exists() for name, path in GENERATED_MANIFESTS.items()}
    text = {name: path.exists() for name, path in TEXT_FIXTURES.items()}
    audio_exists = AUDIO_ROOT.exists()
    ready = all(generated.values()) and all(text.values()) and audio_exists
    return FixtureStatus(
        ready=ready,
        generated_manifests=generated,
        text_fixtures=text,
        audio_root_exists=audio_exists,
    ).as_dict()


def load_generated_manifest(name: str) -> dict[str, Any]:
    try:
        path = GENERATED_MANIFESTS[name]
    except KeyError as exc:
        valid = ", ".join(sorted(GENERATED_MANIFESTS))
        raise FixtureError(f"Unknown generated manifest `{name}`. Valid names: {valid}") from exc
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise FixtureError(f"Generated manifest must be an object: {path}")
    items = payload.get("items")
    if not isinstance(items, list):
        raise FixtureError(f"Generated manifest has no `items` list: {path}")
    return payload


def load_all_generated_manifests() -> dict[str, dict[str, Any]]:
    return {name: load_generated_manifest(name) for name in GENERATED_MANIFESTS}


def load_text_fixture(name: str) -> dict[str, Any]:
    try:
        path = TEXT_FIXTURES[name]
    except KeyError as exc:
        valid = ", ".join(sorted(TEXT_FIXTURES))
        raise FixtureError(f"Unknown text fixture `{name}`. Valid names: {valid}") from exc
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise FixtureError(f"Text fixture must be an object: {path}")
    return payload


def resolve_fixture_audio(audio_file: str) -> Path:
    path = Path(audio_file)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "fixtures":
        return PROJECT_ROOT / path
    return FIXTURES_ROOT / path
