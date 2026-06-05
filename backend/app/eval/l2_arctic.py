from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEXT_LINE_RE = re.compile(r'^\s*text\s*=\s*"(.*)"\s*$')
SILENCE_LABELS = {"", "sil", "sp", "spn", "<eps>"}


@dataclass(frozen=True)
class TextGridStats:
    interval_count: int
    non_empty_label_count: int
    suspected_issue_count: int


def parse_textgrid_labels(path: Path) -> list[str]:
    labels: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = TEXT_LINE_RE.match(line)
        if match is None:
            continue
        labels.append(match.group(1).replace('""', '"').strip())
    return labels


def textgrid_stats(path: Path) -> TextGridStats:
    labels = parse_textgrid_labels(path)
    non_empty_labels = [label for label in labels if label.strip().lower() not in SILENCE_LABELS]
    return TextGridStats(
        interval_count=len(labels),
        non_empty_label_count=len(non_empty_labels),
        suspected_issue_count=sum(1 for label in non_empty_labels if _looks_like_issue_label(label)),
    )


def summarize_l2_arctic_annotations(
    items: list[dict[str, Any]],
    *,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    annotated_items = [item for item in items if item.get("has_manual_annotation") is True]
    available_paths = [
        _resolve_annotation_path(str(item["annotation_file"]), project_root=project_root)
        for item in annotated_items
        if item.get("annotation_file")
    ]
    existing_paths = [path for path in available_paths if path.exists()]
    parsed_stats = [textgrid_stats(path) for path in existing_paths]
    interval_count = sum(item.interval_count for item in parsed_stats)
    non_empty_label_count = sum(item.non_empty_label_count for item in parsed_stats)
    suspected_issue_count = sum(item.suspected_issue_count for item in parsed_stats)
    return {
        "annotated_manifest_count": len(annotated_items),
        "available_annotation_count": len(existing_paths),
        "available_annotation_rate": len(existing_paths) / len(annotated_items) if annotated_items else 0.0,
        "parsed_interval_count": interval_count,
        "non_empty_label_count": non_empty_label_count,
        "suspected_issue_label_count": suspected_issue_count,
        "mispronunciation_hit_rate": None,
        "hit_rate_status": "not_computed_no_textgrid" if not existing_paths else "not_computed_no_detector",
    }


def _resolve_annotation_path(annotation_file: str, *, project_root: Path) -> Path:
    path = Path(annotation_file)
    return path if path.is_absolute() else project_root / path


def _looks_like_issue_label(label: str) -> bool:
    normalized = label.strip().lower()
    if normalized in SILENCE_LABELS:
        return False
    return any(marker in label for marker in ["*", "->", "{", "}", "[", "]"]) or "err" in normalized
