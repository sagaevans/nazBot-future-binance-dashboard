# ==========================================
# BETA v2.0 — Sniper System
# FILE: bot_logic.py
# FUNGSI: Escalation Timeframe (Anti-Pingpong), 8-Column Ledger, & Gold Radar
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

import pandas as pd
from ta.trend import ema_indicator, sma_indicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.momentum import RSIIndicator
from binance.client import Client
from binance.exceptions import BinanceAPIException

logger = logging.getLogger('bot')

API_KEY = os.environ.get('BINANCE_API_KEY', '')
API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

# --- PENGATURAN MUTLAK PRO ---
TARGET_LEVERAGE = 50
BASE_MARGIN = 5.0
TP_TARGET_ROE = 0.50   # Target 50% ROE (Hit & Run)

# --- PENGATURAN DCA DINAMIS ---
DCA_1_DROP_PERCENT = 2.0  
DCA_2_DROP_PERCENT = 3.0  
DCA_3_DROP_PERCENT = 4.0  

DCA_1_MARGIN_RATIO = 0.50  
DCA_2_MARGIN_RATIO = 0.50  
DCA_3_MARGIN_RATIO = 1.00  

MAX_VIP, MAX_ALT = 8, 8
EMA_TREND, MA_STRUCT, BB_WINDOW, VOL_LOOKBACK = 200, 99, 20, 5
ATR_WINDOW = 14

VIP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT", "XRPUSDT", "ALICEUSDT"]
VIP_SET = set(VIP_SYMBOLS)
VIP_TFS = ['15m', '1h', '4h']

# --- PEMBAGIAN TIMEFRAME & ESCALATION (BETA 2.0) ---
ALT_TFS_FAST = ['5m', '15m', '1h', '4h']
ALT_TFS_SAFE = ['15m', '1h', '4h']
ALT_TF_ORDER = ['5m', '15m', '1h', '4h'] # Kasta hierarki Timeframe

TOP_ALT_LIMIT = 50
STATE_FILE = 'status.txt'

# --- FITUR EMAS (SINGLE EXPOSURE) ---
GOLD_PAIRS = ["XAUUSDT", "XAUTUSDT", "PAXGUSDT"]
GOLD_SET = set(GOLD_PAIRS)
GOLD_TFS = ['15m', '1h', '4h']

# --- LEDGER SETTINGS (8 KOLOM) ---
LEDGER_FILE = 'profit_ledger.txt'
START_BALANCE = 5000.0 # Patokan untuk perhitungan Growth %

# --- VARIABEL GLOBAL PAPAN SKOR ---
TOTAL_CLOSED_ROE = 0.0
TOTAL_CLOSED_ROE_PERCENT = 0.0 # Running total angka murni
TOTAL_SUCCESS_TRADES = 0
CLOSED_HISTORY = []
_coin_escalation_level: Dict[str, int] = {} # Buku hitam anti-pingpong

_client = Client(API_KEY, API_SECRET, testnet=True) # Ganti testnet=False untuk real account

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
            if e.code in (-4028, -2011, -2021):
                raise
            time.sleep(2 ** attempt + random.uniform(0, 1))
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API Error: {fn.__name__}")

# ========== FUNGSI LEDGER 8 KOLOM (BETA 2.0) ==========
def get_binance_balance() -> float:
    """Mengambil Saldo USDT Riil di Dompet Futures."""
    try:
        account_info = _api_call(_client.futures_account)
        for asset in account_info.get('assets', []):
            if asset['asset'] == 'USDT':
                return float(asset['walletBalance'])
    except Exception as e:
        logger.error(f"Gagal ambil saldo riil Binance: {e}")
    return 0.0

def _fetch_realized_pnl(symbol: str) -> float:
    """Mengambil data PnL Riil dari transaksi koin yang baru di-close."""
    try:
        income_data = _api_call(_client.futures_income_history, symbol=symbol, incomeType="REALIZED_PNL", limit=1)
        if income_data:
            return float(income_data[0]['income'])
    except Exception:
        pass
    return (BASE_MARGIN * TP_TARGET_ROE) # Estimasi fallback jika API limit

def get_last_ledger_totals() -> Tuple[float, float]:
    """Membaca Akumulasi Total PnL dan ROE dari baris terakhir."""
    if not os.path.exists(LEDGER_FILE) or os.path.getsize(LEDGER_FILE) == 0:
        return 0.0, 0.0
    try:
        with open(LEDGER_FILE, 'r') as f:
            lines = [l for l in f.readlines() if '|' in l and 'TIME' not in l and '---' not in l]
            if not lines:
                return 0.0, 0.0
            last_line = lines[-1]
            parts = [p.strip() for p in last_line.split('|')]
            if len(parts) >= 8:
                tot_pnl = float(parts[4].replace('$', '').replace('+', ''))
                tot_roe = float(parts[5].replace('%', '').replace('+', ''))
                return tot_pnl, tot_roe
    except:
        pass
    return 0.0, 0.0

def catat_transaksi_v2(symbol: str, pnl_usd: float, roe_percent: float):
    """Mencatat format 8 Kolom Ledger (Running Total + Saldo Riil)."""
    prev_tot_pnl, prev_tot_roe = get_last_ledger_totals()
    new_tot_pnl = prev_tot_pnl + pnl_usd
    new_tot_roe = prev_tot_roe + roe_percent
    
    current_balance = get_binance_balance()
    growth_pct = ((current_balance - START_BALANCE) / START_BALANCE) * 100 if START_BALANCE > 0 else 0.0
    
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
    except Exception:
        pass
    return 'OFF'

def setup_account_environment() -> None:
    try:
        _client.futures_change_position_mode(dualSidePosition=True)
    except Exception:
        pass

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
            except Exception:
                return TARGET_LEVERAGE, target_margin
        return TARGET_LEVERAGE, target_margin
    except Exception:
        return TARGET_LEVERAGE, target_margin

# ========== TREND ALIGNMENT FILTER (15m EMA200) ==========
def _is_trend_aligned(symbol: str) -> bool:
    try:
        bars = _api_call(_client.futures_klines, symbol=symbol, interval='15m', limit=210)
        df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume','ct','qv','tr','tb','tq','i'])
        close = df['close'].astype(float)
        ema200 = ema_indicator(close, window=200)
        current_price = float(close.iloc[-1])
        current_ema200 = float(ema200.iloc[-1])
        return current_price > current_ema200
    except Exception as e:
        logger.warning(f"Trend filter error for {symbol}: {e}")
        return False

# ========== PRO SIGNAL LOGIC (ATR & 4 WALLS) ==========
def get_adaptive_signal(symbol: str, tf: str, is_vip: bool) -> Optional[dict]:
    try:
        bars = _api_call(_client.futures_klines, symbol=symbol, interval=tf, limit=300)
        df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume','ct','qv','tr','tb','tq','i'])[['open','high','low','close','volume']].astype(float)

        if len(df) < EMA_TREND + 1:
            return None

        close, high, low = df['close'], df['high'], df['low']
        ema200 = ema_indicator(close, window=EMA_TREND)
        ma99 = sma_indicator(close, window=MA_STRUCT)
        bb = BollingerBands(close=close, window=BB_WINDOW, window_dev=2)
        rsi = RSIIndicator(close, window=14).rsi()
        atr = AverageTrueRange(high, low, close, window=ATR_WINDOW).average_true_range()

        df['vol_ma'] = df['volume'].shift(1).rolling(window=VOL_LOOKBACK).mean()
        df.bfill(inplace=True)

        idx_curr, idx_prev = len(df) - 1, len(df) - 2
        c_close, c_low, c_atr = close.iat[idx_curr], low.iat[idx_curr], atr.iat[idx_curr]
        p_open, p_close, p_low = df['open'].iat[idx_prev], close.iat[idx_prev], low.iat[idx_prev]

        if df['volume'].iat[idx_prev] >= df['vol_ma'].iat[idx_prev]:
            return None

        if p_close <= p_open:
            return None
        body = abs(p_close - p_open) or 0.00000001
        shadow_req = 2.0 if is_vip else 1.2
        if ((min(p_open, p_close) - p_low) / body) < shadow_req:
            return None

        dynamic_proximity = c_atr * 0.15

        c_ema200, c_ma99, c_bb_dn = ema200.iat[idx_curr], ma99.iat[idx_curr], bb.bollinger_lband().iat[idx_curr]
        dynamic_floors = [t for t in [c_ema200, c_ma99, c_bb_dn] if t < c_close]
        closest_dynamic = max(dynamic_floors) if dynamic_floors else 0
        hit_dynamic = closest_dynamic > 0 and (abs(c_low - closest_dynamic)) <= dynamic_proximity

        static_support = low.iloc[-100:-5].min()
        hit_static = static_support > 0 and (abs(c_low - static_support)) <= dynamic_proximity

        if hit_dynamic or hit_static:
            reason = "Dynamic Wall" if hit_dynamic else "Static Support"
            if rsi.iat[idx_curr] < 35:
                reason += " + OVERSOLD"
            return {'side': 'LONG', 'reason': reason}

        return None
    except Exception:
        return None

# ---------- EXECUTION ENGINE ----------
def execute_order(symbol: str, side: str, position_side: str, margin_to_use: float, is_dca: bool = False) -> bool:
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

        _api_call(_client.futures_create_order, symbol=symbol, side=side, type='MARKET', quantity=qty_str, positionSide=position_side)

        if not is_dca:
            tp_raw = curr_price * (1 + (TP_TARGET_ROE / actual_lev))
            price_precision = max(0, -int(math.floor(math.log10(tick))))
            tp_str = f"{round(round(tp_raw / tick) * tick, price_precision):.{price_precision}f}"
            try:
                _api_call(_client.futures_create_order, symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET', stopPrice=tp_str, closePosition=True, positionSide=position_side, timeInForce='GTE_GTC', workingType='MARK_PRICE')
            except Exception:
                _api_call(_client.futures_create_order, symbol=symbol, side='SELL', type='LIMIT', price=tp_str, quantity=qty_str, positionSide=position_side, timeInForce='GTC')

        logger.info(f"🚀 {'DCA' if is_dca else 'ENTRY'} [{symbol}] Margin Terpakai: ${adjusted_margin:.2f} | Lev: {actual_lev}x")
        return True
    except Exception as e:
        logger.error(f"Order Gagal [{symbol}]: {e}")
        return False

# ---------- DCA MONITOR ----------
def _monitor_positions(positions: List[dict]):
    for p in positions:
        amt = float(p['positionAmt'])
        if amt == 0:
            continue
        symbol, unrealized, mark_price = p['symbol'], float(p['unRealizedProfit']), float(p['markPrice'])
        actual_lev = float(p.get('leverage', TARGET_LEVERAGE))

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
            logger.info(f"💉 DCA TAHAP 1 [{symbol}] Triggered at ROE {roe_percent:.2f}% | Target Suntikan: ${dca1_amount:.2f}")
            execute_order(symbol, 'BUY', 'LONG', dca1_amount, is_dca=True)

        elif roe_percent <= dca2_trigger and current_margin < (base_adj + dca1_amount + 2.0):
            logger.info(f"💉 DCA TAHAP 2 [{symbol}] Triggered at ROE {roe_percent:.2f}% | Target Suntikan: ${dca2_amount:.2f}")
            execute_order(symbol, 'BUY', 'LONG', dca2_amount, is_dca=True)

        elif roe_percent <= dca3_trigger and current_margin < (base_adj + dca1_amount + dca2_amount + 2.0):
            logger.info(f"🔥 DCA TAHAP 3 TERAKHIR [{symbol}] Triggered at ROE {roe_percent:.2f}% | Target Suntikan: ${dca3_amount:.2f}")
            execute_order(symbol, 'BUY', 'LONG', dca3_amount, is_dca=True)

# ---------- PARALLEL SCANNER ----------
def _scan_single_alt(symbol: str, active_keys: List[str], allowed_tfs: List[str]) -> Optional[Tuple[str, dict]]:
    if f"{symbol}_LONG" in active_keys:
        return None
    for tf in allowed_tfs:
        sig = get_adaptive_signal(symbol, tf, is_vip=False)
        if sig:
            if _is_trend_aligned(symbol):
                logger.info(f"🎯 PRO Sinyal {symbol} ({tf}) via {sig['reason']} | Trend aligned")
                return (symbol, sig)
    return None

# Global shutdown flag
_stop_event = None

def shutdown_bot():
    global _stop_event
    if _stop_event:
        _stop_event.set()

def run_bot(stop_event: threading.Event) -> None:
    global _stop_event, TOTAL_CLOSED_ROE, TOTAL_CLOSED_ROE_PERCENT, TOTAL_SUCCESS_TRADES, CLOSED_HISTORY, _coin_escalation_level
    _stop_event = stop_event
    setup_account_environment()

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

                # --- LOGIKA SAKSI BISU, ESCALATION TIER, & PENULISAN LEDGER ---
                if not first_run:
                    closed_keys = _previous_active_keys - current_active_set
                    for k in closed_keys:
                        symbol = k.split('_')[0]
                        
                        # 1. Ambil PnL Riil untuk Ledger
                        pnl_usd = _fetch_realized_pnl(symbol)
                        roe_percent = (pnl_usd / BASE_MARGIN) * 100 # Kalkulasi persen kembalian ROE bersih
                        
                        # 2. Catat ke Ledger 8 Kolom
                        catat_transaksi_v2(symbol, pnl_usd, roe_percent)
                        
                        # 3. Update Papan Skor Global
                        TOTAL_CLOSED_ROE += roe_percent
                        TOTAL_CLOSED_ROE_PERCENT += roe_percent
                        TOTAL_SUCCESS_TRADES += 1

                        # 4. ANTI-PINGPONG: Naikkan kasta Timeframe setelah TP (Bukan VIP & Bukan GOLD)
                        if symbol not in VIP_SET and symbol not in GOLD_SET:
                            curr_level = _coin_escalation_level.get(symbol, 0)
                            _coin_escalation_level[symbol] = curr_level + 1
                            logger.info(f"📈 [ANTI-PINGPONG] {symbol} selesai! Naik level ke indeks TF: {_coin_escalation_level[symbol]}")

                        now_str = datetime.now().strftime("%H:%M:%S")
                        history_str = f"{pnl_usd:+.2f}$ ({roe_percent:+.2f}%) | Tot: +{TOTAL_CLOSED_ROE_PERCENT:.2f}%"
                        CLOSED_HISTORY.insert(0, {'time': now_str, 'symbol': symbol, 'roe': history_str})

                        if len(CLOSED_HISTORY) > 20:
                            CLOSED_HISTORY.pop()

                _previous_active_keys = current_active_set
                first_run = False

                vip_count = sum(1 for k in active_keys if k.split('_')[0] in VIP_SET)
                alt_count = sum(1 for k in active_keys if k.split('_')[0] not in VIP_SET and k.split('_')[0] not in GOLD_SET)

                # --- RADAR EMAS (SINGLE EXPOSURE RULE) ---
                gold_active_count = sum(1 for k in active_keys if k.split('_')[0] in GOLD_SET)
                if gold_active_count == 0 and not _stop_event.is_set():
                    for symbol in GOLD_PAIRS:
                        if f"{symbol}_LONG" not in active_keys:
                            for tf in GOLD_TFS:
                                sig = get_adaptive_signal(symbol, tf, is_vip=True)
                                if sig:
                                    logger.info(f"🏆 RADAR EMAS: Sinyal {symbol} ({tf}) via {sig['reason']}")
                                    if execute_order(symbol, 'BUY', 'LONG', BASE_MARGIN):
                                        active_keys.append(f"{symbol}_LONG")
                                        current_active_set.add(f"{symbol}_LONG")
                                        _previous_active_keys = current_active_set
                                        break # Hentikan pencarian koin emas lainnya (Single Exposure)
                            if gold_active_count > 0: break # Mencegah loop iterasi ke gold selanjutnya jika sudah ada yg masuk

                # --- VIP SCAN ---
                for symbol in VIP_SYMBOLS:
                    if _stop_event.is_set(): break
                    if vip_count >= MAX_VIP: break
                    if f"{symbol}_LONG" not in active_keys:
                        for tf in VIP_TFS:
                            sig = get_adaptive_signal(symbol, tf, is_vip=True)
                            if sig:
                                logger.info(f"👑 VIP Sinyal {symbol} ({tf}) via {sig['reason']}")
                                if execute_order(symbol, 'BUY', 'LONG', BASE_MARGIN):
                                    vip_count += 1
                                    active_keys.append(f"{symbol}_LONG")
                                    current_active_set.add(f"{symbol}_LONG")
                                    _previous_active_keys = current_active_set
                                    break

                # --- ALT SCAN (DENGAN ESCALATION KASTA) ---
                if alt_count < MAX_ALT and not _stop_event.is_set():
                    tickers = _get_cached_ticker()
                    # Filter: Tidak termasuk VIP_SET dan GOLD_SET
                    alts = [t['symbol'] for t in sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
                            if t['symbol'].endswith('USDT') and t['symbol'] not in VIP_SET and t['symbol'] not in GOLD_SET][:TOP_ALT_LIMIT]

                    futures = []
                    for s in alts:
                        if f"{s}_LONG" in active_keys: continue

                        base_tfs = ALT_TFS_FAST if alt_count < 4 else ALT_TFS_SAFE
                        esc_level = _coin_escalation_level.get(s, 0)

                        if esc_level >= len(ALT_TF_ORDER):
                            continue

                        valid_tfs = [tf for tf in base_tfs if ALT_TF_ORDER.index(tf) >= esc_level]

                        if not valid_tfs:
                            continue 

                        futures.append(executor.submit(_scan_single_alt, s, active_keys, valid_tfs))

                    for future in as_completed(futures):
                        if _stop_event.is_set(): break
                        res = future.result()
                        if res and alt_count < MAX_ALT:
                            symbol, sig = res
                            if execute_order(symbol, 'BUY', 'LONG', BASE_MARGIN):
                                alt_count += 1
                                active_keys.append(f"{symbol}_LONG")
                                current_active_set.add(f"{symbol}_LONG")
                                _previous_active_keys = current_active_set

                # --- HEARTBEAT LOGIC ---
                current_time = time.time()
                if current_time - _last_heartbeat_time >= 60.0:
                    gold_status = "1 Aktif" if gold_active_count > 0 else "0 Aktif"
                    logger.info(f"👀 System OK [BETA v2.0] | Market: (VIP: {vip_count}/{MAX_VIP} | ALT: {alt_count}/{MAX_ALT} | GOLD: {gold_status})")
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
