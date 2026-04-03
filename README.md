# 🎯 nazBot Alpha 2.0 - Ultimate Hybrid Sniper (Binance Futures)

nazBot Alpha 2.0 adalah sistem trading otomatis profesional untuk **Binance Futures** yang berjalan 24/7. Menggunakan strategi **S/R Bouncer (Mean Reversion)** yang diperkuat dengan filter **Anti-Fakeout** dan **Vectorized Calculation** untuk akurasi maksimal.

---

## 🚀 FITUR & LOGIKA STRATEGI

### 1. Dual-Squad Engine (Hybrid System)
* **⭐ VIP Squad:** Fokus pada 6 koin elit (`BTC`, `ETH`, `SOL`, `BNB`, `ADA`, `DOT`) di Timeframe **15m**.
* **🐺 Hunter Squad:** Memindai **Top 50 Volume Altcoins** dengan sistem *Cascading Timeframe* (**5m > 3m > 1m**). Bot otomatis turun ke TF rendah jika TF tinggi sepi sinyal.

### 2. Sniper Logic (Anti-Fakeout Filters)
Bot ini tidak asal "hit" garis, melainkan melalui filter ketat:
* **Vectorized SnR:** Algoritma Pandas untuk mendeteksi *Swing High/Low* secara instan.
* **Body Ratio Filter:** Menolak candle dengan sumbu (*shadow*) panjang (menghindari manipulasi market).
* **ATR Zone Width:** Memastikan zona S/R cukup kuat (bukan sekadar noise).
* **RSI & Proximity:** Mencegah entry "telat" jika harga sudah terbang jauh dari pantulan.

### 3. Money Management
* **Leverage:** 25x (Cross Margin).
* **Target Profit:** **Fixed 50% ROE** (Order TP langsung dipasang ke server Binance saat entry).
* **No Stop Loss:** Didesain untuk persiapan strategi **DCA (Averaging)** jika market berbalik arah.

---

## 🛠️ PANDUAN DEPLOY DI REPLIT (LENGKAP 24/7)

Ikuti langkah demi langkah ini untuk menjalankan bot tanpa error:

### LANGKAH 1: IMPORT PROJECT
1. Buka [Replit.com](https://replit.com/).
2. Klik **"+ Create Repl"** -> Pilih **"Import from GitHub"**.
3. Masukkan URL Repository ini: `https://github.com/sagaevans/nazBot-Alpha-v2-Public.git`.

### LANGKAH 2: INSTALASI MANUAL (SHELL)
Agar **Zero Error**, buka tab **Shell** (di sebelah Console) di Replit, lalu jalankan perintah ini satu per satu:
```bash
pip install --upgrade pip
pip install pandas numpy
pip install python-binance ta
pip install Flask Werkzeug Jinja2 itsdangerous click blinker
pip install requests urllib3 certifi charset-normalizer idna cryptography

LANGKAH 3: SETTING API KEY (SECRETS)
Di panel kiri Replit, klik ikon gembok (Secrets).

Tambahkan dua data berikut:

Key: BINANCE_API_KEY | Value: (Isi API Key Binance Anda)

Key: BINANCE_API_SECRET | Value: (Isi Secret Key Binance Anda)

LANGKAH 4: MENJALANKAN BOT
Klik tombol "Run" di bagian atas Replit.

Tunggu log muncul: 🔥 nazBot Alpha 2.0 AKTIF.

Dashboard Trading akan muncul di jendela Webview.

LANGKAH 5: AGAR BOT JALAN 24 JAM (UPTIME)
Agar bot tidak mati saat tab ditutup (PENTING untuk akun Replit Gratis):

Copy URL dari Webview Replit Anda (Contoh: https://test-demo-binance.username.repl.co).

Buka UptimeRobot (Gratis).

Buat "New Monitor" -> Type: HTTP(s).

Masukkan URL Replit Anda tadi. Set interval setiap 5 menit.

Klik Create Monitor. Selesai! Bot akan dijaga tetap hidup 24/7.

📊 DASHBOARD OVERVIEW
Dashboard Flask menyediakan pantauan real-time:

Balance & Net PNL: Pantauan saldo USDT secara instan.

VIP & Hunter Tables: Detail posisi aktif, harga entry, dan ROE berjalan.

History Panen: Catatan koin yang baru saja menyentuh target Take Profit.

⚠️ DISCLAIMER
Trading Cryptocurrency mengandung risiko finansial yang sangat tinggi. nazBot Alpha 2.0 adalah alat bantu analisis teknis dan bukan jaminan keuntungan pasti. Pengembang tidak bertanggung jawab atas kerugian modal yang terjadi. Gunakan Testnet untuk uji coba. Risk Management is your responsibility!

Author: NasZ / sagaevans

Version: 2.0.0 (Ultimate Hybrid)

License: MIT
