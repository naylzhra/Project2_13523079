import csv
import sys
import time
from datetime import datetime

from influxdb_client import WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

import config
from db import influx_client, pg_connect

TABLES = ["customers", "services", "machines", "orders", "order_details", "shipments", "wash_runs", "machine_readings"]
IDENTITY = {"customers": "customer_id", "services": "service_id", "machines": "machine_id", "orders": "order_id", "shipments": "shipment_id", "wash_runs": "run_id"}
MEASUREMENTS = ["order", "order_detail", "payment", "shipment", "wash_run", "machine_reading"]
CHUNK = 10_000


def read_csv(table):
    with open(f"data/{table}.csv", newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)

def epoch(iso):
    return int(datetime.fromisoformat(iso).timestamp())

def tag(value):
    return str(value).replace(",", r"\,").replace("=", r"\=").replace(" ", r"\ ")

def text(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

def pg_has_data(conn):
    return any(conn.execute(f"SELECT EXISTS (SELECT 1 FROM {t})").fetchone()[0] for t in TABLES)

def pg_load(conn):
    for table in TABLES:
        with open(f"data/{table}.csv", encoding="utf-8") as f, \
                conn.cursor().copy(f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true)") as copy:
            while chunk := f.read(1 << 20):
                copy.write(chunk)
    for table, column in IDENTITY.items():
        conn.execute(f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
                     f"(SELECT max({column}) FROM {table}))")
    conn.commit()
    conn.execute("ANALYZE")
    conn.commit()

def influx_lines():
    services = {r["service_id"]: r["service_name"] for r in read_csv("services")}
    machines = {r["machine_id"]: r["machine_type"] for r in read_csv("machines")}
    orders = list(read_csv("orders"))
    order_time = {o["order_id"]: epoch(o["order_time"]) for o in orders}
    detail_service = {}

    for o in orders:
        yield (f'order order_id={o["order_id"]}i,customer_id={o["customer_id"]}i,'
               f'total_amount={o["total_amount"]}i,status={text(o["status"])} '
               f'{order_time[o["order_id"]]}')
        if o["payment_time"]:
            yield (f'payment,payment_method={tag(o["payment_method"])} '
                   f'order_id={o["order_id"]}i,amount={o["total_amount"]}i '
                   f'{epoch(o["payment_time"])}')

    for d in read_csv("order_details"):
        name = services[d["service_id"]]
        detail_service[(d["order_id"], d["detail_no"])] = name
        yield (f'order_detail,detail_no={d["detail_no"]},service_name={tag(name)} '
               f'order_id={d["order_id"]}i,weight_kg={d["weight_kg"]},subtotal={d["subtotal"]}i '
               f'{order_time[d["order_id"]]}')

    for s in read_csv("shipments"):
        yield (f'shipment,shipment_type={s["shipment_type"]} '
               f'shipment_id={s["shipment_id"]}i,order_id={s["order_id"]}i,'
               f'shipment_status={text(s["shipment_status"])} {epoch(s["created_at"])}')

    for r in read_csv("wash_runs"):
        start, end = epoch(r["start_time"]), epoch(r["end_time"])
        name = detail_service[(r["order_id"], r["detail_no"])]
        yield (f'wash_run,machine_id={r["machine_id"]},machine_type={machines[r["machine_id"]]},'
               f'service_name={tag(name)} run_id={r["run_id"]}i,order_id={r["order_id"]}i,'
               f'detail_no={r["detail_no"]}i,end_time={end}i,duration_s={end - start}i {start}')

    for r in read_csv("machine_readings"):
        water = f',water_lpm={r["water_lpm"]}' if r["water_lpm"] else ""
        yield (f'machine_reading,machine_id={r["machine_id"]},machine_type={machines[r["machine_id"]]} '
               f'temperature_c={r["temperature_c"]},power_w={r["power_w"]}{water},rpm={r["rpm"]}i '
               f'{epoch(r["recorded_at"])}')

def influx_has_data(client):
    tables = client.query_api().query(
        f'from(bucket: "{config.INFLUXDB_BUCKET}") |> range(start: 0) |> limit(n: 1)')
    return any(t.records for t in tables)

def influx_load(client):
    write_api = client.write_api(write_options=SYNCHRONOUS)
    batch, total = [], 0
    for line in influx_lines():
        batch.append(line)
        if len(batch) == CHUNK:
            write_api.write(config.INFLUXDB_BUCKET, record=batch, write_precision=WritePrecision.S)
            total += len(batch)
            batch = []
    if batch:
        write_api.write(config.INFLUXDB_BUCKET, record=batch, write_precision=WritePrecision.S)
        total += len(batch)
    return total

def reset(conn, client):
    conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY")
    conn.commit()
    client.delete_api().delete("1970-01-01T00:00:00Z", "2100-01-01T00:00:00Z", "", bucket=config.INFLUXDB_BUCKET, org=config.INFLUXDB_ORG)

def main():
    with pg_connect() as conn, influx_client() as client:
        if "--reset" in sys.argv:
            reset(conn, client)
            print("reset: all PostgreSQL rows and InfluxDB points deleted")
        elif pg_has_data(conn) or influx_has_data(client):
            sys.exit("Databases already contain data. Run with --reset to delete it and reload.")

        t0 = time.perf_counter()
        pg_load(conn)
        t1 = time.perf_counter()
        points = influx_load(client)
        t2 = time.perf_counter()
    print(f"PostgreSQL: {len(TABLES)} tables loaded in {t1 - t0:.1f} s")
    print(f"InfluxDB:   {points} points written in {t2 - t1:.1f} s")

if __name__ == "__main__":
    main()
