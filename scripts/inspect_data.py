from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from common import ROOT, find_files


def read_csv_sample(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, nrows=5, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, nrows=5)


def inspect_vector(path: Path) -> dict:
    last_error = None
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            gdf = gpd.read_file(path, rows=5, encoding=encoding)
            return {
                "path": str(path.relative_to(ROOT)),
                "type": "spatial",
                "crs": str(gdf.crs),
                "columns": [str(c) for c in gdf.columns],
                "sample": gdf.drop(columns="geometry", errors="ignore").head(2).to_dict("records"),
            }
        except Exception as exc:
            last_error = exc
    return {"path": str(path.relative_to(ROOT)), "type": "spatial", "error": str(last_error)}


def inspect_csv(path: Path) -> dict:
    try:
        df = read_csv_sample(path)
        return {
            "path": str(path.relative_to(ROOT)),
            "type": "table",
            "columns": [str(c) for c in df.columns],
            "sample": df.head(2).to_dict("records"),
        }
    except Exception as exc:
        return {"path": str(path.relative_to(ROOT)), "type": "table", "error": str(exc)}


def main() -> None:
    files = find_files(["*.shp", "*.geojson", "*.csv"])
    print(f"Found {len(files)} readable candidate files")
    for item in files:
        if item.suffix.lower() in {".shp", ".geojson", ".json"}:
            result = inspect_vector(item)
        else:
            result = inspect_csv(item)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
