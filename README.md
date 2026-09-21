# 臺中 YouBike 逐時供需與天氣關聯分析

本專案每小時保存臺中市 YouBike 場站快照，結合中央氣象署與 CODiS 雨量資料，分析不同地區、場站、時段及天氣下的缺車與缺空位風險。

## 專案重點

- 1,300,000 筆以上逐時場站觀測
- 依每個小時選擇「當時有資料且距離最近」的雨量站
- 觀察行政區、場站、時段與雨量的供需差異
- Streamlit 互動篩選、地圖與原始資料查詢

> 本資料為每小時快照，不是完整租借交易紀錄。因此「缺車／缺空位」代表觀測當下的供需壓力，不能直接解讀為租借次數。

## 啟動方式

在專案資料夾開啟終端機：

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

瀏覽器會開啟 `http://localhost:8501`。

目前的套件設定支援 Python 3.14；PyArrow 使用 25.0.1，Windows 會直接下載官方安裝檔，
不需要自行安裝 CMake 或編譯原始碼。

## 更新資料

將最新版來源檔放到 `data/raw/`：

- `ubike_history.csv`
- `weather_history.csv`
- `weather_history_merged.csv`

執行：

```bash
python build_dataset.py
```

程式會重新產生：

- `data/processed/ubike_weather.parquet`
- `data/processed/summary.json`

## 頁面

1. 首頁：專案動機、研究問題、資料流程與限制
2. YouBike 整體：逐時趨勢、行政區比較、高風險場站
3. 天氣與雨量：不同雨量強度下的供需差異
4. 站點與區域：單站趨勢、時段輪廓、最新站點地圖
5. 原始資料查詢：依日期、行政區、關鍵字與供需狀態篩選

## 資料來源

- 臺中市政府資料開放平台：YouBike 場站即時資料
- 交通部中央氣象署：自動雨量站觀測資料
- CODiS 氣候觀測資料查詢服務：歷史逐時雨量

## 技術

Python、Pandas、NumPy、PyArrow、Plotly、Streamlit、Windows 工作排程器

## 專案結構

```text
youbike_streamlit_project/
├─ app.py                         # Streamlit 儀表板
├─ build_dataset.py               # 清理、配對天氣與產生展示資料
├─ pipeline/
│  ├─ collect_ubike.py            # YouBike 每小時抓取
│  ├─ collect_weather.py          # 雨量每小時抓取
│  └─ codis_backfill.py           # CODiS 歷史資料補回
├─ data/
│  ├─ processed/                  # 已整理、可直接展示的資料
│  └─ raw/                        # 本機原始 CSV（不推上 GitHub）
├─ .streamlit/config.toml
├─ requirements.txt
└─ .env.example
```

## 放到 GitHub／Streamlit Community Cloud

專案已內附壓縮後的展示資料，不需要將 200 MB 以上的原始 CSV 推上 GitHub。
將此資料夾上傳到 GitHub 後，在 Streamlit Community Cloud 指定主程式為 `app.py` 即可。
`.env` 與 API 金鑰不可上傳。
