from .common import SECOND, at, epoch, flux_records, influx_write, rfc

MACHINE_ID = 3
RECORDED_AT = at("2026-09-15T12:00:00Z")
CORRECTED = (45.0, 2000.0)   # temperature, power


def setup(conn):
    machine_type, temp, power = conn.execute(
        "SELECT m.machine_type, r.temperature_c, r.power_w "
        "FROM machine_readings r JOIN machines m USING (machine_id) "
        "WHERE r.machine_id = %s AND r.recorded_at = %s", (MACHINE_ID, RECORDED_AT)).fetchone()
    return {"machine_type": machine_type, "original": (temp, power)}

def pg_set(conn, values):
    with conn.transaction():
        updated = conn.execute(
            "UPDATE machine_readings SET temperature_c = %s, power_w = %s "
            "WHERE machine_id = %s AND recorded_at = %s",
            (*values, MACHINE_ID, RECORDED_AT)).rowcount
        if updated != 1:
            raise RuntimeError("reading to correct not found")

def flux_set(client, ctx, values):
    temp, power = values
    influx_write(client, [
        f"machine_reading,machine_id={MACHINE_ID},machine_type={ctx['machine_type']} "
        f"temperature_c={float(temp)!r},power_w={float(power)!r} {epoch(RECORDED_AT)}"])

def pg_state(conn, ctx):
    return conn.execute(
        "SELECT temperature_c, power_w FROM machine_readings WHERE machine_id = %s AND recorded_at = %s",
        (MACHINE_ID, RECORDED_AT)).fetchone()

def flux_state(client, ctx):
    fields = {r["_field"]: r["_value"] for r in flux_records(client, f"""range(start: {rfc(RECORDED_AT)}, stop: {rfc(RECORDED_AT + SECOND)})
  |> filter(fn: (r) => r._measurement == "machine_reading" and r.machine_id == "{MACHINE_ID}"
                       and (r._field == "temperature_c" or r._field == "power_w"))""")}
    return (fields.get("temperature_c"), fields.get("power_w"))

def mongo_set(db, values):
    match = {"machine.machine_id": MACHINE_ID, "recorded_at": RECORDED_AT}
    doc = db.machine_readings.find_one(match, {"_id": 0})
    if doc is None:
        raise RuntimeError("reading to correct not found")
    temp, power = values
    db.machine_readings.delete_many(match)
    db.machine_readings.insert_one({**doc, "temperature_c": float(temp), "power_w": float(power)})

def mongo_state(db, ctx):
    doc = db.machine_readings.find_one({"machine.machine_id": MACHINE_ID, "recorded_at": RECORDED_AT})
    return (doc["temperature_c"], doc["power_w"]) if doc else (None, None)


WRITE = {
    "title": "Koreksi satu pembacaan sensor",
    "state": "(temperature_c, power_w) of the reading",
    "setup": setup,
    "pg": lambda conn, ctx: pg_set(conn, CORRECTED),
    "flux": lambda client, ctx: flux_set(client, ctx, CORRECTED),
    "pg_undo": lambda conn, ctx: pg_set(conn, ctx["original"]),
    "flux_undo": lambda client, ctx: flux_set(client, ctx, ctx["original"]),
    "mongo": lambda db, ctx: mongo_set(db, CORRECTED),
    "mongo_undo": lambda db, ctx: mongo_set(db, ctx["original"]),
    "pg_state": pg_state, "flux_state": flux_state, "mongo_state": mongo_state,
}
