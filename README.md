# PostgreSQL vs InfluxDB: Laundry Database
## Setup
### Databases (Docker)
PostgreSQL 18, InfluxDB 2.7.12, dan MongoDB 8.0.4 sama-sama berjalan di Docker, sehingga ketiganya memiliki network path dan overhead VM yang sama selama benchmark. Jalankan perintah-perintah berikut di
PowerShell dari direktori proyek dengan Docker Desktop running Linux containers.

1. Salin environment template, jika belum memiliki `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
   Edit `.env` dan ubah placeholder kredensial (`INFLUXDB_USERNAME`,
   `INFLUXDB_PASSWORD`, `INFLUXDB_TOKEN`, `PG_USER`, `PG_PASSWORD`, `MONGO_USER`,
   `MONGO_PASSWORD`).

2. Validasi konfigurasi, lalu jalankan ketiga basis data:
   ```powershell
   docker compose config --quiet
   docker compose up -d --wait
   docker compose ps
   ```
   Ketiga service seharusnya berstatus `healthy`.
   | Service | Host address | Data volume |
   |---|---|---|
   | `postgres` | `127.0.0.1:5433` | `postgres_data` |
   | `influxdb` | `127.0.0.1:8086` | `influxdb_data`, `influxdb_config` |
   | `mongo` | `127.0.0.1:27017` | `mongo_data` |
   UI InfluxDB tersedia di <http://127.0.0.1:8086>; masuk dengan username dan password dari `.env`.

3. Verifikasi PostgreSQL:
   ```powershell
   docker compose exec postgres psql -U <PG_USER> -d laundry -c "\dt"
   ```

4. Verifikasi InfluxDB:
   ```powershell
   Invoke-RestMethod http://127.0.0.1:8086/health
   docker compose exec influxdb influx bucket list --org laundry
   ```
   Health seharusnya menampilkan `status: pass` dan versi `2.7.12`. Daftar bucket
   seharusnya memuat `laundry_metrics` dengan retention `infinite`.

Untuk menghentikan ketiga service tanpa menghapus datanya, gunakan `docker compose down`. 
Untuk menghapus semua datanya tambahkan `--volumes`.


### Python environment
Buat dan aktifkan virtual environment di PowerShell, lalu install dependensinya:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip freeze > requirements.lock.txt
```

## Data
Jalankan dari direktori proyek dengan virtual environment aktif dan ketiga basis data berjalan.
1. Generate the 30-day synthetic dataset (seed 42) into `data/*.csv`:
   ```powershell
   python generator.py
   ```

2. Load file-file tersebut ke PostgreSQL, InfluxDB, dan MongoDB:
   ```powershell
   python load.py
   ```
   `python load.py --reset` akan menghapus **semua** baris di delapan tabel **semua** point di `laundry_metrics`, dan **semua** collection di database MongoDB `laundry`.

## Read queries
Jalankan read query:
```powershell
python queries.py    # semua query
python queries.py R6 R7    # hanya query yang disebutkan
```

| Query | Deskripsi |
|---|---|
| R1 | Jumlah pesanan per hari |
| R2 | Jumlah pembayaran per hari |
| R3 | Berat cucian per hari  |
| R4 | Jumlah pemasukan per jenis layanan (hanya pesanan yang sudah dibayar) |
| R5 | Jumlah pesanan per status saat ini |
| R6 | Rata-rata suhu dan daya per mesin per jam |
| R7 | Energi (kWh) per jenis layanan |

Setiap query dijalankan sekali tanpa diukur waktunya di setiap basis data sebagai warm-up, lalu 5 kali dengan pengukuran waktu. Rata-rata dan waktu setiap run untuk tiap query kemudian dituliskan ke `results/<name>.txt`.


## Write operations
Jalankan write operations:
```powershell
python writes.py  # semua write operations
python writes.py D2 D4 # hanya query yang disebutkan
```

| Op | Deskripsi | Parameter tetap |
|---|---|---|
| D1 | Menambahkan pesanan dengan 2 detail | order pada 2026-10-01 01:00 UTC, customer 1, Regular 3.5 kg + Express 2.0 kg |
| D2 | Mencatat pembayaran | pesanan belum dibayar dengan nomor terkecil, dibayar dengan QRIS pada 2026-10-01 02:00 UTC; InfluxDB terlebih dahulu mencari timestamp point pesanan |
| D3 | Memasukkan 192 machine readings | 16 mesin x 12 idle readings pada satu jam setelah dataset |
| D4 | Mengupdate nilai suatu sensor reading | mesin 3 pada 2026-09-15 12:00 UTC -> 45.0 C, 2000.0 W |
| D5 | Menghapus machine readings yang lebih lama dari suatu tanggal | readings sebelum 2026-09-02 (4,608) |

Setiap operasi dijalankan **sekali** di setiap basis data (diukur waktunya), dan basis data langsung dikembalikan ke kondisi semula setelahnya. Hasil setiap operasi kemudian ditulis ke `results/<name>.txt`

## Perbandingan dengan MongoDB
Tambahkan `--mongo` untuk menjalankan query read dan write operations yang sama di PostgreSQL, InfluxDB, dan MongoDB. Hasilnya akan ditulis ke `results_mongo/<name>.txt`:
```powershell
python queries.py --mongo         # semua query read
python queries.py --mongo R4 R7   # hanya query yang disebutkan
python writes.py --mongo          # semua write operations
```
