"""Build the compact dataset used by the Streamlit dashboard.

Run from the project root after placing the source CSV files in data/raw/:
    python build_dataset.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

UBIKE_FILE = RAW_DIR / "ubike_history.csv"
WEATHER_FILES = [
    RAW_DIR / "weather_history_merged.csv",
    RAW_DIR / "weather_history.csv",
]


def haversine_matrix(
    left_lat: np.ndarray,
    left_lon: np.ndarray,
    right_lat: np.ndarray,
    right_lon: np.ndarray,
) -> np.ndarray:
    """Return all pairwise distances in kilometres."""
    lat1 = np.radians(left_lat)[:, None]
    lon1 = np.radians(left_lon)[:, None]
    lat2 = np.radians(right_lat)[None, :]
    lon2 = np.radians(right_lon)[None, :]
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def load_ubike() -> pd.DataFrame:
    usecols = [
        "場站代號",
        "場站中文名稱",
        "場站所屬行政區",
        "中文地址",
        "場站總停車格數",
        "目前可借車輛數",
        "目前可還空位數",
        "緯度",
        "經度",
        "場站營運狀態",
        "各車種可借數量明細(一般車,電輔車)",
        "抓取時間",
    ]
    df = pd.read_csv(UBIKE_FILE, usecols=usecols, low_memory=False)
    df["抓取時間"] = pd.to_datetime(df["抓取時間"], errors="coerce")
    df = df.dropna(subset=["抓取時間", "場站代號"]).copy()
    df["hour"] = df["抓取時間"].dt.floor("h")

    numeric = [
        "場站總停車格數",
        "目前可借車輛數",
        "目前可還空位數",
        "緯度",
        "經度",
        "場站營運狀態",
    ]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    vehicle_detail = (
        df["各車種可借數量明細(一般車,電輔車)"]
        .fillna("0,0")
        .astype(str)
        .str.split(",", n=1, expand=True)
    )
    df["一般車可借數"] = pd.to_numeric(vehicle_detail[0], errors="coerce").fillna(0)
    df["電輔車可借數"] = pd.to_numeric(vehicle_detail[1], errors="coerce").fillna(0)

    capacity = df["場站總停車格數"].replace(0, np.nan)
    df["可借率"] = (df["目前可借車輛數"] / capacity).clip(0, 1)
    operating = df["場站營運狀態"].eq(1)
    df["缺車"] = operating & df["目前可借車輛數"].le(2)
    df["缺空位"] = operating & df["目前可還空位數"].le(2)
    df["供需狀態"] = np.select(
        [~operating, df["缺車"], df["缺空位"]],
        ["暫停營運", "缺車風險", "缺空位風險"],
        default="供需正常",
    )
    df["日期"] = df["hour"].dt.date.astype(str)
    df["小時"] = df["hour"].dt.hour
    df["星期"] = df["hour"].dt.dayofweek.map(
        {0: "週一", 1: "週二", 2: "週三", 3: "週四", 4: "週五", 5: "週六", 6: "週日"}
    )
    return df


def load_weather() -> pd.DataFrame:
    frames = [pd.read_csv(path, low_memory=False) for path in WEATHER_FILES if path.exists()]
    if not frames:
        raise FileNotFoundError("找不到天氣資料")
    weather = pd.concat(frames, ignore_index=True)
    weather["observation_time"] = pd.to_datetime(
        weather["observation_time"], errors="coerce", utc=True
    )
    weather["hour"] = (
        weather["observation_time"]
        .dt.tz_convert("Asia/Taipei")
        .dt.tz_localize(None)
        .dt.floor("h")
    )
    for col in ["latitude", "longitude", "rainfall_1hr_mm"]:
        weather[col] = pd.to_numeric(weather[col], errors="coerce")
    weather = weather.dropna(subset=["hour", "station_id", "latitude", "longitude"])
    weather["station_id"] = weather["station_id"].astype(str)

    # A station can appear in both the backfill and live file. Keep one hourly row.
    weather = (
        weather.sort_values("observation_time")
        .drop_duplicates(["hour", "station_id"], keep="last")
        .reset_index(drop=True)
    )
    return weather


def make_hour_station_weather(ubike: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """For each YouBike station/hour, select the nearest station reporting that hour."""
    bike_stations = (
        ubike[["場站代號", "緯度", "經度"]]
        .dropna()
        .drop_duplicates("場站代號")
        .sort_values("場站代號")
        .reset_index(drop=True)
    )
    weather_stations = (
        weather[["station_id", "station_name", "district", "latitude", "longitude"]]
        .drop_duplicates("station_id")
        .sort_values("station_id")
        .reset_index(drop=True)
    )
    distances = haversine_matrix(
        bike_stations["緯度"].to_numpy(),
        bike_stations["經度"].to_numpy(),
        weather_stations["latitude"].to_numpy(),
        weather_stations["longitude"].to_numpy(),
    )
    station_index = {sid: idx for idx, sid in enumerate(weather_stations["station_id"])}
    weather_by_hour = {
        hour: group.dropna(subset=["rainfall_1hr_mm"]).copy()
        for hour, group in weather.groupby("hour", sort=False)
    }

    rows: list[pd.DataFrame] = []
    for hour in sorted(ubike["hour"].dropna().unique()):
        observed = weather_by_hour.get(hour)
        if observed is None or observed.empty:
            continue
        valid_ids = [sid for sid in observed["station_id"] if sid in station_index]
        if not valid_ids:
            continue
        valid_indices = np.array([station_index[sid] for sid in valid_ids])
        nearest_local = np.argmin(distances[:, valid_indices], axis=1)
        nearest_indices = valid_indices[nearest_local]

        lookup = observed.drop_duplicates("station_id").set_index("station_id")
        selected_ids = weather_stations.iloc[nearest_indices]["station_id"].to_numpy()
        part = pd.DataFrame(
            {
                "場站代號": bike_stations["場站代號"].to_numpy(),
                "hour": hour,
                "雨量站代號": selected_ids,
                "最近雨量站": [lookup.loc[sid, "station_name"] for sid in selected_ids],
                "雨量站行政區": [lookup.loc[sid, "district"] for sid in selected_ids],
                "雨量站距離_km": distances[np.arange(len(bike_stations)), nearest_indices],
                "每小時雨量_mm": [lookup.loc[sid, "rainfall_1hr_mm"] for sid in selected_ids],
            }
        )
        rows.append(part)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    print("讀取 YouBike 資料…")
    ubike = load_ubike()
    print("讀取天氣資料…")
    weather = load_weather()
    print("依每個小時配對最近且有觀測值的雨量站…")
    station_weather = make_hour_station_weather(ubike, weather)
    merged = ubike.merge(station_weather, on=["場站代號", "hour"], how="left")
    merged["雨量狀態"] = pd.cut(
        merged["每小時雨量_mm"],
        bins=[-0.001, 0, 2.5, 10, np.inf],
        labels=["無雨", "微雨", "小雨", "中大雨"],
    ).astype("string").fillna("無資料")

    keep = [
        "場站代號", "場站中文名稱", "場站所屬行政區", "中文地址", "場站總停車格數",
        "目前可借車輛數", "目前可還空位數", "一般車可借數", "電輔車可借數",
        "抓取時間", "hour", "日期", "小時", "星期", "緯度", "經度", "場站營運狀態",
        "可借率", "缺車", "缺空位", "供需狀態", "最近雨量站", "雨量站行政區",
        "雨量站距離_km", "每小時雨量_mm", "雨量狀態",
    ]
    merged = merged[keep].sort_values(["抓取時間", "場站代號"]).reset_index(drop=True)

    # Keep Streamlit's memory use manageable. These values repeat heavily, so
    # categorical and smaller numeric dtypes reduce RAM without losing meaning.
    category_cols = [
        "場站中文名稱", "場站所屬行政區", "中文地址", "日期", "星期", "供需狀態",
        "最近雨量站", "雨量站行政區", "雨量狀態",
    ]
    for col in category_cols:
        merged[col] = merged[col].astype("category")
    for col in [
        "場站總停車格數", "目前可借車輛數", "目前可還空位數", "一般車可借數", "電輔車可借數"
    ]:
        merged[col] = merged[col].astype("uint16")
    merged["場站代號"] = merged["場站代號"].astype("int32")
    merged["小時"] = merged["小時"].astype("uint8")
    merged["場站營運狀態"] = merged["場站營運狀態"].astype("int8")
    for col in ["緯度", "經度", "可借率", "雨量站距離_km", "每小時雨量_mm"]:
        merged[col] = merged[col].astype("float32")
    merged.to_parquet(PROCESSED_DIR / "ubike_weather.parquet", index=False, compression="zstd")

    summary = {
        "rows": int(len(merged)),
        "stations": int(merged["場站代號"].nunique()),
        "districts": int(merged["場站所屬行政區"].nunique()),
        "snapshots": int(merged["抓取時間"].nunique()),
        "start": str(merged["抓取時間"].min()),
        "end": str(merged["抓取時間"].max()),
        "weather_match_rate": round(float(merged["每小時雨量_mm"].notna().mean()), 4),
    }
    (PROCESSED_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
