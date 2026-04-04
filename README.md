# 🎯 nazBot Alpha 3.0
**Bot Hybrid Sniper Dashboard & Long-Only DCA Berkinerja Tinggi untuk Binance Futures**

## 📌 Deskripsi Sistem
nazBot Alpha 3.0 adalah bot trading otomatis kelas institusi untuk Binance Futures yang didesain khusus untuk kondisi *bull market* atau menangkap pantulan *major support* saat *bear market*. Bot ini murni menggunakan strategi **LONG ONLY** dengan jaring pengaman **DCA (Dollar Cost Averaging) Presisi 3 Lapis** dan beroperasi tanpa Stop Loss (Mode Survival/HODL).

Sistem ini berjalan dengan arsitektur *multi-threading* yang memisahkan mesin *trading* utama dengan *dashboard web* (Flask) agar pemantauan berjalan *real-time* tanpa mengganggu proses pemindaian pasar.

---

## 🚀 Pembaruan Performa & Arsitektur v3.0
Versi 3.0 membawa perombakan besar-besaran di ruang mesin untuk kecepatan, efisiensi memori, dan keamanan API:
* **NumPy Vectorization:** Mengganti iterasi Pandas standar dengan operasi vektor NumPy dan *downcasting* `float32` untuk kalkulasi indikator yang super cepat dan hemat RAM.
* **Token Bucket Rate Limiter:** Membatasi permintaan API secara ketat (20 panggilan/detik) untuk menjamin bot kebal dari pemblokiran *Weight Limit* Binance (Error 429/418).
* **Smart TTL Caching:** Menerapkan sistem *cache* dengan Time-To-Live (TTL) 5 detik untuk data Ticker dan metode *lookup* O(1) untuk filter koin, memangkas drastis panggilan jaringan yang berulang.
* **Resilient API Handling:** Dilengkapi fitur *exponential backoff* dengan *randomized jitter* untuk menangani server *disconnect*, *timeout*, dan API *overload* tanpa membuat sistem *crash*.
* **Graceful Shutdown:** Penambahan protokol `SIGINT/SIGTERM` di `main.py` agar sistem dan *thread* bisa dimatikan dengan aman tanpa risiko kebocoran memori (*memory leak*).

---

## ⚙️ Parameter Trading & Manajemen Risiko

* **Mode Eksekusi:** LONG ONLY (Hanya mencari peluang pantulan/Buy).
* **Leverage:** Fixed **50x**.
    * *Auto-Adjust Feature:* Jika Binance menolak 50x karena batasan khusus koin (Error -4028), bot otomatis mendeteksi batas maksimal leverage (misal 20x atau 25x) dan menghitung ulang ukuran koin (*quantity*) agar ekuivalen nilai USD margin tetap sama.
* **Take Profit (TP):** **100% ROE** berdasarkan margin aktual. Dipasang saat *entry* pertama menggunakan order `TAKE_PROFIT_MARKET` (dengan *fallback* ke `LIMIT` jika gagal).
* **Stop Loss (SL):** **DISABLED** (Tidak ada cut loss otomatis).

---

## 💰 Strategi Margin & DCA (Dollar Cost Averaging)
Bot menggunakan sistem *average down* bertahap berdasarkan persentase minus ROE (*Return on Equity*). Alokasi dana dikunci dengan nominal USD absolut, bukan persentase lot, agar ketahanan portofolio sangat terukur.

* **Entry Awal:** $5 USDT.
* **DCA Tahap 1:** Tembak **$3 USDT** saat posisi menyentuh **-100% ROE**.
* **DCA Tahap 2:** Tembak **$3 USDT** saat posisi menyentuh **-150% ROE**.
* **DCA Tahap 3 (Max):** Tembak **$10 USDT** saat posisi menyentuh **-300% ROE**.

*Catatan: Bot memiliki toleransi pembacaan selisih margin (`current_margin < BASE_MARGIN + X`) untuk memastikan bot tidak menembak DCA dua kali di tahap yang sama akibat fluktuasi harga.*

---

## 📊 Analisis Teknikal (Strategi "4 Tembok Sniper")
Bot akan melakukan *entry* jika kondisi di bawah ini terpenuhi. Bot memadukan indikator dinamis (*Lagging*) dan indikator statis (*Leading*) sebagai tembok pantulan:

1. **Floor Detection (4 Tembok):** Bot mendeteksi apakah harga terendah (*low*) menyentuh atau sangat dekat (toleransi 0.3%) dengan salah satu tembok berikut:
   * **Tembok Dinamis:** EMA 200, SMA 99, atau Bollinger Bands Bawah (Window 20, Dev 2).
   * **Tembok Statis (Historical Support):** Titik harga terendah dari 100 *candle* terakhir (mengabaikan 5 *candle* terbaru).
2. **Candle Pattern (Rejection):**
   * Jika harga menyentuh salah satu tembok, bot akan melihat *candle* sebelumnya.
   * *Candle* tersebut wajib ditutup *Bullish* (Close > Open).
   * Wajib memiliki ekor bawah (*lower shadow*) yang panjang. Rasio ekor dibanding badan *candle* minimal **2.0x untuk VIP** dan **0.8x untuk Altcoin**.
3. **Volume Exhaustion:** Volume *candle* sebelumnya harus lebih kecil dari rata-rata volume 5 periode terakhir (*Volume MA 5*), menandakan tekanan jual (*seller*) sudah melemah.

---

## 🗂️ Manajemen Portofolio (Alokasi Slot)
Bot membagi jatah pemindaian pasar menjadi dua kategori dengan *Timeframe* (TF) yang berbeda untuk diversifikasi risiko:

1.  **Koin VIP (Maksimal 6 Posisi Aktif)**
    * Koin: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `ADAUSDT`, `DOTUSDT`.
    * Timeframe: Khusus **15m** (Lebih stabil).
2.  **Altcoin (Maksimal 8 Posisi Aktif)**
    * Koin: Memindai Top 50 Altcoin berdasarkan volume harian tertinggi (mengabaikan koin VIP).
    * Timeframe: Agresif mencari peluang di multi-TF: **1m, 3m, 5m, 15m, 1h, 4h**.
    * Jika salah satu TF memberikan sinyal valid, bot akan *entry* dan melompati TF lainnya untuk koin tersebut.

---

## 📁 Struktur File Sistem

1.  `main.py`: File *launcher* utama dengan protokol *graceful shutdown*. Menjalankan server Flask dan mesin Trading secara paralel.
2.  `app.py`: Modul Dashboard Web UI.
    * Menampilkan saldo murni USDT, Net Profit, dan Floating PNL.
    * Memisahkan pemantauan koin ke dalam 2 tabel: **VIP Positions** dan **Altcoin Positions**.
    * Menampilkan *badge* informasi *Leverage Auto-Adjust*.
3.  `bot_logic.py`: Mesin *core trading*.
    * Berisi seluruh logika teknikal dan sistem 4 Tembok yang sudah dioptimasi dengan NumPy.
    * Sistem eksekusi order dengan perlindungan *exponential backoff* untuk API Error.
    * Sistem *log* cerdas yang memberitahu alasan *entry* (apakah karena Tembok Dinamis atau Tembok Statis).

---

## 🛠️ Cara Instalasi (Telah diuji di Replit)

1.  **Environment:** Pastikan Python 3.10+ terinstal.
2.  **API Keys:** Masukkan `BINANCE_API_KEY` dan `BINANCE_API_SECRET` ke dalam *Secrets* Replit atau file `.env`.
3.  **Requirements:** Jalankan `pip install -r requirements.txt` (Pastikan `pandas`, `numpy`, `ta`, `python-binance`, dan `flask` tercantum).
4.  **Run:** Jalankan `python main.py` dan akses dashboard di port 8080.

---

## ⚠️ Disclaimer
*Trading Futures memiliki risiko tinggi. nazBot Alpha 3.0 adalah alat bantu teknis. Pengguna bertanggung jawab penuh atas konfigurasi leverage dan margin yang digunakan. Sangat disarankan untuk melakukan uji coba secara menyeluruh di Testnet Binance sebelum digunakan di akun Real.*
