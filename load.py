import csv
import sys
import time
from datetime import datetime

from influxdb_client import WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

import config
from db import influx_client, mongo_client, pg_connect

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

def at(iso):
    return datetime.fromisoformat(iso) if iso else None

def mongo_orders():
    services = {r["service_id"]: r["service_name"] for r in read_csv("services")}
    orders = {}
    for o in read_csv("orders"):
        payment = {"method": o["payment_method"], "time": at(o["payment_time"])} if o["payment_time"] else None
        orders[o["order_id"]] = {
            "_id": int(o["order_id"]), "customer_id": int(o["customer_id"]), "status": o["status"],
            "order_time": at(o["order_time"]), "completed_at": at(o["completed_at"]),
            "total_amount": int(o["total_amount"]), "payment": payment, "details": [], "shipments": []}
    for d in read_csv("order_details"):
        orders[d["order_id"]]["details"].append({
            "detail_no": int(d["detail_no"]), "service_id": int(d["service_id"]),
            "service_name": services[d["service_id"]], "weight_kg": float(d["weight_kg"]),
            "subtotal": int(d["subtotal"])})
    for s in read_csv("shipments"):
        orders[s["order_id"]]["shipments"].append({
            "shipment_id": int(s["shipment_id"]), "shipment_type": s["shipment_type"],
            "shipment_status": s["shipment_status"], "created_at": at(s["created_at"])})
    return list(orders.values())

def mongo_readings():
    machines = {r["machine_id"]: r["machine_type"] for r in read_csv("machines")}
    for r in read_csv("machine_readings"):
        doc = {"recorded_at": at(r["recorded_at"]),
               "machine": {"machine_id": int(r["machine_id"]), "machine_type": machines[r["machine_id"]]},
               "temperature_c": float(r["temperature_c"]), "power_w": float(r["power_w"]),
               "rpm": int(r["rpm"])}
        if r["water_lpm"]:
            doc["water_lpm"] = float(r["water_lpm"])
        yield doc

def mongo_create_readings(db):
    db.create_collection("machine_readings", timeseries={
        "timeField": "recorded_at", "metaField": "machine", "granularity": "minutes"})
    db.machine_readings.create_index([("machine.machine_id", 1), ("recorded_at", 1)])

def mongo_has_data(db):
    return bool(db.list_collection_names(filter={"name": {"$regex": "^(?!system[.])"}}))

def mongo_load(db):
    services = {r["service_id"]: r["service_name"] for r in read_csv("services")}
    machines = {r["machine_id"]: r["machine_type"] for r in read_csv("machines")}
    db.customers.insert_many([{"_id": int(c["customer_id"]), "name": c["name"],
                               "phone_number": c["phone_number"], "address": c["address"]}
                              for c in read_csv("customers")])
    db.services.insert_many([{"_id": int(s["service_id"]), "service_name": s["service_name"],
                              "price": int(s["price"])} for s in read_csv("services")])
    db.machines.insert_many([{"_id": int(m["machine_id"]), "machine_name": m["machine_name"],
                              "machine_type": m["machine_type"],
                              "installed_at": at(m["installed_at"] + "T00:00:00Z")}
                             for m in read_csv("machines")])
    orders = mongo_orders()
    db.orders.insert_many(orders)
    detail_service = {(o["_id"], d["detail_no"]): d["service_name"] for o in orders for d in o["details"]}
    db.wash_runs.insert_many([{
        "_id": int(r["run_id"]), "machine_id": int(r["machine_id"]),
        "machine_type": machines[r["machine_id"]], "order_id": int(r["order_id"]),
        "detail_no": int(r["detail_no"]),
        "service_name": detail_service[(int(r["order_id"]), int(r["detail_no"]))],
        "start_time": at(r["start_time"]), "end_time": at(r["end_time"])} for r in read_csv("wash_runs")])
    mongo_create_readings(db)
    batch, total = [], 0
    for doc in mongo_readings():
        batch.append(doc)
        if len(batch) == CHUNK:
            db.machine_readings.insert_many(batch)
            total += len(batch)
            batch = []
    if batch:
        db.machine_readings.insert_many(batch)
        total += len(batch)
    return total

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

def reset(conn, client, mongo):
    conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY")
    conn.commit()
    client.delete_api().delete("1970-01-01T00:00:00Z", "2100-01-01T00:00:00Z", "", bucket=config.INFLUXDB_BUCKET, org=config.INFLUXDB_ORG)
    mongo.drop_database(config.MONGO_DB)

def main():
    with pg_connect() as conn, influx_client() as client, mongo_client() as mongo:
        db = mongo[config.MONGO_DB]
        if "--reset" in sys.argv:
            reset(conn, client, mongo)
            print("reset: all PostgreSQL rows, InfluxDB points and MongoDB collections deleted")
        elif pg_has_data(conn) or influx_has_data(client) or mongo_has_data(db):
            sys.exit("Databases already contain data. Run with --reset to delete it and reload.")

        t0 = time.perf_counter()
        pg_load(conn)
        t1 = time.perf_counter()
        points = influx_load(client)
        t2 = time.perf_counter()
        readings = mongo_load(db)
        t3 = time.perf_counter()
    print(f"PostgreSQL: {len(TABLES)} tables loaded in {t1 - t0:.1f} s")
    print(f"InfluxDB:   {points} points written in {t2 - t1:.1f} s")
    print(f"MongoDB:    5 collections + {readings} readings loaded in {t3 - t2:.1f} s")

if __name__ == "__main__":
    main()
