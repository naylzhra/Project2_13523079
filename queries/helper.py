import os
import sys
import statistics
import time
from db import influx_client, pg_connect
from config import START, STOP
from . import QUERIES


def run_pg(conn, name):
    """Return (sorted rows, seconds spent executing and fetching)."""
    t0 = time.perf_counter()
    rows = conn.execute(QUERIES[name]["sql"], {"start": START, "stop": STOP}).fetchall()
    elapsed = time.perf_counter() - t0
    return sorted(tuple(row) for row in rows), elapsed


def run_flux(client, name):
    """Return (sorted rows, seconds spent executing and fetching)."""
    t0 = time.perf_counter()
    tables = client.query_api().query(QUERIES[name]["flux"])
    elapsed = time.perf_counter() - t0
    columns = QUERIES[name].get("flux_columns", ["_time", "_value"])
    rows = [tuple(rec.values[c] for c in columns) for table in tables for rec in table.records]
    return sorted(rows), elapsed


def rows_match(a, b, tolerance):
    """Exact comparison, or per-value tolerance for float columns."""
    if tolerance is None:
        return a == b
    if len(a) != len(b):
        return False
    for row_a, row_b in zip(a, b):
        for x, y in zip(row_a, row_b):
            if isinstance(x, float) or isinstance(y, float):
                if abs(x - y) > tolerance:
                    return False
            elif x != y:
                return False
    return True


RUNS = 5


def compare(conn, client, name):
    """Run the query RUNS times on each database.

    Return (equal, pg_rows, flux_rows, pg_times, flux_times); the times are
    lists of seconds, one per run, and the rows come from the last run.
    One untimed warm-up run on each database comes first.
    """
    run_pg(conn, name)
    run_flux(client, name)
    pg_times, flux_times = [], []
    for _ in range(RUNS):
        pg_rows, pg_s = run_pg(conn, name)
        flux_rows, flux_s = run_flux(client, name)
        pg_times.append(pg_s)
        flux_times.append(flux_s)
    equal = rows_match(pg_rows, flux_rows, QUERIES[name].get("tolerance"))
    return equal, pg_rows, flux_rows, pg_times, flux_times


def format_times(times):
    """'avg 12.34 ms  (runs: 10.00, 12.00, ...)', in milliseconds."""
    runs = ", ".join(f"{t * 1000:.2f}" for t in times)
    return f"avg {statistics.mean(times) * 1000:.2f} ms  (runs: {runs})"


RESULTS_DIR = "results"


def write_result(name, equal, pg_rows, flux_rows, pg_times, flux_times):
    """Write the full result of one query to results/<name>.txt."""
    q = QUERIES[name]
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"{name}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{name}: {q['title']}\n")
        f.write(f"rows: {len(pg_rows)}  "
                f"PostgreSQL vs InfluxDB: {'IDENTICAL' if equal else 'DIFFERENT'}\n")
        f.write(f"time over {RUNS} runs (after 1 untimed warm-up run)\n")
        f.write(f"  PostgreSQL: {format_times(pg_times)}\n")
        f.write(f"  InfluxDB:   {format_times(flux_times)}\n\n")
        f.write(" | ".join(q["columns"]) + "\n")
        for row in pg_rows:
            f.write(" | ".join(str(v) for v in row) + "\n")
        if not equal:
            f.write("\ndiffering rows (PostgreSQL xor InfluxDB):\n")
            for row in sorted(set(pg_rows) ^ set(flux_rows)):
                f.write(f"{row}\n")
    return path


def main():
    names = sys.argv[1:] or list(QUERIES)
    with pg_connect() as conn, influx_client() as client:
        for name in names:
            equal, pg_rows, flux_rows, pg_times, flux_times = compare(conn, client, name)
            q = QUERIES[name]
            print(f"{name}: {q['title']}  ({len(pg_rows)} rows)  "
                  f"{'IDENTICAL' if equal else 'DIFFERENT'}")
            print(f"  PostgreSQL {format_times(pg_times)}")
            print(f"  InfluxDB   {format_times(flux_times)}")
            print(f"  {' | '.join(q['columns'])}")
            for row in pg_rows[:5]:
                print(f"  {row}")
            if len(pg_rows) > 5:
                print(f"  ... {len(pg_rows) - 5} more")
            if not equal:
                diff = sorted(set(pg_rows) ^ set(flux_rows))
                print(f"  differing rows (PostgreSQL xor InfluxDB): {diff[:10]}")
            print(f"  saved to {write_result(name, equal, pg_rows, flux_rows, pg_times, flux_times)}")


if __name__ == "__main__":
    main()
