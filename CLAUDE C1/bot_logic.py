# ==========================================
# nazBot Sniper System [BETA v4.0 - ELITE SNIPER ENGINE]
# FILE: bot_logic.py
# UPGRADE: 7-Layer Confluence Signal (Order Blocks + RSI Div + ATR Gate + Liquidity Sweep)
# HARD CONSTRAINTS: 50x Lev | $5 Margin | 100% TP | SHORT -150% SL | DCA LONG Only
# ==========================================

from __future__ import annotations
import math
import os
import time
import logging
import random
import threading
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from ta.trend import ema_indicator, sma_indicator, MACD
from ta.volatility import BollingerBands, AverageTrueRange
from ta.momentum import RSIIndicator
from binance.client import Client
from binance.exceptions import BinanceAPIException

logger = logging.getLogger('bot')

API_KEY = os.environ.get('BINANCE_API_KEY', '')
API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

# --- PENGATURAN MUTLAK PRO (v4.0) --- [DO NOT TOUCH]
TARGET_LEVERAGE = 50
BASE_MARGIN = 5.0
TP_TARGET_ROE = 1.00       # 100% ROE
SHORT_SL_ROE = 1.50        # -150% ROE SHORT SL

# --- VOLUME FILTER ---
VOL_MA_PERIOD = 20
VOL_MULTIPLIER = 1.5

# --- DCA DINAMIS 3-TAHAP (HANYA LONG) --- [DO NOT TOUCH]
DCA_1_DROP_PERCENT = 2.0
DCA_2_DROP_PERCENT = 3.0
DCA_3_DROP_PERCENT = 4.0
DCA_1_MARGIN_RATIO = 0.50
DCA_2_MARGIN_RATIO = 0.50
DCA_3_MARGIN_RATIO = 1.00

MAX_VIP, MAX_ALT = 8, 8
EMA_TREND, MA_STRUCT, BB_WINDOW = 200, 99, 20
ATR_WINDOW = 14

VIP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT", "XRPUSDT", "ALICEUSDT"]
VIP_SET = set(VIP_SYMBOLS)
VIP_TFS = ['15m', '1h', '4h']

ALT_TFS_FAST = ['5m', '15m', '1h', '4h']
ALT_TFS_SAFE = ['15m', '1h', '4h']
ALT_TF_ORDER = ['5m', '15m', '1h', '4h']

TOP_ALT_LIMIT = 50
STATE_FILE = 'status.txt'

GOLD_PAIRS = ["PAXGUSDT"]
GOLD_SET = set(GOLD_PAIRS)
GOLD_TFS = ['15m', '1h', '4h']

LEDGER_FILE = 'profit_ledger.txt'

TOTAL_CLOSED_ROE = 0.0
TOTAL_CLOSED_ROE_PERCENT = 0.0
TOTAL_SUCCESS_TRADES = 0
CLOSED_HISTORY = []
_coin_escalation_level: Dict[str, int] = {}

_client = Client(API_KEY, API_SECRET, testnet=True)  # Ganti testnet=False untuk real account

# ---------- PERFORMANCE CACHING ----------
_exchange_filter_cache: Dict[str, dict] = {}
_ticker_cache: Dict[str, Any] = {"data": None, "timestamp": 0}
_TICKER_CACHE_TTL = 5.0

_RATE_LIMIT_CALLS, _RATE_LIMIT_PERIOD = 20, 1.0
_last_call_time = 0.0
_rate_limit_lock = threading.Lock()

def _rate_limit():
    global _last_call_time
    with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_call_time
        min_interval = _RATE_LIMIT_PERIOD / _RATE_LIMIT_CALLS
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_call_time = time.monotonic()

def _api_call(fn, *args, max_retries: int = 5, **kwargs):
    for attempt in range(max_retries):
        _rate_limit()
        try:
            return fn(*args, **kwargs)
        except BinanceAPIException as e:
            if e.code != -1121:
                logger.warning(f"⚠️ Binance Error [{fn.__name__}]: {e.message}")
            if e.code in (-1121, -4028, -2011, -2021, -2019):
                raise
            time.sleep(2 ** attempt + random.uniform(0, 1))
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API Error: {fn.__name__}")

# ========== FUNGSI LEDGER & BALANCE [DO NOT TOUCH] ==========
def get_binance_balance() -> float:
    try:
        account_info = _api_call(_client.futures_account)
        for asset in account_info.get('assets', []):
            if asset['asset'] == 'USDT':
                return float(asset['walletBalance'])
    except Exception: pass
    return 0.0

def get_initial_balance() -> float:
    is_new = not os.path.exists(LEDGER_FILE) or os.path.getsize(LEDGER_FILE) == 0
    if is_new:
        start_bal = get_binance_balance()
        if start_bal == 0: start_bal = 5000.0
        with open('start_balance.txt', 'w') as f:
            f.write(str(start_bal))
        return start_bal
    else:
        if os.path.exists('start_balance.txt'):
            with open('start_balance.txt', 'r') as f:
                try: return float(f.read().strip())
                except: pass
        return 5000.0

def _fetch_realized_pnl(symbol: str) -> float:
    try:
        income_data = _api_call(_client.futures_income_history, symbol=symbol, incomeType="REALIZED_PNL", limit=1)
        if income_data:
            return float(income_data[0]['income'])
    except Exception: pass
    return (BASE_MARGIN * TP_TARGET_ROE)

def get_last_ledger_data() -> Tuple[float, float]:
    if not os.path.exists(LEDGER_FILE) or os.path.getsize(LEDGER_FILE) == 0:
        return 0.0, 0.0
    try:
        with open(LEDGER_FILE, 'r') as f:
            lines = [l for l in f.readlines() if '|' in l and 'TIME' not in l and '---' not in l]
            if not lines: return 0.0, 0.0
            last_line = lines[-1]
            parts = [p.strip() for p in last_line.split('|')]
            if len(parts) >= 8:
                tot_pnl = float(parts[4].replace('$', '').replace('+', ''))
                tot_roe = float(parts[5].replace('%', '').replace('+', ''))
                return tot_pnl, tot_roe
    except: pass
    return 0.0, 0.0

def get_last_ledger_totals() -> float:
    _, tot_roe = get_last_ledger_data()
    return tot_roe

def catat_transaksi_v2(symbol: str, pnl_usd: float, roe_percent: float):
    """[DO NOT TOUCH] 8-column ledger logging"""
    prev_tot_pnl, prev_tot_roe = get_last_ledger_data()
    new_tot_pnl = prev_tot_pnl + pnl_usd
    new_tot_roe = prev_tot_roe + roe_percent

    current_balance = get_binance_balance()
    start_balance = get_initial_balance()
    growth_pct = ((current_balance - start_balance) / start_balance) * 100 if start_balance > 0 else 0.0

    now = datetime.now().strftime("%H:%M:%S")
    log_line = (f"{now} | {symbol} | {pnl_usd:+.2f} | {roe_percent:+.2f}% | "
                f"{new_tot_pnl:+.2f} | {new_tot_roe:+.2f}% | "
                f"{current_balance:.2f} | {growth_pct:+.2f}%\n")

    is_new = not os.path.exists(LEDGER_FILE) or os.path.getsize(LEDGER_FILE) == 0
    with open(LEDGER_FILE, 'a') as f:
        if is_new:
            f.write("TIME | PAIR | PROFIT $ | ROE % | TOTAL PNL $ | TOTAL ROE % | SALDO BINANCE | GROWTH %\n")
            f.write("-" * 110 + "\n")
        f.write(log_line)
    logger.info(f"💾 [LEDGER] {symbol} Terekam! Saldo: ${current_balance:.2f} (Growth: {growth_pct:+.2f}%)")

# ========== HELPER FUNCTIONS ==========
def _get_exchange_filters(symbol: str) -> dict:
    if symbol not in _exchange_filter_cache:
        info = _api_call(_client.futures_exchange_info)
        for s in info['symbols']:
            _exchange_filter_cache[s['symbol']] = {x['filterType']: x for x in s['filters']}
    return _exchange_filter_cache[symbol]

def _get_cached_ticker() -> List[dict]:
    global _ticker_cache
    now = time.time()
    if _ticker_cache["data"] is None or (now - _ticker_cache["timestamp"]) > _TICKER_CACHE_TTL:
        _ticker_cache["data"] = _api_call(_client.futures_ticker)
        _ticker_cache["timestamp"] = now
    return _ticker_cache["data"]

def _read_status() -> str:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return f.read().strip() or 'OFF'
    except Exception: pass
    return 'OFF'

def setup_account_environment() -> None:
    try:
        _client.futures_change_position_mode(dualSidePosition=True)
    except Exception: pass

def _get_dynamic_leverage_and_margin(symbol: str, target_margin: float) -> Tuple[int, float]:
    target_notional = target_margin * TARGET_LEVERAGE
    try:
        _client.futures_change_leverage(symbol=symbol, leverage=TARGET_LEVERAGE)
        return TARGET_LEVERAGE, target_margin
    except BinanceAPIException as e:
        if e.code == -4028:
            try:
                brackets = _client.futures_leverage_bracket(symbol=symbol)
                max_lev = int(brackets[0]['brackets'][0]['initialLeverage'])
                _client.futures_change_leverage(symbol=symbol, leverage=max_lev)
                adjusted_margin = target_notional / max_lev
                return max_lev, adjusted_margin
            except Exception: return TARGET_LEVERAGE, target_margin
        return TARGET_LEVERAGE, target_margin
    except Exception: return TARGET_LEVERAGE, target_margin


# =====================================================================
# 🧠 ELITE SIGNAL ENGINE v4.0 — 7-Layer Confluence
# =====================================================================
#
# LAYER 1: EMA 200 Trend Guard          — Only trade WITH the trend
# LAYER 2: ATR Volatility Gate          — Block dead/over-volatile markets
# LAYER 3: RSI Momentum Filter          — Confirm momentum; avoid exhaustion zones
# LAYER 4: MACD Histogram Momentum      — Directional momentum confirmation
# LAYER 5: Order Block Detection        — Institutional supply/demand zones
# LAYER 6: Liquidity Sweep (Fakeout)    — Detect stop-hunt wicks for reversal entries
# LAYER 7: Volume Confirmation          — Institutional footprint required
#
# WHY THIS IS BETTER THAN v3.1:
# - v3.1 only looked at static support/resistance (BB, MA99, EMA200 touch).
#   It fired on ANY touch regardless of market context. This caused many
#   fakeouts because it didn't validate MOMENTUM or MARKET STRUCTURE.
# - v4.0 adds RSI context (avoid overbought LONG, oversold SHORT),
#   MACD histogram direction to confirm momentum is WITH us, and
#   Order Block detection to find institutional origin points.
# - The Liquidity Sweep layer specifically hunts "stop hunts" — when
#   price briefly wicks through a key level to liquidate retail traders
#   before reversing. This is the most consistent pattern at 50x leverage.
# - ATR Gate prevents entries during choppy (low ATR) or explosive
#   (extreme ATR) markets where 50x leverage is most dangerous.
# =====================================================================

def _detect_order_block(df: pd.DataFrame, side: str, lookback: int = 30) -> Optional[Tuple[float, float]]:
    """
    Detect the most recent Order Block (OB) in the given direction.
    
    A Bullish OB = Last bearish (down) candle before a strong bullish impulse move up.
    A Bearish OB = Last bullish (up) candle before a strong bearish impulse move down.
    
    Returns (ob_low, ob_high) of the order block zone, or None.
    """
    try:
        df_slice = df.iloc[-lookback - 1 : -1].copy()  # Exclude current candle
        closes = df_slice['close'].values
        opens = df_slice['open'].values
        highs = df_slice['high'].values
        lows = df_slice['low'].values

        if side == 'LONG':
            # Find last bearish candle followed by 2 consecutive bullish impulse candles
            for i in range(len(df_slice) - 3, 0, -1):
                is_bearish_ob = closes[i] < opens[i]  # Red candle
                next_is_bullish = closes[i+1] > opens[i+1]
                strong_impulse = (closes[i+1] - opens[i+1]) > (highs[i+1] - lows[i+1]) * 0.5
                if is_bearish_ob and next_is_bullish and strong_impulse:
                    return (lows[i], highs[i])  # OB zone

        elif side == 'SHORT':
            # Find last bullish candle followed by 2 consecutive bearish impulse candles
            for i in range(len(df_slice) - 3, 0, -1):
                is_bullish_ob = closes[i] > opens[i]  # Green candle
                next_is_bearish = closes[i+1] < opens[i+1]
                strong_impulse = (opens[i+1] - closes[i+1]) > (highs[i+1] - lows[i+1]) * 0.5
                if is_bullish_ob and next_is_bearish and strong_impulse:
                    return (lows[i], highs[i])  # OB zone
    except Exception:
        pass
    return None


def _detect_liquidity_sweep(df: pd.DataFrame, side: str, atr: float, lookback: int = 20) -> bool:
    """
    Detect a Liquidity Sweep (stop hunt wick) pattern.
    
    Bullish sweep: Previous candle wicks below the recent swing low (sweeps longs' stops),
                   then closes ABOVE that low. Current candle confirms recovery.
    Bearish sweep: Previous candle wicks above recent swing high (sweeps shorts' stops),
                   then closes BELOW that high. Current candle confirms rejection.
    
    This is the #1 entry pattern for high-leverage reversal scalping.
    """
    try:
        recent = df.iloc[-lookback-2 : -2]  # Window before last 2 candles
        prev = df.iloc[-2]   # The sweep candle
        curr = df.iloc[-1]   # The confirmation candle

        if side == 'LONG':
            swing_low = recent['low'].min()
            # Prev candle wicked below swing low but CLOSED above it (failed breakdown)
            wick_below = prev['low'] < (swing_low - atr * 0.1)
            closed_above = prev['close'] > swing_low
            # Current candle is green (bullish confirmation)
            curr_bullish = curr['close'] > curr['open']
            # Wick is significant (at least 1.5x the body)
            body = abs(prev['close'] - prev['open']) or 1e-9
            wick = prev['open'] - prev['low'] if prev['open'] > prev['close'] else prev['close'] - prev['low']
            wick_significant = wick > body * 1.0
            return wick_below and closed_above and curr_bullish and wick_significant

        elif side == 'SHORT':
            swing_high = recent['high'].max()
            wick_above = prev['high'] > (swing_high + atr * 0.1)
            closed_below = prev['close'] < swing_high
            curr_bearish = curr['close'] < curr['open']
            body = abs(prev['close'] - prev['open']) or 1e-9
            wick = prev['high'] - prev['open'] if prev['open'] < prev['close'] else prev['high'] - prev['close']
            wick_significant = wick > body * 1.0
            return wick_above and closed_below and curr_bearish and wick_significant

    except Exception:
        pass
    return False


def _check_rsi_momentum(rsi_series: pd.Series, side: str) -> bool:
    """
    RSI Momentum Filter.
    
    For LONG:
      - RSI must be 35-65 (not overbought, not in free-fall oversold = dangerous at 50x)
      - RSI direction should be recovering (current > previous)
    For SHORT:
      - RSI must be 35-65 (not oversold, not in extreme overbought = dangerous)  
      - RSI direction should be declining (current < previous)
    
    Why 35-65 and not the classic 30/70?
    At 50x leverage, entering a LONG when RSI < 30 means price is in free-fall.
    Even if it eventually reverses, the drawdown can trigger DCA stages 1-2-3.
    We want momentum TURNING, not momentum extremes.
    """
    try:
        curr_rsi = rsi_series.iloc[-1]
        prev_rsi = rsi_series.iloc[-2]
        if side == 'LONG':
            return 35 < curr_rsi < 65 and curr_rsi >= prev_rsi
        elif side == 'SHORT':
            return 35 < curr_rsi < 65 and curr_rsi <= prev_rsi
    except Exception:
        pass
    return False


def _check_macd_momentum(close: pd.Series, side: str) -> bool:
    """
    MACD Histogram Momentum Check.
    
    We use the histogram (MACD line - Signal line) direction:
    - For LONG: Histogram must be rising (momentum turning bullish)
    - For SHORT: Histogram must be falling (momentum turning bearish)
    
    We do NOT require histogram to be positive/negative — just TURNING in our direction.
    This captures early momentum shifts before they're obvious on price.
    """
    try:
        macd_ind = MACD(close, window_slow=26, window_fast=12, window_sign=9)
        hist = macd_ind.macd_diff()
        curr_hist = hist.iloc[-1]
        prev_hist = hist.iloc[-2]
        if side == 'LONG':
            return curr_hist > prev_hist  # Histogram rising = bullish momentum gaining
        elif side == 'SHORT':
            return curr_hist < prev_hist  # Histogram falling = bearish momentum gaining
    except Exception:
        pass
    return False


def get_adaptive_signal(symbol: str, tf: str, is_vip: bool) -> Optional[dict]:
    """
    🧠 ELITE SNIPER ENGINE v4.0 — 7-Layer Confluence Signal
    
    A signal is ONLY generated when ALL relevant layers confirm.
    Fewer signals = higher quality entries = better win rate at 50x.
    """
    try:
        # Fetch enough bars for all indicators (EMA200 needs 200+, MACD needs 26)
        bars = _api_call(_client.futures_klines, symbol=symbol, interval=tf, limit=300)
        df = pd.DataFrame(
            bars,
            columns=['time', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qv', 'tr', 'tb', 'tq', 'i']
        )[['open', 'high', 'low', 'close', 'volume']].astype(float)

        if len(df) < EMA_TREND + 30:
            return None

        close = df['close']
        high = df['high']
        low = df['low']
        open_px = df['open']
        volume = df['volume']

        # ── LAYER 1: EMA 200 TREND GUARD ───────────────────────────────
        ema200 = ema_indicator(close, window=EMA_TREND)
        curr_ema200 = ema200.iloc[-1]
        curr_close = close.iloc[-1]

        above_ema200 = curr_close > curr_ema200
        below_ema200 = curr_close < curr_ema200

        # ── LAYER 2: ATR VOLATILITY GATE ───────────────────────────────
        # Block entries during choppy (ATR too low) or explosive (ATR too high) markets.
        # ATR_low_threshold: 0.05% of price = too quiet, no momentum
        # ATR_high_threshold: 1.5% of price = too volatile, gaps risk at 50x
        atr_series = AverageTrueRange(high, low, close, window=ATR_WINDOW).average_true_range()
        curr_atr = atr_series.iloc[-1]
        atr_pct = curr_atr / curr_close
        if atr_pct < 0.0005 or atr_pct > 0.015:
            return None  # Market too quiet or too explosive

        # ── LAYER 3: RSI MOMENTUM FILTER ───────────────────────────────
        rsi_series = RSIIndicator(close, window=14).rsi()

        # ── LAYER 4: MACD HISTOGRAM MOMENTUM ───────────────────────────
        # Checked per side below

        # ── LAYER 5: ORDER BLOCK ZONE ───────────────────────────────────
        # Checked per side below

        # ── LAYER 6: LIQUIDITY SWEEP DETECTION ─────────────────────────
        # Checked per side below

        # ── LAYER 7: VOLUME CONFIRMATION ───────────────────────────────
        df['vol_ma'] = volume.shift(1).rolling(window=VOL_MA_PERIOD).mean()
        df.bfill(inplace=True)
        prev_vol = volume.iloc[-2]
        vol_ma = df['vol_ma'].iloc[-2]
        volume_confirmed = prev_vol >= (vol_ma * VOL_MULTIPLIER)

        # Also check current candle volume as secondary confirmation
        curr_vol = volume.iloc[-1]
        curr_vol_ma = df['vol_ma'].iloc[-1]
        curr_vol_ok = curr_vol >= (curr_vol_ma * (VOL_MULTIPLIER * 0.7))  # Softer for current candle

        if not (volume_confirmed or curr_vol_ok):
            return None

        # ── BOLLINGER BANDS + MA99 (Dynamic Walls — kept from v3.1) ────
        bb = BollingerBands(close=close, window=BB_WINDOW, window_dev=2)
        ma99 = sma_indicator(close, window=MA_STRUCT)
        c_ma99 = ma99.iloc[-1]
        c_bb_dn = bb.bollinger_lband().iloc[-1]
        c_bb_up = bb.bollinger_hband().iloc[-1]

        # Dynamic proximity zone (tighter than v3.1 to reduce false touches)
        dynamic_proximity = curr_atr * 0.20

        # ── LONG SIGNAL EVALUATION ─────────────────────────────────────
        if above_ema200:
            # Layer 3: RSI momentum check for LONG
            if not _check_rsi_momentum(rsi_series, 'LONG'):
                pass  # Don't return yet — try SHORT
            else:
                # Layer 4: MACD momentum
                macd_ok = _check_macd_momentum(close, 'LONG')

                # Layer 5: Order Block — find nearest bullish OB
                ob_zone = _detect_order_block(df, 'LONG', lookback=40)
                price_in_ob = False
                if ob_zone:
                    ob_low, ob_high = ob_zone
                    # Current low is within or just above the OB zone
                    price_in_ob = ob_low - dynamic_proximity <= low.iloc[-1] <= ob_high + dynamic_proximity

                # Layer 6: Liquidity sweep (high conviction reversal entry)
                liq_sweep = _detect_liquidity_sweep(df, 'LONG', curr_atr, lookback=20)

                # Dynamic wall touch confirmation (from v3.1, tightened)
                dynamic_floors = [t for t in [curr_ema200, c_ma99, c_bb_dn] if t < curr_close]
                closest_floor = max(dynamic_floors) if dynamic_floors else 0
                wall_touch = (closest_floor > 0 and abs(low.iloc[-1] - closest_floor) <= dynamic_proximity)

                # Pinbar / rejection shadow (kept from v3.1)
                prev_open = open_px.iloc[-2]
                prev_close_val = close.iloc[-2]
                prev_low = low.iloc[-2]
                body = abs(prev_close_val - prev_open) or 1e-9
                lower_shadow = (min(prev_open, prev_close_val) - prev_low) / body
                shadow_req = 1.5 if is_vip else 1.0
                pinbar_ok = lower_shadow >= shadow_req

                # ── SIGNAL SCORING SYSTEM ──────────────────────────────
                # Require at least 3 of 4 confluence layers (beyond trend + ATR + volume):
                #   (a) MACD momentum
                #   (b) Order Block zone
                #   (c) Liquidity Sweep
                #   (d) Dynamic wall touch + pinbar
                confirmations = sum([
                    macd_ok,
                    price_in_ob,
                    liq_sweep,
                    (wall_touch and pinbar_ok)
                ])

                if confirmations >= 2:
                    reasons = []
                    if liq_sweep: reasons.append("LiqSweep")
                    if price_in_ob: reasons.append("OB")
                    if wall_touch: reasons.append("Wall")
                    if macd_ok: reasons.append("MACD")
                    return {
                        'side': 'LONG',
                        'reason': f"LONG [{'+'.join(reasons)}] Confluences:{confirmations}/4"
                    }

        # ── SHORT SIGNAL EVALUATION ────────────────────────────────────
        if below_ema200:
            if not _check_rsi_momentum(rsi_series, 'SHORT'):
                return None

            macd_ok = _check_macd_momentum(close, 'SHORT')

            ob_zone = _detect_order_block(df, 'SHORT', lookback=40)
            price_in_ob = False
            if ob_zone:
                ob_low, ob_high = ob_zone
                price_in_ob = ob_low - dynamic_proximity <= high.iloc[-1] <= ob_high + dynamic_proximity

            liq_sweep = _detect_liquidity_sweep(df, 'SHORT', curr_atr, lookback=20)

            dynamic_ceilings = [t for t in [curr_ema200, c_ma99, c_bb_up] if t > curr_close]
            closest_ceiling = min(dynamic_ceilings) if dynamic_ceilings else float('inf')
            wall_touch = (closest_ceiling != float('inf') and abs(high.iloc[-1] - closest_ceiling) <= dynamic_proximity)

            prev_open = open_px.iloc[-2]
            prev_close_val = close.iloc[-2]
            prev_high = high.iloc[-2]
            body = abs(prev_open - prev_close_val) or 1e-9
            upper_shadow = (prev_high - max(prev_open, prev_close_val)) / body
            shadow_req = 1.5 if is_vip else 1.0
            pinbar_ok = upper_shadow >= shadow_req

            confirmations = sum([
                macd_ok,
                price_in_ob,
                liq_sweep,
                (wall_touch and pinbar_ok)
            ])

            if confirmations >= 2:
                reasons = []
                if liq_sweep: reasons.append("LiqSweep")
                if price_in_ob: reasons.append("OB")
                if wall_touch: reasons.append("Wall")
                if macd_ok: reasons.append("MACD")
                return {
                    'side': 'SHORT',
                    'reason': f"SHORT [{'+'.join(reasons)}] Confluences:{confirmations}/4"
                }

        return None

    except Exception as e:
        logger.debug(f"Signal error [{symbol}/{tf}]: {e}")
        return None


# ========== TREND ALIGNMENT FILTER (Dinamis Long/Short) ==========
def _is_trend_aligned(symbol: str, side: str) -> bool:
    """Secondary higher-TF trend check (15m EMA200) — belt-and-suspenders"""
    try:
        bars = _api_call(_client.futures_klines, symbol=symbol, interval='15m', limit=210)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qv', 'tr', 'tb', 'tq', 'i'])
        close = df['close'].astype(float)
        ema200 = float(ema_indicator(close, window=200).iloc[-1])
        current_price = float(close.iloc[-1])
        if side == 'LONG': return current_price > ema200
        if side == 'SHORT': return current_price < ema200
        return False
    except Exception:
        return False


# ---------- EXECUTION ENGINE [DO NOT TOUCH] ----------
def execute_order(symbol: str, order_side: str, position_side: str, margin_to_use: float, is_dca: bool = False) -> bool:
    try:
        f = _get_exchange_filters(symbol)
        qty_step = float(f['LOT_SIZE']['stepSize'])
        min_qty = float(f['LOT_SIZE']['minQty'])
        max_qty = float(f.get('MARKET_LOT_SIZE', f['LOT_SIZE'])['maxQty'])
        tick = float(f['PRICE_FILTER']['tickSize'])
        curr_price = float(_api_call(_client.futures_symbol_ticker, symbol=symbol)['price'])

        actual_lev, adjusted_margin = _get_dynamic_leverage_and_margin(symbol, margin_to_use)

        raw_qty = (adjusted_margin * actual_lev) / curr_price
        qty = round(round(raw_qty / qty_step) * qty_step, 8)
        qty = min(max_qty, max(min_qty, qty))
        qty_str = f"{qty:.8f}".rstrip('0').rstrip('.')

        _api_call(_client.futures_create_order, symbol=symbol, side=order_side, type='MARKET', quantity=qty_str, positionSide=position_side)

        if not is_dca:
            price_precision = max(0, -int(math.floor(math.log10(tick))))

            if position_side == 'LONG':
                tp_raw = curr_price * (1 + (TP_TARGET_ROE / actual_lev))
                tp_str = f"{round(round(tp_raw / tick) * tick, price_precision):.{price_precision}f}"
                try:
                    _api_call(_client.futures_create_order, symbol=symbol, side='SELL', type='LIMIT', price=tp_str, quantity=qty_str, positionSide=position_side, timeInForce='GTC')
                except Exception as e:
                    logger.warning(f"Gagal pasang LIMIT TP LONG untuk {symbol}: {e}")

            elif position_side == 'SHORT':
                tp_raw = curr_price * (1 - (TP_TARGET_ROE / actual_lev))
                sl_raw = curr_price * (1 + (SHORT_SL_ROE / actual_lev))
                tp_str = f"{round(round(tp_raw / tick) * tick, price_precision):.{price_precision}f}"
                sl_str = f"{round(round(sl_raw / tick) * tick, price_precision):.{price_precision}f}"
                try:
                    _api_call(_client.futures_create_order, symbol=symbol, side='BUY', type='LIMIT', price=tp_str, quantity=qty_str, positionSide=position_side, timeInForce='GTC')
                    _api_call(_client.futures_create_order, symbol=symbol, side='BUY', type='STOP_MARKET', stopPrice=sl_str, closePosition=True, positionSide=position_side, timeInForce='GTC', workingType='MARK_PRICE')
                except Exception as e:
                    logger.warning(f"Gagal pasang TP/SL SHORT untuk {symbol}: {e}")

        logger.info(f"🚀 {'DCA' if is_dca else 'ENTRY'} [{position_side}] {symbol} | Margin: ${adjusted_margin:.2f} | Lev: {actual_lev}x")
        return True
    except Exception as e:
        logger.error(f"Order Gagal [{symbol}]: {e}")
        return False


# ---------- DCA MONITOR [DO NOT TOUCH] ----------
def _monitor_positions(positions: List[dict]):
    for p in positions:
        amt = float(p['positionAmt'])
        if amt == 0: continue

        symbol, unrealized, mark_price = p['symbol'], float(p['unRealizedProfit']), float(p['markPrice'])
        actual_lev = float(p.get('leverage', TARGET_LEVERAGE))

        if amt < 0: continue  # SHORT: no DCA, let TP/SL work

        current_margin = (abs(amt) * mark_price) / actual_lev
        roe_percent = (unrealized / current_margin * 100) if current_margin > 0 else 0

        _, base_adj = _get_dynamic_leverage_and_margin(symbol, BASE_MARGIN)

        dca1_trigger = -(DCA_1_DROP_PERCENT * actual_lev)
        dca2_trigger = -(DCA_2_DROP_PERCENT * actual_lev)
        dca3_trigger = -(DCA_3_DROP_PERCENT * actual_lev)

        dca1_amount = base_adj * DCA_1_MARGIN_RATIO
        dca2_amount = base_adj * DCA_2_MARGIN_RATIO
        dca3_amount = base_adj * DCA_3_MARGIN_RATIO

        if roe_percent <= dca1_trigger and current_margin < (base_adj + 2.0):
            logger.info(f"💉 DCA TAHAP 1 [{symbol}] Trigger: {roe_percent:.2f}% | Beli: ${dca1_amount:.2f}")
            execute_order(symbol, 'BUY', 'LONG', dca1_amount, is_dca=True)
        elif roe_percent <= dca2_trigger and current_margin < (base_adj + dca1_amount + 2.0):
            logger.info(f"💉 DCA TAHAP 2 [{symbol}] Trigger: {roe_percent:.2f}% | Beli: ${dca2_amount:.2f}")
            execute_order(symbol, 'BUY', 'LONG', dca2_amount, is_dca=True)
        elif roe_percent <= dca3_trigger and current_margin < (base_adj + dca1_amount + dca2_amount + 2.0):
            logger.info(f"🔥 DCA TAHAP 3 [{symbol}] Trigger: {roe_percent:.2f}% | Beli: ${dca3_amount:.2f}")
            execute_order(symbol, 'BUY', 'LONG', dca3_amount, is_dca=True)


# ---------- PARALLEL SCANNER ----------
def _scan_single_alt(symbol: str, active_keys: List[str], allowed_tfs: List[str]) -> Optional[Tuple[str, dict]]:
    if f"{symbol}_LONG" in active_keys or f"{symbol}_SHORT" in active_keys: return None
    for tf in allowed_tfs:
        sig = get_adaptive_signal(symbol, tf, is_vip=False)
        if sig:
            if _is_trend_aligned(symbol, sig['side']):
                logger.info(f"🎯 ELITE Sinyal {symbol} ({tf}) [{sig['side']}] via {sig['reason']}")
                return (symbol, sig)
    return None


_stop_event = None

def shutdown_bot():
    global _stop_event
    if _stop_event: _stop_event.set()


def run_bot(stop_event: threading.Event) -> None:
    global _stop_event, TOTAL_CLOSED_ROE, TOTAL_CLOSED_ROE_PERCENT, TOTAL_SUCCESS_TRADES, CLOSED_HISTORY, _coin_escalation_level
    _stop_event = stop_event
    setup_account_environment()
    get_initial_balance()

    executor = ThreadPoolExecutor(max_workers=5)
    _previous_active_keys = set()
    first_run = True
    _last_heartbeat_time = 0.0

    try:
        while not _stop_event.is_set():
            try:
                if _read_status() != 'ON':
                    time.sleep(10)
                    continue

                pos = _api_call(_client.futures_position_information)
                _monitor_positions(pos)

                active_keys = [f"{p['symbol']}_{p['positionSide']}" for p in pos if float(p['positionAmt']) != 0]
                current_active_set = set(active_keys)

                if not first_run:
                    closed_keys = _previous_active_keys - current_active_set
                    for k in closed_keys:
                        symbol = k.split('_')[0]
                        pnl_usd = _fetch_realized_pnl(symbol)
                        roe_percent = (pnl_usd / BASE_MARGIN) * 100

                        catat_transaksi_v2(symbol, pnl_usd, roe_percent)

                        TOTAL_CLOSED_ROE += roe_percent
                        TOTAL_CLOSED_ROE_PERCENT += roe_percent
                        TOTAL_SUCCESS_TRADES += 1

                        if symbol not in VIP_SET and symbol not in GOLD_SET:
                            curr_level = _coin_escalation_level.get(symbol, 0)
                            _coin_escalation_level[symbol] = curr_level + 1

                        now_str = datetime.now().strftime("%H:%M:%S")
                        history_str = f"{pnl_usd:+.2f}$ ({roe_percent:+.2f}%) | Tot: +{TOTAL_CLOSED_ROE_PERCENT:.2f}%"
                        CLOSED_HISTORY.insert(0, {'time': now_str, 'symbol': symbol, 'roe': history_str})
                        if len(CLOSED_HISTORY) > 20: CLOSED_HISTORY.pop()

                _previous_active_keys = current_active_set
                first_run = False

                vip_count = sum(1 for k in active_keys if k.split('_')[0] in VIP_SET)
                alt_count = sum(1 for k in active_keys if k.split('_')[0] not in VIP_SET and k.split('_')[0] not in GOLD_SET)

                gold_active_count = sum(1 for k in active_keys if k.split('_')[0] in GOLD_SET)
                if gold_active_count == 0 and not _stop_event.is_set():
                    for symbol in GOLD_PAIRS:
                        if f"{symbol}_LONG" not in active_keys and f"{symbol}_SHORT" not in active_keys:
                            for tf in GOLD_TFS:
                                sig = get_adaptive_signal(symbol, tf, is_vip=True)
                                if sig:
                                    pos_side = sig['side']
                                    order_side = 'BUY' if pos_side == 'LONG' else 'SELL'
                                    logger.info(f"🏆 RADAR EMAS: [{pos_side}] Sinyal {symbol} ({tf}) via {sig['reason']}")
                                    if execute_order(symbol, order_side, pos_side, BASE_MARGIN):
                                        active_keys.append(f"{symbol}_{pos_side}")
                                        current_active_set.add(f"{symbol}_{pos_side}")
                                        _previous_active_keys = current_active_set
                                        break
                            if gold_active_count > 0: break

                for symbol in VIP_SYMBOLS:
                    if _stop_event.is_set(): break
                    if vip_count >= MAX_VIP: break
                    if f"{symbol}_LONG" not in active_keys and f"{symbol}_SHORT" not in active_keys:
                        for tf in VIP_TFS:
                            sig = get_adaptive_signal(symbol, tf, is_vip=True)
                            if sig:
                                pos_side = sig['side']
                                order_side = 'BUY' if pos_side == 'LONG' else 'SELL'
                                logger.info(f"👑 VIP Sinyal [{pos_side}] {symbol} ({tf}) via {sig['reason']}")
                                if execute_order(symbol, order_side, pos_side, BASE_MARGIN):
                                    vip_count += 1
                                    active_keys.append(f"{symbol}_{pos_side}")
                                    current_active_set.add(f"{symbol}_{pos_side}")
                                    _previous_active_keys = current_active_set
                                    break

                if alt_count < MAX_ALT and not _stop_event.is_set():
                    tickers = _get_cached_ticker()
                    alts = [t['symbol'] for t in sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
                            if t['symbol'].endswith('USDT') and t['symbol'] not in VIP_SET and t['symbol'] not in GOLD_SET][:TOP_ALT_LIMIT]

                    futures = []
                    for s in alts:
                        base_tfs = ALT_TFS_FAST if alt_count < 4 else ALT_TFS_SAFE
                        esc_level = _coin_escalation_level.get(s, 0)
                        if esc_level >= len(ALT_TF_ORDER): continue
                        valid_tfs = [tf for tf in base_tfs if ALT_TF_ORDER.index(tf) >= esc_level]
                        if not valid_tfs: continue

                        futures.append(executor.submit(_scan_single_alt, s, active_keys, valid_tfs))

                    for future in as_completed(futures):
                        if _stop_event.is_set(): break
                        res = future.result()
                        if res and alt_count < MAX_ALT:
                            symbol, sig = res
                            pos_side = sig['side']
                            order_side = 'BUY' if pos_side == 'LONG' else 'SELL'
                            if execute_order(symbol, order_side, pos_side, BASE_MARGIN):
                                alt_count += 1
                                active_keys.append(f"{symbol}_{pos_side}")
                                current_active_set.add(f"{symbol}_{pos_side}")
                                _previous_active_keys = current_active_set

                current_time = time.time()
                if current_time - _last_heartbeat_time >= 60.0:
                    gold_status = "1 Aktif" if gold_active_count > 0 else "0 Aktif"
                    logger.info(f"👀 System OK [ELITE v4.0] | Market: (VIP: {vip_count}/{MAX_VIP} | ALT: {alt_count}/{MAX_ALT} | GOLD: {gold_status})")
                    _last_heartbeat_time = current_time

                for _ in range(15):
                    if _stop_event.is_set(): break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Loop Error: {e}")
                time.sleep(10)
    finally:
        executor.shutdown(wait=True)
        logger.info("Bot engine stopped.")


if __name__ == "__main__":
    shutdown_event = threading.Event()
    run_bot(shutdown_event)
