from __future__ import annotations

from pathlib import Path

import numpy as np
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

# 依行政院人事行政總處公布的 2026 年政府行政機關辦公日曆表。
# 週六、週日會另外由程式自動判定，這裡只列平日放假的日期。
NATIONAL_HOLIDAYS_2026 = {
    pd.Timestamp("2026-01-01").date(): "元旦",
    pd.Timestamp("2026-02-16").date(): "農曆春節",
    pd.Timestamp("2026-02-17").date(): "農曆春節",
    pd.Timestamp("2026-02-18").date(): "農曆春節",
    pd.Timestamp("2026-02-19").date(): "農曆春節",
    pd.Timestamp("2026-02-20").date(): "農曆春節",
    pd.Timestamp("2026-02-27").date(): "和平紀念日補假",
    pd.Timestamp("2026-04-03").date(): "兒童節補假",
    pd.Timestamp("2026-04-06").date(): "清明節補假",
    pd.Timestamp("2026-05-01").date(): "勞動節",
    pd.Timestamp("2026-06-19").date(): "端午節",
    pd.Timestamp("2026-09-25").date(): "中秋節",
    pd.Timestamp("2026-09-28").date(): "教師節",
    pd.Timestamp("2026-10-09").date(): "國慶日補假",
    pd.Timestamp("2026-10-26").date(): "臺灣光復暨金門古寧頭大捷紀念日補假",
    pd.Timestamp("2026-12-25").date(): "行憲紀念日",
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
    st.write(
        "這一頁比較下雨時的站點車輛，與該站在**相同小時、相同日型態（平日／週末）**"
        "沒有下雨時的平常水準。這樣不會把早晚尖峰本來就有的差異誤認為雨天影響。"
    )

    weather_df = df.dropna(subset=["每小時雨量_mm"]).copy()
    weather_df = weather_df[weather_df["場站營運狀態"].eq(1)].copy()
    weather_df["日型態"] = weather_df["抓取時間"].dt.dayofweek.lt(5).map(
        {True: "平日", False: "週末"}
    )

    dry = weather_df[weather_df["每小時雨量_mm"].le(0)]
    baseline = (
        dry.groupby(["場站代號", "小時", "日型態"], as_index=False, observed=True)
        .agg(
            平常可借車輛=("目前可借車輛數", "median"),
            平常可借率=("可借率", "median"),
            無雨樣本數=("場站代號", "size"),
        )
    )
    rainy_compare = weather_df[weather_df["每小時雨量_mm"].gt(0)].merge(
        baseline, on=["場站代號", "小時", "日型態"], how="left"
    )
    rainy_compare = rainy_compare[rainy_compare["無雨樣本數"].ge(3)].copy()

    if rainy_compare.empty:
        st.warning("目前篩選條件沒有足夠的雨天與無雨資料可以比較，請擴大日期或行政區範圍。")
        return

    rainy_compare["比平常多出的車輛"] = (
        rainy_compare["目前可借車輛數"] - rainy_compare["平常可借車輛"]
    )
    rainy_compare["可借率差"] = rainy_compare["可借率"] - rainy_compare["平常可借率"]

    extra_bikes = rainy_compare["比平常多出的車輛"].mean()
    availability_diff = rainy_compare["可借率差"].mean()
    more_bikes_share = rainy_compare["比平常多出的車輛"].gt(0).mean()

    cols = st.columns(4)
    cols[0].metric("可比較的雨天觀測", f"{len(rainy_compare):,} 筆")
    cols[1].metric("下雨時平均多出的車", f"{extra_bikes:+.2f} 輛／站")
    cols[2].metric("可借率相對平常", f"{availability_diff * 100:+.1f} 個百分點")
    cols[3].metric("車輛比平常多的比例", percent(more_bikes_share))

    if extra_bikes > 0:
        st.success(
            f"在目前篩選範圍內，下雨時每個站平均比平常同時段多 {extra_bikes:.2f} 輛車。"
            "這個結果符合『雨天可能較少人騎走 YouBike』的現象。"
        )
    elif extra_bikes < 0:
        st.info(
            f"在目前篩選範圍內，下雨時每個站平均比平常同時段少 {abs(extra_bikes):.2f} 輛車，"
            "沒有出現雨天車輛較容易留在站內的現象。"
        )
    else:
        st.info("下雨時的站點車輛數與平常同時段大致相同。")

    by_hour = (
        rainy_compare.groupby("小時", as_index=False, observed=True)
        .agg(比平常多出的車輛=("比平常多出的車輛", "mean"), 雨天觀測數=("場站代號", "size"))
    )
    fig = px.bar(
        by_hour,
        x="小時",
        y="比平常多出的車輛",
        color="比平常多出的車輛",
        color_continuous_scale=["#E76F51", "#F7FBFA", "#16A085"],
        color_continuous_midpoint=0,
        title="下雨時，各時段比平常多／少幾輛車",
        hover_data=["雨天觀測數"],
    )
    fig.add_hline(y=0, line_color="#555", line_dash="dash")
    fig.update_layout(coloraxis_colorbar_title="車輛差")
    st.plotly_chart(fig, width="stretch")
    st.caption("正數＝下雨時站內車輛比平常多；負數＝下雨時站內車輛比平常少。")

    district = (
        rainy_compare.groupby("場站所屬行政區", as_index=False, observed=True)
        .agg(
            平均車輛差=("比平常多出的車輛", "mean"),
            雨天觀測數=("場站代號", "size"),
            車輛較多比例=("比平常多出的車輛", lambda values: values.gt(0).mean()),
        )
    )
    district = district[district["雨天觀測數"].ge(30)].sort_values("平均車輛差")
    fig = px.bar(
        district,
        x="平均車輛差",
        y="場站所屬行政區",
        orientation="h",
        color="平均車輛差",
        color_continuous_scale=["#E76F51", "#F7FBFA", "#16A085"],
        color_continuous_midpoint=0,
        title="各行政區：下雨時比平常多／少幾輛車",
        hover_data={"雨天觀測數": True, "車輛較多比例": ":.1%"},
    )
    st.plotly_chart(fig, width="stretch")

    rain_level = (
        rainy_compare.groupby("雨量狀態", as_index=False, observed=True)
        .agg(
            平均車輛差=("比平常多出的車輛", "mean"),
            平均可借率差=("可借率差", "mean"),
            觀測筆數=("場站代號", "size"),
        )
    )
    order = ["微雨", "小雨", "中大雨"]
    rain_level["雨量狀態"] = pd.Categorical(rain_level["雨量狀態"], order, ordered=True)
    rain_level = rain_level.sort_values("雨量狀態")
    st.subheader("不同雨量強度的比較")
    st.dataframe(
        rain_level,
        width="stretch",
        hide_index=True,
        column_config={
            "平均車輛差": st.column_config.NumberColumn(format="%+.2f 輛"),
            "平均可借率差": st.column_config.NumberColumn(format="%+.2f"),
            "觀測筆數": st.column_config.NumberColumn(format="%d 筆"),
        },
    )

    st.warning(
        "重要限制：資料是每小時快照，沒有每一筆租借與歸還紀錄。車輛比平常多可以支持"
        "『可能較少人借車』的推測，但也可能受到還車、調度、停駛與其他因素影響，不能直接當成租借量。"
    )


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


def page_day_type(df: pd.DataFrame) -> None:
    st.title("🚲 通勤型與休閒型分析")
    st.write(
        "比較**平日（通勤型）**與**假日（休閒型）**各時段的車輛流動。"
        "假日包含週六、週日及 2026 年政府行政機關辦公日曆表所列國定假日與補假。"
    )

    flow = df.sort_values(["場站代號", "抓取時間"]).copy()
    grouped = flow.groupby("場站代號", observed=True)
    flow["前次時間"] = grouped["抓取時間"].shift()
    flow["前次車輛"] = grouped["目前可借車輛數"].shift()
    flow["間隔分鐘"] = (flow["抓取時間"] - flow["前次時間"]).dt.total_seconds() / 60
    flow["車輛淨變動"] = flow["目前可借車輛數"] - flow["前次車輛"]
    flow["推估流動量"] = flow["車輛淨變動"].abs()
    flow["日期"] = flow["抓取時間"].dt.date
    flow["國定假日名稱"] = flow["日期"].map(NATIONAL_HOLIDAYS_2026)
    flow["是否國定假日"] = flow["國定假日名稱"].notna()
    flow["是否週末"] = flow["抓取時間"].dt.dayofweek.ge(5)
    flow["日型態"] = np.where(
        flow["是否週末"] | flow["是否國定假日"],
        "假日（休閒型）",
        "平日（通勤型）",
    )

    # 只比較約一小時的連續快照，避免把漏抓數小時後的差異算成單一時段流動。
    flow = flow[
        flow["場站營運狀態"].eq(1)
        & flow["間隔分鐘"].between(30, 90)
        & flow["推估流動量"].notna()
    ].copy()
    if flow.empty or flow["日型態"].nunique() < 2:
        st.warning("目前篩選範圍不足以同時比較平日與假日，請擴大日期範圍。")
        return

    day_summary = (
        flow.groupby(["日期", "日型態"], as_index=False, observed=True)
        .agg(每日推估流動量=("推估流動量", "sum"), 有效站時數=("推估流動量", "size"))
    )
    summary = (
        flow.groupby("日型態", as_index=False, observed=True)
        .agg(
            每站每小時平均流動=("推估流動量", "mean"),
            有效站時數=("推估流動量", "size"),
        )
        .merge(
            day_summary.groupby("日型態", as_index=False, observed=True).agg(
                平均每日流動=("每日推估流動量", "mean"),
                天數=("日期", "nunique"),
            ),
            on="日型態",
        )
        .set_index("日型態")
    )
    weekday_flow = summary.loc["平日（通勤型）", "每站每小時平均流動"]
    holiday_flow = summary.loc["假日（休閒型）", "每站每小時平均流動"]
    difference = holiday_flow / weekday_flow - 1 if weekday_flow else np.nan
    national_dates = flow.loc[flow["是否國定假日"], "日期"].nunique()

    cols = st.columns(5)
    cols[0].metric("平日天數", f"{summary.loc['平日（通勤型）', '天數']:.0f} 天")
    cols[1].metric("假日天數", f"{summary.loc['假日（休閒型）', '天數']:.0f} 天")
    cols[2].metric("其中國定假日", f"{national_dates} 天")
    cols[3].metric("平日每站每小時流動", f"{weekday_flow:.2f} 輛")
    cols[4].metric(
        "假日每站每小時流動",
        f"{holiday_flow:.2f} 輛",
        delta=f"較平日 {difference:+.1%}" if pd.notna(difference) else None,
    )

    if national_dates == 0:
        st.info(
            "目前所選日期沒有涵蓋國定假日，因此這次的假日結果來自週六、週日；"
            "未來資料涵蓋國定假日時，程式會自動把它歸入假日。"
        )

    hourly = (
        flow.groupby(["日型態", "小時"], as_index=False, observed=True)
        .agg(
            每站平均流動=("推估流動量", "mean"),
            平均淨變動=("車輛淨變動", "mean"),
            有效站時數=("推估流動量", "size"),
        )
    )
    fig = px.line(
        hourly,
        x="小時",
        y="每站平均流動",
        color="日型態",
        markers=True,
        hover_data={"有效站時數": True, "平均淨變動": ":+.2f"},
        color_discrete_map={"平日（通勤型）": "#2E7D32", "假日（休閒型）": "#F39C12"},
        title="平日與假日：各時段每站平均車輛流動",
    )
    fig.add_vrect(x0=7, x1=9, fillcolor="#2E7D32", opacity=0.08, line_width=0)
    fig.add_vrect(x0=17, x1=19, fillcolor="#2E7D32", opacity=0.08, line_width=0)
    fig.update_layout(hovermode="x unified", yaxis_title="推估流動量（輛／站時）")
    st.plotly_chart(fig, width="stretch")
    st.caption("綠色淡區為通勤尖峰 07–09 時與 17–19 時；線越高代表該時段站內車輛變動越大。")

    periods = pd.cut(
        flow["小時"],
        bins=[-1, 6, 9, 15, 19, 23],
        labels=["深夜清晨", "早通勤", "日間", "晚通勤", "夜間"],
    )
    period_flow = (
        flow.assign(時段=periods)
        .groupby(["時段", "日型態"], as_index=False, observed=True)
        .agg(每站平均流動=("推估流動量", "mean"))
    )
    fig = px.bar(
        period_flow,
        x="時段",
        y="每站平均流動",
        color="日型態",
        barmode="group",
        color_discrete_map={"平日（通勤型）": "#2E7D32", "假日（休閒型）": "#F39C12"},
        title="不同時段的平日／假日流動差異",
        text_auto=".2f",
    )
    st.plotly_chart(fig, width="stretch")

    station_type = (
        flow.groupby(
            ["場站代號", "場站中文名稱", "場站所屬行政區", "日型態"],
            as_index=False,
            observed=True,
        )
        .agg(每站平均流動=("推估流動量", "mean"), 樣本數=("推估流動量", "size"))
    )
    station_pivot = station_type.pivot(
        index=["場站代號", "場站中文名稱", "場站所屬行政區"],
        columns="日型態",
        values=["每站平均流動", "樣本數"],
    ).reset_index()
    station_pivot.columns = [
        "場站代號", "場站中文名稱", "場站所屬行政區",
        "假日平均流動", "平日平均流動", "假日樣本數", "平日樣本數",
    ]
    station_pivot = station_pivot.dropna().copy()
    station_pivot = station_pivot[
        station_pivot["假日樣本數"].ge(12) & station_pivot["平日樣本數"].ge(12)
    ]
    station_pivot["假日減平日"] = station_pivot["假日平均流動"] - station_pivot["平日平均流動"]
    threshold = 0.10
    station_pivot["站點型態"] = np.select(
        [
            station_pivot["平日平均流動"] > station_pivot["假日平均流動"] * (1 + threshold),
            station_pivot["假日平均流動"] > station_pivot["平日平均流動"] * (1 + threshold),
        ],
        ["通勤型", "休閒型"],
        default="混合型",
    )

    st.subheader("哪些站比較像通勤型或休閒型？")
    st.caption("平日或假日平均流動量高出另一類至少 10% 才分類；差距較小列為混合型。")
    type_counts = station_pivot["站點型態"].value_counts()
    type_cols = st.columns(3)
    for column, label in zip(type_cols, ["通勤型", "休閒型", "混合型"]):
        column.metric(label, f"{type_counts.get(label, 0):,} 站")

    left, right = st.columns(2)
    with left:
        commute = station_pivot.sort_values("假日減平日").head(15)
        fig = px.bar(
            commute,
            x="假日減平日",
            y="場站中文名稱",
            orientation="h",
            color_discrete_sequence=["#2E7D32"],
            title="平日流動較高：通勤特徵最明顯的站",
            hover_data=["場站所屬行政區", "平日平均流動", "假日平均流動"],
        )
        fig.update_layout(yaxis={"categoryorder": "total descending"})
        st.plotly_chart(fig, width="stretch")
    with right:
        leisure = station_pivot.sort_values("假日減平日", ascending=False).head(15)
        fig = px.bar(
            leisure,
            x="假日減平日",
            y="場站中文名稱",
            orientation="h",
            color_discrete_sequence=["#F39C12"],
            title="假日流動較高：休閒特徵最明顯的站",
            hover_data=["場站所屬行政區", "平日平均流動", "假日平均流動"],
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")

    st.warning(
        "判讀限制：這裡的『流動量』是相鄰約一小時快照中，可借車輛數變化的絕對值。"
        "同一小時內的借還可能互相抵消，站務調度也會造成變化，因此它適合比較型態，"
        "但不是官方精確租借筆數。"
    )

def page_nearby(df: pd.DataFrame) -> None:
    st.title("🧭 周邊替代站")
    st.write(
        "選擇一個 YouBike 站點後，尋找直線距離 **500 公尺內**、正在營運且仍有車可借的替代站。"
    )
    st.caption("此頁使用所選時間的場站快照；距離是依經緯度計算的直線距離，不是實際步行路線。")

    snapshot_times = sorted(df["抓取時間"].dropna().unique(), reverse=True)
    selected_time = st.selectbox(
        "選擇資料時間",
        snapshot_times,
        format_func=lambda value: pd.Timestamp(value).strftime("%Y-%m-%d %H:%M"),
    )
    snapshot = df[df["抓取時間"].eq(selected_time)].copy()
    snapshot = snapshot.drop_duplicates("場站代號", keep="last")
    snapshot["顯示站名"] = (
        snapshot["場站中文名稱"].astype(str).str.replace("YouBike2.0_", "", regex=False)
    )
    station_options = snapshot.sort_values(["場站所屬行政區", "顯示站名"])["顯示站名"].tolist()
    default_index = next(
        (index for index, name in enumerate(station_options) if "賴厝國小" in name),
        0,
    )
    selected_name = st.selectbox(
        "選擇要查詢的站點（可以直接輸入站名搜尋）",
        station_options,
        index=default_index,
    )
    reference = snapshot[snapshot["顯示站名"].eq(selected_name)].iloc[0]

    lat1 = np.radians(float(reference["緯度"]))
    lon1 = np.radians(float(reference["經度"]))
    lat2 = np.radians(snapshot["緯度"].astype(float))
    lon2 = np.radians(snapshot["經度"].astype(float))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    haversine_value = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    )
    snapshot["距離_公尺"] = 6_371_000 * 2 * np.arcsin(np.sqrt(haversine_value))

    nearby = snapshot[
        snapshot["場站代號"].ne(reference["場站代號"])
        & snapshot["距離_公尺"].gt(0)
        & snapshot["距離_公尺"].le(500)
    ].copy()
    nearby = nearby.sort_values("距離_公尺")

    alternatives = nearby[
        nearby["場站營運狀態"].eq(1)
        & nearby["目前可借車輛數"].gt(0)
    ].copy()
    alternatives = alternatives.sort_values(["距離_公尺", "目前可借車輛數"], ascending=[True, False])

    reference_available = int(reference["目前可借車輛數"])
    if reference["場站營運狀態"] != 1:
        st.error(f"{selected_name} 在這個時間點暫停營運。")
    elif reference_available == 0:
        st.error(f"{selected_name} 在這個時間點沒有車可借，請查看下方替代站。")
    else:
        st.success(f"{selected_name} 本站目前有 {reference_available} 輛車可借，附近替代站如下。")

    if alternatives.empty:
        st.warning("這個時間點在 500 公尺內找不到有車可借的其他站點。")
        nearest_name = "沒有符合站點"
        nearest_distance = "—"
        nearest_bikes = "—"
    else:
        nearest = alternatives.iloc[0]
        nearest_name = nearest["顯示站名"]
        nearest_distance = f"{nearest['距離_公尺']:.0f} 公尺"
        nearest_bikes = f"{int(nearest['目前可借車輛數'])} 輛"

    cols = st.columns(4)
    cols[0].metric("查詢站點可借車輛", f"{reference_available} 輛")
    cols[1].metric("最近可借替代站", nearest_name)
    cols[2].metric("距離", nearest_distance)
    cols[3].metric("替代站可借車輛", nearest_bikes)

    if not alternatives.empty:
        nearest = alternatives.iloc[0]
        st.info(
            f"距離 **{selected_name}** 最近且有車可借的是 **{nearest['顯示站名']}**，"
            f"直線距離約 **{nearest['距離_公尺']:.0f} 公尺**，"
            f"當時有 **{int(nearest['目前可借車輛數'])} 輛**可借。"
        )

    nearby["地圖標示"] = np.select(
        [
            nearby["場站營運狀態"].ne(1),
            nearby["目前可借車輛數"].le(0),
        ],
        ["暫停營運", "目前無車"],
        default="其他可借站",
    )
    if not alternatives.empty:
        nearest_station_id = alternatives.iloc[0]["場站代號"]
        nearby.loc[nearby["場站代號"].eq(nearest_station_id), "地圖標示"] = "最近替代站"

    reference_map = pd.DataFrame([reference]).copy()
    reference_map["距離_公尺"] = 0.0
    reference_map["地圖標示"] = "查詢站點"
    map_df = pd.concat([reference_map, nearby], ignore_index=True)
    map_df["地圖點大小"] = map_df["目前可借車輛數"].clip(lower=1) + 4
    fig = px.scatter_map(
        map_df,
        lat="緯度",
        lon="經度",
        color="地圖標示",
        size="地圖點大小",
        hover_name="顯示站名",
        hover_data={
            "目前可借車輛數": True,
            "目前可還空位數": True,
            "距離_公尺": ":.0f",
            "中文地址": True,
            "地圖點大小": False,
            "緯度": False,
            "經度": False,
        },
        color_discrete_map={
            "查詢站點": "#E76F51",
            "最近替代站": "#1976D2",
            "其他可借站": "#16A085",
            "目前無車": "#9E9E9E",
            "暫停營運": "#424242",
        },
        zoom=15,
        height=600,
    )
    fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, width="stretch")

    if not nearby.empty:
        st.subheader("500 公尺內所有鄰近站點")
        st.caption("灰色的站點不是漏掉，而是該時間點沒有車可借；系統會繼續尋找下一個可借站。")
        table = nearby[
            [
                "顯示站名", "地圖標示", "距離_公尺", "目前可借車輛數",
                "一般車可借數", "電輔車可借數", "中文地址",
            ]
        ].copy()
        table["距離_公尺"] = table["距離_公尺"].round().astype(int)
        table["判定說明"] = np.select(
            [
                table["地圖標示"].eq("最近替代站"),
                table["地圖標示"].eq("其他可借站"),
                table["地圖標示"].eq("目前無車"),
                table["地圖標示"].eq("暫停營運"),
            ],
            [
                "最近且有車，推薦前往",
                "有車，可作為替代站",
                "目前 0 輛，因此略過",
                "暫停營運，因此略過",
            ],
            default="",
        )
        table = table.drop(columns=["地圖標示"]).rename(columns={"顯示站名": "鄰近站點"})
        st.dataframe(
            table,
            width="stretch",
            hide_index=True,
            column_config={
                "距離_公尺": st.column_config.NumberColumn("距離", format="%d 公尺"),
                "目前可借車輛數": st.column_config.NumberColumn("可借車輛", format="%d 輛"),
                "一般車可借數": st.column_config.NumberColumn("一般車", format="%d 輛"),
                "電輔車可借數": st.column_config.NumberColumn("電輔車", format="%d 輛"),
            },
        )


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
    [
        "🏠 首頁", "📊 YouBike 整體", "🌧 天氣與雨量", "📍 站點與區域",
        "🚲 通勤型與休閒型", "🧭 周邊替代站", "🔎 原始資料查詢",
    ],
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
elif page == "🚲 通勤型與休閒型":
    page_day_type(filtered)
elif page == "🧭 周邊替代站":
    page_nearby(df)
else:
    page_raw(filtered)
