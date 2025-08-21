# -*- coding: utf-8 -*-
import math
import numpy as np
import pandas as pd
import streamlit as st

# ====== ページ設定（余白を詰めてシンプルに） ======
st.set_page_config(page_title="FXシミュレーション", layout="wide")
st.markdown("""
<style>
/* 全体の余白を軽く圧縮 */
.block-container {padding-top: 1rem; padding-bottom: 1rem;}
/* KPIカード間の余白調整 */
.css-1xarl3l, .css-12oz5g7 {gap: 0.75rem !important;}
/* フッター/メニュー非表示（必要なら） */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ====== 定数 ======
LOT_UNITS = 100_000               # 1枚=10万通貨
FEE_PER_LOT_PER_SIDE = 1_100.0    # 手数料（片側/枚/税込）：建て時・決済時のみ

# ====== ユーティリティ ======
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

# ====== 損益計算（手数料込み・売りはスワップをマイナス） ======
def compute_series(
    prices: np.ndarray,
    initial_deposit: float,
    lots: int,
    direction_sign: int,            # 買い:+1 / 売り:-1
    swap_per_lot_per_day_input: float,  # 入力は「受取額（正の値）」で
):
    n = len(prices)
    units = lots * LOT_UNITS
    diff = np.diff(prices, prepend=prices[0])

    # スワップ：買い=＋、売り=−（入力は正で想定）
    swap_per_lot_effective = (1 if direction_sign == 1 else -1) * abs(swap_per_lot_per_day_input)
    swap = np.full(n, swap_per_lot_effective * lots, dtype=float)

    pnl_fx = direction_sign * diff * units

    # 手数料：建て時・決済時のみ控除
    fee = np.zeros(n)
    if n >= 1 and lots > 0:
        fee[0]  -= FEE_PER_LOT_PER_SIDE * lots
    if n >= 2 and lots > 0:
        fee[-1] -= FEE_PER_LOT_PER_SIDE * lots

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
        "スワップポイント損益": float(swap.sum()),
        "手数料合計": float(fee.sum()),  # 負の値（支払い）
    }
    return df, summary

# ====== サイドバー（入力：ご指定の順＋シンプル配置） ======
with st.sidebar:
    st.header("入力")

    # 1) 初回入金
    deposit = st.number_input("初回入金額（円）", value=10_000_000, step=100_000, format="%d", min_value=0)

    # 2) 必要証拠金（1枚）
    per_lot_margin = st.number_input("必要証拠金（1枚あたり／円）", value=40_000, step=1_000, format="%d", min_value=0)

    # 3) 実効レバレッジ（指定も可能）
    leff_target = st.number_input("実効レバレッジ（指定可）", value=3.0, step=0.1, min_value=0.1)

    # 4) 枚数：3モード（自動/レバから自動/手動）— シンプルなラジオ
    mode = st.radio("枚数の設定", ["自動計算（証拠金）", "実効レバから自動", "手動入力"], horizontal=False)

    # 7) 初期レート（lots計算に使うので先に取得）※0.1円刻み
    s0 = st.number_input("初期レート（MXN/JPY）", value=7.8, step=0.1, format="%.1f")

    # 4)（続き）lots決定
    if mode == "自動計算（証拠金）":
        lots_candidate = lots_by_margin(deposit, per_lot_margin)
        lots = lots_candidate
        lots_note = f"証拠金上限で自動：{lots} 枚"
    elif mode == "実効レバから自動":
        lots_lev = lots_by_target_leverage(leff_target, deposit, s0)
        lots_cap = lots_by_margin(deposit, per_lot_margin)
        lots = max(1, min(lots_lev, lots_cap))
        lots_note = f"目標 {leff_target:.2f} 倍 → {lots_lev} 枚 / 証拠金上限 {lots_cap} 枚 → 採用 {lots} 枚"
    else:
        lots_manual = st.number_input("枚数（手動・整数）", value=33, min_value=1, step=1)
        lots_cap = lots_by_margin(deposit, per_lot_margin)
        if lots_manual > lots_cap:
            st.warning(f"証拠金不足のため {lots_cap} 枚までに調整しました。")
            lots = lots_cap
        else:
            lots = int(lots_manual)
        lots_note = f"手動指定：{lots} 枚（上限 {lots_cap} 枚）"

    # 5) 売買方向
    direction = st.radio("売買方向", ["買い", "売り"], horizontal=True)
    dir_sign = 1 if direction == "買い" else -1

    # 6) スワップ（受取額/日/枚：正の値で入力）
    swap_per_lot_per_day = st.number_input("スワップ（円／枚／日）", value=150, step=10, format="%d", min_value=0)

    # 8) 期末レート（0.1円刻み）
    s1 = st.number_input("期末レート（MXN/JPY）", value=8.2, step=0.1, format="%.1f")

    # 9) 運用期間
    days = st.slider("運用期間（日）", min_value=30, max_value=730, value=365, step=5)

# ====== 本体（KPIのみ。余白を詰めてカード中心） ======
st.title("FXシミュレーション")

# 実効レバ（結果）と必要証拠金合計を先に計算
leff_actual = (lots * s0 * LOT_UNITS) / deposit if deposit > 0 and s0 > 0 else 0.0
need_margin_total = per_lot_margin * lots

# 価格系列（直線。損益にのみ使用／表示はしない）
prices = build_prices_linear(days, s0, s1)

# 損益（手数料込み）
df, sm = compute_series(
    prices=prices,
    initial_deposit=deposit,
    lots=lots,
    direction_sign=dir_sign,
    swap_per_lot_per_day_input=swap_per_lot_per_day,
)

# ====== KPI 3つ（中央寄せ・詰め配置） ======
k1, k2, k3 = st.columns([1,1,1])
with k1:
    st.metric("期末口座状況", f"{sm['期末口座状況']:,.0f} 円")
with k2:
    st.metric("総損益（手数料込み）", f"{sm['総損益(手数料込み)']:,.0f} 円")
with k3:
    st.metric("スワップポイント損益", f"{sm['スワップポイント損益']:,.0f} 円")

# ====== 補助情報（1行2列で簡潔表示） ======
c1, c2 = st.columns([1,1])
with c1:
    st.caption(f"実効レバレッジ（計算結果）：{leff_actual:.2f} 倍")
with c2:
    st.caption(f"必要証拠金の目安（合計）：{need_margin_total:,} 円")

# ====== 注記（常時） ======
st.caption("手数料：1100円（消費税込み）売買成立時に発生")
st.caption(lots_note)
