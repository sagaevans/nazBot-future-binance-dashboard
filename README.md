# 🎯 nazBot Sniper System [BETA v3.0]
**Automated Binance Futures Trading Bot & Web Dashboard**

nazBot Sniper System adalah bot trading *crypto futures* otomatis yang dirancang untuk platform Binance (Testnet/Mainnet). Membawa filosofi "Sniper" (Sabar Menunggu, Tembak Presisi), bot ini dilengkapi dengan berbagai filter teknikal tingkat lanjut, manajemen risiko otomatis (DCA), dan sebuah Web Dashboard interaktif.

Versi **BETA v3.0** membawa pembaruan masif pada stabilitas order (Anti-Slippage), manajemen koin (Anti-Pingpong), dan keakuratan pencatatan Ledger berbasis Saldo Riil.

---

## ✨ Fitur Utama (v3.0)

### 1. 🛡️ Limit Order Take Profit (Anti-Slippage)
Bot sekarang menggunakan murni pesanan **LIMIT** untuk *Take Profit*. Begitu bot melakukan *entry* (Market Order), bot akan otomatis memasang jaring *Take Profit* di buku antrean (*Order Book*) tepat pada target **100% ROE**. Ini mengeliminasi risiko *slippage* atau rugi karena *spread* kosong, khususnya di Testnet.

### 2. 📡 Sniper Strategy & 4 Walls Protection
Sinyal *entry* tidak dilakukan secara asal. Bot menganalisa *Price Action* dan indikator teknikal:
- **Trend Alignment:** Wajib berada di atas EMA 200 (TF 15m) untuk memastikan arah tren positif.
- **Dynamic Supports:** Mencari pantulan dari garis EMA 200, MA 99, atau Lower Bollinger Bands.
- **RSI Filter & Volume Spike:** Menghindari pembelian pucuk (*Overbought*) dan mencegah *entry* saat terjadi *Panic Selling/Buying* (Volume Spike Filter).
- **Shadow/Pinbar Confirmation:** Menuntut adanya ekor bawah (*shadow*) sebagai konfirmasi pantulan harga.

### 3. 💉 3-Stage Dynamic DCA (Martingale)
Sistem penyelamatan posisi (*Recovery*) yang rapi jika harga berbalik arah setelah *entry*:
- **Tahap 1:** Drop 2% ROE -> Suntik Margin 0.5x
- **Tahap 2:** Drop 3% ROE -> Suntik Margin 0.5x
- **Tahap 3:** Drop 4% ROE -> Suntik Margin 1.0x (Last Stand)

### 4. 📈 Sistem Escalation (Anti-Pingpong)
Mencegah bot melakukan *spam order* pada koin yang sama. Jika bot baru saja *Take Profit* dari koin `ALT`, koin tersebut akan dinaikkan level *Timeframe*-nya (misal dari 5m ke 15m) untuk pencarian sinyal berikutnya.

### 5. 🏆 Gold Radar (Single Exposure)
Berburu khusus untuk koin bernilai emas fisik (`PAXGUSDT`). Dibatasi ketat hanya untuk 1 posisi aktif (*Single Exposure*) guna mencegah penumpukan margin pada satu jenis aset, serta diatur menggunakan Leverage khusus (10x).

### 6. 🌐 Terintegrasi Web Dashboard & Keep-Alive
Aplikasi ini sudah membungkus *Bot Engine* (Background Thread) dan *Web Server Flask* (Main Thread) ke dalam satu wadah. Dashboard menampilkan:
- Saldo Riil USDT Binance.
- Posisi terbuka secara *real-time* (Roe, PnL, Tipe Koin).
- **8-Column Dynamic Ledger:** Mencatat rekam jejak profit, akumulasi PnL, dan persentase pertumbuhan modal (*Growth %*).
- Flask Web Server sekaligus bertindak sebagai sasaran "Ping" untuk layanan pihak ketiga (seperti UptimeRobot) agar bot berjalan 24/7.

---

## 📂 Struktur File

- `main.py` : Pusat komando utama. Menjalankan *Flask server* dan menembak *Bot logic* ke *background thread*.
- `app.py` : File web server (API Endpoint, Rute Halaman, dan Kalkulasi Tampilan Dashboard).
- `bot_logic.py` : Otak dari sistem trading (Algoritma Sinyal, Order Binance, Ledger, dan DCA).
- `templates/index.html` : Antarmuka visual Dashboard (UI/UX).
- `status.txt` : File sakelar (ON/OFF) yang menghubungkan tombol Dashboard dengan memori Bot.
- `profit_ledger.txt` : *Buku Jurnal* otomatis yang mencatat semua transaksi sukses.

---

## ⚙️ Persyaratan Sistem & Instalasi

### Prasyarat:
- Python 3.8+
- Akun Binance (dengan fitur Futures & API Key yang sudah diaktifkan)
- *Library* yang dibutuhkan: `pandas`, `ta`, `python-binance`, `flask`

### Cara Menjalankan:
1. Simpan *API Key* dan *Secret Key* Binance kamu ke dalam *Environment Variables* (*Secrets* di Replit):
   - `BINANCE_API_KEY` = *<Kunci_API_Kamu>*
   - `BINANCE_API_SECRET` = *<Kunci_Rahasia_Kamu>*
2. Buka terminal dan instal *library* (jika belum):
   ```bash
   pip install pandas ta python-binance flask
   
## 🛠️ TAMBAHAN  : Cara Instalasi (Telah diuji di Replit)

1.  **Environment:** Pastikan Python 3.10+ terinstal.
2.  **API Keys:** Masukkan `BINANCE_API_KEY` dan `BINANCE_API_SECRET` ke dalam *Secrets* Replit atau file `.env`.
3.  **Requirements:** Jalankan `pip install -r requirements.txt` (Pastikan `pandas`, `numpy`, `ta`, `python-binance`, dan `flask` tercantum).
4.  **Run:** Jalankan `python main.py` dan akses dashboard di port 8080.

---

## ⚠️ Disclaimer
*Trading Futures memiliki risiko tinggi. nazBot Alpha 4.0 adalah alat bantu teknis. Pengguna bertanggung jawab penuh atas konfigurasi leverage dan margin yang digunakan. Sangat disarankan untuk melakukan uji coba secara menyeluruh di Testnet Binance sebelum digunakan di akun Real.*
