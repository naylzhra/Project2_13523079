import os
import sys
import statistics
import time
from db import influx_client, mongo_client, pg_connect
from config import MONGO_DB, START, STOP
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

def run_mongo(db, name):
    """Return (sorted rows, seconds spent executing and fetching)."""
    q = QUERIES[name]
    t0 = time.perf_counter()
    docs = list(db[q["mongo"]["collection"]].aggregate(q["mongo"]["pipeline"]))
    elapsed = time.perf_counter() - t0
    return sorted(tuple(doc[c] for c in q["columns"]) for doc in docs), elapsed


def rows_match(a, b, tolerance):
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


def compare(runners, name):
    for run in runners.values():
        run()
    rows, times = {}, {db: [] for db in runners}
    for _ in range(RUNS):
        for db, run in runners.items():
            rows[db], seconds = run()
            times[db].append(seconds)
    tolerance = QUERIES[name].get("tolerance")
    equal = {db: rows_match(rows["PostgreSQL"], rows[db], tolerance) for db in runners if db != "PostgreSQL"}
    return rows, times, equal


def format_times(times):
    """'avg 12.34 ms  (runs: 10.00, 12.00, ...)', in milliseconds."""
    runs = ", ".join(f"{t * 1000:.2f}" for t in times)
    return f"avg {statistics.mean(times) * 1000:.2f} ms  (runs: {runs})"


def verdicts(equal):
    return "  ".join(f"PostgreSQL vs {db}: {'IDENTICAL' if same else 'DIFFERENT'}" for db, same in equal.items())


RESULTS_DIR = "results"
MONGO_RESULTS_DIR = "results_mongo"


def parse_args(available):
    args = sys.argv[1:]
    names = [a for a in args if a != "--mongo"] or list(available)
    if "--mongo" in args:
        return names, ("PostgreSQL", "InfluxDB", "MongoDB"), MONGO_RESULTS_DIR
    return names, ("PostgreSQL", "InfluxDB"), RESULTS_DIR


def write_result(name, rows, times, equal, results_dir=RESULTS_DIR):
    """Write the full result of one query to <results_dir>/<name>.txt."""
    q = QUERIES[name]
    os.makedirs(results_dir, exist_ok=True)
    path = os.path.join(results_dir, f"{name}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{name}: {q['title']}\n")
        f.write(f"rows: {len(rows['PostgreSQL'])}  {verdicts(equal)}\n")
        f.write(f"time over {RUNS} runs (after 1 untimed warm-up run)\n")
        for db in times:
            f.write(f"  {db + ':':<12}{format_times(times[db])}\n")
        f.write("\n" + " | ".join(q["columns"]) + "\n")
        for row in rows["PostgreSQL"]:
            f.write(" | ".join(str(v) for v in row) + "\n")
        for db, same in equal.items():
            if not same:
                f.write(f"\ndiffering rows (PostgreSQL xor {db}):\n")
                for row in sorted(set(rows["PostgreSQL"]) ^ set(rows[db])):
                    f.write(f"{row}\n")
    return path


def main():
    names, databases, results_dir = parse_args(QUERIES)
    with pg_connect() as conn, influx_client() as client, mongo_client() as mongo:
        db = mongo[MONGO_DB]
        for name in names:
            runners = {"PostgreSQL": lambda: run_pg(conn, name),
                       "InfluxDB": lambda: run_flux(client, name),
                       "MongoDB": lambda: run_mongo(db, name)}
            runners = {d: runners[d] for d in databases}
            rows, times, equal = compare(runners, name)
            q = QUERIES[name]
            print(f"{name}: {q['title']}  ({len(rows['PostgreSQL'])} rows)  {verdicts(equal)}")
            for d in databases:
                print(f"  {d:<11}{format_times(times[d])}")
            print(f"  {' | '.join(q['columns'])}")
            for row in rows["PostgreSQL"][:5]:
                print(f"  {row}")
            if len(rows["PostgreSQL"]) > 5:
                print(f"  ... {len(rows['PostgreSQL']) - 5} more")
            for d, same in equal.items():
                if not same:
                    diff = sorted(set(rows["PostgreSQL"]) ^ set(rows[d]))
                    print(f"  differing rows (PostgreSQL xor {d}): {diff[:10]}")
            print(f"  saved to {write_result(name, rows, times, equal, results_dir)}")


if __name__ == "__main__":
    main()
