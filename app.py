from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "processed" / "ubike_weather.parquet"

st.set_page_config(
    page_title="臺中 YouBike 逐時供需分析",
    page_icon="🚲",
    layout="wide",
)

WEEK_ORDER = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
STATUS_COLORS = {
    "供需正常": "#2FA67C", "缺車風險": "#F4A261",
    "缺空位風險": "#E76F51", "暫停營運": "#7F8C8D",
}


@st.cache_data(show_spinner="載入分析資料中…")
def load_data() -> pd.DataFrame:
    df = pd.read_parquet(DATA_FILE)
    df["抓取時間"] = pd.to_datetime(df["抓取時間"])
    df["hour"] = pd.to_datetime(df["hour"])
    return df


def percent(value: float) -> str:
    return f"{value:.1%}"


def metric_row(df: pd.DataFrame) -> None:
    latest = df["抓取時間"].max()
    latest_df = df[df["抓取時間"] == latest]
    cols = st.columns(5)
    cols[0].metric("資料筆數", f"{len(df):,}")
    cols[1].metric("場站數", f"{df['場站代號'].nunique():,}")
    cols[2].metric("行政區", f"{df['場站所屬行政區'].nunique()}")
    cols[3].metric("最新可借車輛", f"{latest_df['目前可借車輛數'].sum():,.0f}")
    cols[4].metric("天氣配對率", percent(df["每小時雨量_mm"].notna().mean()))


@st.cache_data(show_spinner=False)
def filter_data(df: pd.DataFrame, districts: tuple[str, ...], start_date, end_date) -> pd.DataFrame:
    mask = (
        df["場站所屬行政區"].isin(districts)
        & df["抓取時間"].dt.date.ge(start_date)
        & df["抓取時間"].dt.date.le(end_date)
    )
    return df.loc[mask].copy()


def page_home(df: pd.DataFrame) -> None:
    st.title("🚲 臺中 YouBike 逐時供需與天氣關聯分析")
    st.caption("以每小時快照觀察場站缺車、缺空位與降雨之間的關係")
    metric_row(df)
    st.divider()
    left, right = st.columns([1.25, 1])
    with left:
        st.subheader("專案動機")
        st.write(
            "YouBike 官方資料呈現的是當下狀態，無法直接回看場站在不同時段的供需變化。"
            "本專案自動保存臺中市各站每小時快照，結合中央氣象署雨量觀測，"
            "用來找出經常缺車或缺空位的地區、時段與場站。"
        )
        st.subheader("分析問題")
        st.markdown(
            "- 哪些行政區與場站最常出現缺車或缺空位？\n"
            "- 一天中哪些時段供需壓力最高？\n"
            "- 降雨時，場站可借率與供需狀態是否改變？\n"
            "- 使用者查詢特定區域時，哪些站點目前較容易借車？"
        )
    with right:
        st.subheader("資料處理流程")
        st.info(
            "臺中 YouBike API → 每小時排程保存 → 清理與衍生指標\n\n"
            "中央氣象署／CODiS → 統一逐時雨量 → 配對當時最近且有資料的測站\n\n"
            "Pandas 分析 → Parquet 壓縮 → Streamlit 互動儀表板"
        )
        st.warning(
            "本資料是每小時快照，因此『缺車／缺空位』代表觀測當下的供需壓力，"
            "不能等同於實際租借次數或完整旅次資料。"
        )
    st.subheader("資料涵蓋期間")
    st.write(
        f"{df['抓取時間'].min():%Y-%m-%d %H:%M} ～ {df['抓取時間'].max():%Y-%m-%d %H:%M}，"
        f"共 {df['抓取時間'].nunique():,} 次快照。"
    )


def page_overview(df: pd.DataFrame) -> None:
    st.title("📊 YouBike 整體供需")
    metric_row(df)
    hourly = (
        df.groupby("hour", as_index=False, observed=True)
        .agg(
            平均可借率=("可借率", "mean"),
            缺車站比例=("缺車", "mean"),
            缺空位站比例=("缺空位", "mean"),
        )
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hourly["hour"], y=hourly["缺車站比例"], name="缺車站比例"))
    fig.add_trace(go.Scatter(x=hourly["hour"], y=hourly["缺空位站比例"], name="缺空位站比例"))
    fig.update_layout(title="逐時供需風險變化", yaxis_tickformat=".0%", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")

    district = (
        df.groupby("場站所屬行政區", as_index=False, observed=True)
        .agg(場站數=("場站代號", "nunique"), 缺車率=("缺車", "mean"), 缺空位率=("缺空位", "mean"))
        .sort_values("缺車率", ascending=False)
    )
    left, right = st.columns(2)
    with left:
        fig = px.bar(
            district.head(15), x="缺車率", y="場站所屬行政區", orientation="h",
            title="缺車風險較高的行政區（前 15 名）", text_auto=".1%",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_tickformat=".0%")
        st.plotly_chart(fig, width="stretch")
    with right:
        fig = px.bar(
            district.sort_values("缺空位率", ascending=False).head(15),
            x="缺空位率", y="場站所屬行政區", orientation="h",
            title="缺空位風險較高的行政區（前 15 名）", text_auto=".1%",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_tickformat=".0%")
        st.plotly_chart(fig, width="stretch")

    station = (
        df.groupby(
            ["場站代號", "場站中文名稱", "場站所屬行政區"],
            as_index=False,
            observed=True,
        )
        .agg(觀測次數=("hour", "size"), 缺車率=("缺車", "mean"), 缺空位率=("缺空位", "mean"))
    )
    st.subheader("高風險場站排行")
    risk_type = st.radio("排行方式", ["缺車率", "缺空位率"], horizontal=True)
    station_display = station.sort_values(risk_type, ascending=False).head(20).copy()
    station_display["缺車率"] = station_display["缺車率"] * 100
    station_display["缺空位率"] = station_display["缺空位率"] * 100
    st.dataframe(
        station_display,
        width="stretch",
        hide_index=True,
        column_config={"缺車率": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                       "缺空位率": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)},
    )


def page_weather(df: pd.DataFrame) -> None:
    st.title("🌧 天氣與雨量")
    weather_df = df.dropna(subset=["每小時雨量_mm"]).copy()
    rainy = weather_df["每小時雨量_mm"].gt(0)
    cols = st.columns(4)
    cols[0].metric("有雨觀測比例", percent(rainy.mean()))
    cols[1].metric("無雨平均可借率", percent(weather_df.loc[~rainy, "可借率"].mean()))
    cols[2].metric("有雨平均可借率", percent(weather_df.loc[rainy, "可借率"].mean()))
    cols[3].metric("最大逐時雨量", f"{weather_df['每小時雨量_mm'].max():.1f} mm")

    comparison = (
        weather_df.groupby("雨量狀態", as_index=False, observed=True)
        .agg(觀測筆數=("場站代號", "size"), 平均可借率=("可借率", "mean"),
             缺車率=("缺車", "mean"), 缺空位率=("缺空位", "mean"))
    )
    order = ["無雨", "微雨", "小雨", "中大雨"]
    comparison["雨量狀態"] = pd.Categorical(comparison["雨量狀態"], order, ordered=True)
    comparison = comparison.sort_values("雨量狀態")
    long = comparison.melt(
        id_vars="雨量狀態", value_vars=["平均可借率", "缺車率", "缺空位率"],
        var_name="指標", value_name="比例",
    )
    fig = px.bar(long, x="雨量狀態", y="比例", color="指標", barmode="group", text_auto=".1%",
                 title="不同雨量狀態下的供需指標")
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, width="stretch")

    by_hour = (
        weather_df.assign(是否下雨=rainy.map({True: "有雨", False: "無雨"}))
        .groupby(["小時", "是否下雨"], as_index=False, observed=True)["可借率"].mean()
    )
    fig = px.line(by_hour, x="小時", y="可借率", color="是否下雨", markers=True,
                  title="有雨／無雨時的逐時平均可借率")
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, width="stretch")
    st.caption("這裡顯示關聯而非因果；通勤日、節假日及調度也可能同時影響結果。")


def page_station(df: pd.DataFrame) -> None:
    st.title("📍 站點與區域")
    district = st.selectbox("選擇行政區", sorted(df["場站所屬行政區"].unique()))
    district_df = df[df["場站所屬行政區"] == district]
    stations = district_df[["場站代號", "場站中文名稱"]].drop_duplicates().sort_values("場站中文名稱")
    station_name = st.selectbox("選擇場站", stations["場站中文名稱"].tolist())
    station_df = district_df[district_df["場站中文名稱"] == station_name].sort_values("抓取時間")

    latest = station_df.iloc[-1]
    cols = st.columns(4)
    cols[0].metric("目前可借", f"{latest['目前可借車輛數']:.0f} 輛")
    cols[1].metric("目前空位", f"{latest['目前可還空位數']:.0f} 格")
    cols[2].metric("缺車率", percent(station_df["缺車"].mean()))
    cols[3].metric("缺空位率", percent(station_df["缺空位"].mean()))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=station_df["抓取時間"], y=station_df["目前可借車輛數"], name="可借車輛"))
    fig.add_trace(go.Scatter(x=station_df["抓取時間"], y=station_df["目前可還空位數"], name="可還空位"))
    fig.update_layout(title=f"{station_name} 逐時供需變化", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")

    hour_profile = station_df.groupby("小時", as_index=False, observed=True).agg(
        平均可借車輛=("目前可借車輛數", "mean"), 平均可還空位=("目前可還空位數", "mean")
    )
    fig = px.line(hour_profile, x="小時", y=["平均可借車輛", "平均可還空位"], markers=True,
                  title="一天中的平均變化")
    st.plotly_chart(fig, width="stretch")

    st.subheader(f"{district}最新場站地圖")
    latest_time = district_df["抓取時間"].max()
    map_df = district_df[district_df["抓取時間"] == latest_time].copy()
    map_df["狀態顏色"] = map_df["供需狀態"].map(STATUS_COLORS)
    fig = px.scatter_map(
        map_df, lat="緯度", lon="經度", color="供需狀態", size="場站總停車格數",
        hover_name="場站中文名稱", hover_data=["目前可借車輛數", "目前可還空位數", "中文地址"],
        color_discrete_map=STATUS_COLORS, zoom=11, height=600,
    )
    fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, width="stretch")


def page_raw(df: pd.DataFrame) -> None:
    st.title("🔎 原始資料查詢")
    st.write("依目前側邊欄條件顯示資料；為避免瀏覽器卡頓，畫面最多顯示 5,000 筆。")
    keyword = st.text_input("搜尋場站名稱或地址")
    view = df
    if keyword:
        mask = (
            view["場站中文名稱"].str.contains(keyword, case=False, na=False)
            | view["中文地址"].str.contains(keyword, case=False, na=False)
        )
        view = view[mask]
    status_options = ["供需正常", "缺車風險", "缺空位風險", "暫停營運"]
    status = st.multiselect("供需狀態", status_options, default=status_options)
    view = view[view["供需狀態"].isin(status)]
    show_cols = [
        "抓取時間", "場站中文名稱", "場站所屬行政區", "目前可借車輛數", "目前可還空位數",
        "一般車可借數", "電輔車可借數", "供需狀態", "每小時雨量_mm", "最近雨量站",
    ]
    st.metric("篩選結果", f"{len(view):,} 筆")
    st.dataframe(view[show_cols].head(5000), width="stretch", hide_index=True)
    export_view = view[show_cols].head(100_000)
    csv = export_view.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "下載篩選結果 CSV（最多 10 萬筆）", csv, "ubike_filtered.csv", "text/csv"
    )


df = load_data()
st.sidebar.title("🚲 專案導覽")
page = st.sidebar.radio(
    "選擇頁面",
    ["🏠 首頁", "📊 YouBike 整體", "🌧 天氣與雨量", "📍 站點與區域", "🔎 原始資料查詢"],
)
st.sidebar.divider()
all_districts = sorted(df["場站所屬行政區"].unique())
selected_districts = st.sidebar.multiselect("全站行政區篩選", all_districts, default=all_districts)
min_date, max_date = df["抓取時間"].dt.date.min(), df["抓取時間"].dt.date.max()
date_range = st.sidebar.date_input("資料日期", value=(min_date, max_date), min_value=min_date, max_value=max_date)
if len(date_range) == 2 and selected_districts:
    filtered = filter_data(df, tuple(selected_districts), date_range[0], date_range[1])
else:
    filtered = df.iloc[0:0].copy()

if filtered.empty:
    st.warning("目前篩選條件沒有資料，請重新選擇行政區或日期。")
    st.stop()

if page == "🏠 首頁":
    page_home(filtered)
elif page == "📊 YouBike 整體":
    page_overview(filtered)
elif page == "🌧 天氣與雨量":
    page_weather(filtered)
elif page == "📍 站點與區域":
    page_station(filtered)
else:
    page_raw(filtered)
