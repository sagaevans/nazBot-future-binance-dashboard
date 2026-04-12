# 🚀 nazBot Sniper System [RC v5.2 - REAL ACCOUNT MODE]

**nazBot Sniper** adalah sistem *Automated Quantitative Trading* tingkat lanjut yang dirancang untuk pasar **Binance Futures**. Pada versi Release Candidate (RC) 5.2 ini, bot telah berevolusi dari mode agresif (Testnet) menjadi mode **Defensif, Efisien, dan Presisi Tinggi** yang dioptimalkan khusus untuk pelestarian modal di **Akun Real**.

Sistem ini berjalan secara independen di server lokal dengan perlindungan Cloudflare, memastikan eksekusi *latency* rendah tanpa intervensi *cloud provider* pihak ketiga.

---

## 🌟 Fitur Utama (Core Upgrades v5.2)

### 1. 🛡️ Eksekusi Fixed Notional (Anti-Overexposure)
Meninggalkan sistem margin tetap, bot sekarang menggunakan sistem **Fixed Notional Size**. 
* **Target Posisi Baku:** Selalu **50 USDT** per koin.
* **Auto-Margin Calculation:** Modal (Margin) yang dipotong dari dompet akan beradaptasi otomatis dengan *leverage* maksimal koin tersebut (Contoh: Leverage 50x = Margin $1. Leverage 25x = Margin $2).
* **Benefit:** Memastikan eksposur risiko yang seimbang di seluruh portofolio tanpa membebani ketahanan dana.

### 2. 🎣 Smart Limit Maker (Zero Taker Fee)
Bot tidak lagi menghajar harga pasar (*Market Order*). Setiap sinyal *entry* akan dieksekusi murni sebagai **Limit Order (Maker)**.
* Menghilangkan risiko *slippage* (selip harga) sekecil apa pun.
* Memangkas biaya transaksi secara masif (menghindari *Taker Fee* Binance).

### 3. 🧠 Smart Order Upgrading (Hedge Fund Logic)
Dilengkapi dengan "Satpam Antrean" cerdas. Jika bot memiliki antrean *Limit Order* yang menggantung dan muncul sinyal baru di koin yang sama:
* Bot akan menganalisa: *"Apakah harga baru ini lebih menguntungkan?"*
* Jika **YA** (Lebih diskon untuk LONG / Lebih pucuk untuk SHORT), bot akan membatalkan antrean lama dan menggantinya dengan harga baru (*Order Upgrading*).
* Jika **TIDAK**, bot akan mengabaikan sinyal baru dan tetap antre di harga terbaik.

### 4. 🐋 Sentimen Makro: Fear & Greed Index (VIP Only)
Koin Fundamental/VIP (BTC, ETH, SOL, dll) beroperasi dengan logika *Smart Money*:
* **Haram SHORT:** Koin VIP dikunci secara permanen hanya untuk posisi **LONG**.
* **Fear Mode Only:** Bot menarik data *Global Crypto Fear & Greed Index* setiap jam. Koin VIP **hanya akan menembak** jika skor berada di fase ketakutan ekstrem (Skor 0 - 45). Saat pasar sedang serakah (Greed), VIP akan hibernasi.

### 5. 🕸️ Jaring Bunglon (Auto-Adjusting Limit Net) & 7-Level DCA
Sistem *Dynamic Cost Averaging* berlapis untuk menahan gempuran pasar:
* **7 Lapis Peluru DCA:** Terpicu di -100%, -200%, -300%, -400%, -600%, -800%, hingga -1000% ROE.
* **Dynamic Take Profit:** Target egois (100% ROE) akan otomatis menyusut menjadi 50% (DCA 2), dan berubah ke Mode Survival 15% (DCA 3+) agar modal cepat terbebas.
* **Auto-Limit Repricing:** Setiap kali DCA tersentuh, bot otomatis mencabut jaring TP lama dan memasang jaring Limit TP baru sesuai harga rata-rata (*average entry*) secara presisi.

### 6. 🔒 Liquidity Guard (Filter Volume)
Bot otomatis menendang "Koin Hantu" atau "Dummy Coin". Hanya Altcoin dengan volume transaksi 24 jam di atas **$1,000,000 USDT** yang lolos sensor radar.

---

## 🎯 Strategi "5-Confluence"
Bot tetap mempertahankan inti akurasi *Sniper*, hanya melakukan entri jika 5 syarat teknikal ini terpenuhi dalam satu *candlestick*:
1. **Trend Alignment:** Searah dengan EMA 200.
2. **Volume Anomaly:** Lonjakan volume minimal 1.2x dari rata-rata (MA 20).
3. **Price Rejection:** Ekor *candle* (*shadow* / Pinbar) yang panjang.
4. **Dynamic Walls:** Harga menabrak MA 99 atau pita luar Bollinger Bands.
5. **Static S/R:** Harga menyentuh *Support* atau *Resistance* terkuat dalam 100 *candle* terakhir.

---

## 🛠️ Stack Teknologi & Persyaratan Sistem
* **Backend:** Python 3.10+
* **Trading Engine:** `python-binance`, `pandas`, `ta`, `requests`
* **Infrastructure:** Local PC Server + Cloudflare Tunnels (Disarankan untuk operasional Real Account).
* **Environment:** Setup `BINANCE_API_KEY` dan `BINANCE_API_SECRET` pada *environment variables* lokal Anda. *Wajib mencentang izin Futures dan MAKSIMALKAN keamanan dengan mematikan izin Withdrawals pada API Binance.*

---

## ⚡ Cara Menjalankan Bot
1. Pastikan semua *library* sudah terpasang:
   ```bash
   pip install pandas ta python-binance flask requests

   Jalankan mesin utama:

Bash
python main.py
Akses Dashboard (Web UI) melalui URL lokal (misal: http://localhost:8080) atau link Cloudflare Tunnel Anda.

📜 Disclaimer Mutlak
Bot ini beroperasi di pasar Binance Futures menggunakan uang riil. Cryptocurrency trading adalah aktivitas berisiko tinggi (High Risk). Segala pengaturan ukuran notional, leverage, dan target DCA telah diuji, namun kondisi pasar ekstrem (Black Swan events) dapat menyebabkan likuidasi. Gunakan dengan bijak, pantau secara berkala, dan pengembang tidak bertanggung jawab atas segala kerugian finansial yang terjadi.
