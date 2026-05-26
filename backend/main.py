from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

app = FastAPI(title="Songpa Land Analysis API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def geojson(name: str) -> dict:
    path = PROCESSED / name
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(path.read_text(encoding="utf-8"))


def csv_records(name: str) -> list[dict]:
    path = PROCESSED / name
    if not path.exists():
        return []
    try:
        return pd.read_csv(path).fillna("").to_dict("records")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read {name}: {exc}") from exc


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/parcels")
def parcels() -> dict:
    return geojson("parcels_enriched.geojson")


@app.get("/api/buildings")
def buildings() -> dict:
    return geojson("buildings_enriched.geojson")


@app.get("/api/zoning")
def zoning() -> dict:
    return geojson("zoning_songpa.geojson")


@app.get("/api/census")
def census() -> dict:
    return geojson("census_songpa.geojson")


@app.get("/api/stats/use")
def stats_use() -> list[dict]:
    return csv_records("stats_use.csv")


@app.get("/api/stats/zoning")
def stats_zoning() -> list[dict]:
    return csv_records("stats_zoning.csv")


@app.get("/api/stats/population")
def stats_population() -> list[dict]:
    return csv_records("stats_population.csv")
