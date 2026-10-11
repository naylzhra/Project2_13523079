# PostgreSQL vs InfluxDB: Laundry Database
## Setup
### Databases (Docker)
PostgreSQL 18 dan InfluxDB 2.7.12 sama-sama berjalan di Docker, sehingga keduanya memiliki network path dan overhead VM yang sama selama benchmark. Jalankan perintah-perintah berikut di
PowerShell dari direktori proyek dengan Docker Desktop running Linux containers.

1. Salin environment template, jika belum memiliki `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
   Edit `.env` dan ubah placeholder kredensial (`INFLUXDB_USERNAME`,
   `INFLUXDB_PASSWORD`, `INFLUXDB_TOKEN`, `PG_USER`, `PG_PASSWORD`).

2. Validasi konfigurasi, lalu jalankan kedua basis data:
   ```powershell
   docker compose config --quiet
   docker compose up -d --wait
   docker compose ps
   ```
   Kedua service seharusnya berstatus `healthy`.
   | Service | Host address | Data volume |
   |---|---|---|
   | `postgres` | `127.0.0.1:5433` | `postgres_data` |
   | `influxdb` | `127.0.0.1:8086` | `influxdb_data`, `influxdb_config` |
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

Untuk menghentikan kedua service tanpa menghapus datanya, gunakan `docker compose down`. 
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
Jalankan dari direktori proyek dengan virtual environment aktif dan kedua basis data berjalan.
1. Generate the 30-day synthetic dataset (seed 42) into `data/*.csv`:
   ```powershell
   python generator.py
   ```

2. Load file-file tersebut ke PostgreSQL dan InfluxDB:
   ```powershell
   python load.py
   ```
   `python load.py --reset` akan menghapus **semua** baris di delapan tabel dan **semua** point di `laundry_metrics`.

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
