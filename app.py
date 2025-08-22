# -*- coding: utf-8 -*-
import math
import uuid
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ===== ページ設定 =====
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

def lots_cap_by_margin(deposit: float, per_lot_margin: float) -> int:
    return max(1, safe_floor(deposit / max(1.0, per_lot_margin)))

def lots_from_leverage(leff: float, deposit: float, s0: float) -> int:
    if s0 <= 0: return 1
    return max(1, safe_floor((leff * deposit) / (s0 * LOT_UNITS)))

def compute_series(prices, initial_deposit, lots, direction_sign, swap_per_lot_per_day_input):
    n = len(prices)
    units = lots * LOT_UNITS
    diff = np.diff(prices, prepend=prices[0])

    swap_per_lot_effective = (1 if direction_sign == 1 else -1) * abs(swap_per_lot_per_day_input)
    daily_swap = swap_per_lot_effective * lots
    swap = np.zeros(n, dtype=float)
    if n > 1: swap[1:] = daily_swap

    pnl_fx = direction_sign * diff * units

    fee = np.zeros(n)
    if n >= 1 and lots > 0: fee[0]  -= FEE_PER_LOT_PER_SIDE * lots
    if n >= 2 and lots > 0: fee[-1] -= FEE_PER_LOT_PER_SIDE * lots

    pnl_total = pnl_fx + swap + fee
    equity = initial_deposit + np.cumsum(pnl_total)

    fx_total   = float(pnl_fx.sum())
    swap_total = float(swap.sum())
    fee_total  = float(fee.sum())
    end_equity = float(equity[-1])

    fx_fee_inclusive = fx_total - abs(fee_total)

    return {
        "期末口座状況": end_equity,
        "為替差損益(手数料込)": fx_fee_inclusive,
        "スワップポイント利益": swap_total,
        "手数料合計": fee_total,
        "equity_series": equity,
        "price_series": prices
    }

# ================================
# サイドバー
# ================================
with st.sidebar:
    st.header("入力")
    defaults = {
        "deposit": 10_000_000,
        "per_lot_margin": 40_000,
        "leff": 3.0,
        "lots": 33,
        "s0": 7.8,
        "s1": 8.2,
        "days": 365,
        "_lock": False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    def _recalc_from_leff():
        cap = lots_cap_by_margin(st.session_state.deposit, st.session_state.per_lot_margin)
        lots_lev = lots_from_leverage(st.session_state.leff, st.session_state.deposit, st.session_state.s0)
        st.session_state.lots = max(1, min(lots_lev, cap))

    def _recalc_from_lots():
        cap = lots_cap_by_margin(st.session_state.deposit, st.session_state.per_lot_margin)
        st.session_state.lots = max(1, min(int(st.session_state.lots), cap))
        if st.session_state.deposit > 0 and st.session_state.s0 > 0:
            leff_actual = (st.session_state.lots * st.session_state.s0 * LOT_UNITS) / st.session_state.deposit
            st.session_state.leff = max(0.1, round(leff_actual, 2))

    def on_change_deposit():
        if st.session_state._lock: return
        st.session_state._lock = True; _recalc_from_leff(); st.session_state._lock = False
    st.number_input("初回入金額（円）", value=st.session_state.deposit,
                    step=100_000, format="%d", min_value=0, on_change=on_change_deposit)

    def on_change_margin():
        if st.session_state._lock: return
        st.session_state._lock = True; _recalc_from_leff(); st.session_state._lock = False
    st.number_input("必要証拠金（1枚あたり／円）", value=st.session_state.per_lot_margin,
                    step=1_000, format="%d", min_value=0, on_change=on_change_margin)

    def on_change_leff():
        if st.session_state._lock: return
        st.session_state._lock = True; _recalc_from_leff(); st.session_state._lock = False
    st.number_input("実効レバレッジ（指定可）", key="leff",
                    step=0.1, min_value=0.1, on_change=on_change_leff)

    def on_change_lots():
        if st.session_state._lock: return
        st.session_state._lock = True; _recalc_from_lots(); st.session_state._lock = False
    st.number_input("枚数（整数）", key="lots",
                    min_value=1, step=1, on_change=on_change_lots)

    direction = st.radio("売買方向", ["買い", "売り"], horizontal=True)
    dir_sign = 1 if direction == "買い" else -1

    swap_per_lot_per_day = st.number_input("スワップ（円／枚／日）",
                                           value=150, step=10, format="%d", min_value=0)

    def on_change_s0():
        if st.session_state._lock: return
        st.session_state._lock = True; _recalc_from_leff(); st.session_state._lock = False
    st.session_state.s0 = st.number_input("初期レート（MXN/JPY）", value=st.session_state.s0,
                                          step=0.1, format="%.1f", on_change=on_change_s0)

    st.session_state.s1 = st.number_input("期末レート（MXN/JPY）",
                                          value=st.session_state.s1, step=0.1, format="%.1f")

    st.session_state.days = st.slider("運用期間（日）",
                                      min_value=30, max_value=730,
                                      value=st.session_state.days, step=5)

# ================================
# 本体
# ================================
st.title("FXシミュレーション")

prices = build_prices_linear(st.session_state.days, st.session_state.s0, st.session_state.s1)
sm = compute_series(prices, st.session_state.deposit, st.session_state.lots,
                    dir_sign, swap_per_lot_per_day)

leff_actual = (
    (st.session_state.lots * st.session_state.s0 * LOT_UNITS) / st.session_state.deposit
    if st.session_state.deposit > 0 and st.session_state.s0 > 0 else 0.0
)
need_margin_total = st.session_state.per_lot_margin * st.session_state.lots

k1, k2, k3 = st.columns(3)
k1.metric("期末口座状況", f"{sm['期末口座状況']:,.0f} 円")
k2.metric("為替差損益（手数料込）", f"{sm['為替差損益(手数料込)']:,.0f} 円")
k3.metric("スワップポイント利益", f"{sm['スワップポイント利益']:,.0f} 円")

c1, c2 = st.columns(2)
c1.caption(f"実効レバレッジ（計算結果）：{leff_actual:.2f} 倍")
c2.caption(f"必要証拠金の目安（合計）：{need_margin_total:,} 円")
# ================================
# チャート（横長・低めリボン表示）
# ================================
st.markdown("### レートチャート（TradingView）")

# 説明は小さく1行で
st.caption(
    f"期間: {st.session_state.days}日 ｜ 初期: {st.session_state.s0:.1f} ｜ 期末: {st.session_state.s1:.1f} ｜ "
    f"方向: {'買い' if dir_sign==1 else '売り'} ｜ 枚数: {st.session_state.lots}枚 (レバ {leff_actual:.2f}倍)"
)

# シンボル選択も横幅を取らないようコンパクトに
cols = st.columns([3,1.2,6])
with cols[1]:
    symbol_choices = ["OANDA:MXNJPY", "FX_IDC:MXNJPY", "FOREXCOM:MXNJPY", "SAXO:MXNJPY"]
    tv_symbol = st.selectbox(" ", symbol_choices, index=0, label_visibility="collapsed")

# 超横長に見せるため、高さは低め（例: 340px）
import uuid, streamlit.components.v1 as components
container_id = f"tv_{uuid.uuid4().hex}"
tradingview_embed = f"""
<div class="tradingview-widget-container" style="width:100%;">
  <div id="{container_id}"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
    new TradingView.widget({{
      "container_id": "{container_id}",
      "width": "100%",
      "height": 340,                 // ← 縦を低くして横長感を強調（320〜380推奨）
      "symbol": "{tv_symbol}",
      "interval": "D",
      "timezone": "Asia/Tokyo",
      "theme": "light",
      "style": "1",
      "locale": "ja",
      "withdateranges": true,
      "allow_symbol_change": false,  // 上部シンボル切替バーを消して縦を節約
      "hide_top_toolbar": true,      // 上部ツールバー非表示
      "hide_side_toolbar": true,     // 右サイドツールバー非表示
      "hide_legend": true,           // 凡例非表示で縦を節約
      "toolbar_bg": "#ffffff",
      "enable_publishing": false,
      "save_image": false
    }});
  </script>
</div>
"""
components.html(tradingview_embed, height=360)  # 埋め込みコンテナも低めに






