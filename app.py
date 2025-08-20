# -*- coding: utf-8 -*-
import math, numpy as np, pandas as pd, streamlit as st
st.set_page_config(page_title="FXシミュレーション（NISA風）", layout="wide")

def round_0005(x: float) -> float:
    third = math.floor(x*1000)/1000.0
    fourth = int(x*10000) % 10
    return third if fourth <= 4 else third + 0.0005

def build_prices(mode, days, s0, s1=None, manual=None):
    if mode == "手入力（日足レート配列）":
        arr = [float(v) for v in manual.replace("\n", ",").split(",") if v.strip()!=""]
        return np.array(arr, dtype=float)
    return np.linspace(s0, s1, days+1)

def compute(prices, deposit, lots, sign, swap_per_lot_per_day, lev):
    units = lots * 100_000
    diff = np.diff(prices, prepend=prices[0])
    pnl_fx = sign * diff * units
    swap = np.full_like(prices, swap_per_lot_per_day * lots, dtype=float)
    pnl_total = pnl_fx + swap
    equity = deposit + np.cumsum(pnl_total)
    req_margin = (prices * units) / lev
    ml = equity / req_margin * 100.0
    mc = ml < 100.0
    df = pd.DataFrame({
        "day": np.arange(len(prices)), "price": prices, "pnl_fx": pnl_fx,
        "swap": swap, "pnl_total": pnl_total, "口座状況": equity,
        "required_margin": req_margin, "margin_level_pct": ml, "margin_call": mc
    })
    s = {
        "総損益": float(pnl_total.sum()),
        "うちスワップ": float(swap.sum()),
        "うち為替損益": float(pnl_fx.sum()),
        "ROI": float(pnl_total.sum()/deposit),
        "最大ドローダウン": float((equity/np.maximum.accumulate(equity)-1.0).min()),
        "初回MC発生日": int(df.loc[df["margin_call"]].head(1)["day"].values[0]) if df["margin_call"].any() else None
    }
    return df, s

def to_csv(df): return df.to_csv(index=False).encode("utf-8-sig")

with st.sidebar:
    st.header("入力")
    pair = st.selectbox("通貨ペア", ["MXN/JPY"])
    deposit = st.number_input("初回入金額 (円)", value=10_000_000, step=100_000, format="%d")
    lev = st.number_input("最大レバレッジ", value=25, min_value=1, max_value=100, step=1)
    lots_mode = st.radio("枚数の決め方", ["直接指定", "実効レバから自動"], horizontal=True)

    c = st.columns(2)
    with c[0]:
        init_raw = st.number_input("初期レート (MXN/JPY)", value=7.8476, step=0.0001, format="%.4f")
    with c[1]:
        s0 = round_0005(init_raw)
        st.caption("丸め規則（小数第4位→0/5）")
        st.metric("使用する初期レート", f"{s0:.4f}")

    days = st.slider("運用期間（日）", 30, 730, 365, step=5)
    direction = st.radio("売買方向", ["買い", "売り"], horizontal=True)
    sign = 1 if direction=="買い" else -1
    swap = st.number_input("スワップ (円/枚/日)", value=150, step=10, format="%d")

    price_mode = st.radio("レートの作り方", ["期末レートで線形補間", "手入力（日足レート配列）"])
    if price_mode == "期末レートで線形補間":
        s1 = st.number_input("期末レート (MXN/JPY)", value=8.2000, step=0.0005, format="%.4f")
        manual = None
    else:
        manual = st.text_area("レート配列（カンマ/改行）", height=140)
        s1 = None

    if lots_mode=="直接指定":
        lots = st.number_input("建玉枚数（1枚=10万通貨）", value=33, min_value=1, max_value=2000, step=1)
    else:
        target_lev = st.number_input("目標レバレッジ", value=3.0, step=0.1)
        lots = int(round((deposit * target_lev) / (s0 * 100_000)))
        st.metric("自動計算の建玉枚数", f"{lots} 枚")
    lots = int(lots)

st.title("FXシミュレーション（NISA風UI）")
prices = build_prices(price_mode, days, s0, s1, manual)
if len(prices) < 2: st.stop()
df, sm = compute(prices, deposit, lots, sign, swap, lev)

c1,c2,c3,c4 = st.columns(4)
c1.metric("期末口座状況", f"{df['口座状況'].iloc[-1]:,.0f} 円")
c2.metric("総損益", f"{sm['総損益']:,.0f} 円")
c3.metric("スワップ累計", f"{sm['うちスワップ']:,.0f} 円")
c4.metric("最大ドローダウン", f"{sm['最大ドローダウン']*100:.1f} %")

t1,t2,t3 = st.tabs(["価格推移","口座状況/維持率","データ＆DL"])
with t1:
    st.subheader("価格（日足）")
    st.line_chart(df.set_index("day")[["price"]])
with t2:
    col = st.columns(2)
    with col[0]:
        st.subheader("口座状況（円）")
        st.line_chart(df.set_index("day")[["口座状況"]])
    with col[1]:
        st.subheader("証拠金維持率（%）")
        st.line_chart(df.set_index("day")[["margin_level_pct"]])
    st.info("維持率100%割れあり：日目 {}".format(sm["初回MC発生日"]) if sm["初回MC発生日"] is not None else "維持率100%割れは発生していません。")
with t3:
    st.dataframe(df.head(100), use_container_width=True)
    st.download_button("CSV（全データ）", data=to_csv(df), file_name="fx_timeseries.csv", mime="text/csv")
    st.download_button("CSV（サマリー）", data=to_csv(pd.DataFrame([sm])), file_name="fx_summary.csv", mime="text/csv")
st.caption("※ シミュレーション用途です。実取引の助言ではありません。")
