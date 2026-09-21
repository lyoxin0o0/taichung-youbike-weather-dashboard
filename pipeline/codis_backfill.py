import requests
import pandas as pd
import os
import time

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ==================================================
# 1. 設定
# ==================================================

# 你目前 weather_fetch.py 產生的檔案
STATION_FILE = "data/weather_history.csv"

# 補回來的歷史資料先另外存一份
BACKFILL_FILE = "data/weather_codis_20260821_20260901.csv"

# 歷史 + 現有資料合併後
MERGED_FILE = "data/weather_history_merged.csv"


# 要補的時間
START_TIME = pd.Timestamp(
    "2026-08-21 00:00:00",
    tz="Asia/Taipei"
)

# 為了完整包含 9/1，
# 結束設為 9/2 00:00，之後程式使用 < END_TIME
END_TIME = pd.Timestamp(
    "2026-09-02 22:00:00",
    tz="Asia/Taipei"
)


CODIS_PAGE = "https://codis.cwa.gov.tw/StationData"

CODIS_API = "https://codis.cwa.gov.tw/api/station"


# ==================================================
# 2. CODiS HTTP Header
# ==================================================

HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",

    "Content-Type":
        "application/x-www-form-urlencoded; charset=UTF-8",

    "X-Requested-With": "XMLHttpRequest",

    "Referer":
        "https://codis.cwa.gov.tw/StationData",

    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/152.0 Safari/537.36"
}


# ==================================================
# 3. 建立 Session + 自動重試
# ==================================================

session = requests.Session()

retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[
        429,
        500,
        502,
        503,
        504
    ]
)

adapter = HTTPAdapter(
    max_retries=retry
)

session.mount(
    "https://",
    adapter
)

session.headers.update(
    HEADERS
)


# ==================================================
# 4. 先進入 CODiS 頁面取得 Session
# ==================================================

print("正在連線 CODiS...")

try:

    response = session.get(
        CODIS_PAGE,
        timeout=30
    )

    response.raise_for_status()

except requests.RequestException as e:

    print("無法連線 CODiS：", e)
    exit()


print("CODiS 連線成功")


# ==================================================
# 5. 讀取目前臺中測站資料
# ==================================================

if not os.path.exists(STATION_FILE):

    print(
        f"找不到 {STATION_FILE}"
    )

    print(
        "請確認 codis_backfill.py "
        "跟 weather_history.csv "
        "放在同一個資料夾。"
    )

    exit()


station_df = pd.read_csv(
    STATION_FILE
)


required_columns = [
    "station_id",
    "station_name",
    "district",
    "latitude",
    "longitude"
]


for column in required_columns:

    if column not in station_df.columns:

        print(
            f"weather_history.csv "
            f"缺少欄位：{column}"
        )

        exit()


# 同一測站可能因為你執行過好幾次，
# 所以只留一筆作為測站清單
station_df = (
    station_df[
        required_columns
    ]
    .drop_duplicates(
        subset=["station_id"]
    )
    .reset_index(drop=True)
)


print(
    f"讀到 {len(station_df)} 個臺中測站"
)


# ==================================================
# 6. 判斷 CODiS 測站類型
# ==================================================

def get_station_type(station_id):

    station_id = str(
        station_id
    ).strip()

    # 署屬氣象站
    if station_id.startswith("46"):

        return "cwb"

    # 自動氣象站
    elif station_id.startswith("C0"):

        return "auto_C0"

    # 自動雨量站
    elif station_id.startswith("C1"):

        return "auto_C1"

    # C2 為農業站
    # 不走這個 CODiS station API
    else:

        return None


# ==================================================
# 7. 處理雨量特殊值
# ==================================================

def clean_rainfall(value):

    if value is None:
        return None

    try:

        value = float(value)

    except (ValueError, TypeError):

        return None


    # CODiS 的 -9.8 為雨跡
    # 為了跟你 weather_fetch.py 一致，
    # 這裡當成 0 mm
    if value == -9.8:

        return 0.0


    # -99.x 類通常代表缺測
    if value <= -90:

        return None


    return value


# ==================================================
# 8. 處理 CODiS 時間
# ==================================================

def parse_codis_time(value):

    if value is None:

        return None


    try:

        dt = pd.Timestamp(value)

    except Exception:

        return None


    # CODiS 有些資料把午夜記成前一天 23:59
    # 轉成下一天 00:00
    if (
        dt.hour == 23
        and dt.minute == 59
    ):

        dt = dt + pd.Timedelta(
            minutes=1
        )


    # CODiS 沒附 timezone 時，
    # 視為臺灣時間
    if dt.tzinfo is None:

        dt = dt.tz_localize(
            "Asia/Taipei"
        )

    else:

        dt = dt.tz_convert(
            "Asia/Taipei"
        )


    return dt


# ==================================================
# 9. 抓取單一測站
# ==================================================

def fetch_station_history(
    station_id,
    station_name,
    district,
    latitude,
    longitude
):

    stn_type = get_station_type(
        station_id
    )


    if stn_type is None:

        print(
            f"略過 {station_id} "
            f"{station_name}："
            "不是 46 / C0 / C1 測站"
        )

        return []


    payload = {

        "date":
            "2026-08-21T00:00:00.000+08:00",

        "type":
            "report_date",

        "stn_ID":
            station_id,

        "stn_type":
            stn_type,

        "start":
            "2026-08-21T00:00:00",

        "end": "2026-09-02T22:00:00"
    }


    try:

        response = session.post(
            CODIS_API,
            data=payload,
            timeout=60
        )

        response.raise_for_status()


        try:

            data = response.json()

        except ValueError:

            print(
                f"  {station_id} "
                "回傳內容不是 JSON"
            )

            return []


    except requests.RequestException as e:

        print(
            f"  {station_id} "
            f"下載失敗：{e}"
        )

        return []


    # ==============================================
    # CODiS 回傳格式：
    #
    # data
    #   └── [0]
    #        └── dts
    #             ├── DataTime
    #             └── Precipitation
    #                    └── Accumulation
    # ==============================================

    try:

        dts = data["data"][0]["dts"]

    except (
        KeyError,
        IndexError,
        TypeError
    ):

        print(
            f"  {station_id} "
            "沒有找到 dts 資料"
        )

        return []


    rows = []


    for item in dts:

        observation_time = (
            parse_codis_time(
                item.get("DataTime")
            )
        )


        if observation_time is None:

            continue


        # 只留下 8/21～9/1
        if not (
            START_TIME
            <= observation_time
            < END_TIME
        ):

            continue


        # 原則上 report_date 就是逐時資料
        # 再保險確認一次只留整點
        if observation_time.minute != 0:

            continue


        rainfall_raw = (
            item
            .get(
                "Precipitation",
                {}
            )
            .get(
                "Accumulation"
            )
        )


        rainfall = clean_rainfall(
            rainfall_raw
        )


        rows.append({

            "observation_time":
                observation_time.isoformat(),

            "station_id":
                station_id,

            "station_name":
                station_name,

            "district":
                district,

            "latitude":
                latitude,

            "longitude":
                longitude,

            "rainfall_1hr_mm":
                rainfall
        })


    return rows


# ==================================================
# 10. 開始逐測站抓取
# ==================================================

all_rows = []

success_count = 0
skip_count = 0


total = len(
    station_df
)


for index, station in station_df.iterrows():

    station_id = str(
        station["station_id"]
    ).strip()

    station_name = station[
        "station_name"
    ]

    district = station[
        "district"
    ]

    latitude = station[
        "latitude"
    ]

    longitude = station[
        "longitude"
    ]


    print(
        f"\n[{index + 1}/{total}] "
        f"{station_name} "
        f"({station_id})"
    )


    if get_station_type(
        station_id
    ) is None:

        skip_count += 1


    rows = fetch_station_history(

        station_id,
        station_name,
        district,
        latitude,
        longitude
    )


    if rows:

        success_count += 1

        all_rows.extend(
            rows
        )

        print(
            f"  成功抓到 "
            f"{len(rows)} 筆逐時資料"
        )

    else:

        print(
            "  沒有取得資料"
        )


    # 稍微休息，
    # 不要瞬間大量要求 CODiS
    time.sleep(0.5)


# ==================================================
# 11. 檢查結果
# ==================================================

if not all_rows:

    print(
        "\n沒有抓到任何歷史雨量資料。"
    )

    exit()


history_df = pd.DataFrame(
    all_rows
)


# ==================================================
# 12. 歷史資料去重
# ==================================================

history_df[
    "_time"
] = pd.to_datetime(
    history_df[
        "observation_time"
    ],
    errors="coerce",
    utc=True
)


history_df = (
    history_df
    .drop_duplicates(
        subset=[
            "_time",
            "station_id"
        ],
        keep="last"
    )
    .sort_values(
        [
            "_time",
            "station_id"
        ]
    )
)


history_df.drop(
    columns=["_time"],
    inplace=True
)


# ==================================================
# 13. 先獨立存一份歷史資料
# ==================================================

history_df.to_csv(

    BACKFILL_FILE,

    index=False,

    encoding="utf-8-sig"
)


# ==================================================
# 14. 再跟目前 weather_history.csv 合併
# ==================================================

current_df = pd.read_csv(
    STATION_FILE
)


combined_df = pd.concat(

    [
        history_df,
        current_df
    ],

    ignore_index=True
)


# 統一時間，避免不同格式造成重複
combined_df[
    "_time"
] = pd.to_datetime(

    combined_df[
        "observation_time"
    ],

    errors="coerce",

    utc=True
)


before = len(
    combined_df
)


combined_df = (
    combined_df
    .drop_duplicates(

        subset=[
            "_time",
            "station_id"
        ],

        keep="last"
    )
)


after = len(
    combined_df
)


removed = before - after


combined_df = (
    combined_df
    .sort_values(
        [
            "_time",
            "station_id"
        ]
    )
)


# 統一轉回臺灣時間
combined_df[
    "observation_time"
] = (
    combined_df["_time"]
    .dt
    .tz_convert(
        "Asia/Taipei"
    )
    .map(
        lambda x:
        x.isoformat()
        if pd.notna(x)
        else ""
    )
)


combined_df.drop(
    columns=["_time"],
    inplace=True
)


# ==================================================
# 15. 存合併後檔案
# ==================================================

combined_df.to_csv(

    MERGED_FILE,

    index=False,

    encoding="utf-8-sig"
)


# ==================================================
# 16. 顯示結果
# ==================================================

print(
    "\n================================="
)

print(
    "CODiS 歷史雨量補資料完成"
)

print(
    "================================="
)


print(
    f"成功測站：{success_count}"
)

print(
    f"略過測站：{skip_count}"
)

print(
    f"歷史資料筆數：{len(history_df)}"
)

print(
    f"合併時移除重複：{removed}"
)

print(
    f"合併後總筆數：{len(combined_df)}"
)


print(
    "\n歷史資料："
    f"{BACKFILL_FILE}"
)

print(
    "合併資料："
    f"{MERGED_FILE}"
)