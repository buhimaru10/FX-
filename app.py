# -*- coding: utf-8 -*-
import datetime as dt
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="FXシミュレーション", layout="wide")

# ------------------ ヘルパ ------------------
def build_dates(start_date: dt.date, days: int) -> pd.DatetimeIndex:
    return pd.date_range(start=start_date, periods=days + 1, freq="D")

def build_prices_linear(days: int, s0: float, s1: float) -> np.ndarray:
    return np.linspace(s0, s1, days + 1)

def compute_series(
    dates: pd.DatetimeIndex,
    prices: np.ndarray,
    initial_deposit: float,
    lots: int,
    direction_sign: int,
    swap_per_lot_per_day: float,
    fee_per_lot_roundtrip: float,  # 1,100円（往復/枚）ではなく、片側/枚=1,100円を渡す
) -> tuple[pd.DataFrame, dict]:
    """
    手数料は「建て」と「決済」の2回のみ発生（1枚あたり 1,100円を各タイミングで控除）。
    総損益・口座状況は手数料込みで表示。
    """
    n = len(prices)
    units = lots * 100_000                       # 1枚=10万通貨
    diff = np.diff(prices, prepend=prices[0])

    pnl_fx = direction_sign * diff * units                   # 為替損益（毎日）
    swap = np.full(n, swap_per_lot_per_day * lots, float)    # スワップ（毎日）

    fee = np.zeros(n)                                        # 手数料（建て/決済のみ）
    if n >= 1:
        fee[0] -= fee_per_lot_roundtrip * lots               # 建て時
    if n >= 2:
        fee[-1] -= fee_per_lot_roundtrip * lots              # 決済時

    pnl_total = pnl_fx + swap + fee
    equity = initial_deposit + np.cumsum(pnl_total)

    df = pd.DataFrame({
        "date": dates,
        "price": prices,
        "pnl_fx": pnl_fx,
        "swap": swap,
        "fee": fee,
        "pnl_total": pnl_total,
        "口座状況": equity,
    })

    summary = {
        "期末口座状況": float(equity[-1]),
        "総損益(手数料込み)": float(equity[-1] - initial_deposit),
        "スワップ累計": float(swap.sum()),
        "手数料合計": float(fee.sum()),  # 負の値（支払い）
    }
    return df, summary


# ------------------ サイドバー（入力） ------------------
with st.sidebar:
    st.header("入力")
    initial_deposit = st.number_input("初回入金額（円）", value=10_000_000, step=100_000, format="%d")
    leverage_note = st.number_input("レバレッジ（参考）", value=25, min_value=1, max_value=100, step=1)
    lots = int(st.number_input("建玉枚数（1枚＝10万通貨）", value=33, min_value=1, max_value=5000, step=1))

    # 1枚あたりの必要証拠金（表示/管理用）
    per_lot_margin = st.number_input("必要証拠金（1枚あたり／円）", value=40_000, step=1_000, format="%d")
    st.caption(f"必要証拠金の目安（合計）：{per_lot_margin * max(lots,1):,} 円")

    direction = st.radio("売買方向", ["買い", "売り"], horizontal=True)
    direction_sign = 1 if direction == "買い" else -1

    swap_per_lot_per_day = st.number_input("スワップ（円／枚／日）", value=150, step=10, format="%d")
    days = st.slider("運用期間（日）", min_value=30, max_value=730, value=365, step=5)

    # 価格は 0.1 円刻み
    s0 = st.number_input("初期レート（MXN/JPY）", value=7.8, step=0.1, format="%.1f")
    s1 = st.number_input("期末レート（MXN/JPY）", value=8.2, step=0.1, format="%.1f")

    # 開始日：自動（本日）/ 手動
    start_mode = st.radio("開始日", ["自動（本日）", "手動"], horizontal=True)
    if start_mode == "手動":
        start_date = st.date_input("手動の開始日", value=dt.date.today())
    else:
        start_date = dt.date.today()
        st.caption(f"開始日：本日（{start_date.isoformat()}）")

# ------------------ メイン ------------------
st.title("FXシミュレーション")

# 日付 & 価格系列
dates = build_dates(start_date, days)
prices = build_prices_linear(days, s0, s1)

# 手数料：1枚あたり 1,100 円（税込）／建て時と決済時のみ
FEE_PER_LOT_PER_SIDE = 1_100.0

df, sm = compute_series(
    dates=dates,
    prices=prices,
    initial_deposit=initial_deposit,
    lots=lots,
    direction_sign=direction_sign,
    swap_per_lot_per_day=swap_per_lot_per_day,
    fee_per_lot_roundtrip=FEE_PER_LOT_PER_SIDE,  # 片側/枚
)

# KPI（手数料込みのみ）
c1, c2, c3 = st.columns(3)
c1.metric("期末口座状況", f"{sm['期末口座状況']:,.0f} 円")
c2.metric("総損益（手数料込み）", f"{sm['総損益(手数料込み)']:,.0f} 円")
c3.metric("スワップ累計", f"{sm['スワップ累計']:,.0f} 円")

# グラフ（価格・口座状況）
g1, g2 = st.columns(2)
with g1:
    st.subheader("価格推移（日足）")
    st.line_chart(df.set_index("date")[["price"]])
with g2:
    st.subheader("口座状況の推移（円）")
    st.line_chart(df.set_index("date")[["口座状況"]])

# 注記（常時表示）
st.caption("手数料：1100円（消費税込み）売買成立時に発生")
