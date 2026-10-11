import os
import sys
import time

from db import influx_client, pg_connect
from queries.helper import RESULTS_DIR
from . import WRITES
from .common import influx_rebuild


def timed(fn, *args):
    t0 = time.perf_counter()
    fn(*args)
    return time.perf_counter() - t0


def run(conn, client, name):
    """Run one write operation once on each database, then revert it.

    The operation is timed; reading its effect and reverting it are not, so
    the loaded dataset is unchanged afterwards.
    Return (before, pg_after, flux_after, restored, pg_seconds, flux_seconds).
    """
    w = WRITES[name]
    ctx = w["setup"](conn)
    before = (w["pg_state"](conn, ctx), w["flux_state"](client, ctx))
    try:
        pg_s = timed(w["pg"], conn, ctx)
        pg_after = w["pg_state"](conn, ctx)
    finally:
        w["pg_undo"](conn, ctx)
    try:
        flux_s = timed(w["flux"], client, ctx)
        flux_after = w["flux_state"](client, ctx)
    finally:
        w["flux_undo"](client, ctx)
    restored = (w["pg_state"](conn, ctx), w["flux_state"](client, ctx)) == before
    return before, tuple(pg_after), tuple(flux_after), restored, pg_s, flux_s


def verdict(before, pg_after, flux_after, restored):
    pg_before, flux_before = tuple(before[0]), tuple(before[1])
    same = pg_after == flux_after and pg_before == flux_before
    changed = pg_after != pg_before
    return ("IDENTICAL" if same else "DIFFERENT",
            "applied" if changed else "NO CHANGE",
            "restored" if restored else "NOT RESTORED")


def write_result(name, before, pg_after, flux_after, restored, pg_s, flux_s):
    w = WRITES[name]
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"{name}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{name}: {w['title']}\n")
        f.write("PostgreSQL vs InfluxDB: {}  ({}, {})\n".format(
            *verdict(before, pg_after, flux_after, restored)))
        f.write("time\n")
        f.write(f"  PostgreSQL: {pg_s * 1000:.2f} ms\n")
        f.write(f"  InfluxDB:   {flux_s * 1000:.2f} ms\n\n")
        f.write(f"state: {w['state']}\n")
        f.write(f"  before:  PostgreSQL {tuple(before[0])}  InfluxDB {tuple(before[1])}\n")
        f.write(f"  applied: PostgreSQL {pg_after}  InfluxDB {flux_after}\n")
        f.write(f"  data restored afterwards: {'yes' if restored else 'NO'}\n")
    return path


def main():
    names = sys.argv[1:] or list(WRITES)
    with pg_connect() as conn, influx_client() as client:
        conn.autocommit = True
        try:
            for name in names:
                result = run(conn, client, name)
                before, pg_after, flux_after, restored, pg_s, flux_s = result
                same, changed, back = verdict(before, pg_after, flux_after, restored)
                print(f"{name}: {WRITES[name]['title']}  {same}  ({changed}, {back})")
                print(f"  PostgreSQL {pg_s * 1000:.2f} ms  |  InfluxDB {flux_s * 1000:.2f} ms")
                print(f"  saved to {write_result(name, *result)}")
        finally:
            # PostgreSQL undoes exactly; InfluxDB is reset by a clean reload.
            points = influx_rebuild(client)
            print(f"InfluxDB bucket rebuilt from data/*.csv ({points} points)")


if __name__ == "__main__":
    main()
