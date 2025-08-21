# -*- coding: utf-8 -*-
import datetime as dt
import math
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="FXシミュレーション", layout="wide")

LOT_UNITS = 100_000                 # 1枚=10万通貨
FEE_PER_LOT_PER_SIDE = 1_100.0      # 手数料（1枚あたり／片側／税込）：建て時と決済時に発生

# ------------------ ヘルパ ------------------
def safe_floor(x: float) -> int:
    try:
        if math.isnan(x) or math.isinf(x):
            return 0
        return int(math.floor(x))
    except Exception:
        return 0

def build_prices_linear(days: int, s0: float, s1: float) -> np.ndarray:
    days = max(1, int(days))
    return np.linspace(s0, s1, days + 1)

def compute_series(
    prices: np.ndarray,
    initial_deposit: float,
    lots: int,
    direction_sign: int,
    swap_per_lot_per_day_input: float,
) -> tuple[pd.DataFrame, dict]:
    """
    ・手数料は建て時と決済時のみ（各 1,100 円/枚）
    ・スワップは「買い:+/ 売り:-」で毎日加算
    ・KPIと口座状況は手数料込み
    """
    n = len(prices)
    units = lots * LOT_UNITS
    diff = np.diff(prices, prepend=prices[0])

    # 売りはスワップをマイナスに（買い:+1, 売り:-1）
    swap_per_lot_effective = (1 if direction_sign == 1 else -1) * abs(swap_per_lot_per_day_input)
    swap = np.full(n, swap_per_lot_effective * lots, dtype=float)

    pnl_fx = direction_sign * diff * units

    fee = np.zeros(n)
    if n >= 1 and lots > 0:
        fee[0]  -= FEE_PER_LOT_PER_SIDE * lots   # 建て時
    if n >= 2 and lots > 0:
        fee[-1] -= FEE_PER_LOT_PER_SIDE * lots   # 決済時

    pnl_total = pnl_fx + swap + fee
    equity = initial_deposit + np.cumsum(pnl_total)

    df = pd.DataFrame({
        "pnl_fx": pnl_fx,
        "swap": swap,
        "fee": fee,
        "pnl_total": pnl_total,
        "equity": equity,
    })

    summary = {
        "期末口座状況": float(equity[-1]),
        "総損益(手数料込み)": float(equity[-1] - initial_deposit),
        "スワップ累計": float(swap.sum()),
        "手数料合計": float(fee.sum()),  # 負値（支払い）
    }
    return df, summary

def auto_calc_lots(eff_lev: float, deposit: float, s0: float, per_lot_margin: float) -> int:
    """
    枚数 = min( レバ基準, 証拠金基準 ) を切り下げ、最低1枚
    - レバ基準 lots_lev = floor( (eff_lev * deposit) / (s0 * 100,000) )
    - 証拠金基準 lots_margin = floor( deposit / per_lot_margin )
    """
    if s0 <= 0:
        return 1
    lots_lev = safe_floor((eff_lev * deposit) / (s0 * LOT_UNITS))
    lots_margin = safe_floor(deposit / max(1.0, per_lot_margin))
    lots = max(1, min(lots_lev, lots_margin))
    return lots

# ------------------ 入力（指定の順に並べ替え） ------------------
with st.sidebar:
    st.header("入力")

    # 1) 初回入金
    deposit = st.number_input("初回入金額（円）", value=10_000_000, step=100_000, format="%d", min_value=0)

    # 2) 必要証拠金（1枚）
    per_lot_margin = st.number_input("必要証拠金（1枚あたり／円）", value=40_000, step=1_000, format="%d", min_value=0)
    st.caption(f"必要証拠金の目安（合計）：{per_lot_margin * max(1, 1):,} 円（枚数は下で自動計算）")

    # 3) 実効レバレッジ
    eff_lev = st.number_input("実効レバレッジ", value=3.0, step=0.1, min_value=0.1)

    # 7) 初期レート（0.1円刻み）— 枚数計算で使うためここで受ける
    s0 = st.number_input("初期レート（MXN/JPY）", value=7.8, step=0.1, format="%.1f")

    # 4) 枚数（自動計算・表示のみ）
    lots_auto = auto_calc_lots(eff_lev, deposit, s0, per_lot_margin)
    st.metric("枚数（自動計算）", f"{lots_auto} 枚")

    # 5) 売買方向
    direction = st.radio("売買方向", ["買い", "売り"], horizontal=True)
    dir_sign = 1 if direction == "買い" else -1

    # 6) スワップ
    swap_per_lot_per_day = st.number_input("スワップ（円／枚／日）", value=150, step=10, format="%d")

    # 8) 期末レート（0.1円刻み）
    s1 = st.number_input("期末レート（MXN/JPY）", value=8.2, step=0.1, format="%.1f")

    # 9) 運用期間
    days = st.slider("運用期間（日）", min_value=30, max_value=730, value=365, step=5)

# ------------------ 本体 ------------------
st.title("FXシミュレーション")

# 価格系列（直線）
prices = build_prices_linear(days, s0, s1)

# 計算（手数料込みのみ）
df, sm = compute_series(
    prices=prices,
    initial_deposit=deposit,
    lots=lots_auto,
    direction_sign=dir_sign,
    swap_per_lot_per_day_input=swap_per_lot_per_day,
)

# KPI（3つ）
k1, k2, k3 = st.columns(3)
k1.metric("期末口座状況", f"{sm['期末口座状況']:,.0f} 円")
k2.metric("総損益（手数料込み）", f"{sm['総損益(手数料込み)']:,.0f} 円")
k3.metric("スワップ累計", f"{sm['スワップ累計']:,.0f} 円")

# 注記のみ（グラフは一切表示しない）
st.caption("手数料：1100円（消費税込み）売買成立時に発生")
