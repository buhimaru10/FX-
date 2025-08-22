# -*- coding: utf-8 -*-
import math
import numpy as np
import pandas as pd
import streamlit as st

# ===== ページ設定（余白をコンパクトに） =====
st.set_page_config(page_title="FXシミュレーション", layout="wide")
st.markdown("""
<style>
.block-container { padding-top: 1rem; padding-bottom: 1rem; }
#MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ===== 定数 =====
LOT_UNITS = 100_000            # 1枚=10万通貨
FEE_PER_LOT_PER_SIDE = 1_100.0 # 手数料（片側/枚/税込）：建て・決済の2回のみ控除

# ===== ユーティリティ =====
def safe_floor(x: float) -> int:
    try:
        if math.isnan(x) or math.isinf(x): return 0
        return int(math.floor(x))
    except Exception:
        return 0

def build_prices_linear(days: int, s0: float, s1: float) -> np.ndarray:
    """ 初期～期末を直線で補間（表示はしない／損益計算にのみ使用） """
    days = max(1, int(days))
    return np.linspace(s0, s1, days + 1)  # 長さ n=days+1（初日を含む）

def lots_by_margin(deposit: float, per_lot_margin: float) -> int:
    """ 証拠金基準の上限枚数（切り下げ、最低1） """
    return max(1, safe_floor(deposit / max(1.0, per_lot_margin)))

def lots_by_target_leverage(leff_target: float, deposit: float, s0: float) -> int:
    """ 目標実効レバからの枚数（切り下げ、最低1） """
    if s0 <= 0: return 1
    return max(1, safe_floor((leff_target * deposit) / (s0 * LOT_UNITS)))

# ===== 損益計算：手数料込み・売りはスワップをマイナス・初日はスワップ0 =====
def compute_series(prices: np.ndarray,
                   initial_deposit: float,
                   lots: int,
                   direction_sign: int,              # 買い:+1 / 売り:-1
                   swap_per_lot_per_day_input: float # 入力は受取額（正の値）
                   ):
    n = len(prices)                      # = days + 1
    units = lots * LOT_UNITS
    diff = np.diff(prices, prepend=prices[0])  # 初日は0、その後は日次変化

    # --- スワップ：買い=＋、売り=−／初日は0、翌日以降に計上 ---
    swap_per_lot_effective = (1 if direction_sign == 1 else -1) * abs(swap_per_lot_per_day_input)
    daily_swap = swap_per_lot_effective * lots
    swap = np.zeros(n, dtype=float)
    if n > 1:
        swap[1:] = daily_swap  # 初日0、2日目以降に同額

    # --- 為替損益（建玉方向で±） ---
    pnl_fx = direction_sign * diff * units

    # --- 手数料：建て時・決済時のみ控除（1,100円/枚/片側） ---
    fee = np.zeros(n)
    if n >= 1 and lots > 0:
        fee[0]  -= FEE_PER_LOT_PER_SIDE * lots
    if n >= 2 and lots > 0:
        fee[-1] -= FEE_PER_LOT_PER_SIDE * lots

    # --- 合成P/Lと口座状況 ---
    pnl_total = pnl_fx + swap + fee
    equity = initial_deposit + np.cumsum(pnl_total)

    # --- 集計（KPI用） ---
    fx_total   = float(pnl_fx.sum())
    swap_total = float(swap.sum())
    fee_total  = float(fee.sum())              # 負の値（手数料）
    end_equity = float(equity[-1])

    summary = {
        "期末口座状況": end_equity,
        "為替差損益(手数料込)": fx_total + fee_total,         # 為替P/L＋手数料（スワップ除く）
        "スワップポイント利益": swap_total,                     # 買い:+／売り:−、合計 = (日/枚)×枚数×日数 に一致
        "総損益(手数料込み)": end_equity - initial_deposit,     # 参考（画面表示はしない）
        "手数料合計": fee_total
    }
    return summary

# ===== サイドバー（指定の順に配置） =====
with st.sidebar:
    st.header("入力")

    # 1) 初回入金
    deposit = st.number_input("初回入金額（円）", value=10_000_000, step=100_000, format="%d", min_value=0)

    # 2) 必要証拠金（1枚）
    per_lot_margin = st.number_input("必要証拠金（1枚あたり／円）", value=40_000, step=1_000, format="%d", min_value=0)

    # 3) 実効レバレッジ（指定可）
    leff_target = st.number_input("実効レバレッジ（指定可）", value=3.0, step=0.1, min_value=0.1)

    # 4) 枚数の設定（自動/レバから自動/手動）
    lots_mode = st.radio("枚数の設定", ["自動計算（証拠金）", "実効レバから自動", "手動入力"], horizontal=False)

    # 5) 売買方向
    direction = st.radio("売買方向", ["買い", "売り"], horizontal=True)
    dir_sign = 1 if direction == "買い" else -1

    # 6) スワップ（受取額/日/枚：正の値で入力）
    swap_per_lot_per_day = st.number_input("スワップ（円／枚／日）", value=150, step=10, format="%d", min_value=0)

    # 7) 初期レート（0.1円刻み） ← 期末レートの直前へ移動済み
    s0 = st.number_input("初期レート（MXN/JPY）", value=7.8, step=0.1, format="%.1f")

    # 8) 期末レート（0.1円刻み）
    s1 = st.number_input("期末レート（MXN/JPY）", value=8.2, step=0.1, format="%.1f")

    # 9) 運用期間
    days = st.slider("運用期間（日）", min_value=30, max_value=730, value=365, step=5)

    # --- lots 決定（切り下げ＆証拠金上限を尊重） ---
    if lots_mode == "自動計算（証拠金）":
        lots = lots_by_margin(deposit, per_lot_margin)
        lots_note = f"証拠金上限で自動：{lots} 枚"
    elif lots_mode == "実効レバから自動":
        lots_lev = lots_by_target_leverage(leff_target, deposit, s0)
        lots_cap = lots_by_margin(deposit, per_lot_margin)
        lots = max(1, min(lots_lev, lots_cap))
        lots_note = f"目標 {leff_target:.2f} 倍→{lots_lev} 枚 / 証拠金上限 {lots_cap} 枚 → 採用 {lots} 枚"
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

# ===== 本体（KPIのみ・シンプル表示） =====
st.title("FXシミュレーション")

# 価格系列（直線。損益計算にのみ使用）
prices = build_prices_linear(days, s0, s1)

# 計算（手数料込み）
sm = compute_series(
    prices=prices,
    initial_deposit=deposit,
    lots=lots,
    direction_sign=dir_sign,
    swap_per_lot_per_day_input=swap_per_lot_per_day,
)

# 実効レバ（結果）& 必要証拠金合計
leff_actual = (lots * s0 * LOT_UNITS) / deposit if deposit > 0 and s0 > 0 else 0.0
need_margin_total = per_lot_margin * lots

# ===== KPI（ご指定の順） =====
k1, k2, k3 = st.columns(3)
k1.metric("期末口座状況", f"{sm['期末口座状況']:,.0f} 円")
k2.metric("為替差損益（手数料込）", f"{sm['為替差損益(手数料込)']:,.0f} 円")
k3.metric("スワップポイント利益", f"{sm['スワップポイント利益']:,.0f} 円")

# 補助情報（1行2列）
c1, c2 = st.columns(2)
c1.caption(f"実効レバレッジ（計算結果）：{leff_actual:.2f} 倍")
c2.caption(f"必要証拠金の目安（合計）：{need_margin_total:,} 円")

# 注記（常時）
st.caption("手数料：1100円（消費税込み）売買成立時に発生")
st.caption(lots_note)
