#!/usr/bin/env python3
"""Interactive text-only driver for a full speaking-coach session.

Drives the same backend REST endpoints the browser uses, but turn-by-turn from
the terminal -- no microphone, no frontend. Use it to play out a whole scenario
(interview / restaurant_ordering / meeting): send a sentence, read the AI reply
and grammar feedback, send the next one, then `/end` for the after-class summary.

Requires a running backend (``make dev-backend``; default http://127.0.0.1:8000).
Whether replies come from a fixture or the real LLM depends on the backend's
provider config (``.env``); this script does not care.

Usage:
    python3 scripts/chat_session.py                 # defaults to interview
    python3 scripts/chat_session.py -s restaurant_ordering
    python3 scripts/chat_session.py --base-url http://127.0.0.1:8000

In-session commands:
    /end       end the session and print the summary
    /summary   print the current summary without ending
    /analysis  dump accumulated grammar/pronunciation analysis
    /quit      exit without ending the session
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


class Client:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise SystemExit(f"HTTP {exc.code} on {method} {path}: {body}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit(
                f"Cannot reach backend at {self.base} ({exc.reason}). "
                "Start it with `make dev-backend`."
            ) from exc

    def health(self) -> dict:
        return self._request("GET", "/api/health")

    def create_session(self, scenario_id: str) -> dict:
        return self._request("POST", "/api/sessions", {"scenario_id": scenario_id})

    def text_turn(self, session_id: str, text: str) -> dict:
        return self._request(
            "POST", f"/api/sessions/{session_id}/turns/text", {"text": text}
        )

    def end_session(self, session_id: str) -> dict:
        return self._request("POST", f"/api/sessions/{session_id}/end")

    def summary(self, session_id: str) -> dict:
        return self._request("GET", f"/api/sessions/{session_id}/summary")

    def analysis(self, session_id: str) -> dict:
        return self._request("GET", f"/api/sessions/{session_id}/analysis")


def _print_grammar(correction: dict) -> None:
    corrected = correction.get("corrected_text") or ""
    original = correction.get("user_text") or ""
    issues = correction.get("issues") or []
    if corrected and corrected.strip() and corrected.strip() != original.strip():
        print(f"  ✎ corrected: {corrected}")
    better = correction.get("better_expression")
    if better:
        print(f"  ★ better: {better}")
    for issue in issues:
        sev = issue.get("severity", "?")
        msg = issue.get("explanation_zh") or issue.get("error_type", "")
        span = issue.get("original_span", "")
        print(f"    - [{sev}] {span!r}: {msg}")


def _print_summary(summary: dict) -> None:
    print("\n=== Session Summary ===")
    fields = [
        ("grammar_score", "Grammar"),
        ("pronunciation_score", "Pronunciation"),
        ("fluency_score", "Fluency"),
        ("vocabulary_score", "Vocabulary"),
        ("task_completion_rate", "Task completion"),
    ]
    for key, label in fields:
        if key in summary and summary[key] is not None:
            print(f"  {label}: {summary[key]}")
    for key, label in (("top_issues", "Top issues"), ("next_drills", "Next drills")):
        items = summary.get(key) or []
        if items:
            print(f"  {label}:")
            for item in items:
                print(f"    - {item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)}")


def run(scenario_id: str, base_url: str) -> None:
    client = Client(base_url)

    try:
        health = client.health()
        providers = health.get("providers", health)
        provider_bits = {
            k: providers[k]
            for k in (
                "llm_provider",
                "llm_model",
                "asr_provider",
                "pronunciation_provider",
                "tts_provider",
            )
            if k in providers
        }
        if provider_bits:
            print("backend providers:", json.dumps(provider_bits, ensure_ascii=False))
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return

    created = client.create_session(scenario_id)
    session_id = created["session"]["id"]
    print(f"\n=== Scenario: {created['scenario'].get('title', scenario_id)} (session {session_id}) ===")
    print(f"AI: {created['opening_line']}")
    goals = created.get("conversation_goals") or []
    if goals:
        print("Goals: " + "; ".join(goals))
    targets = created.get("target_expressions") or []
    if targets:
        print("Target expressions: " + "; ".join(targets))
    print("\nType your line and press Enter. Commands: /end /summary /analysis /quit\n")

    while True:
        try:
            line = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(exiting without ending session)")
            return

        if not line:
            continue
        if line == "/quit":
            print("(exiting without ending session)")
            return
        if line == "/summary":
            _print_summary(client.summary(session_id))
            continue
        if line == "/analysis":
            print(json.dumps(client.analysis(session_id), ensure_ascii=False, indent=2))
            continue
        if line == "/end":
            client.end_session(session_id)
            _print_summary(client.summary(session_id))
            print("\n(session ended)")
            return

        result = client.text_turn(session_id, line)
        print(f"AI: {result['ai_turn']['text']}")
        print(f"  (goal: {result.get('current_goal', '')} | next: {result.get('next_intent', '')})")
        _print_grammar(result.get("grammar_result") or {})
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-s",
        "--scenario",
        default="interview",
        choices=["interview", "restaurant_ordering", "meeting"],
        help="scenario id (default: interview)",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="backend base URL (default: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()
    run(args.scenario, args.base_url)


if __name__ == "__main__":
    main()
