# 🚀 nazBot Alpha 2.0 - Ultimate Adaptive Hybrid Sniper

nazBot Alpha 2.0 adalah bot trading otomatis untuk Binance Futures yang menggabungkan presisi **Price Action** dengan ketahanan **Smart DCA**. Bot ini dirancang untuk mendeteksi pantulan harga pada struktur market kunci (Tembok Teknis) dan mengelola risiko secara dinamis.

---

## 🧠 Core Strategy: "The 3-Walls Adaptive"

Bot memantau tiga level pertahanan harga (Support/Resistance) secara real-time untuk mencari titik pantulan (*rejection*):

1.  **🏰 Tembok Utama (EMA 200):** Basis tren jangka panjang.
2.  **🛡️ Tembok Struktur (MA 99):** Penahan volatilitas menengah.
3.  **🌊 Tembok Ekstrem (Bollinger Bands Dev 2):** Area jenuh beli/jual (*oversold/overbought*).

### 🔍 Filter Entry (Anti-False Breakout)
* **Volume Exhaustion:** Bot hanya masuk jika volume transaksi menurun saat mendekati tembok (menandakan tekanan mulai habis).
* **Shadow Rejection (Pinbar):** Harus ada ekor candle yang jelas sebagai bukti penolakan harga.
    * **VIP (BTC, ETH, dkk):** Ekor wajib **2x** panjang badan candle.
    * **Alts:** Ekor wajib minimal **0.8x** panjang badan candle.

---

## 🛡️ Risk Management: Smart DCA & Dynamic SL

Untuk menjaga Winrate tinggi (87.5%+) namun tetap aman dari kiamat market, bot menggunakan logika hibrida:

### 1. Smart DCA (Second Life)
Bot tidak menggunakan DCA statis/martingale. Bot menggunakan **DCA Teknikal**:
* Jika Entry 1 di Tembok 1 gagal (jebol), bot akan menunggu harga menyentuh **Tembok 2** di bawahnya untuk melakukan **1x DCA** (menambah margin).
* Tujuannya untuk memperbaiki *Average Price* sehingga pantulan kecil saja sudah cukup untuk keluar dengan profit.

### 2. Dynamic Stop Loss (The Breach Cut)
Bot tidak membiarkan posisi "nyangkut" selamanya.
* **Trigger:** Jika harga melakukan *Candle Close* di bawah tembok terakhir atau menembus ujung ekor (*Low*) candle sinyal.
* **Hard Cap:** Stop Loss otomatis tereksekusi jika kerugian mencapai **-30% ROE** (sebagai pengaman modal utama).

### 3. Vengeance Re-entry (Balas Dendam Pintar)
Jika posisi terkena *Cut Loss*, bot akan mencatat harga tersebut. Bot diharamkan masuk lagi di koin yang sama kecuali harga sudah jatuh lebih dalam (minimal 2-3%) dari harga *Cut Loss* sebelumnya untuk mencari pijakan baru.

---

## 🔥 Fitur Sistem

| Fitur | Keterangan |
| :--- | :--- |
| **VIP Squad** | 6 Slot (BTC, ETH, SOL, BNB, ADA, DOT). Fokus **LONG Only** (Trend Follower). |
| **Hunter Squad** | 8 Slot Altcoin Fleksibel. Bisa **LONG/SHORT** (Scalping Agresif). |
| **Cascading TF** | Memindai sinyal dari `1m` hingga `4h` secara berurutan. |
| **Auto TP** | Take Profit otomatis di-set pada **+50% ROE**. |
| **API Robustness** | Dilengkapi *Exponential Backoff* (Anti-Banned) & *Fallback System* (Limit Order jika Market terlalu liar). |

---

## 🛠️ Cara Instalasi

1.  **Environment:** Pastikan Python 3.10+ terinstal.
2.  **API Keys:** Masukkan `BINANCE_API_KEY` dan `BINANCE_API_SECRET` ke dalam Secrets Replit atau `.env`.
3.  **Requirements:** `pip install -r requirements.txt`
4.  **Run:** Jalankan `python main.py` dan akses dashboard di port 8080.

---

## ⚠️ Disclaimer
*Trading Futures memiliki risiko tinggi. nazBot Alpha 2.0 adalah alat bantu teknis. Pengguna bertanggung jawab penuh atas konfigurasi leverage dan margin yang digunakan. Disarankan uji coba di Testnet terlebih dahulu.*
