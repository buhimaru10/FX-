# -*- coding: utf-8 -*-
import math
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ===== ページ設定（余白コンパクト） =====
st.set_page_config(page_title="FXシミュレーション", layout="wide")
st.markdown("""
<style>
.block-container { padding-top: 1rem; padding-bottom: 1rem; }
#MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ===== 定数 =====
LOT_UNITS = 100_000                 # 1枚=10万通貨
FEE_PER_LOT_PER_SIDE = 1_100.0      # 手数料（片側/枚/税込）…建て・決済の2回、損益に関わらず必ず発生

# ===== ユーティリティ =====
def safe_floor(x: float) -> int:
    try:
        if math.isnan(x) or math.isinf(x): return 0
        return int(math.floor(x))
    except Exception:
        return 0

def build_prices_linear(days: int, s0: float, s1: float) -> np.ndarray:
    """初期～期末を直線で補間（表示はしない／損益計算にのみ使用）"""
    days = max(1, int(days))
    return np.linspace(s0, s1, days + 1)  # n = days+1（初日を含む）

def lots_cap_by_margin(deposit: float, per_lot_margin: float) -> int:
    """証拠金基準の上限枚数（切り下げ、最低1）"""
    return max(1, safe_floor(deposit / max(1.0, per_lot_margin)))

def lots_from_leverage(leff: float, deposit: float, s0: float) -> int:
    """目標実効レバからの枚数（切り下げ、最低1）"""
    if s0 <= 0: return 1
    return max(1, safe_floor((leff * deposit) / (s0 * LOT_UNITS)))

# ===== 損益計算（手数料=固定コスト・売りはスワップをマイナス・初日はスワップ0） =====
def compute_series(prices: np.ndarray,
                   initial_deposit: float,
                   lots: int,
                   direction_sign: int,              # 買い:+1 / 売り:-1
                   swap_per_lot_per_day_input: float # 入力は受取額（正の値）
                   ):
    n = len(prices)                      # = days + 1
    units = lots * LOT_UNITS
    diff = np.diff(prices, prepend=prices[0])  # 初日は0

    # スワップ：買い=＋、売り=−。初日は0、翌日以降に計上（合計＝日額×枚数×日数）
    swap_per_lot_effective = (1 if direction_sign == 1 else -1) * abs(swap_per_lot_per_day_input)
    daily_swap = swap_per_lot_effective * lots
    swap = np.zeros(n, dtype=float)
    if n > 1:
        swap[1:] = daily_swap

    # 為替損益（建玉方向で±）
    pnl_fx = direction_sign * diff * units

    # 手数料：建て時・決済時に必ず発生（方向や損益に関係なく固定コスト）
    fee = np.zeros(n)
    if n >= 1 and lots > 0:
        fee[0]  -= FEE_PER_LOT_PER_SIDE * lots   # 建て時
    if n >= 2 and lots > 0:
        fee[-1] -= FEE_PER_LOT_PER_SIDE * lots   # 決済時

    # 合成P/Lと口座状況
    pnl_total = pnl_fx + swap + fee
    equity = initial_deposit + np.cumsum(pnl_total)

    # 集計（手数料は常にコスト：fee_totalは負の値）
    fx_total   = float(pnl_fx.sum())
    swap_total = float(swap.sum())
    fee_total  = float(fee.sum())
    fee_abs    = abs(fee_total)
    end_equity = float(equity[-1])

    # 為替差損益（手数料込）= 為替P/L − 手数料
    fx_fee_inclusive = fx_total - fee_abs

    summary = {
        "期末口座状況": end_equity,
        "為替差損益(手数料込)": fx_fee_inclusive,
        "スワップポイント利益": swap_total,
        "総損益(手数料込み)": end_equity - initial_deposit,  # 参考（画面表示はしない）
        "手数料合計": fee_total
    }
    return summary

# ================================
# サイドバー（双方向リンク：実効レバ⇄枚数）
# ================================
with st.sidebar:
    st.header("入力")

    # セッション初期値
    defaults = {
        "deposit": 10_000_000,
        "per_lot_margin": 40_000,
        "leff": 3.0,
        "lots": 33,
        "s0": 7.8,
        "s1": 8.2,
        "days": 365,
        "_lock": False,  # 相互更新の再帰ループ防止
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    # ---- 相互更新用ヘルパ ----
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

    # 1) 初回入金
    def on_change_deposit():
        if st.session_state._lock: return
        st.session_state._lock = True
        _recalc_from_leff()
        st.session_state._lock = False

    st.session_state.deposit = st.number_input(
        "初回入金額（円）", value=st.session_state.deposit,
        step=100_000, format="%d", min_value=0, on_change=on_change_deposit
    )

    # 2) 必要証拠金（1枚）
    def on_change_margin():
        if st.session_state._lock: return
        st.session_state._lock = True
        _recalc_from_leff()
        st.session_state._lock = False

    st.session_state.per_lot_margin = st.number_input(
        "必要証拠金（1枚あたり／円）", value=st.session_state.per_lot_margin,
        step=1_000, format="%d", min_value=0, on_change=on_change_margin
    )

    # 3) 実効レバ（指定可）— lots と相互更新
    def on_change_leff():
        if st.session_state._lock: return
        st.session_state._lock = True
        _recalc_from_leff()
        st.session_state._lock = False

    st.number_input(
        "実効レバレッジ（指定可）", key="leff",
        step=0.1, min_value=0.1, on_change=on_change_leff
    )

    # 4) 枚数（整数）— leff と相互更新（実効レバの直下に配置）
    def on_change_lots():
        if st.session_state._lock: return
        st.session_state._lock = True
        _recalc_from_lots()
        st.session_state._lock = False

    st.number_input(
        "枚数（整数）", key="lots",
        min_value=1, step=1, on_change=on_change_lots
    )

    # 5) 売買方向
    direction = st.radio("売買方向", ["買い", "売り"], horizontal=True)
    dir_sign = 1 if direction == "買い" else -1

    # 6) スワップ（受取額/日/枚：正の値で入力）
    swap_per_lot_per_day = st.number_input(
        "スワップ（円／枚／日）", value=150, step=10, format="%d", min_value=0
    )

    # 7) 初期レート（0.1円刻み）
    def on_change_s0():
        if st.session_state._lock: return
        st.session_state._lock = True
        _recalc_from_leff()
        st.session_state._lock = False

    st.session_state.s0 = st.number_input(
        "初期レート（MXN/JPY）", value=st.session_state.s0,
        step=0.1, format="%.1f", on_change=on_change_s0
    )

    # 8) 期末レート（0.1円刻み）
    st.session_state.s1 = st.number_input(
        "期末レート（MXN/JPY）", value=st.session_state.s1,
        step=0.1, format="%.1f"
    )

    # 9) 運用期間
    st.session_state.days = st.slider(
        "運用期間（日）", min_value=30, max_value=730, value=st.session_state.days, step=5
    )

# ================================
# 本体（KPIのみ・ご指定順）＋右側にTradingView
# ================================
st.title("FXシミュレーション")

# 価格系列（直線。損益計算にのみ使用）
prices = build_prices_linear(st.session_state.days, st.session_state.s0, st.session_state.s1)

# 計算（手数料は固定コストとして建て/決済で必ず控除）
sm = compute_series(
    prices=prices,
    initial_deposit=st.session_state.deposit,
    lots=st.session_state.lots,
    direction_sign=dir_sign,
    swap_per_lot_per_day_input=swap_per_lot_per_day,
)

# 実効レバ（結果）& 必要証拠金合計
leff_actual = (
    (st.session_state.lots * st.session_state.s0 * LOT_UNITS) / st.session_state.deposit
    if st.session_state.deposit > 0 and st.session_state.s0 > 0 else 0.0
)
need_margin_total = st.session_state.per_lot_margin * st.session_state.lots

# KPI（期末口座状況 → 為替差損益（手数料込） → スワップポイント利益）
k1, k2, k3 = st.columns(3)
k1.metric("期末口座状況", f"{sm['期末口座状況']:,.0f} 円")
k2.metric("為替差損益（手数料込）", f"{sm['為替差損益(手数料込)']:,.0f} 円")
k3.metric("スワップポイント利益", f"{sm['スワップポイント利益']:,.0f} 円")

# 補助情報
c1, c2 = st.columns(2)
c1.caption(f"実効レバレッジ（計算結果）：{leff_actual:.2f} 倍")
c2.caption(f"必要証拠金の目安（合計）：{need_margin_total:,} 円")

# 注記
cap_display = lots_cap_by_margin(st.session_state.deposit, st.session_state.per_lot_margin)
st.caption("手数料：1100円（消費税込み）売買成立時に発生（売買成立時：建て・決済の2回）")
st.caption(f"証拠金上限（枚数）：{cap_display} 枚")

# ================================
# 右側スペース：TradingView レートチャートのみ表示
# ================================
left_info, right_chart = st.columns([1, 2])

with left_info:
    st.subheader("説明")
    st.markdown(
        f"""
- **期間**：{st.session_state.days}日  
- **初期レート**：{st.session_state.s0:.1f} MXN/JPY  
- **期末レート**：{st.session_state.s1:.1f} MXN/JPY  
- **方向**：{"買い" if dir_sign==1 else "売り"}  
- **枚数**：{st.session_state.lots} 枚（実効レバ {leff_actual:.2f} 倍）  
- **スワップ/日/枚**：{int(swap_per_lot_per_day)} 円  
- **手数料**：建て・決済 各 {int(FEE_PER_LOT_PER_SIDE)} 円/枚（固定コスト）
        """
    )

with right_chart:
    st.subheader("レートチャート（TradingView）")
    tradingview_embed = """
    <!-- TradingView Widget BEGIN -->
    <div class="tradingview-widget-container">
      <div id="tradingview_chart"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
        new TradingView.widget({
          "container_id": "tradingview_chart",
          "width": "100%",
          "height": 520,
          "symbol": "FX:MXNJPY",         // ★ MXN/JPY
          "interval": "D",
          "timezone": "Asia/Tokyo",
          "theme": "light",
          "style": "1",
          "locale": "ja",
          "toolbar_bg": "#f1f3f6",
          "enable_publishing": false,
          "hide_legend": false,
          "save_image": false,
          "studies": ["MASimple@tv-basicstudies"]
        });
      </script>
    </div>
    <!-- TradingView Widget END -->
    """
    components.html(tradingview_embed, height=540)


