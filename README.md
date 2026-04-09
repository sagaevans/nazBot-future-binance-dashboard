# 🚀 nazBot Sniper System [BETA v3.3 - Dynamic Recovery]

**nazBot Sniper** adalah sistem *Automated Algorithmic Trading* yang dirancang khusus untuk pasar **Binance Futures**. Dibangun dengan Python dan antarmuka Web Dashboard interaktif, bot ini menggunakan pendekatan presisi tinggi (Sniper) dipadukan dengan jaring pengaman *Dynamic Cost Averaging* (DCA) berlapis.

## ✨ Fitur Utama (Core Features)

### 🎯 1. Strategi "5-Confluence" (Akurasi Tinggi)
Bot hanya akan membuka posisi (ENTRY) jika dan hanya jika 5 syarat teknikal ini terpenuhi secara bersamaan dalam satu *candlestick*:
* **Trend Alignment:** Harga harus searah dengan EMA 200.
* **Volume Anomaly:** Terjadi lonjakan volume minimal 1.2x dari rata-rata (MA 20).
* **Price Rejection (Pinbar):** Terdapat ekor *candle* (shadow) penolakan yang kuat.
* **Dynamic Walls:** Harga menyentuh atau menyerempet MA 99 atau pita luar Bollinger Bands.
* **Static S/R:** Harga berada di area *Support* atau *Resistance* 100 candle terakhir.

### 🛡️ 2. Dynamic Take Profit & 7-Level DCA
Sistem pemulihan (*recovery*) super tangguh untuk mencegah kerugian saat pasar berbalik arah (Floating Loss):
* **7 Lapis DCA:** Menembak peluru DCA secara bertahap saat ROE menyentuh -100%, -200%, -300%, -400%, -600%, -800%, hingga -1000%.
* **Dynamic TP Scaling:** Ego trading dikontrol oleh mesin. 
    * *Belum DCA / DCA 1x* ➡️ Target Take Profit **100% ROE**.
    * *DCA 2x* ➡️ Target Take Profit turun menjadi **50% ROE**.
    * *DCA 3x atau lebih* ➡️ Mode Survival aktif! Target Take Profit menjadi **15% ROE** (Exit cepat untuk memutar kembali modal).

### ⚡ 3. Failsafe Virtual & Resurrection Logic
* **Virtual SL/TP:** Mengatasi *slippage* atau kegagalan API Binance. Bot mengecek ROE setiap detik. Jika target tercapai, bot langsung membanting setir melakukan *Market Close*.
* **Auto-Resurrection:** Jika server/bot sempat mati, saat dihidupkan kembali, bot akan langsung mendeteksi posisi yang tertinggal dan melakukan *Rapid-Fire DCA* massal sesuai dengan level kerugian.

### 👻 4. Liquidity Guard
Bot terintegrasi dengan filter likuiditas (*Anti-Dummy Coin*). Hanya koin dengan volume transaksi 24 Jam di atas **$1,000,000 USDT** yang akan masuk ke dalam radar. Ini mencegah bot terjebak pada koin dengan *slippage* brutal atau tanpa *order book*.

### 📊 5. Web Dashboard & Portfolio Export
Antarmuka UI/UX modern bergaya *Glassmorphism* untuk memantau performa bot secara *real-time*:
* **Live PNL & Wallet Balance Monitoring.**
* **Panic Button (CLOSE ALL):** Satu klik untuk membatalkan semua order dan menutup semua posisi aktif.
* **📸 Export Visual:** Fitur tangkapan layar Jurnal & Grafik menjadi file PNG resolusi tinggi untuk portofolio.
* **📊 Export Excel:** Fitur ekstraksi data Jurnal ke dalam format `.xlsx` murni untuk analisis lanjutan.

---

## 🛠️ Stack Teknologi
* **Backend:** Python 3.x, Flask (Web Server)
* **Trading Engine:** `python-binance` (Binance API), `pandas`, `ta` (Technical Analysis Library)
* **Frontend UI:** HTML5, Tailwind CSS, SweetAlert2, Chart.js
* **Export Tools:** `html2canvas` (Image), `SheetJS` (Excel)

---

## ⚙️ Cara Instalasi & Setup

1. **Clone Repository / Setup di Replit:**
   Pastikan struktur file sudah sesuai (`main.py`, `app.py`, `bot_logic.py`, dan folder `templates/index.html`).

2. **Environment Variables (Rahasia API):**
   Masukkan API Key Binance kamu di bagian *Secrets* (Replit) atau `.env` file:
   * `BINANCE_API_KEY` = *Your_API_Key*
   * `BINANCE_API_SECRET` = *Your_API_Secret*

3. **Install Dependencies:**
   Jalankan perintah ini di console/terminal:
   ```bash
   pip install pandas ta python-binance flask
  
## ⚠️ Peringatan Penting (Keep Alive)
Karena bot ini beroperasi di cloud (seperti Replit), server bisa "tertidur" jika tidak ada aktivitas. SANGAT DISARANKAN untuk menyambungkan URL Webview Dashboard bot ini ke layanan pemantau seperti UptimeRobot atau Cron-job.org (Ping setiap 5 menit) agar bot tetap "melek" 24/7 dan tidak ketinggalan momen DCA.
---

📜 Disclaimer
Cryptocurrency futures trading carries a high level of risk and may not be suitable for all investors. This bot is provided "as is" for educational and experimental purposes. The creator is not responsible for any financial losses incurred while using this software.
 
