import requests
import pandas as pd
import os

from dotenv import load_dotenv


# =========================
# 1. 讀取 .env
# =========================

load_dotenv()

API_KEY = os.getenv("CWA_API_KEY")

if not API_KEY:
    print("找不到 CWA_API_KEY，請檢查 .env")
    exit()


# =========================
# 2. 中央氣象署 API
# =========================

URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001"

headers = {
    "Authorization": API_KEY
}

params = {
    "format": "JSON"
}


# =========================
# 3. 抓取資料
# =========================

try:
    response = requests.get(
        URL,
        headers=headers,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

except requests.RequestException as e:
    print("API 抓取失敗：", e)
    exit()


# =========================
# 4. 取得所有測站
# =========================

try:
    stations = data["records"]["Station"]

except KeyError:
    print("找不到 Station 資料")
    print(data)
    exit()


# =========================
# 5. 雨量特殊值處理
# =========================

def clean_rainfall(value):

    if value in ["T", -98, "-98"]:
        return 0.0

    if value in ["X", -99, "-99", None]:
        return None

    try:
        return float(value)

    except (ValueError, TypeError):
        return None


# =========================
# 6. 篩選臺中市
# =========================

rows = []

for station in stations:

    geo = station.get("GeoInfo", {})

    if geo.get("CountyName") != "臺中市":
        continue

    station_name = station.get("StationName")
    station_id = station.get("StationId")

    district = geo.get("TownName")

    observation_time = (
        station
        .get("ObsTime", {})
        .get("DateTime")
    )

    rainfall_raw = (
        station
        .get("RainfallElement", {})
        .get("Past1hr", {})
        .get("Precipitation")
    )

    rainfall = clean_rainfall(rainfall_raw)


    latitude = None
    longitude = None

    coordinates = geo.get("Coordinates", [])

    for coordinate in coordinates:

        if coordinate.get("CoordinateName") == "WGS84":

            latitude = coordinate.get("StationLatitude")
            longitude = coordinate.get("StationLongitude")

            break


    rows.append({
        "observation_time": observation_time,
        "station_id": station_id,
        "station_name": station_name,
        "district": district,
        "latitude": latitude,
        "longitude": longitude,
        "rainfall_1hr_mm": rainfall
    })


# =========================
# 7. DataFrame
# =========================

df = pd.DataFrame(rows)

print(df)

print(f"\n本次共抓到 {len(df)} 個臺中市雨量測站")


# =========================
# 8. 儲存 CSV + 防止重複
# =========================

file_name = "data/weather_history.csv"


if os.path.exists(file_name):

    # 讀取原本資料
    old_df = pd.read_csv(
        file_name
    )

    # 舊資料 + 本次新資料合併
    combined_df = pd.concat(
        [
            old_df,
            df
        ],
        ignore_index=True
    )

    before = len(combined_df)

    # 同一個測站 + 同一個觀測時間
    # 只保留一筆
    combined_df = combined_df.drop_duplicates(
        subset=[
            "observation_time",
            "station_id"
        ],
        keep="last"
    )

    after = len(combined_df)

    removed = before - after

    # 依時間排序
    combined_df = combined_df.sort_values(
        [
            "observation_time",
            "station_id"
        ]
    )

    # 覆寫成整理好的版本
    combined_df.to_csv(
        file_name,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        f"\n本次移除 {removed} 筆重複資料"
    )

else:

    # 第一次執行
    df.to_csv(
        file_name,
        index=False,
        encoding="utf-8-sig"
    )


print(
    f"資料已儲存到 {file_name}"
)