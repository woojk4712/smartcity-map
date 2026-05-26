import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import "./styles.css";

const VWORLD_KEY = "BF515956-8C98-331A-990C-E9030EC2B3F6";
const API = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const useColors = {
  "단독주택": "#f6a23a",
  "공동주택": "#5578f0",
  "제1종근린생활시설": "#6cc36c",
  "제2종근린생활시설": "#7bd4e8",
  "업무시설": "#c069d8",
  "교육연구시설": "#f4d35e",
  "종교시설": "#8dd7a5",
  "판매시설": "#ef6f6c",
  "의료시설": "#b18cf0",
  "미분류": "#8c98a4"
};

const zoningColors = ["#d875e4", "#f29d38", "#7ad3e2", "#6fa8ff", "#a2d867", "#ffcf5a", "#b78cff", "#ef7f7f"];

const emptyGeojson = { type: "FeatureCollection", features: [] };

const staticPaths = {
  "/api/parcels": "./data/processed/parcels_enriched.geojson",
  "/api/buildings": "./data/processed/buildings_enriched.geojson",
  "/api/zoning": "./data/processed/zoning_songpa.geojson",
  "/api/census": "./data/processed/census_songpa.geojson",
  "/api/stats/use": "./data/processed/stats_use.csv",
  "/api/stats/zoning": "./data/processed/stats_zoning.csv",
  "/api/stats/population": "./data/processed/stats_population.csv"
};

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const headers = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
  });
}

async function getJson(path) {
  try {
    const res = await fetch(`${API}${path}`);
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    return res.json();
  } catch (error) {
    const staticPath = staticPaths[path];
    if (!staticPath) throw error;
    const res = await fetch(staticPath);
    if (!res.ok) throw new Error(`${staticPath} ${res.status}`);
    return staticPath.endsWith(".csv") ? parseCsv(await res.text()) : res.json();
  }
}

function valueText(value, suffix = "") {
  if (typeof value === "string" && value.trim() && Number.isNaN(Number(value))) return value;
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`;
}

function App() {
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [layers, setLayers] = useState({ parcels: true, buildings: true, zoning: false, census: false });
  const [data, setData] = useState({ parcels: emptyGeojson, buildings: emptyGeojson, zoning: emptyGeojson, census: emptyGeojson });
  const [stats, setStats] = useState({ use: [], zoning: [], population: [] });
  const [hover, setHover] = useState(null);
  const [selected, setSelected] = useState(null);
  const [statView, setStatView] = useState("use");

  useEffect(() => {
    const map = new maplibregl.Map({
      container: "map",
      center: [127.115, 37.505],
      zoom: 12.2,
      pitch: 0,
      style: {
        version: 8,
        sources: {
          vworld: {
            type: "raster",
            tiles: [`https://api.vworld.kr/req/wmts/1.0.0/${VWORLD_KEY}/Base/{z}/{y}/{x}.png`],
            tileSize: 256,
            attribution: "VWorld"
          }
        },
        layers: [{ id: "vworld-base", type: "raster", source: "vworld" }]
      }
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "bottom-left");
    map.on("load", () => setReady(true));
    return () => map.remove();
  }, []);

  useEffect(() => {
    Promise.all([
      getJson("/api/parcels"),
      getJson("/api/buildings"),
      getJson("/api/zoning"),
      getJson("/api/census"),
      getJson("/api/stats/use"),
      getJson("/api/stats/zoning"),
      getJson("/api/stats/population")
    ])
      .then(([parcels, buildings, zoning, census, use, zoningStats, population]) => {
        setData({ parcels, buildings, zoning, census });
        setStats({ use, zoning: zoningStats, population });
      })
      .catch((err) => console.error(err));
  }, []);

  const zoningMap = useMemo(() => {
    const names = [...new Set(stats.zoning.map((d) => d.zoning_name || "미분류"))];
    return Object.fromEntries(names.map((name, i) => [name, zoningColors[i % zoningColors.length]]));
  }, [stats.zoning]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;

    const addOrUpdateSource = (id, geojson) => {
      if (map.getSource(id)) map.getSource(id).setData(geojson);
      else map.addSource(id, { type: "geojson", data: geojson });
    };
    addOrUpdateSource("parcels", data.parcels);
    addOrUpdateSource("buildings", data.buildings);
    addOrUpdateSource("zoning", data.zoning);
    addOrUpdateSource("census", data.census);

    if (!map.getLayer("zoning-fill")) {
      map.addLayer({ id: "zoning-fill", type: "fill", source: "zoning", paint: { "fill-color": "#7b8490", "fill-opacity": 0.38 } });
      map.addLayer({ id: "parcels-fill", type: "fill", source: "parcels", paint: { "fill-color": ["coalesce", ["get", "use_color"], "#f6a23a"], "fill-opacity": 0.18 } });
      map.addLayer({ id: "parcels-line", type: "line", source: "parcels", paint: { "line-color": "#ffffff", "line-width": 0.45, "line-opacity": 0.55 } });
      map.addLayer({ id: "buildings-fill", type: "fill", source: "buildings", paint: { "fill-color": ["match", ["get", "main_use"], ...Object.entries(useColors).flat(), "#8c98a4"], "fill-opacity": 0.72 } });
      map.addLayer({ id: "buildings-line", type: "line", source: "buildings", paint: { "line-color": "#222936", "line-width": 0.35, "line-opacity": 0.75 } });
      map.addLayer({
        id: "census-fill",
        type: "fill",
        source: "census",
        paint: {
          "fill-color": ["interpolate", ["linear"], ["to-number", ["get", "population"], 0], 0, "#2f80ed", 200, "#72d6ff", 500, "#ffd166", 1000, "#ef476f"],
          "fill-opacity": 0.42
        }
      });
      map.addLayer({ id: "selected-line", type: "line", source: "buildings", filter: ["==", ["get", "building_id"], ""], paint: { "line-color": "#ffffff", "line-width": 3 } });
    }

    map.setPaintProperty("zoning-fill", "fill-color", ["match", ["coalesce", ["get", "zoning_name"], "미분류"], ...Object.entries(zoningMap).flat(), "#7b8490"]);
    map.setPaintProperty("parcels-fill", "fill-color", ["match", ["coalesce", ["get", "zoning_name"], "미분류"], ...Object.entries(zoningMap).flat(), "#f6a23a"]);
  }, [ready, data, zoningMap]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const setVisibility = (ids, visible) => ids.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", visible ? "visible" : "none"));
    setVisibility(["parcels-fill", "parcels-line"], layers.parcels);
    setVisibility(["buildings-fill", "buildings-line"], layers.buildings);
    setVisibility(["zoning-fill"], layers.zoning);
    setVisibility(["census-fill"], layers.census);
  }, [ready, layers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const click = (e) => {
      const features = map.queryRenderedFeatures(e.point, { layers: ["buildings-fill", "parcels-fill", "zoning-fill", "census-fill"] });
      if (!features.length) return;
      const p = features[0].properties || {};
      setSelected(p);
      new maplibregl.Popup({ closeButton: true })
        .setLngLat(e.lngLat)
        .setHTML(`<strong>${p.jibun || p.address || p.pnu || "선택 항목"}</strong><br/>주용도: ${p.main_use || "-"}<br/>용도지역: ${p.zoning_name || p.zoning_registry || "-"}<br/>연면적: ${valueText(p.gross_area, "㎡")}<br/>층수: ${p.floor_count || "-"}<br/>사용승인일: ${p.approval_date || "-"}`)
        .addTo(map);
    };
    const move = (e) => {
      const features = map.queryRenderedFeatures(e.point, { layers: ["buildings-fill", "parcels-fill"] });
      map.getCanvas().style.cursor = features.length ? "pointer" : "";
      setHover(features[0]?.properties || null);
    };
    map.on("click", click);
    map.on("mousemove", move);
    return () => {
      map.off("click", click);
      map.off("mousemove", move);
    };
  }, [ready]);

  const useChart = stats.use.slice(0, 8).map((d) => ({ name: d.main_use || "미분류", value: Number(d.building_count) || 0 }));
  const zoningChart = stats.zoning.filter((d) => d.zoning_name !== "미분류").slice(0, 8).map((d) => ({ name: d.zoning_name || "미분류", value: Number(d.parcel_count) || 0 }));
  const populationSummary = useMemo(() => {
    const rows = stats.population;
    return rows.reduce((acc, d) => {
      acc.areas += 1;
      acc.population += Number(d.population) || 0;
      acc.households += Number(d.households) || 0;
      acc.area += Number(d.area_sqm) || 0;
      return acc;
    }, { areas: 0, population: 0, households: 0, area: 0 });
  }, [stats.population]);
  const totalBuildings = stats.use.reduce((a, d) => a + (Number(d.building_count) || 0), 0);
  const totalParcels = stats.zoning.reduce((a, d) => a + (Number(d.parcel_count) || 0), 0);

  return (
    <div className="app">
      <header>송파구 토지건축물 분석</header>
      <aside className="panel left">
        <h2>송파구 데이터 뷰어</h2>
        {Object.entries({ parcels: "필지", buildings: "건축물 주용도", zoning: "용도지역", census: "집계구 인구/가구" }).map(([key, label]) => (
          <label className="check" key={key}><input type="checkbox" checked={layers[key]} onChange={(e) => setLayers({ ...layers, [key]: e.target.checked })} />{label}</label>
        ))}
        <h3>주용도 범례</h3>
        <Legend items={useColors} />
        <h3>용도지역 범례</h3>
        <Legend items={zoningMap} />
        {hover && <div className="hoverbox">{hover.main_use || hover.zoning_name || hover.jibun || hover.pnu}</div>}
      </aside>
      <main id="map" />
      <aside className="panel right">
        <h2>송파구 통계</h2>
        <div className="tabs">
          {[["use", "건축물 주용도"], ["zoning", "용도지역"], ["population", "인구/가구"]].map(([key, label]) => (
            <button key={key} className={statView === key ? "active" : ""} onClick={() => setStatView(key)}>{label}</button>
          ))}
        </div>
        {statView === "use" && (
          <>
            <div className="metric"><b>{valueText(totalBuildings)}</b><span>건축물</span><b>{valueText(stats.use.length)}</b><span>주용도</span></div>
            <Donut data={useChart} color={(name) => useColors[name] || "#8c98a4"} />
            <Table rows={stats.use.slice(0, 14)} columns={[["main_use", "용도"], ["building_count", "동수"], ["total_gross_area", "연면적"], ["ratio", "비율"]]} percent="ratio" />
          </>
        )}
        {statView === "zoning" && (
          <>
            <div className="metric"><b>{valueText(totalParcels)}</b><span>필지</span><b>{valueText(stats.zoning.length)}</b><span>용도지역</span></div>
            <Donut data={zoningChart} color={(name) => zoningMap[name] || "#8c98a4"} />
            <Table rows={stats.zoning.slice(0, 14)} columns={[["zoning_name", "지역"], ["parcel_count", "필지"], ["total_parcel_area", "면적"], ["ratio", "비율"]]} percent="ratio" />
          </>
        )}
        {statView === "population" && (
          <>
            <div className="metric"><b>{valueText(populationSummary.areas)}</b><span>집계구</span><b>{valueText(populationSummary.population)}</b><span>총인구</span><b>{valueText(populationSummary.households)}</b><span>가구수</span><b>{valueText(populationSummary.area, "㎡")}</b><span>면적</span></div>
            <div className="note">현재 집계구 경계 파일에 총인구/가구수 컬럼이 없으면 값은 0으로 표시됩니다.</div>
            <Table rows={stats.population.slice(0, 14)} columns={[["TOT_OA_CD", "집계구"], ["population", "인구"], ["households", "가구"], ["population_density", "인구밀도"]]} />
          </>
        )}
        <h3>선택 항목</h3>
        <div className="selected">{selected ? JSON.stringify(selected, null, 2) : "지도에서 필지 또는 건축물을 선택하세요."}</div>
      </aside>
    </div>
  );
}

function Donut({ data, color }) {
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={210}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={58} outerRadius={88} paddingAngle={2}>
            {data.map((d) => <Cell key={d.name} fill={color(d.name)} />)}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function Legend({ items }) {
  return <div className="legend">{Object.entries(items).slice(0, 12).map(([name, color]) => <div key={name}><i style={{ background: color }} /> <span>{name}</span></div>)}</div>;
}

function Table({ rows, columns, percent }) {
  return (
    <table>
      <thead><tr>{columns.map(([_, label]) => <th key={label}>{label}</th>)}</tr></thead>
      <tbody>{rows.map((row, i) => <tr key={i}>{columns.map(([key]) => <td key={key}>{key === percent ? `${((Number(row[key]) || 0) * 100).toFixed(1)}%` : valueText(row[key])}</td>)}</tr>)}</tbody>
    </table>
  );
}

createRoot(document.getElementById("root")).render(<App />);
