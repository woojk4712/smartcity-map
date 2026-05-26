from __future__ import annotations

import json
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd

from common import PROCESSED_DIR, SONGPA_CODE, find_files, first_file, normalize_pnu


BUILDING_COLUMNS = {
    "A1": "building_id",
    "A2": "pnu",
    "A4": "address",
    "A5": "jibun",
    "A9": "main_use",
    "A12": "building_area",
    "A13": "approval_date",
    "A14": "gross_area",
    "A21": "building_mgmt_no",
    "A23": "sgg_code",
    "A26": "floor_count",
    "A27": "basement_count",
}

VALID_ZONING_NAMES = {
    "제1종전용주거지역",
    "제2종전용주거지역",
    "제1종일반주거지역",
    "제2종일반주거지역",
    "제3종일반주거지역",
    "준주거지역",
    "중심상업지역",
    "일반상업지역",
    "근린상업지역",
    "유통상업지역",
    "전용공업지역",
    "일반공업지역",
    "준공업지역",
    "보전녹지지역",
    "생산녹지지역",
    "자연녹지지역",
    "보전관리지역",
    "생산관리지역",
    "계획관리지역",
    "농림지역",
    "자연환경보전지역",
}

ZONING_KEYWORDS = (
    "전용주거지역",
    "일반주거지역",
    "준주거지역",
    "상업지역",
    "공업지역",
    "녹지지역",
    "관리지역",
    "농림지역",
    "자연환경보전지역",
)

NON_ZONING_KEYWORDS = (
    "도로",
    "소로",
    "중로",
    "대로",
    "철도",
    "주차장",
    "정류장",
    "정거장",
    "환기구",
    "출입구",
    "공원",
    "광장",
    "학교",
    "시설",
    "지구단위계획",
    "정비",
    "개발구역",
    "고시",
    "입안",
    "폐지",
    "터널",
)


def read_spatial(path: Path) -> gpd.GeoDataFrame:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return gpd.read_file(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return gpd.read_file(path)


def read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, low_memory=False)


def read_sgis_metric_csv(path: Path, metric_name: str, item_code: str | None = None) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(path, header=None, names=["year", "TOT_OA_CD", "item_code", metric_name], encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        df = pd.read_csv(path, header=None, names=["year", "TOT_OA_CD", "item_code", metric_name])
    if item_code:
        df = df[df["item_code"].astype(str).eq(item_code)].copy()
    df["TOT_OA_CD"] = df["TOT_OA_CD"].astype(str).str.replace(r"\.0$", "", regex=True)
    df[metric_name] = pd.to_numeric(df[metric_name].replace("N/A", pd.NA), errors="coerce").fillna(0)
    return df[["TOT_OA_CD", metric_name]].groupby("TOT_OA_CD", as_index=False)[metric_name].sum()


def load_census_metrics() -> pd.DataFrame:
    population_files = find_files(["*인구총괄*.csv", "*인구수*.csv"])
    household_files = [p for p in find_files(["*가구총괄*.csv"]) if "세대구성" not in p.name]
    metrics: pd.DataFrame | None = None
    if population_files:
        population = read_sgis_metric_csv(population_files[0], "population", "to_in_001")
        population = population[population["TOT_OA_CD"].str.startswith("11240")].copy()
        print(f"Population metric rows: {len(population):,} from {population_files[0]}")
        metrics = population
    else:
        print("Population metric CSV not found")
    if household_files:
        households = read_sgis_metric_csv(household_files[0], "households", "to_ga_001")
        households = households[households["TOT_OA_CD"].str.startswith("11240")].copy()
        print(f"Household metric rows: {len(households):,} from {household_files[0]}")
        metrics = households if metrics is None else metrics.merge(households, on="TOT_OA_CD", how="outer")
    else:
        print("Household metric CSV not found")
    if metrics is None:
        return pd.DataFrame(columns=["TOT_OA_CD", "population", "households"])
    for col in ["population", "households"]:
        if col not in metrics.columns:
            metrics[col] = 0
    return metrics.fillna({"population": 0, "households": 0})


def to_4326(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:5186")
    return gdf.to_crs("EPSG:4326")


def clean_geometry(gdf: gpd.GeoDataFrame, name: str) -> gpd.GeoDataFrame:
    before = len(gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if not gdf.empty:
        gdf["geometry"] = gdf.geometry.make_valid()
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid].copy()
    removed = before - len(gdf)
    if removed:
        print(f"{name}: removed {removed:,} invalid/empty geometries")
    return gdf


def clip_to_songpa(gdf: gpd.GeoDataFrame, songpa: gpd.GeoDataFrame, name: str) -> gpd.GeoDataFrame:
    if gdf.empty or songpa.empty:
        return gdf
    target_crs = gdf.crs
    clip_geom = songpa.to_crs(target_crs)[["geometry"]].dissolve()
    clipped = gpd.clip(gdf, clip_geom)
    print(f"{name}: clipped {len(gdf):,} -> {len(clipped):,}")
    return clipped


def print_bounds(name: str, gdf: gpd.GeoDataFrame) -> None:
    if gdf.empty:
        print(f"{name} bounds EPSG:4326: empty")
        return
    bounds = gdf.to_crs("EPSG:4326").total_bounds
    print(f"{name} bounds EPSG:4326: [{bounds[0]:.6f}, {bounds[1]:.6f}, {bounds[2]:.6f}, {bounds[3]:.6f}]")


def write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = clean_geometry(gdf, path.stem)
    if not gdf.empty:
        gdf["geometry"] = gdf.geometry.simplify(0.00001, preserve_topology=True)
        gdf = clean_geometry(gdf, f"{path.stem} after simplify")
    print_bounds(path.name, gdf)
    gdf.to_file(path, driver="GeoJSON")


def make_empty_geojson(path: Path) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")


def clean_text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def is_valid_zoning_name(value: object) -> bool:
    text = clean_text(value)
    if not text:
        return False
    if text in VALID_ZONING_NAMES:
        return True
    if any(word in text for word in NON_ZONING_KEYWORDS):
        return False
    return any(word in text for word in ZONING_KEYWORDS)


def extract_zoning_name(row: pd.Series) -> str | None:
    for column in ("ALIAS", "REMARK"):
        text = clean_text(row.get(column))
        if is_valid_zoning_name(text):
            return text
    return None


def build_registry() -> pd.DataFrame:
    path = first_file(["*건축물*대장*.csv", "*.csv"], required=False)
    if not path:
        return pd.DataFrame()
    df = read_csv(path)
    if "시군구코드" in df.columns:
        df = df[df["시군구코드"].astype(str).str.zfill(5).eq(SONGPA_CODE)].copy()
    if {"법정동코드", "대지구분코드", "번", "지"}.issubset(df.columns):
        sgg = df["시군구코드"].astype(str).str.zfill(5)
        dong = df["법정동코드"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
        land_code = pd.to_numeric(df["대지구분코드"], errors="coerce").fillna(0).astype(int) + 1
        land = land_code.astype(str).str.zfill(1)
        bun = df["번"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
        ji = df["지"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
        df["pnu"] = sgg + dong + land + bun + ji
    rename = {
        "관리건축물대장PK": "building_mgmt_no",
        "대지위치": "address",
        "건물명": "building_name",
        "지역코드명": "zoning_registry",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    keep = [c for c in ["pnu", "building_mgmt_no", "address", "building_name", "zoning_registry"] if c in df.columns]
    return df[keep].drop_duplicates("pnu") if "pnu" in keep else pd.DataFrame()


def process_parcels(registry: pd.DataFrame) -> gpd.GeoDataFrame:
    path = first_file(["*LDREG*.shp", "*연속지적*.shp"])
    raw = read_spatial(path)
    print(f"Parcels source CRS: {raw.crs}")
    parcels = clean_geometry(to_4326(raw), "parcels")
    parcels = parcels[parcels["PNU"].astype(str).str.startswith(SONGPA_CODE)].copy()
    parcels["pnu"] = parcels["PNU"].map(normalize_pnu)
    parcels["parcel_area"] = parcels.to_crs("EPSG:5186").area
    parcels = parcels.rename(columns={"JIBUN": "jibun"})
    if not registry.empty and "pnu" in registry.columns:
        parcels = parcels.merge(registry, on="pnu", how="left")
    keep = [c for c in ["pnu", "jibun", "parcel_area", "address", "building_name", "zoning_registry", "geometry"] if c in parcels.columns]
    return parcels[keep]


def process_buildings(registry: pd.DataFrame) -> gpd.GeoDataFrame:
    paths = [p for p in find_files(["*.shp"]) if "D010" in p.name or "GIS" in str(p)]
    if not paths:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    raw = read_spatial(paths[0])
    print(f"Buildings source CRS: {raw.crs}")
    buildings = clean_geometry(to_4326(raw), "buildings")
    buildings = buildings.rename(columns={k: v for k, v in BUILDING_COLUMNS.items() if k in buildings.columns})
    if "sgg_code" in buildings.columns:
        buildings = buildings[buildings["sgg_code"].astype(str).str.zfill(5).eq(SONGPA_CODE)].copy()
    elif "pnu" in buildings.columns:
        buildings = buildings[buildings["pnu"].astype(str).str.startswith(SONGPA_CODE)].copy()
    if "pnu" in buildings.columns:
        buildings["pnu"] = buildings["pnu"].map(normalize_pnu)
    if not registry.empty and "pnu" in buildings.columns:
        buildings = buildings.merge(registry, on="pnu", how="left", suffixes=("", "_registry"))
    keep = [
        c
        for c in [
            "building_id",
            "building_mgmt_no",
            "pnu",
            "address",
            "jibun",
            "main_use",
            "gross_area",
            "building_area",
            "floor_count",
            "basement_count",
            "approval_date",
            "zoning_registry",
            "geometry",
        ]
        if c in buildings.columns
    ]
    return buildings[keep]


def process_zoning(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    path = first_file(["*UQ161*.shp", "*연속주제*.shp"], required=False)
    if not path:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    raw = read_spatial(path)
    print(f"Zoning source CRS: {raw.crs}")
    zoning = clean_geometry(to_4326(raw), "zoning")
    zoning = zoning[zoning["COL_ADM_SE"].astype(str).eq(SONGPA_CODE)].copy()
    zoning["zoning_name"] = zoning.apply(extract_zoning_name, axis=1)
    zoning = zoning[zoning["zoning_name"].notna()].copy()
    zoning = zoning.rename(columns={"MNUM": "zoning_code", "REMARK": "remark"})
    if not parcels.empty:
        minx, miny, maxx, maxy = parcels.total_bounds
        zoning = zoning.cx[minx:maxx, miny:maxy].copy()
    keep = [c for c in ["zoning_code", "zoning_name", "remark", "geometry"] if c in zoning.columns]
    return zoning[keep]


def build_registry_zoning_layer(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if parcels.empty or "zoning_registry" not in parcels.columns:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    valid = parcels[parcels["zoning_registry"].map(is_valid_zoning_name)].copy()
    if valid.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    valid["zoning_name"] = valid["zoning_registry"].map(clean_text)
    dissolved = valid[["zoning_name", "geometry"]].dissolve(by="zoning_name", as_index=False)
    dissolved["zoning_code"] = dissolved["zoning_name"]
    dissolved["remark"] = "건축물대장 지역코드명 기반 보강"
    return dissolved[["zoning_code", "zoning_name", "remark", "geometry"]]


def attach_zoning(parcels: gpd.GeoDataFrame, zoning: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if parcels.empty or zoning.empty:
        parcels = parcels.copy()
        if "zoning_registry" in parcels.columns:
            parcels["zoning_name"] = parcels["zoning_registry"].where(parcels["zoning_registry"].map(is_valid_zoning_name), "미분류")
        else:
            parcels["zoning_name"] = "미분류"
        return parcels
    centroids = parcels.to_crs("EPSG:5186").copy()
    centroids["geometry"] = centroids.geometry.centroid
    joined = gpd.sjoin(
        centroids,
        zoning.to_crs("EPSG:5186")[["zoning_name", "geometry"]],
        how="left",
        predicate="within",
    )
    parcels = parcels.copy()
    spatial_zoning = joined.groupby(level=0)["zoning_name"].first().reindex(parcels.index)
    registry_zoning = parcels["zoning_registry"] if "zoning_registry" in parcels.columns else pd.Series("", index=parcels.index)
    registry_zoning = registry_zoning.replace("", pd.NA)
    registry_zoning = registry_zoning.where(registry_zoning.map(is_valid_zoning_name), pd.NA)
    spatial_zoning = spatial_zoning.replace("", pd.NA)
    spatial_zoning = spatial_zoning.where(spatial_zoning.map(is_valid_zoning_name), pd.NA)
    parcels["zoning_name"] = registry_zoning.fillna(spatial_zoning).fillna("미분류")
    return parcels


def process_census(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    paths = [p for p in find_files(["*집계*.shp", "*bnd_oa*.shp", "*census*.shp", "*인구*.shp", "*집계*.geojson", "*census*.geojson"])]
    if not paths:
        make_empty_geojson(PROCESSED_DIR / "census_songpa.geojson")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    raw = read_spatial(paths[0])
    print(f"Census source CRS: {raw.crs}")
    census = clean_geometry(to_4326(raw), "census")
    if not parcels.empty:
        census = clip_to_songpa(census, parcels, "census")
    if "TOT_OA_CD" in census.columns:
        census["TOT_OA_CD"] = census["TOT_OA_CD"].astype(str).str.replace(r"\.0$", "", regex=True)
        metrics = load_census_metrics()
        if not metrics.empty:
            census = census.merge(metrics, on="TOT_OA_CD", how="left")
            matched = int(census["population"].notna().sum() if "population" in census.columns else 0)
            print(f"Census metric matched rows: {matched:,} / {len(census):,}")
    for col in ["population", "households"]:
        if col not in census.columns:
            census[col] = 0
        census[col] = pd.to_numeric(census[col], errors="coerce").fillna(0)
    projected = census.to_crs("EPSG:5186")
    census["area_sqm"] = projected.area
    census["population_density"] = census["population"] / (census["area_sqm"] / 1_000_000)
    census["household_density"] = census["households"] / (census["area_sqm"] / 1_000_000)
    return census


def create_stats(buildings: gpd.GeoDataFrame, parcels: gpd.GeoDataFrame, census: gpd.GeoDataFrame) -> None:
    if "main_use" in buildings.columns and not buildings.empty:
        stats_use = buildings.assign(gross_area=pd.to_numeric(buildings.get("gross_area"), errors="coerce").fillna(0))
        stats_use = stats_use.groupby("main_use", dropna=False).agg(
            building_count=("main_use", "size"),
            total_gross_area=("gross_area", "sum"),
            avg_gross_area=("gross_area", "mean"),
        ).reset_index()
        stats_use["ratio"] = stats_use["building_count"] / stats_use["building_count"].sum()
    else:
        stats_use = pd.DataFrame(columns=["main_use", "building_count", "total_gross_area", "avg_gross_area", "ratio"])
    stats_use.to_csv(PROCESSED_DIR / "stats_use.csv", index=False, encoding="utf-8-sig")

    if "zoning_name" in parcels.columns and not parcels.empty:
        stats_zoning = parcels.groupby("zoning_name", dropna=False).agg(
            parcel_count=("zoning_name", "size"),
            total_parcel_area=("parcel_area", "sum"),
        ).reset_index()
        stats_zoning["ratio"] = stats_zoning["parcel_count"] / stats_zoning["parcel_count"].sum()
    else:
        stats_zoning = pd.DataFrame(columns=["zoning_name", "parcel_count", "total_parcel_area", "ratio"])
    stats_zoning.to_csv(PROCESSED_DIR / "stats_zoning.csv", index=False, encoding="utf-8-sig")

    if not census.empty:
        keep = [
            c
            for c in ["BASE_DATE", "ADM_CD", "TOT_OA_CD", "population", "households", "area_sqm", "population_density", "household_density"]
            if c in census.columns
        ]
        stats_population = census.drop(columns="geometry", errors="ignore")[keep].copy()
    else:
        stats_population = pd.DataFrame(columns=["area_sqm", "population", "households", "population_density", "household_density"])
    stats_population.to_csv(PROCESSED_DIR / "stats_population.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    print("Building registry...")
    registry = build_registry()
    print(f"Registry rows: {len(registry):,}")
    print("Processing parcels...")
    parcels = process_parcels(registry)
    print(f"Parcels: {len(parcels):,}")
    print("Processing buildings...")
    buildings = process_buildings(registry)
    buildings = clip_to_songpa(buildings, parcels, "buildings")
    print(f"Buildings: {len(buildings):,}")
    print("Processing zoning...")
    zoning = process_zoning(parcels)
    print(f"Valid UQ161 zoning polygons: {len(zoning):,}")
    if zoning.empty:
        print("No valid Songpa zoning names found in UQ161; using registry zoning names for zoning_songpa.geojson.")
        zoning = build_registry_zoning_layer(parcels)
    zoning = clip_to_songpa(zoning, parcels, "zoning")
    print(f"Zoning polygons: {len(zoning):,}")
    print("Joining zoning to parcels...")
    parcels = attach_zoning(parcels, zoning)
    print("Processing census...")
    census = process_census(parcels)

    print("Writing GeoJSON files...")
    write_geojson(parcels, PROCESSED_DIR / "parcels_enriched.geojson")
    write_geojson(buildings, PROCESSED_DIR / "buildings_enriched.geojson")
    write_geojson(zoning, PROCESSED_DIR / "zoning_songpa.geojson")
    if not census.empty:
        write_geojson(census, PROCESSED_DIR / "census_songpa.geojson")
    print("Writing statistics...")
    create_stats(buildings, parcels, census)
    print(f"Processed data written to data/processed in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
