# 🚀 nazBot Sniper System [RC v5.2 - REAL ACCOUNT MODE]

**nazBot Sniper** adalah sistem *Automated Quantitative Trading* untuk pasar **Binance Futures**. Pada versi Release Candidate (RC) 5.2 ini, bot dirancang dengan pendekatan **defensif, efisien, dan presisi tinggi** untuk membantu menjaga eksposur modal saat digunakan pada **akun real**.

> ⚠️ **Peringatan:** Bot ini dapat melakukan transaksi pada Binance Futures menggunakan uang riil. Gunakan dengan risiko sendiri. Pastikan memahami risiko leverage, likuidasi, volatilitas ekstrem, dan kemungkinan kerugian modal.

---

## 🌟 Fitur Utama

### 1. 🛡️ Fixed Notional Execution

Bot menggunakan sistem **Fixed Notional Size**.

* Target posisi standar: **50 USDT** per koin.
* Margin akan menyesuaikan otomatis berdasarkan leverage.
* Tujuan: menjaga eksposur agar lebih konsisten di setiap posisi.

Contoh:

* Leverage 50x → margin sekitar 1 USDT untuk posisi 50 USDT.
* Leverage 25x → margin sekitar 2 USDT untuk posisi 50 USDT.

---

### 2. 🎣 Smart Limit Maker

Bot menggunakan **Limit Order** untuk entry, bukan Market Order.

Tujuannya:

* Mengurangi risiko *slippage*.
* Menghindari eksekusi harga yang terlalu buruk.
* Mengoptimalkan biaya transaksi dengan pendekatan maker order.

---

### 3. 🧠 Smart Order Upgrading

Jika ada limit order yang masih menggantung dan muncul sinyal baru pada koin yang sama, bot akan membandingkan harga lama dan harga baru.

* Untuk posisi **LONG**, bot akan memilih harga yang lebih rendah.
* Untuk posisi **SHORT**, bot akan memilih harga yang lebih tinggi.
* Jika harga baru lebih baik, order lama dibatalkan dan diganti.
* Jika harga baru tidak lebih baik, sinyal baru diabaikan.

---

### 4. 🐋 Sentimen Makro: Fear & Greed Index

Untuk koin fundamental/VIP seperti BTC, ETH, SOL, dan sejenisnya, bot menggunakan filter tambahan berdasarkan *Crypto Fear & Greed Index*.

Aturan VIP:

* Koin VIP hanya boleh **LONG**.
* Koin VIP tidak mengambil posisi SHORT.
* Entry hanya dilakukan ketika skor Fear & Greed berada pada area takut, yaitu sekitar **0 - 45**.
* Ketika pasar terlalu serakah, bot akan menahan entry pada koin VIP.

---

### 5. 🕸️ Auto-Adjusting Limit Net & 7-Level DCA

Bot menggunakan sistem DCA bertingkat untuk mengelola posisi yang bergerak berlawanan arah.

Level DCA:

* DCA 1: -100% ROE
* DCA 2: -200% ROE
* DCA 3: -300% ROE
* DCA 4: -400% ROE
* DCA 5: -600% ROE
* DCA 6: -800% ROE
* DCA 7: -1000% ROE

Setelah DCA aktif, target Take Profit akan disesuaikan ulang berdasarkan harga rata-rata posisi.

---

### 6. 🔒 Liquidity Guard

Bot hanya memproses altcoin dengan volume transaksi 24 jam di atas **1,000,000 USDT**.

Tujuannya:

* Menghindari koin dengan likuiditas rendah.
* Mengurangi risiko order sulit tereksekusi.
* Menghindari koin yang terlalu mudah dimanipulasi.

---

## 🎯 Strategi 5-Confluence

Bot hanya melakukan entry ketika beberapa syarat teknikal terpenuhi dalam satu candlestick.

Syarat utama:

1. **Trend Alignment**
   Harga searah dengan EMA 200.

2. **Volume Anomaly**
   Volume meningkat minimal 1.2x dari rata-rata volume MA 20.

3. **Price Rejection**
   Candle memiliki shadow/pinbar yang menunjukkan penolakan harga.

4. **Dynamic Walls**
   Harga menyentuh MA 99 atau area luar Bollinger Bands.

5. **Static Support/Resistance**
   Harga menyentuh support atau resistance kuat dari 100 candle terakhir.

---

## 🛠️ Stack Teknologi

* **Backend:** Python 3.10+
* **Trading Engine:** `python-binance`, `pandas`, `ta`, `requests`
* **Web Dashboard:** Flask
* **Environment Config:** `.env`
* **Deployment:** VPS AWS / Local PC Server
* **Optional Tunnel:** Cloudflare Tunnel

---

## 📁 Struktur Project

Contoh struktur folder:

```bash
nazbot/
├── .env
├── app.py
├── bot_logic.py
├── ledger_manager.py
├── main.py
├── requirements.txt
├── status.txt
├── templates/
└── venv/
```

Keterangan penting:

* `.env` berisi API Binance.
* `main.py` digunakan untuk menjalankan bot.
* `app.py` digunakan untuk dashboard/web UI.
* `bot_logic.py` berisi logic utama trading.
* `venv/` adalah virtual environment Python.

---

## 🔐 Setup API Binance

Bot membutuhkan API Binance agar dapat membaca akun dan melakukan transaksi Futures.

### 1. Buat API Key di Binance

Di akun Binance, buat API Key baru.

Aktifkan izin yang dibutuhkan:

* ✅ Enable Futures
* ✅ Enable Reading
* ✅ Enable Spot & Margin Trading jika memang dibutuhkan oleh kode
* ❌ Disable Withdrawals

> Sangat disarankan untuk mengaktifkan **IP whitelist** dan hanya mengizinkan IP VPS AWS yang digunakan bot.

---

### 2. Buat file `.env`

Masuk ke folder project:

```bash
cd ~/nazbot
```

Buat atau edit file `.env`:

```bash
nano .env
```

Isi file `.env` dengan format berikut:

```env
BINANCE_API_KEY=YOUR_BINANCE_API_KEY
BINANCE_API_SECRET=YOUR_BINANCE_API_SECRET
```

Contoh format yang benar:

```env
BINANCE_API_KEY=abc123
BINANCE_API_SECRET=xyz456
```

Contoh format yang salah:

```env
BINANCE_API_KEY = abc123
BINANCE_API_SECRET = xyz456
```

Jangan gunakan spasi sebelum atau sesudah tanda `=`.

---

### 3. Simpan file `.env`

Jika menggunakan `nano`:

1. Tekan `CTRL + O`
2. Tekan `Enter`
3. Tekan `CTRL + X`

---

### 4. Amankan permission `.env`

Jalankan:

```bash
chmod 600 .env
```

Cek file `.env` tanpa menampilkan isi API:

```bash
sed -E 's/=.*/=***MASKED***/' .env
```

Output yang benar:

```env
BINANCE_API_KEY=***MASKED***
BINANCE_API_SECRET=***MASKED***
```

---

## 🔁 Cara Mengganti API Binance

Jika ingin mengganti API lama ke API baru:

1. Masuk ke folder project:

```bash
cd ~/nazbot
```

2. Edit file `.env`:

```bash
nano .env
```

3. Ganti value berikut:

```env
BINANCE_API_KEY=API_KEY_BARU
BINANCE_API_SECRET=API_SECRET_BARU
```

4. Simpan file.

5. Pastikan format benar:

```bash
sed -E 's/=.*/=***MASKED***/' .env
```

6. Restart bot agar API baru terbaca.

> Setelah API baru berhasil digunakan, hapus atau disable API lama dari akun Binance.

---

## ⚡ Cara Menjalankan Bot di VPS AWS

### 1. Masuk ke folder project

```bash
cd ~/nazbot
```

### 2. Aktifkan virtual environment

```bash
source venv/bin/activate
```

Jika belum ada virtual environment, buat terlebih dahulu:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependency

Jika tersedia `requirements.txt`:

```bash
pip install -r requirements.txt
```

Jika tidak, install manual:

```bash
pip install pandas ta python-binance flask requests python-dotenv
```

### 4. Jalankan bot

```bash
python main.py
```

Jika berhasil, dashboard dapat diakses melalui URL lokal, misalnya:

```text
http://localhost:8080
```

Atau melalui URL tunnel jika menggunakan Cloudflare Tunnel.

---

## 🧪 Cek Apakah `.env` Terbaca

Untuk memastikan file `.env` ada:

```bash
ls -la .env
```

Untuk melihat nama konfigurasi tanpa membuka secret:

```bash
sed -E 's/=.*/=***MASKED***/' .env
```

Untuk mencari apakah kode membaca `.env`:

```bash
grep -nE "load_dotenv|dotenv|os.getenv|os.environ|BINANCE_API_KEY|BINANCE_API_SECRET|Client\(" main.py bot_logic.py app.py
```

---

## 🧯 Troubleshooting

### `.env` tidak terlihat saat `ls`

File `.env` adalah hidden file di Linux.

Gunakan:

```bash
ls -la
```

Bukan hanya:

```bash
ls
```

---

### Bot tidak membaca API baru

Coba lakukan:

```bash
cd ~/nazbot
source venv/bin/activate
python main.py
```

Jika bot sebelumnya masih berjalan, hentikan proses lama terlebih dahulu.

Cek proses Python:

```bash
pgrep -af "python|main.py|app.py"
```

---

### Permission denied saat membaca `.env`

Atur ulang permission:

```bash
chmod 600 .env
```

Pastikan file dimiliki oleh user yang menjalankan bot:

```bash
ls -la .env
```

---

### Dependency belum terinstall

Install ulang dependency:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Jika `requirements.txt` belum lengkap:

```bash
pip install pandas ta python-binance flask requests python-dotenv
```

---

## 🚫 File yang Tidak Boleh Diupload ke GitHub

Jangan pernah upload file berikut ke repository publik:

```bash
.env
venv/
__pycache__/
*.pyc
log.txt
profit_ledger.txt
start_balance.txt
```

Tambahkan ke `.gitignore`:

```gitignore
.env
venv/
__pycache__/
*.pyc
log.txt
profit_ledger.txt
start_balance.txt
```

Jika `.env` sudah pernah terupload ke GitHub, segera:

1. Hapus API lama dari Binance.
2. Buat API baru.
3. Update `.env`.
4. Restart bot.
5. Pastikan `.env` masuk `.gitignore`.

---

## 🛡️ Rekomendasi Keamanan

Untuk penggunaan real account:

* Jangan aktifkan izin withdrawal pada API.
* Gunakan IP whitelist VPS AWS.
* Gunakan API khusus untuk bot ini saja.
* Jangan membagikan file `.env`.
* Jangan screenshot isi `.env`.
* Jangan menjalankan bot dengan API utama akun jika tidak perlu.
* Pantau posisi dan margin secara berkala.
* Gunakan modal kecil terlebih dahulu untuk pengujian real account.

---

## 📜 Disclaimer

Bot ini beroperasi di pasar **Binance Futures** dan dapat menggunakan uang riil.

Cryptocurrency trading adalah aktivitas berisiko tinggi. Leverage dapat memperbesar keuntungan, tetapi juga dapat memperbesar kerugian dan menyebabkan likuidasi.

Segala pengaturan notional, leverage, DCA, dan target profit tidak menjamin keuntungan. Kondisi pasar ekstrem, gangguan API, koneksi server, bug kode, atau volatilitas mendadak dapat menyebabkan kerugian.

Gunakan dengan bijak. Pengembang tidak bertanggung jawab atas segala kerugian finansial yang terjadi akibat penggunaan bot ini.
