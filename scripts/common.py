from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
SONGPA_CODE = "11710"


def candidate_roots() -> list[Path]:
    return [RAW_DIR, ROOT]


def find_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for base in candidate_roots():
        if not base.exists():
            continue
        for pattern in patterns:
            files.extend(base.rglob(pattern))
    seen = set()
    unique: list[Path] = []
    for path in files:
        key = path.resolve()
        if key not in seen and PROCESSED_DIR not in path.parents:
            unique.append(path)
            seen.add(key)
    return unique


def first_file(patterns: list[str], required: bool = True) -> Path | None:
    files = find_files(patterns)
    if files:
        return files[0]
    if required:
        raise FileNotFoundError(f"No file found for patterns: {patterns}")
    return None


def normalize_pnu(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(19)
