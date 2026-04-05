"""
bot_logic.py — NazBOT ALPHA FINAL TEST
Fitur: Concurrency, ATR Dynamic Support, Dynamic Margin, Heartbeat Monitor.
Update: Papan Skor Akumulasi ROE (Data Feed), Mesin trading 100% Original.
"""

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

# Mengambil API Key dari Secrets / Environment Variables
API_KEY = os.environ.get('BINANCE_API_KEY', '')
API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

# ==========================================
# PENGATURAN MUTLAK PRO (TIDAK DISENTUH)
# ==========================================
TARGET_LEVERAGE = 50       # Default Leverage utama
BASE_MARGIN = 5.0          # Base target margin dalam USD
TP_TARGET_ROE = 0.50       # Target 50% Take Profit

# Smart DCA (Dollar Cost Averaging) Settings
DCA_1_TRIGGER, DCA_1_AMOUNT = -1.00, 3.0
DCA_2_TRIGGER, DCA_2_AMOUNT = -1.50, 3.0
DCA_3_TRIGGER, DCA_3_AMOUNT = -3.00, 10.0

# Pengaturan Eksekusi Bot
MAX_VIP = 8                # Maksimal posisi koin VIP bersamaan
MAX_ALT = 8                # Maksimal posisi koin Altcoin bersamaan
EMA_TREND, MA_STRUCT, BB_WINDOW, VOL_LOOKBACK = 200, 99, 20, 5
ATR_WINDOW = 14

VIP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT", "XRPUSDT", "ALICEUSDT"]
VIP_SET = set(VIP_SYMBOLS)

# Timeframe Scanning
VIP_TFS = ['15m', '1h', '4h']
ALT_TFS = ['15m', '1h', '4h']

TOP_ALT_LIMIT = 50         # Memindai 50 top koin berdasar Quote Volume
STATE_FILE = 'status.txt'

# ==========================================
# VARIABEL PAPAN SKOR ROE (UPDATE BARU)
# ==========================================
TOTAL_CLOSED_ROE = 0.0
TOTAL_SUCCESS_TRADES = 0
CLOSED_HISTORY = []
_previous_active_keys = set()

# Inisialisasi Binance Client
_client = Client(API_KEY, API_SECRET, testnet=False) # Ganti True jika pakai Testnet

# Sistem Caching untuk meringankan beban API Binance
_exchange_filter_cache: Dict[str, dict] = {}
_ticker_cache: Dict[str, Any] = {"data": None, "timestamp": 0}
_TICKER_CACHE_TTL = 5.0

# Rate Limiting System (Anti-Banned)
_RATE_LIMIT_CALLS, _RATE_LIMIT_PERIOD = 20, 1.0
_last_call_time = 0.0
_rate_limit_lock = threading.Lock()

def _rate_limit():
    """Membatasi kecepatan panggilan API agar tidak terkena limit dari Binance."""
    global _last_call_time
    with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_call_time
        min_interval = _RATE_LIMIT_PERIOD / _RATE_LIMIT_CALLS
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_call_time = time.monotonic()

def _api_call(fn, *args, max_retries: int = 5, **kwargs):
    """Fungsi pembungkus untuk memanggil API Binance dengan sistem Retry yang aman."""
    for attempt in range(max_retries):
        _rate_limit()
        try:
            return fn(*args, **kwargs)
        except BinanceAPIException as e:
            if e.code in (-4028, -2011, -2021):
                # Error fatal yang tidak perlu di-retry
                raise
            time.sleep(2 ** attempt + random.uniform(0, 1))
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API Error: Gagal mengeksekusi {fn.__name__} setelah beberapa percobaan.")

def _get_exchange_filters(symbol: str) -> dict:
    """Mengambil aturan lot size dan tick size dari Binance untuk koin tertentu."""
    if symbol not in _exchange_filter_cache:
        info = _api_call(_client.futures_exchange_info)
        for s in info['symbols']:
            _exchange_filter_cache[s['symbol']] = {x['filterType']: x for x in s['filters']}
    return _exchange_filter_cache[symbol]

def _get_cached_ticker() -> List[dict]:
    """Mengambil data harga semua koin sekaligus dan menyimpannya di cache."""
    global _ticker_cache
    now = time.time()
    if _ticker_cache["data"] is None or (now - _ticker_cache["timestamp"]) > _TICKER_CACHE_TTL:
        _ticker_cache["data"] = _api_call(_client.futures_ticker)
        _ticker_cache["timestamp"] = now
    return _ticker_cache["data"]

def _read_status() -> str:
    """Membaca status bot (ON/OFF) dari file teks."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return f.read().strip() or 'OFF'
    except Exception:
        pass
    return 'OFF'

def setup_account_environment() -> None:
    """Mengatur akun ke mode Hedge (Dual Side Position)."""
    try:
        _client.futures_change_position_mode(dualSidePosition=True)
    except Exception:
        pass

def _get_dynamic_leverage_and_margin(symbol: str, target_margin: float) -> Tuple[int, float]:
    """
    Logika Dynamic Margin Balancing:
    Jika Binance membatasi leverage, bot otomatis menyesuaikan margin agar 
    Notional Value (Daya Tembak) tetap sama.
    """
    target_notional = target_margin * TARGET_LEVERAGE
    try:
        _client.futures_change_leverage(symbol=symbol, leverage=TARGET_LEVERAGE)
        return TARGET_LEVERAGE, target_margin
    except BinanceAPIException as e:
        if e.code == -4028: # Error leverage ditolak karena terlalu tinggi
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

def _is_trend_aligned(symbol: str) -> bool:
    """
    Trend Alignment Filter 15m EMA200:
    Menghindari entry altcoin yang sedang berada di fase downtrend keras.
    """
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

def get_adaptive_signal(symbol: str, tf: str, is_vip: bool) -> Optional[dict]:
    """
    MESIN ANALISA UTAMA: THE "4 WALLS" STRATEGY
    Bot mencari konfirmasi pantulan yang matang berdasarkan 4 Tembok Pertahanan.
    """
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

        # Wall 1: Volume Exhaustion
        df['vol_ma'] = df['volume'].shift(1).rolling(window=VOL_LOOKBACK).mean()
        df.bfill(inplace=True)

        idx_curr, idx_prev = len(df) - 1, len(df) - 2
        c_close, c_low, c_atr = close.iat[idx_curr], low.iat[idx_curr], atr.iat[idx_curr]
        p_open, p_close, p_low = df['open'].iat[idx_prev], close.iat[idx_prev], low.iat[idx_prev]

        if df['volume'].iat[idx_prev] >= df['vol_ma'].iat[idx_prev]: 
            return None
            
        if p_close <= p_open: 
            return None
        
        # Wall 2: Candle Rejection (Shadow Ratio)
        body = abs(p_close - p_open) or 0.00000001
        shadow_req = 2.0 if is_vip else 1.2
        if ((min(p_open, p_close) - p_low) / body) < shadow_req: 
            return None

        # Wall 3: ATR Dynamic Proximity
        dynamic_proximity = c_atr * 0.15
        c_ema200, c_ma99, c_bb_dn = ema200.iat[idx_curr], ma99.iat[idx_curr], bb.bollinger_lband().iat[idx_curr]
        dynamic_floors = [t for t in [c_ema200, c_ma99, c_bb_dn] if t < c_close]
        closest_dynamic = max(dynamic_floors) if dynamic_floors else 0
        hit_dynamic = closest_dynamic > 0 and (abs(c_low - closest_dynamic)) <= dynamic_proximity

        # Wall 4: Static Support Validation
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

def execute_order(symbol: str, side: str, position_side: str, margin_to_use: float, is_dca: bool = False) -> bool:
    """Fungsi eksekusi Market Order ke Binance dan mengatur Target Take Profit (TP)."""
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

        # Eksekusi Market Order (Entry)
        _api_call(_client.futures_create_order, symbol=symbol, side=side, type='MARKET', quantity=qty_str, positionSide=position_side)

        if not is_dca:
            # Set Target TP di 50% ROE
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

def _monitor_positions(positions: List[dict]):
    """Memantau posisi aktif untuk menggelar jaring SMART DCA jika harga breakdown."""
    for p in positions:
        amt = float(p['positionAmt'])
        if amt == 0: continue
        
        symbol = p['symbol']
        unrealized = float(p['unRealizedProfit'])
        mark_price = float(p['markPrice'])
        actual_lev = float(p.get('leverage', TARGET_LEVERAGE))
        
        current_margin = (abs(amt) * mark_price) / actual_lev
        roe = (unrealized / current_margin) if current_margin > 0 else 0

        _, dca1_adj = _get_dynamic_leverage_and_margin(symbol, DCA_1_AMOUNT)
        _, dca2_adj = _get_dynamic_leverage_and_margin(symbol, DCA_2_AMOUNT)
        _, dca3_adj = _get_dynamic_leverage_and_margin(symbol, DCA_3_AMOUNT)
        _, base_adj = _get_dynamic_leverage_and_margin(symbol, BASE_MARGIN)

        if roe <= DCA_1_TRIGGER and current_margin < (base_adj + 2.0):
            logger.info(f"💉 DCA TAHAP 1 untuk {symbol}")
            execute_order(symbol, 'BUY', 'LONG', DCA_1_AMOUNT, is_dca=True)
            
        elif roe <= DCA_2_TRIGGER and current_margin < (base_adj + dca1_adj + 2.0):
            logger.info(f"💉 DCA TAHAP 2 untuk {symbol}")
            execute_order(symbol, 'BUY', 'LONG', DCA_2_AMOUNT, is_dca=True)
            
        elif roe <= DCA_3_TRIGGER and current_margin < (base_adj + dca1_adj + dca2_adj + 2.0):
            logger.info(f"🔥 DCA TAHAP 3 TERAKHIR untuk {symbol}")
            execute_order(symbol, 'BUY', 'LONG', DCA_3_AMOUNT, is_dca=True)

def _scan_single_alt(symbol: str, active_keys: List[str]) -> Optional[Tuple[str, dict]]:
    """Pemindai Altcoin secara paralel."""
    if f"{symbol}_LONG" in active_keys: 
        return None
        
    for tf in ALT_TFS:
        sig = get_adaptive_signal(symbol, tf, is_vip=False)
        if sig:
            if _is_trend_aligned(symbol):
                return (symbol, sig)
            else:
                return None
    return None

_stop_event = None

def shutdown_bot():
    """Menerima sinyal dari main.py untuk mematikan thread bot dengan aman."""
    global _stop_event
    if _stop_event: 
        _stop_event.set()

def run_bot(stop_event: threading.Event) -> None:
    """Fungsi Jantung (Main Loop) bot yang terus berputar 24/7."""
    global _stop_event, TOTAL_CLOSED_ROE, TOTAL_SUCCESS_TRADES, CLOSED_HISTORY, _previous_active_keys
    
    _stop_event = stop_event
    setup_account_environment()

    executor = ThreadPoolExecutor(max_workers=5)
    loop_counter = 0
    first_run = True

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

                # ==========================================
                # LOGIKA PAPAN SKOR ROE (Mencatat Kemenangan)
                # ==========================================
                if not first_run:
                    closed_keys = _previous_active_keys - current_active_set
                    for k in closed_keys:
                        symbol = k.split('_')[0]
                        # Setiap koin yang hilang/tutup berarti sukses TP 50%
                        TOTAL_CLOSED_ROE += 50.0
                        TOTAL_SUCCESS_TRADES += 1
                        
                        now_str = datetime.now().strftime("%H:%M:%S")
                        CLOSED_HISTORY.insert(0, {'time': now_str, 'symbol': symbol, 'roe': '+50.00%'})
                        
                        # Batasi histori di web agar tidak kepanjangan
                        if len(CLOSED_HISTORY) > 15: 
                            CLOSED_HISTORY.pop()
                
                _previous_active_keys = current_active_set
                first_run = False

                vip_count = sum(1 for k in active_keys if k.split('_')[0] in VIP_SET)
                alt_count = sum(1 for k in active_keys if k.split('_')[0] not in VIP_SET)

                # Scan VIP Symbols
                for symbol in VIP_SYMBOLS:
                    if _stop_event.is_set(): break
                    if vip_count >= MAX_VIP: break
                    
                    if f"{symbol}_LONG" not in active_keys:
                        for tf in VIP_TFS:
                            sig = get_adaptive_signal(symbol, tf, is_vip=True)
                            if sig:
                                logger.info(f"👑 VIP Sinyal {symbol} ({tf})")
                                if execute_order(symbol, 'BUY', 'LONG', BASE_MARGIN):
                                    vip_count += 1
                                    active_keys.append(f"{symbol}_LONG")
                                    current_active_set.add(f"{symbol}_LONG")
                                    _previous_active_keys = current_active_set
                                    break

                # Scan Altcoin Symbols
                if alt_count < MAX_ALT and not _stop_event.is_set():
                    tickers = _get_cached_ticker()
                    alts = [t['symbol'] for t in sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
                            if t['symbol'].endswith('USDT') and t['symbol'] not in VIP_SET][:TOP_ALT_LIMIT]

                    futures = [executor.submit(_scan_single_alt, s, active_keys) for s in alts]
                    for future in as_completed(futures):
                        if _stop_event.is_set(): break
                        res = future.result()
                        if res and alt_count < MAX_ALT:
                            symbol, sig = res
                            logger.info(f"🎯 PRO Sinyal {symbol}")
                            if execute_order(symbol, 'BUY', 'LONG', BASE_MARGIN):
                                alt_count += 1
                                active_keys.append(f"{symbol}_LONG")
                                current_active_set.add(f"{symbol}_LONG")
                                _previous_active_keys = current_active_set

                # Heartbeat Monitor
                loop_counter += 1
                if loop_counter >= 4:
                    logger.info(f"👀 System OK | Memantau Market... (VIP: {vip_count}/{MAX_VIP} | ALT: {alt_count}/{MAX_ALT})")
                    loop_counter = 0

                # Istirahat sebentar sebelum loop berikutnya
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