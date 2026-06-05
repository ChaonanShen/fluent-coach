#!/usr/bin/env python3
"""Prepare small fixture subsets from downloaded public datasets.

Expected raw-data location:

  dataset/
    dev-clean.tar.gz
    test-clean.tar.gz
    speechocean762.tar.gz
    L2-ARCTIC*.zip or *.tar.gz
    jfleg/ or jfleg*.zip

The script is intentionally idempotent. If a dataset archive is not present yet,
it reports the missing source and continues with the datasets it can find.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import tarfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, TypeVar


PROJECT_ROOT = Path(__file__).resolve().parents[1]
T = TypeVar("T")

L2_NATIVE_LANGUAGE = {
    "ABA": "Arabic",
    "SKA": "Arabic",
    "YBAA": "Arabic",
    "ZHAA": "Arabic",
    "BWC": "Mandarin",
    "LXC": "Mandarin",
    "NCC": "Mandarin",
    "TXHC": "Mandarin",
    "ASI": "Hindi",
    "RRBI": "Hindi",
    "SVBI": "Hindi",
    "TNI": "Hindi",
    "HJK": "Korean",
    "HKK": "Korean",
    "YDCK": "Korean",
    "YKWK": "Korean",
    "EBVS": "Spanish",
    "ERMS": "Spanish",
    "MBMPS": "Spanish",
    "NJS": "Spanish",
    "HQTV": "Vietnamese",
    "PNV": "Vietnamese",
    "THV": "Vietnamese",
    "TLV": "Vietnamese",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract small test fixtures from LibriSpeech, SpeechOcean762, L2-ARCTIC, and JFLEG."
    )
    parser.add_argument("--dataset-root", default="dataset", help="Raw dataset directory.")
    parser.add_argument("--fixtures-root", default="fixtures", help="Fixture output directory.")
    parser.add_argument(
        "--bundle-zip",
        default=None,
        help="Optional zip path for uploading the generated subset, for example fixture-subset.zip.",
    )
    parser.add_argument("--skip-extract", action="store_true", help="Do not extract archives; only scan existing files.")
    parser.add_argument(
        "--convert-wav",
        action="store_true",
        help="Use ffmpeg to convert copied audio to 16 kHz mono WAV when available.",
    )
    parser.add_argument("--limit-librispeech-per-split", type=int, default=30)
    parser.add_argument("--limit-speechocean", type=int, default=45)
    parser.add_argument("--limit-l2-arctic", type=int, default=45)
    parser.add_argument("--limit-jfleg-per-split", type=int, default=80)
    return parser.parse_args()


def resolve_project_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def portable_path(path: Path, base: Path) -> str:
    """Return a slash-separated path that can be moved with the fixture folder."""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return repo_rel(path)


def display_path(path: Path) -> str:
    """Human-readable path for logs on Windows/macOS/Linux."""
    return repo_rel(path)


def safe_member_path(target_dir: Path, member_name: str) -> Path:
    destination = (target_dir / member_name).resolve()
    target = target_dir.resolve()
    if destination != target and target not in destination.parents:
        raise RuntimeError(f"Unsafe archive member path: {member_name}")
    return destination


def extract_archive(archive: Path, target_dir: Path, warnings: list[str]) -> bool:
    marker_dir = target_dir / ".extract_markers"
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(archive.resolve())) + ".done"
    marker = marker_dir / marker_name
    if marker.exists():
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    print(f"extracting {display_path(archive)} -> {display_path(target_dir)}")

    try:
        if name.endswith((".tar.gz", ".tgz", ".tar")):
            with tarfile.open(archive) as tar:
                for member in tar.getmembers():
                    safe_member_path(target_dir, member.name)
                tar.extractall(target_dir)
        elif name.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                for member in zf.namelist():
                    safe_member_path(target_dir, member)
                zf.extractall(target_dir)
        else:
            warnings.append(f"unsupported archive skipped: {display_path(archive)}")
            return False
    except Exception as exc:  # noqa: BLE001 - keep dataset prep resilient.
        warnings.append(f"failed to extract {display_path(archive)}: {exc}")
        return False

    marker.write_text("ok\n", encoding="utf-8")
    return True


def list_archives(dataset_root: Path) -> list[Path]:
    if not dataset_root.exists():
        return []
    archives: list[Path] = []
    for path in dataset_root.rglob("*"):
        if not path.is_file():
            continue
        if ".extract_markers" in path.parts:
            continue
        name = path.name.lower()
        if name.endswith((".tar.gz", ".tgz", ".tar", ".zip")):
            archives.append(path)
    return sorted(archives)


def extract_known_archives(dataset_root: Path, skip_extract: bool, warnings: list[str]) -> None:
    if skip_extract:
        return

    archive_targets: list[tuple[Callable[[str], bool], str]] = [
        (
            lambda name: name
            in {
                "dev-clean.tar.gz",
                "test-clean.tar.gz",
                "dev-other.tar.gz",
                "test-other.tar.gz",
            },
            "librispeech",
        ),
        (lambda name: "speechocean" in name, "speechocean762"),
        (lambda name: ("l2" in name and "arctic" in name) or "l2arctic" in name, "l2_arctic"),
        (lambda name: "jfleg" in name, "jfleg"),
    ]

    for archive in list_archives(dataset_root):
        lower_name = archive.name.lower()
        for matcher, target_name in archive_targets:
            if matcher(lower_name):
                extract_archive(archive, dataset_root / "extracted" / target_name, warnings)
                break


def sample_evenly(items: list[T], limit: int) -> list[T]:
    if limit <= 0 or len(items) <= limit:
        return list(items)
    if limit == 1:
        return [items[0]]
    step = (len(items) - 1) / (limit - 1)
    return [items[round(i * step)] for i in range(limit)]


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def materialize_audio(
    source: Path,
    destination_dir: Path,
    base_name: str,
    convert_wav: bool,
    warnings: list[str],
    fixtures_root: Path,
) -> str:
    destination_dir.mkdir(parents=True, exist_ok=True)
    clean_base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base_name).strip("._")

    if convert_wav:
        if ffmpeg_available():
            destination = destination_dir / f"{clean_base}.wav"
            if not destination.exists():
                command = [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(source),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(destination),
                ]
                subprocess.run(command, check=True)
            return portable_path(destination, fixtures_root)

        warnings.append("ffmpeg not found; copied original audio instead of converting to wav")

    suffix = source.suffix.lower() or ".audio"
    destination = destination_dir / f"{clean_base}{suffix}"
    if not destination.exists():
        shutil.copy2(source, destination)
    return portable_path(destination, fixtures_root)


def write_manifest(output_dir: Path, name: str, items: list[dict[str, Any]], meta: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / name
    payload = {
        "version": 1,
        "generated_by": "scripts/prepare_fixtures.py",
        "count": len(items),
        **meta,
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def extract_utt_id_and_text(line: str) -> tuple[str, str] | None:
    parts = line.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1].strip()


def prepare_librispeech(
    fixtures_root: Path,
    dataset_root: Path,
    audio_root: Path,
    output_dir: Path,
    per_split_limit: int,
    convert_wav: bool,
    warnings: list[str],
) -> list[dict[str, Any]]:
    split_order = ["dev-clean", "test-clean", "dev-other", "test-other"]
    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for transcript_file in sorted(dataset_root.rglob("*.trans.txt")):
        split = next((part for part in transcript_file.parts if part in split_order), None)
        if not split:
            continue
        for line in transcript_file.read_text(encoding="utf-8").splitlines():
            parsed = extract_utt_id_and_text(line)
            if not parsed:
                continue
            utt_id, transcript = parsed
            audio_file = transcript_file.parent / f"{utt_id}.flac"
            if not audio_file.exists():
                warnings.append(f"LibriSpeech audio missing for {utt_id}")
                continue
            parts = utt_id.split("-")
            by_split[split].append(
                {
                    "source_id": utt_id,
                    "split": split,
                    "source_audio": audio_file,
                    "transcript": transcript,
                    "speaker_id": parts[0] if len(parts) >= 1 else None,
                    "chapter_id": parts[1] if len(parts) >= 2 else None,
                }
            )

    selected: list[dict[str, Any]] = []
    for split in split_order:
        records = sorted(by_split.get(split, []), key=lambda item: item["source_id"])
        selected.extend(sample_evenly(records, per_split_limit))

    items: list[dict[str, Any]] = []
    for record in selected:
        source_audio = record.pop("source_audio")
        fixture_audio = materialize_audio(
            source_audio,
            audio_root / "librispeech_subset",
            f"{record['split']}_{record['source_id']}",
            convert_wav,
            warnings,
            fixtures_root,
        )
        items.append(
            {
                "id": f"librispeech_{record['split']}_{record['source_id']}",
                "dataset": "librispeech",
                "license": "CC BY 4.0",
                "test_type": "asr_clean" if "clean" in record["split"] else "asr_challenging",
                "audio_file": fixture_audio,
                "source_audio": repo_rel(source_audio),
                **record,
            }
        )

    write_manifest(
        output_dir,
        "librispeech_subset.json",
        items,
        {"description": "ASR baseline subset from LibriSpeech dev/test splits."},
    )
    return items


def find_speechocean_root(dataset_root: Path) -> Path | None:
    for scores_path in sorted(dataset_root.rglob("scores.json")):
        root = scores_path.parent
        if (root / "WAVE").exists():
            return root
    return None


def score_bucket(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score < 7:
        return "low"
    if score < 8.5:
        return "medium"
    return "high"


def prepare_speechocean(
    fixtures_root: Path,
    dataset_root: Path,
    audio_root: Path,
    output_dir: Path,
    limit: int,
    convert_wav: bool,
    warnings: list[str],
) -> list[dict[str, Any]]:
    root = find_speechocean_root(dataset_root)
    if not root:
        write_manifest(
            output_dir,
            "speechocean762_subset.json",
            [],
            {"description": "SpeechOcean762 subset. Source dataset not found yet."},
        )
        return []

    scores = json.loads((root / "scores.json").read_text(encoding="utf-8"))
    audio_map = {path.stem: path for path in (root / "WAVE").rglob("*") if path.suffix.lower() == ".wav"}
    split_by_utt: dict[str, str] = {}
    for split in ["train", "test"]:
        text_file = root / split / "text"
        if not text_file.exists():
            continue
        for line in text_file.read_text(encoding="utf-8").splitlines():
            parsed = extract_utt_id_and_text(line)
            if parsed:
                split_by_utt[parsed[0]] = split

    records: list[dict[str, Any]] = []
    for utt_id, score_record in scores.items():
        source_audio = audio_map.get(utt_id)
        if not source_audio:
            continue
        sentence_score = score_record.get("total")
        if sentence_score is None:
            sentence_score = score_record.get("accuracy")
        sentence_score = float(sentence_score) if sentence_score is not None else None
        records.append(
            {
                "source_id": utt_id,
                "split": split_by_utt.get(utt_id, "unknown"),
                "source_audio": source_audio,
                "transcript": score_record.get("text", ""),
                "speaker_id": source_audio.parent.name,
                "score_bucket": score_bucket(sentence_score),
                "sentence_scores": {
                    "accuracy": score_record.get("accuracy"),
                    "completeness": score_record.get("completeness"),
                    "fluency": score_record.get("fluency"),
                    "prosodic": score_record.get("prosodic"),
                    "total": score_record.get("total"),
                },
                "word_scores": score_record.get("words", []),
            }
        )

    bucketed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in sorted(records, key=lambda item: item["source_id"]):
        bucketed[record["score_bucket"]].append(record)

    selected: list[dict[str, Any]] = []
    per_bucket = max(1, math.ceil(limit / 3))
    for bucket in ["low", "medium", "high"]:
        selected.extend(sample_evenly(bucketed.get(bucket, []), per_bucket))
    selected_ids = {item["source_id"] for item in selected}
    if len(selected) < limit:
        remaining = [item for item in records if item["source_id"] not in selected_ids]
        selected.extend(sample_evenly(sorted(remaining, key=lambda item: item["source_id"]), limit - len(selected)))
    selected = selected[:limit]

    items: list[dict[str, Any]] = []
    for record in selected:
        source_audio = record.pop("source_audio")
        fixture_audio = materialize_audio(
            source_audio,
            audio_root / "speechocean762_subset",
            f"speechocean_{record['source_id']}",
            convert_wav,
            warnings,
            fixtures_root,
        )
        items.append(
            {
                "id": f"speechocean_{record['source_id']}",
                "dataset": "speechocean762",
                "license": "CC BY 4.0",
                "test_type": "pronunciation_scoring",
                "audio_file": fixture_audio,
                "source_audio": repo_rel(source_audio),
                **record,
            }
        )

    write_manifest(
        output_dir,
        "speechocean762_subset.json",
        items,
        {"description": "Pronunciation assessment subset with low/medium/high score coverage."},
    )
    return items


def find_l2_speaker_dirs(dataset_root: Path) -> list[Path]:
    speaker_dirs: list[Path] = []
    for wav_dir in sorted(dataset_root.rglob("wav")):
        speaker_dir = wav_dir.parent
        if (speaker_dir / "transcript").exists():
            speaker_dirs.append(speaker_dir)
    return speaker_dirs


def read_l2_transcript(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)


def prepare_l2_arctic(
    fixtures_root: Path,
    dataset_root: Path,
    audio_root: Path,
    output_dir: Path,
    limit: int,
    convert_wav: bool,
    warnings: list[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for speaker_dir in find_l2_speaker_dirs(dataset_root):
        speaker_id = speaker_dir.name
        native_language = L2_NATIVE_LANGUAGE.get(speaker_id, "unknown")
        transcript_dir = speaker_dir / "transcript"
        annotation_dir = speaker_dir / "annotation"
        transcript_map = {path.stem: path for path in transcript_dir.glob("*.txt")}
        annotation_map = {
            path.stem: path
            for path in annotation_dir.glob("*")
            if path.suffix.lower() == ".textgrid"
        }

        for source_audio in sorted((speaker_dir / "wav").glob("*.wav")):
            transcript_file = transcript_map.get(source_audio.stem)
            if not transcript_file:
                continue
            annotation_file = annotation_map.get(source_audio.stem)
            records.append(
                {
                    "source_id": f"{speaker_id}_{source_audio.stem}",
                    "speaker_id": speaker_id,
                    "native_language": native_language,
                    "source_audio": source_audio,
                    "transcript": read_l2_transcript(transcript_file),
                    "annotation_file": repo_rel(annotation_file) if annotation_file else None,
                    "has_manual_annotation": annotation_file is not None,
                }
            )

    mandarin = [item for item in records if item["native_language"] == "Mandarin"]
    other = [item for item in records if item["native_language"] != "Mandarin"]
    mandarin = sorted(mandarin, key=lambda item: (not item["has_manual_annotation"], item["source_id"]))
    other = sorted(other, key=lambda item: (item["native_language"], not item["has_manual_annotation"], item["source_id"]))

    mandarin_limit = min(len(mandarin), math.ceil(limit * 0.7))
    selected = sample_evenly(mandarin, mandarin_limit)
    selected_ids = {item["source_id"] for item in selected}
    remaining_limit = limit - len(selected)
    selected.extend(sample_evenly([item for item in other if item["source_id"] not in selected_ids], remaining_limit))
    selected = selected[:limit]

    items: list[dict[str, Any]] = []
    for record in selected:
        source_audio = record.pop("source_audio")
        fixture_audio = materialize_audio(
            source_audio,
            audio_root / "l2_arctic_subset",
            f"l2_arctic_{record['source_id']}",
            convert_wav,
            warnings,
            fixtures_root,
        )
        items.append(
            {
                "id": f"l2_arctic_{record['source_id']}",
                "dataset": "l2_arctic",
                "license": "CC BY-NC 4.0",
                "test_type": "l2_asr_and_mispronunciation",
                "audio_file": fixture_audio,
                "source_audio": repo_rel(source_audio),
                **record,
            }
        )

    write_manifest(
        output_dir,
        "l2_arctic_subset.json",
        items,
        {"description": "Non-native English subset, Mandarin speakers preferred."},
    )
    return items


def create_bundle(fixtures_root: Path, output_dir: Path, bundle_zip: Path) -> Path:
    bundle_zip.parent.mkdir(parents=True, exist_ok=True)
    if bundle_zip.exists():
        bundle_zip.unlink()

    include_roots = [
        output_dir,
        fixtures_root / "audio" / "public",
    ]
    with zipfile.ZipFile(bundle_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for include_root in include_roots:
            if not include_root.exists():
                continue
            for path in sorted(include_root.rglob("*")):
                if path.is_file():
                    archive_name = path.relative_to(fixtures_root.parent).as_posix()
                    zf.write(path, archive_name)
    return bundle_zip


def find_jfleg_sources(dataset_root: Path) -> list[Path]:
    return sorted(
        path
        for path in dataset_root.rglob("*.src")
        if "jfleg" in "/".join(part.lower() for part in path.parts)
    )


def prepare_jfleg(
    dataset_root: Path,
    output_dir: Path,
    per_split_limit: int,
) -> list[dict[str, Any]]:
    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for src_file in find_jfleg_sources(dataset_root):
        split = src_file.parent.name if src_file.parent.name in {"dev", "test"} else src_file.stem
        ref_files = sorted(src_file.parent.glob(f"{src_file.stem}.ref*"))
        if not ref_files:
            continue

        sources = src_file.read_text(encoding="utf-8").splitlines()
        references_by_file = [path.read_text(encoding="utf-8").splitlines() for path in ref_files]
        for index, source in enumerate(sources):
            references = [refs[index] for refs in references_by_file if index < len(refs)]
            if not references:
                continue
            by_split[split].append(
                {
                    "source_id": f"{split}_{index:04d}",
                    "split": split,
                    "source": source,
                    "references": references,
                    "primary_reference": references[0],
                    "reference_count": len(references),
                }
            )

    items: list[dict[str, Any]] = []
    for split in ["dev", "test"]:
        records = by_split.get(split, [])
        for record in sample_evenly(records, per_split_limit):
            items.append(
                {
                    "id": f"jfleg_{record['source_id']}",
                    "dataset": "jfleg",
                    "license": "See source dataset license",
                    "test_type": "grammar_expression_correction",
                    **record,
                }
            )

    write_manifest(
        output_dir,
        "jfleg_subset.json",
        items,
        {"description": "Grammar and fluency correction subset from JFLEG."},
    )
    return items


def main() -> int:
    args = parse_args()
    dataset_root = resolve_project_path(args.dataset_root)
    fixtures_root = resolve_project_path(args.fixtures_root)
    output_dir = fixtures_root / "generated"
    audio_root = fixtures_root / "audio" / "public"
    warnings: list[str] = []

    dataset_root.mkdir(parents=True, exist_ok=True)
    extract_known_archives(dataset_root, args.skip_extract, warnings)

    librispeech = prepare_librispeech(
        fixtures_root,
        dataset_root,
        audio_root,
        output_dir,
        args.limit_librispeech_per_split,
        args.convert_wav,
        warnings,
    )
    speechocean = prepare_speechocean(
        fixtures_root,
        dataset_root,
        audio_root,
        output_dir,
        args.limit_speechocean,
        args.convert_wav,
        warnings,
    )
    l2_arctic = prepare_l2_arctic(
        fixtures_root,
        dataset_root,
        audio_root,
        output_dir,
        args.limit_l2_arctic,
        args.convert_wav,
        warnings,
    )
    jfleg = prepare_jfleg(dataset_root, output_dir, args.limit_jfleg_per_split)

    counts = {
        "librispeech": len(librispeech),
        "speechocean762": len(speechocean),
        "l2_arctic": len(l2_arctic),
        "jfleg": len(jfleg),
    }
    missing = [name for name, count in counts.items() if count == 0]
    summary = {
        "version": 1,
        "generated_by": "scripts/prepare_fixtures.py",
        "counts": counts,
        "missing_or_empty": missing,
        "warnings": sorted(set(warnings)),
        "manifests": {
            "librispeech": portable_path(output_dir / "librispeech_subset.json", fixtures_root),
            "speechocean762": portable_path(output_dir / "speechocean762_subset.json", fixtures_root),
            "l2_arctic": portable_path(output_dir / "l2_arctic_subset.json", fixtures_root),
            "jfleg": portable_path(output_dir / "jfleg_subset.json", fixtures_root),
        },
    }
    write_manifest(output_dir, "dataset_subset_summary.json", [], summary)

    bundle_path: Path | None = None
    if args.bundle_zip:
        bundle_path = create_bundle(fixtures_root, output_dir, resolve_project_path(args.bundle_zip))

    print("\nprepared fixture subsets")
    for name, count in counts.items():
        status = "missing" if count == 0 else f"{count} items"
        print(f"- {name}: {status}")
    if warnings:
        print("\nwarnings")
        for warning in sorted(set(warnings)):
            print(f"- {warning}")
    print(f"\noutput: {display_path(output_dir)}")
    if bundle_path:
        print(f"bundle: {display_path(bundle_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
