#!/usr/bin/env python3
"""Merge gesture recordings and create a Nordic Edge AI Lab upload ZIP."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import zipfile
from pathlib import Path


INPUT_COLUMNS = ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"]
OUTPUT_COLUMNS = ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]
OUTPUT_HEADER = OUTPUT_COLUMNS + ["class", "session_id"]
LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,31}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge XIAO gesture CSV recordings and create a ZIP dataset "
            "for Nordic Edge AI Lab."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("gesture_dataset"),
        help="Recording root containing label directories (default: gesture_dataset).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("gesture_dataset_upload.zip"),
        help="Output ZIP path (default: gesture_dataset_upload.zip).",
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        help="Labels to include. If omitted, include every label directory found.",
    )
    parser.add_argument(
        "--max-files-per-label",
        type=int,
        help="Optional limit for a quick training smoke test.",
    )
    parser.add_argument(
        "--class-map",
        nargs="+",
        metavar="LABEL=ID",
        help="Optional class IDs, for example idle=0 swipe_left=1.",
    )
    parser.add_argument(
        "--keep-csv",
        action="store_true",
        help="Keep the merged CSV next to the ZIP instead of using a temporary file.",
    )
    return parser.parse_args()


def parse_class_map(entries: list[str] | None) -> dict[str, int] | None:
    if not entries:
        return None
    result: dict[str, int] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Invalid --class-map entry: {entry!r}; use LABEL=ID")
        label, value = entry.split("=", 1)
        if not LABEL_RE.fullmatch(label):
            raise ValueError(f"Invalid class label in --class-map: {label!r}")
        try:
            class_id = int(value)
        except ValueError as exc:
            raise ValueError(f"Invalid class ID in --class-map: {value!r}") from exc
        if class_id < 0:
            raise ValueError("Class IDs must be non-negative")
        if label in result:
            raise ValueError(f"Duplicate class label: {label}")
        result[label] = class_id
    if sorted(result.values()) != list(range(len(result))):
        raise ValueError("Class IDs must be contiguous and start at 0")
    return result


def discover_files(input_root: Path, labels: list[str] | None) -> dict[str, list[Path]]:
    if not input_root.is_dir():
        raise ValueError(f"Input directory does not exist: {input_root}")

    requested = set(labels or [])
    files_by_label: dict[str, list[Path]] = {}
    for path in sorted(input_root.rglob("*.csv")):
        if path.name == "dataset.csv":
            continue
        relative = path.relative_to(input_root)
        label = relative.parts[0] if len(relative.parts) > 1 else path.parent.name
        if requested and label not in requested:
            continue
        files_by_label.setdefault(label, []).append(path)

    if labels:
        missing = [label for label in labels if label not in files_by_label]
        if missing:
            raise ValueError("No CSV recordings found for label(s): " + ", ".join(missing))
    if not files_by_label:
        raise ValueError(f"No recording CSV files found under {input_root}")
    return files_by_label


def read_recording(path: Path, label: str, class_id: int, session_id: str) -> list[list[str]]:
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"Missing CSV header: {path}")
        fields = {field.strip() for field in reader.fieldnames if field}
        missing = set(INPUT_COLUMNS + ["label"]) - fields
        if missing:
            raise ValueError(
                f"{path} is missing required columns: {', '.join(sorted(missing))}"
            )

        rows: list[list[str]] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                values = [str(row[column]).strip() for column in INPUT_COLUMNS]
                if any(value == "" or value.lower() == "none" for value in values):
                    raise ValueError("empty sensor value")
                for value in values:
                    float(value)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid sensor row at {path}:{line_number}") from exc

            source_label = str(row.get("label", "")).strip()
            if source_label and source_label != label:
                raise ValueError(
                    f"Label mismatch at {path}:{line_number}: "
                    f"folder={label!r}, row={source_label!r}"
                )
            rows.append(values + [str(class_id), session_id])

    if not rows:
        raise ValueError(f"Recording is empty: {path}")
    return rows


def merge_dataset(
    files_by_label: dict[str, list[Path]],
    input_root: Path,
    class_map: dict[str, int],
    max_files_per_label: int | None,
) -> tuple[list[list[str]], int]:
    merged: list[list[str]] = []
    recording_count = 0
    for label in sorted(files_by_label):
        files = files_by_label[label]
        if max_files_per_label is not None:
            files = files[:max_files_per_label]
        for path in files:
            relative = path.relative_to(input_root).with_suffix("")
            session_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(relative))
            merged.extend(read_recording(path, label, class_map[label], session_id))
            recording_count += 1
    return merged, recording_count


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(OUTPUT_HEADER)
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    if args.max_files_per_label is not None and args.max_files_per_label < 1:
        raise SystemExit("--max-files-per-label must be at least 1")

    try:
        class_map = parse_class_map(args.class_map)
        files_by_label = discover_files(args.input, args.labels)
        labels = sorted(files_by_label)
        if class_map is None:
            class_map = {label: index for index, label in enumerate(labels)}
        unknown = set(labels) - set(class_map)
        if unknown:
            raise ValueError("Missing class IDs for label(s): " + ", ".join(sorted(unknown)))
        rows, recording_count = merge_dataset(
            files_by_label, args.input, class_map, args.max_files_per_label
        )

        output_zip = args.output if args.output.suffix.lower() == ".zip" else args.output.with_suffix(".zip")
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        csv_path = output_zip.with_name(output_zip.stem + ".csv")
        write_csv(csv_path, rows)
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            # Edge AI Lab requires the CSV filename to match the ZIP basename.
            archive.write(csv_path, arcname=csv_path.name)
        if not args.keep_csv:
            csv_path.unlink()

        print(f"Included labels: {', '.join(labels)}")
        print("Class mapping: " + ", ".join(f"{label}={class_map[label]}" for label in labels))
        print(f"Merged recordings: {recording_count}")
        print(f"Merged samples: {len(rows)}")
        print(f"Created ZIP: {output_zip}")
        if args.keep_csv:
            print(f"Created CSV: {csv_path}")
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
