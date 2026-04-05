# 🎯 nazBot Sniper System [BETA v2.0]
*Automated Futures Trading Bot with Dynamic DCA, 8-Column Ledger & Dashboard*

nazBot Sniper System adalah bot trading otomatis berbasis Python yang dirancang untuk mengeksekusi posisi di Binance Futures. Versi BETA v2.0 menghadirkan arsitektur yang lebih kuat dengan filter *Anti-Pingpong*, Radar Emas (*Single Exposure*), dan pencatatan riwayat profit yang terintegrasi langsung dengan saldo riil Binance.

## ✨ Fitur Utama (BETA v2.0)
* **Escalation Timeframe & Anti-Pingpong:** Bot memiliki memori (cooldown 1 jam) untuk koin yang baru saja di-close, dan otomatis menaikkan analisis Timeframe (5m -> 15m) jika market terdeteksi *sideways*.
* **Radar Emas (Single Exposure):** Pemantauan khusus untuk `XAUUSDT`, `XAUTUSDT`, dan `PAXGUSDT`. Sistem memastikan hanya 1 pair emas yang boleh aktif dalam satu waktu.
* **8-Column Ledger System:** Pencatatan otomatis ke `profit_ledger.txt` setiap kali Take Profit/Stop Loss menyentuh target. Mencatat: Waktu, Pair, Profit $, ROE %, Total PnL, Total ROE, Saldo Riil, dan Growth Modal %.
* **Dynamic DCA (Average Down):** Sistem injeksi margin 3 tahap berdasarkan persentase penurunan ROE untuk menyelamatkan posisi *floating*.
* **Web Dashboard UI:** Visualisasi data *real-time* berbasis Flask & Chart.js, menampilkan grafik pertumbuhan saldo *live*, status koin aktif (VIP/ALT/GOLD), dan tabel jurnal transaksi.

## 🛠️ Stack Teknologi
* **Backend:** Python 3.x, Flask
* **Trading API:** `python-binance`
* **Indikator:** `ta` (Technical Analysis Library), `pandas`
* **Frontend:** HTML5, CSS3, Chart.js

## ⚙️ Cara Penggunaan
1. Pastikan `API_KEY` dan `API_SECRET` Binance sudah dimasukkan ke dalam *Environment Variables* (Secrets).
2. Sesuaikan `START_BALANCE` di `bot_logic.py` dan `app.py` sesuai modal awal Anda untuk kalkulasi persentase *Growth*.
3. Jalankan file utama (Orchestrator):
   ```bash
   python main.py
   Buka URL Web Dashboard yang disediakan server (port 8080) dan klik "START BOT".

🚀 POSSIBLE UPGRADE V3.0 (Blueprint)
Pembaruan selanjutnya akan berfokus pada diferensiasi gaya trading antara koin VIP dan komoditas Emas untuk meminimalisir risiko dan memaksimalkan cuan di market bullish.

1. Agresif VIP Mode (100% ROE Target): Khusus untuk kasta koin VIP, aturan Take Profit (TP) akan diubah secara statis menjadi 100% ROE dari margin entry. Mode Hit & Run akan dioptimalkan untuk mengejar target ganda.

2. Gold Semi-Spot Mode: Pendekatan investasi jangka panjang khusus untuk Emas (XAU, XAUT, PAXG):

Max Leverage: Dikunci aman pada 10x (menyerupai Semi-Spot).

Base Margin: Ditetapkan statis sebesar $20.

No Take Profit: Koin emas akan dibiarkan floating mengikuti tren naik tanpa batas TP otomatis.

Extreme Average Down: Jika posisi floating loss menyentuh -100% ROE, bot akan otomatis melakukan DCA / Average Down dengan menyuntikkan margin yang sama ($20) secara berulang tanpa batas maksimal DCA.

   
## 🛠️ TAMBAHAN  : Cara Instalasi (Telah diuji di Replit)

1.  **Environment:** Pastikan Python 3.10+ terinstal.
2.  **API Keys:** Masukkan `BINANCE_API_KEY` dan `BINANCE_API_SECRET` ke dalam *Secrets* Replit atau file `.env`.
3.  **Requirements:** Jalankan `pip install -r requirements.txt` (Pastikan `pandas`, `numpy`, `ta`, `python-binance`, dan `flask` tercantum).
4.  **Run:** Jalankan `python main.py` dan akses dashboard di port 8080.

---

## ⚠️ Disclaimer
*Trading Futures memiliki risiko tinggi. nazBot Alpha 4.0 adalah alat bantu teknis. Pengguna bertanggung jawab penuh atas konfigurasi leverage dan margin yang digunakan. Sangat disarankan untuk melakukan uji coba secara menyeluruh di Testnet Binance sebelum digunakan di akun Real.*
