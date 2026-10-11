import config
from load import influx_lines, read_csv
from .common import at, flux_count, influx_delete, influx_write

START = at(config.START)
CUTOFF = at("2026-09-02T00:00:00Z")
COLUMNS = ["machine_id", "recorded_at", "temperature_c", "power_w", "water_lpm", "rpm"]


def setup(conn):
    """The purged readings, from the same CSV and line protocol the loader uses."""
    rows = [[r[c] or None for c in COLUMNS] for r in read_csv("machine_readings")
            if at(r["recorded_at"]) < CUTOFF]
    cutoff = int(CUTOFF.timestamp())
    lines = [line for line in influx_lines()
             if line.startswith("machine_reading,") and int(line.rsplit(" ", 1)[1]) < cutoff]
    return {"rows": rows, "lines": lines}

def pg(conn, ctx):
    with conn.transaction():
        conn.execute("DELETE FROM machine_readings WHERE recorded_at < %s", (CUTOFF,))

def flux(client, ctx):
    influx_delete(client, "machine_reading", START, CUTOFF)

def pg_undo(conn, ctx):
    with conn.transaction():
        conn.execute("DELETE FROM machine_readings WHERE recorded_at < %s", (CUTOFF,))
        with conn.cursor().copy(f"COPY machine_readings ({', '.join(COLUMNS)}) FROM STDIN") as copy:
            for row in ctx["rows"]:
                copy.write_row(row)
    conn.execute("VACUUM ANALYZE machine_readings")

def flux_undo(client, ctx):
    influx_write(client, ctx["lines"])

def pg_state(conn, ctx):
    return conn.execute("SELECT count(*) FROM machine_readings WHERE recorded_at < %s", (CUTOFF,)).fetchone()

def flux_state(client, ctx):
    return (flux_count(client, "machine_reading", "power_w", START, CUTOFF),)


WRITE = {
    "title": "Hapus pembacaan sensor sebelum tanggal tertentu",
    "state": "(readings before the cut-off,)",
    "setup": setup, "pg": pg, "flux": flux, "pg_undo": pg_undo, "flux_undo": flux_undo,
    "pg_state": pg_state, "flux_state": flux_state,
}
