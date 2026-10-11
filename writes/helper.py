import os
import time

from config import MONGO_DB
from db import influx_client, mongo_client, pg_connect
from queries.helper import RESULTS_DIR, parse_args
from . import WRITES
from .common import influx_rebuild, mongo_rebuild_readings

PREFIX = {"PostgreSQL": "pg", "InfluxDB": "flux", "MongoDB": "mongo"}


def timed(fn, *args):
    t0 = time.perf_counter()
    fn(*args)
    return time.perf_counter() - t0


def run(handles, name):
    """Run one write operation once on each database, then revert it.

    handles maps each database to run (PostgreSQL first) to its connection,
    client or database.
    The operation is timed; reading its effect and reverting it are not, so
    the loaded dataset is unchanged afterwards.
    Return (before, after, restored, seconds); before, after and seconds are
    dicts keyed by database name.
    """
    w = WRITES[name]
    ctx = w["setup"](handles["PostgreSQL"])

    def state(db):
        return tuple(w[f"{PREFIX[db]}_state"](handles[db], ctx))

    before = {db: state(db) for db in handles}
    after, seconds = {}, {}
    for db in handles:
        p = PREFIX[db]
        try:
            seconds[db] = timed(w[p], handles[db], ctx)
            after[db] = state(db)
        finally:
            w[f"{p}_undo"](handles[db], ctx)
    restored = all(state(db) == before[db] for db in handles)
    return before, after, restored, seconds


def verdict(before, after, restored):
    pg = "PostgreSQL"
    same = "  ".join(
        f"PostgreSQL vs {db}: "
        f"{'IDENTICAL' if after[db] == after[pg] and before[db] == before[pg] else 'DIFFERENT'}"
        for db in before if db != pg)
    changed = "applied" if after[pg] != before[pg] else "NO CHANGE"
    return same, changed, "restored" if restored else "NOT RESTORED"


def write_result(name, before, after, restored, seconds, results_dir=RESULTS_DIR):
    w = WRITES[name]
    os.makedirs(results_dir, exist_ok=True)
    path = os.path.join(results_dir, f"{name}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{name}: {w['title']}\n")
        f.write("{}  ({}, {})\n".format(*verdict(before, after, restored)))
        f.write("time (1 run, database reverted afterwards)\n")
        for db in seconds:
            f.write(f"  {db + ':':<12}{seconds[db] * 1000:.2f} ms\n")
        f.write(f"\nstate: {w['state']}\n")
        f.write("  before:  " + "  ".join(f"{db} {before[db]}" for db in before) + "\n")
        f.write("  applied: " + "  ".join(f"{db} {after[db]}" for db in after) + "\n")
        f.write(f"  data restored afterwards: {'yes' if restored else 'NO'}\n")
    return path


def main():
    names, databases, results_dir = parse_args(WRITES)
    with pg_connect() as conn, influx_client() as client, mongo_client() as mongo:
        conn.autocommit = True
        handles = {"PostgreSQL": conn, "InfluxDB": client, "MongoDB": mongo[MONGO_DB]}
        handles = {db: handles[db] for db in databases}
        try:
            for name in names:
                before, after, restored, seconds = run(handles, name)
                same, changed, back = verdict(before, after, restored)
                print(f"{name}: {WRITES[name]['title']}  {same}  ({changed}, {back})")
                print("  " + "  |  ".join(f"{db} {seconds[db] * 1000:.2f} ms" for db in seconds))
                print(f"  saved to {write_result(name, before, after, restored, seconds, results_dir)}")
        finally:
            # PostgreSQL undoes exactly; InfluxDB and MongoDB readings are reset by a clean reload.
            if "InfluxDB" in handles:
                points = influx_rebuild(client)
                print(f"InfluxDB bucket rebuilt from data/*.csv ({points} points)")
            if "MongoDB" in handles:
                readings = mongo_rebuild_readings(handles["MongoDB"])
                print(f"MongoDB machine_readings rebuilt from data/*.csv ({readings} documents)")


if __name__ == "__main__":
    main()
