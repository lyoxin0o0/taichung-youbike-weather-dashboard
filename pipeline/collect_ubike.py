import requests
import pandas as pd
import os
from datetime import datetime

url = "https://newdatacenter.taichung.gov.tw/api/v1/no-auth/resource.download?rid=9468c0d0-e1ed-4ecc-a86f-ab5a9fd590ff"
response = requests.get(url=url, timeout=30)
response.raise_for_status()

data = response.json()


df = pd.DataFrame(data)

# 英文欄位改成中文
columns_name = {
    "sno": "場站代號",
    "sna": "場站中文名稱",
    "sarea": "場站所屬行政區",
    "ar": "中文地址",
    "tot": "場站總停車格數",
    "sbi": "目前可借車輛數",
    "bemp": "目前可還空位數",
    "mday": "資料更新時間",
    "lat": "緯度",
    "lng": "經度",
    "act": "場站營運狀態",
    "sbi_detail": "各車種可借數量明細(一般車,電輔車)"
}

df.rename(columns=columns_name, inplace=True)

# 只留下需要的欄位
df = df[
    [
        "場站代號",
        "場站中文名稱",
        "場站所屬行政區",
        "中文地址",
        "場站總停車格數",
        "目前可借車輛數",
        "目前可還空位數",
        "資料更新時間",
        "緯度",
        "經度",
        "場站營運狀態",
        "各車種可借數量明細(一般車,電輔車)"
    ]
]

# API 本身的資料更新時間
df["資料更新時間"] = pd.to_datetime(
    df["資料更新時間"],
    format="%Y%m%d%H%M%S"
)

# ★ 加入「我們實際抓資料的時間」
df["抓取時間"] = datetime.now()

# 建立 data 資料夾
os.makedirs("data", exist_ok=True)

filename = "data/ubike_history.csv"

# 判斷 CSV 是否已經存在
if os.path.exists(filename):

    # 已經存在 → 接在原本資料下面
    df.to_csv(
        filename,
        mode="a",
        header=False,
        index=False,
        encoding="utf-8-sig"
    )

else:

    # 第一次執行 → 建立新 CSV
    df.to_csv(
        filename,
        index=False,
        encoding="utf-8-sig"
    )

print("YouBike 資料更新完成！")
print("抓取時間：", datetime.now())
print("本次資料筆數：", len(df))

# 不在每次排程後重新讀取整份歷史檔，避免資料變大後浪費記憶體與時間。
print("本次新增筆數：", len(df))
