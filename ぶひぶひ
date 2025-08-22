# -*- coding: utf-8 -*-
import math
import numpy as np
import pandas as pd
import streamlit as st

# ===== ページ設定：余白をコンパクトに =====
st.set_page_config(page_title="FXシミュレーション", layout="wide")
st.markdown("""
<style>
.block-container { padding-top: 1rem; padding-bottom: 1rem; }
#MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ===== 定数 =====
LOT_UNITS = 100_000
FEE_PER_LOT_PER_SIDE = 1_100.0

# ===== ユーティリティ =====
def safe_floor(x: float) -> int:
    try:
        if math.isnan(x) or math.isinf(x): return 0
        return int(math.floor(x))
    except Exception:
        return 0

def build_prices_linear(days: int, s0: float, s1: float) -> np.ndarray:
    days = max(1, int(days))
    return np.linspace(s0, s1, days + 1)

def lots_by_margin(deposit: float, per_lot_margin: float) -> int:
    return max(1, safe_floor(deposit / max(1.0, per_lot_margin)))

def lots_by_target_leverage(leff_target: float, deposit: float, s0: float) -> int:
    if s0 <= 0: return 1
    return max(1, safe_floor((leff_target * deposit) / (s0 * LOT_UNITS)))

# ===== 損益計算 =====
def compute_series(prices: np.ndarray,
                   initial_deposit: float,
                   lots: int,
                   direction_sign: int,
                   swap_per_lot_per_day_input: float):
    n = len(prices)
    units = lots * LOT_UNITS
    diff = np.diff(prices, prepend=prices[0])

    swap_per_lot_effective = (1 if direction_sign == 1 else -1) * abs(swap_per_lot_per_day_input)
    swap = np.full(n, swap_per_lot_effective * lots, dtype=float)

    pnl_fx = direction_sign * diff * units

    fee = np.zeros(n)
    if n >= 1 and lots > 0:
        fee[0]  -= FEE_PER_LOT_PER_SIDE * lots
    if n >= 2 and lots > 0:
        fee[-1] -= FEE_PER_LOT_PER_SIDE * lots

    pnl_total = pnl_fx + swap + fee
    equity = initial_deposit + np.cumsum(pnl_total)

    summary = {
        "期末口座状況": float(equity[-1]),
        "総損益(手数料込み)": float(equity[-1] - initial_deposit),
        "スワップポイント損益": float(swap.sum()),
        "手数料合計": float(fee.sum()),
    }
    return summary

# ===== サイドバー =====
with st.sidebar:
    st.header("入力")

    deposit = st.number_input("初回入金額（円）", value=10_000_000, step=100_000, format="%d", min_value=0)
    per_lot_margin = st.number_input("必要証拠金（1枚あたり／円）", value=40_000, step=1_000, format="%d", min_value=0)
    leff_target = st.number_input("実効レバレッジ（指定可）", value=3.0, step=0.1, min_value=0.1)

    lots_mode = st.radio("枚数の設定", ["自動計算（証拠金）", "実効レバから自動", "手動入力"], horizontal=False)

    # --- 売買方向・スワップ
    direction = st.radio("売買方向", ["買い", "売り"], horizontal=True)
    dir_sign = 1 if direction == "買い" else -1
    swap_per_lot_per_day = st.number_input("スワップ（円／枚／日）", value=150, step=10, format="%d", min_value=0)

    # --- 初期レート・期末レートを並べて配置（0.1円刻み）
    s0 = st.number_input("初期レート（MXN/JPY）", value=7.8, step=0.1, format="%.1f")
    s1 = st.number_input("期末レート（MXN/JPY）", value=8.2, step=0.1, format="%.1f")

    # --- 運用期間
    days = st.slider("運用期間（日）", min_value=30, max_value=730, value=365, step=5)

    # --- lots計算
    if lots_mode == "自動計算（証拠金）":
        lots = lots_by_margin(deposit, per_lot_margin)
        lots_note = f"証拠金上限で自動：{lots} 枚"
    elif lots_mode == "実効レバから自動":
        lots_lev = lots_by_target_leverage(leff_target, deposit, s0)
        lots_cap = lots_by_margin(deposit, per_lot_margin)
        lots = max(1, min(lots_lev, lots_cap))
        lots_note = f"目標 {leff_target:.2f} 倍→{lots_lev} 枚 / 上限 {lots_cap} 枚 → {lots} 枚"
    else:
        lots_cap = lots_by_margin(deposit, per_lot_margin)
        lots_manual = st.number_input("枚数（手動・整数）", value=min(33, lots_cap if lots_cap>0 else 1),
                                      min_value=1, step=1)
        if lots_manual > lots_cap:
            st.warning(f"証拠金不足のため {lots_cap} 枚までに調整しました。")
            lots = lots_cap
        else:
            lots = int(lots_manual)
        lots_note = f"手動指定：{lots} 枚（上限 {lots_cap} 枚）"

# ===== 本体 =====
st.title("FXシミュレーション")

prices = build_prices_linear(days, s0, s1)
sm = compute_series(prices, deposit, lots, dir_sign, swap_per_lot_per_day)

leff_actual = (lots * s0 * LOT_UNITS) / deposit if deposit > 0 and s0 > 0 else 0.0
need_margin_total = per_lot_margin * lots

# KPI
c1, c2, c3 = st.columns(3)
c1.metric("期末口座状況", f"{sm['期末口座状況']:,.0f} 円")
c2.metric("総損益（手数料込み）", f"{sm['総損益(手数料込み)']:,.0f} 円")
c3.metric("スワップポイント損益", f"{sm['スワップポイント損益']:,.0f} 円")

# 補助情報
c1, c2 = st.columns(2)
c1.caption(f"実効レバレッジ（計算結果）：{leff_actual:.2f} 倍")
c2.caption(f"必要証拠金の目安（合計）：{need_margin_total:,} 円")

# 注記
st.caption("手数料：1100円（消費税込み）売買成立時に発生")
st.caption(lots_note)
