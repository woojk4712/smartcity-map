# 송파구 토지건축물 분석

서울특별시 송파구 필지, 건축물, 용도지역, 집계구 데이터를 분석하고 MapLibre GL JS로 시각화하는 최소 실행 버전입니다.

## 구조

```text
songpa-land-analysis/
  frontend/
  backend/
  data/
    raw/
    processed/
  scripts/
  README.md
```

현재 원자료가 프로젝트 루트에 있어도 스크립트가 함께 탐색합니다. 추후에는 `data/raw` 아래로 원자료를 옮겨도 됩니다.

## 1단계 데이터 확인

```bash
python scripts/inspect_data.py
```

SHP, GeoJSON, CSV 파일 목록, CRS, 주요 컬럼, 샘플 값을 출력합니다.

## 2-4단계 전처리와 분석 결과 생성

```bash
python scripts/preprocess.py
```

생성 파일:

- `data/processed/parcels_enriched.geojson`
- `data/processed/buildings_enriched.geojson`
- `data/processed/zoning_songpa.geojson`
- `data/processed/census_songpa.geojson`
- `data/processed/stats_use.csv`
- `data/processed/stats_zoning.csv`
- `data/processed/stats_population.csv`

모든 공간 데이터는 EPSG:4326으로 변환됩니다. 건축물대장은 법정동코드, 대지구분코드, 번, 지로 PNU를 생성해 결합합니다. 용도지역은 필지 중심점 공간조인으로 붙입니다.

## 백엔드

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

API:

- `GET /api/parcels`
- `GET /api/buildings`
- `GET /api/zoning`
- `GET /api/census`
- `GET /api/stats/use`
- `GET /api/stats/zoning`
- `GET /api/stats/population`

## 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173`을 엽니다.

브이월드 WMTS API Key:

```text
BF515956-8C98-331A-990C-E9030EC2B3F6
```

## 확장 방향

- `data/processed`의 GeoJSON/CSV를 PostGIS 테이블로 교체할 수 있도록 백엔드는 파일 읽기 함수를 분리했습니다.
- GeoJSON이 커지면 `tippecanoe`, `tegola`, `Martin` 등을 통해 벡터타일로 확장하는 구조가 적합합니다.
- 현재 화면 범위 기반 통계는 프론트엔드 상태 구조만 마련되어 있으며, 다음 단계에서 bbox API 또는 클라이언트 필터링으로 갱신할 수 있습니다.
