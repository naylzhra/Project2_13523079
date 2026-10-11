from datetime import timedelta
from config import STOP
from .common import at, epoch, flux_count, influx_delete, influx_write

START = at(STOP)
END = START + timedelta(hours=1)
MARKS = [START + timedelta(minutes=5 * i) for i in range(12)]


def setup(conn):
    rows = []
    for machine_id, machine_type in conn.execute(
            "SELECT machine_id, machine_type FROM machines ORDER BY machine_id"):
        water = 0.0 if machine_type == "washer" else None
        for t in MARKS:
            rows.append((machine_id, machine_type, t, 28.0, 4.0, water, 0))
    return {"rows": rows}

def pg(conn, ctx):
    with conn.transaction():
        conn.cursor().executemany(
            "INSERT INTO machine_readings (machine_id, recorded_at, temperature_c, power_w, water_lpm, rpm) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [(mid, t, temp, power, water, rpm) for mid, _, t, temp, power, water, rpm in ctx["rows"]])

def flux(client, ctx):
    lines = []
    for mid, mtype, t, temp, power, water, rpm in ctx["rows"]:
        water_field = f",water_lpm={water}" if water is not None else ""
        lines.append(f"machine_reading,machine_id={mid},machine_type={mtype} "
                     f"temperature_c={temp},power_w={power}{water_field},rpm={rpm}i {epoch(t)}")
    influx_write(client, lines)

def pg_undo(conn, ctx):
    with conn.transaction():
        conn.execute("DELETE FROM machine_readings WHERE recorded_at >= %s AND recorded_at < %s", (START, END))

def flux_undo(client, ctx):
    influx_delete(client, "machine_reading", START, END)

def pg_state(conn, ctx):
    return conn.execute(
        "SELECT count(*) FROM machine_readings WHERE recorded_at >= %s AND recorded_at < %s",
        (START, END)).fetchone()

def flux_state(client, ctx):
    return (flux_count(client, "machine_reading", "power_w", START, END),)

def mongo(db, ctx):
    docs = []
    for mid, mtype, t, temp, power, water, rpm in ctx["rows"]:
        doc = {"recorded_at": t, "machine": {"machine_id": mid, "machine_type": mtype},
               "temperature_c": temp, "power_w": power, "rpm": rpm}
        if water is not None:
            doc["water_lpm"] = water
        docs.append(doc)
    db.machine_readings.insert_many(docs)

def mongo_undo(db, ctx):
    db.machine_readings.delete_many({"recorded_at": {"$gte": START, "$lt": END}})

def mongo_state(db, ctx):
    return (db.machine_readings.count_documents({"recorded_at": {"$gte": START, "$lt": END}}),)


WRITE = {
    "title": "Masukkan satu jam pembacaan sensor mesin (192 baris)",
    "state": "(readings in the hour after the dataset,)",
    "setup": setup, "pg": pg, "flux": flux, "pg_undo": pg_undo, "flux_undo": flux_undo,
    "pg_state": pg_state, "flux_state": flux_state,
    "mongo": mongo, "mongo_undo": mongo_undo, "mongo_state": mongo_state,
}
