# 🚀 nazBot Alpha 4.0 PRO (Sniper Edition)
**Fully Automated Binance Futures Trading Bot with Institutional-Grade Risk Management**

nazBot Alpha 4.0 PRO adalah algoritma trading otomatis berbasis Python yang didesain khusus untuk market Binance Futures. Menggunakan strategi **"Confirmation Bounce"** (Pantulan Terkonfirmasi) dengan arsitektur **4 Walls** dan sistem **Smart DCA**, bot ini bertindak sebagai penembak jitu (sniper) yang hanya masuk ke pasar saat probabilitas kemenangan sangat tinggi.

---

## 🌟 What's New in v4.0 PRO?
Pembaruan masif pada versi 4.0 difokuskan pada keamanan modal, penghindaran jebakan tren turun (*falling knife*), dan kecepatan eksekusi:

* **[NEW] 15m EMA200 Trend Alignment Filter:** Altcoin tidak akan di- *entry* jika harga berada di bawah EMA200 (15m). Ini mencegah bot menangkap koin yang sedang *dumping* keras. (VIP bypass filter ini).
* **[NEW] Hit & Run Strategy:** Target Take Profit (TP) dioptimalkan menjadi **50% ROE**. Eksekusi lebih cepat, meminimalkan paparan risiko di market yang *choppy*.
* **[NEW] Noise Reduction:** Timeframe `5m` dihapus sepenuhnya dari Altcoin. Bot hanya fokus pada sinyal matang di TF `15m`, `1h`, dan `4h`.
* **[NEW] Parallel Scanner Engine:** Menggunakan `ThreadPoolExecutor` untuk memindai 50 top Altcoin secara bersamaan (Asynchronous). Eksekusi tembakan kini hanya memakan waktu hitungan detik.
* **[NEW] Heartbeat Monitor:** Sistem *logging* pemantau detak jantung server, memastikan *looping* berjalan mulus tanpa antrean (*bottleneck*).

---

## 🧠 Core Logic: The "4 Walls" Strategy
Bot ini **TIDAK MENGGUNAKAN LIMIT ORDER BUTA**. Bot menunggu konfirmasi pergerakan harga (*price action*) sebelum mengeksekusi *Market Order*. Sinyal `LONG` hanya akan valid jika 4 syarat "Tembok" ini terpenuhi pada saat penutupan *candle*:

1. **Volume Exhaustion:** Volume *candle* saat ini harus lebih kecil dari rata-rata volume (MA Volume) sebelumnya, menandakan tekanan jual sudah melemah.
2. **Candle Rejection (Shadow/Ekor):** Harus ada penolakan harga dari bawah (Ekor bawah panjang). Rasio ekor harus **≥ 2.0x** (VIP) atau **≥ 1.2x** (Altcoin) dari ukuran badan *candle*.
3. **ATR Dynamic Proximity:** Titik terendah *candle* harus menyentuh atau berada dalam jarak toleransi **15% ATR** dari garis pertahanan dinamis (EMA200, MA99, atau Lower Bollinger Band).
4. **Static Support Validation:** Jika tidak ada garis dinamis, bot mencari level *Support* statis terkuat dari 100 *candle* terakhir.

---

## 🛡️ Risk Management & Defense System
nazBot Alpha 4.0 PRO beroperasi dengan mode **NO-SL (Tanpa Stop Loss)**, digantikan oleh sistem pertahanan dana yang agresif namun terukur:

### 1. Dynamic Margin Balancing
Binance sering membatasi batas maksimal *leverage* pada koin *low-cap* (misal: mentok di 20x). Bot ini dilengkapi fitur **Notional Value Lock**. Jika *leverage* turun, bot otomatis menaikkan modal margin dasar agar "Daya Tembak" (*Notional Value* = Margin x Leverage) tetap setara dengan target (misal: $250 Notional).

### 2. Smart DCA (Dollar Cost Averaging)
Jika harga tembus ke bawah (*breakdown*) setelah *entry*, bot tidak akan panik cut-loss, melainkan menggelar jaring DCA berdasarkan ROE Absolut, bukan persentase harga:
* **DCA 1:** Trigger di **-1.00 ROE** | Suntikan: **$3.0**
* **DCA 2:** Trigger di **-1.50 ROE** | Suntikan: **$3.0**
* **DCA 3:** Trigger di **-3.00 ROE** | Suntikan: **$10.0** (Suntikan raksasa terakhir untuk menarik harga rata-rata secara drastis).

---

## ⚙️ Configuration Variables (in `bot_logic.py`)
Anda dapat menyesuaikan selera risiko Anda melalui variabel global berikut:

```python
TARGET_LEVERAGE = 50       # Default Leverage utama
BASE_MARGIN = 5.0          # Base target margin dalam USD
TP_TARGET_ROE = 0.50       # Target 50% Take Profit
MAX_VIP = 8                # Maksimal posisi koin VIP bersamaan
MAX_ALT = 8                # Maksimal posisi koin Altcoin bersamaan
TOP_ALT_LIMIT = 50         # Memindai 50 top koin berdasar Quote Volume
🚀 Deployment Guide (Replit / Cloud)
Bot ini didesain untuk berjalan 24/7 di environment cloud seperti Replit.

Environment Variables: Setel BINANCE_API_KEY dan BINANCE_API_SECRET di menu Secrets (Replit) atau .env. Pastikan API Key Anda memiliki izin "Enable Futures".

Dependensi: Instal library via terminal: pip install pandas ta python-binance flask

Keep-Alive (Mini Server): Bot dilengkapi Flask Web Server mini bawaan. Gunakan layanan seperti UptimeRobot dan ping URL bot setiap 5 menit agar mesin tidak masuk ke mode Sleep.

Execution: Jalankan tombol Run atau ketik python main.py di terminal. Pantau aktivitas di Console.

## 🛠️ Cara Instalasi (Telah diuji di Replit)

1.  **Environment:** Pastikan Python 3.10+ terinstal.
2.  **API Keys:** Masukkan `BINANCE_API_KEY` dan `BINANCE_API_SECRET` ke dalam *Secrets* Replit atau file `.env`.
3.  **Requirements:** Jalankan `pip install -r requirements.txt` (Pastikan `pandas`, `numpy`, `ta`, `python-binance`, dan `flask` tercantum).
4.  **Run:** Jalankan `python main.py` dan akses dashboard di port 8080.

---

## ⚠️ Disclaimer
*Trading Futures memiliki risiko tinggi. nazBot Alpha 4.0 adalah alat bantu teknis. Pengguna bertanggung jawab penuh atas konfigurasi leverage dan margin yang digunakan. Sangat disarankan untuk melakukan uji coba secara menyeluruh di Testnet Binance sebelum digunakan di akun Real.*
