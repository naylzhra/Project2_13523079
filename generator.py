import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 42
START = datetime(2026, 9, 1, tzinfo=timezone.utc)
DAYS = 30
END = START + timedelta(days=DAYS)
OUT = Path("data")

N_CUSTOMERS = 600
ORDERS_PER_DAY = 80
ORDERS_PER_DAY_SD = 8
TWO_DETAIL_SHARE = 0.30
UNPAID_SHARE = 0.05
PICKUP_SHARE = 0.60
DELIVERY_SHARE = 0.60
OPEN_UNTIL_HOUR = 14         # 00:00-14:00 UTC = 07:00-21:00 WIB
READING_STEP = 300           # 5 minutes

SERVICES = [
    (1, "Regular wash & fold", 7000, 0.60, (40, 50), (45, 60), 40.0, (20, 80)),
    (2, "Express wash & fold", 12000, 0.25, (30, 40), (35, 45), 30.0, (20, 60)),
    (3, "Bedcover & linen", 15000, 0.15, (50, 65), (60, 80), 60.0, (15, 50)),
]
SERVICE = {s[0]: s for s in SERVICES}

# 8 washers (ids 1-8) and 8 dryers (ids 9-16), installed in three batches.
INSTALLED = ["2024-03-01", "2024-03-01", "2024-03-01", "2025-01-15",
             "2025-01-15", "2025-01-15", "2025-06-10", "2025-06-10"]
MACHINES = (
    [(i, f"Washer {i}", "washer", INSTALLED[i - 1]) for i in range(1, 9)]
    + [(8 + i, f"Dryer {i}", "dryer", INSTALLED[i - 1]) for i in range(1, 9)]
)
WASHERS = [m[0] for m in MACHINES if m[2] == "washer"]
DRYERS = [m[0] for m in MACHINES if m[2] == "dryer"]

PAYMENT_METHODS = ["cash", "qris", "bank_transfer"]
PAYMENT_WEIGHTS = [0.35, 0.45, 0.20]

FIRST_NAMES = ["Adi", "Ayu", "Bagus", "Budi", "Citra", "Dewi", "Dimas", "Eka", "Fajar",
               "Fitri", "Gilang", "Hana", "Indah", "Joko", "Kurnia", "Lestari", "Made",
               "Nadia", "Nur", "Putri", "Rizky", "Sari", "Siti", "Taufik", "Wulan", "Yoga"]
LAST_NAMES = ["Pratama", "Saputra", "Wijaya", "Hidayat", "Santoso", "Kusuma", "Nugroho",
              "Lestari", "Wibowo", "Rahman", "Setiawan", "Permana", "Siregar", "Harahap",
              "Gunawan", "Utami", "Purnama", "Halim"]
STREETS = ["Dago", "Dipatiukur", "Tubagus Ismail", "Cisitu", "Sekeloa", "Taman Sari",
           "Ganesha", "Cikutra", "Sadang Serang", "Pahlawan"]


def ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def minutes(rng, lo, hi):
    return timedelta(seconds=rng.randint(lo * 60, hi * 60))

def next_open(dt, rng):
    if dt.hour < OPEN_UNTIL_HOUR:
        return dt
    next_day = (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    return next_day + minutes(rng, 5, 30)

def unique_time(dt, used):
    while dt in used:
        dt += timedelta(seconds=1)
    used.add(dt)
    return dt

def happened(dt):
    return dt is not None and dt < END

def gen_customers(rng):
    customers = []
    for cid in range(1, N_CUSTOMERS + 1):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        phone = "08" + "".join(str(rng.randint(0, 9)) for _ in range(10))
        address = f"Jl. {rng.choice(STREETS)} No. {rng.randint(1, 200)}, Bandung"
        customers.append((cid, name, phone, address))
    return customers

def pick_services(rng, k):
    ids = [s[0] for s in SERVICES]
    weights = [s[3] for s in SERVICES]
    first = rng.choices(ids, weights)[0]
    if k == 1:
        return [first]
    rest = [(i, w) for i, w in zip(ids, weights) if i != first]
    second = rng.choices([i for i, _ in rest], [w for _, w in rest])[0]
    return [first, second]

def gen_orders(rng):
    loyalty = [rng.uniform(0.2, 3.0) for _ in range(N_CUSTOMERS)]
    times = []
    for day in range(DAYS):
        n = max(1, round(rng.gauss(ORDERS_PER_DAY, ORDERS_PER_DAY_SD)))
        day_start = START + timedelta(days=day)
        for sec in rng.sample(range(OPEN_UNTIL_HOUR * 3600), n):
            times.append(day_start + timedelta(seconds=sec))
    times.sort()

    orders = []
    used_payment = set()
    for oid, order_time in enumerate(times, start=1):
        details = []
        k = 2 if rng.random() < TWO_DETAIL_SHARE else 1
        for detail_no, sid in enumerate(pick_services(rng, k), start=1):
            lo, hi = SERVICE[sid][7]
            tenths = rng.randint(lo, hi)
            details.append({
                "detail_no": detail_no,
                "service_id": sid,
                "weight": f"{tenths // 10}.{tenths % 10}",
                "subtotal": SERVICE[sid][2] * tenths // 10,
            })
        pickup = rng.random() < PICKUP_SHARE
        delivery = rng.random() < DELIVERY_SHARE
        paid = rng.random() >= UNPAID_SHARE
        payment_time = None
        if paid:
            delay = minutes(rng, 5, 60) if pickup else minutes(rng, 1, 5)
            payment_time = unique_time(order_time + delay, used_payment)
        orders.append({
            "order_id": oid,
            "customer_id": rng.choices(range(1, N_CUSTOMERS + 1), loyalty)[0],
            "order_time": order_time,
            "details": details,
            "pickup": pickup,
            "delivery": delivery,
            "payment_time": payment_time,
            "payment_method": rng.choices(PAYMENT_METHODS, PAYMENT_WEIGHTS)[0] if paid else None,
            "total_amount": sum(d["subtotal"] for d in details),
        })
    return orders


def simulate_intake(rng, orders):
    for o in orders:
        o["ready"] = None
        if not happened(o["payment_time"]):
            continue
        if o["pickup"]:
            o["pickup_in_progress"] = next_open(o["payment_time"] + minutes(rng, 15, 60), rng)
            o["pickup_done"] = o["pickup_in_progress"] + minutes(rng, 20, 60)
            o["ready"] = o["pickup_done"]
        else:
            o["ready"] = o["payment_time"]


def schedule_runs(rng, orders):
    free = {m: START for m in WASHERS + DRYERS}
    turnaround = timedelta(minutes=2)
    queue = [(o["ready"], o["order_id"], d["detail_no"], o, d)
             for o in orders if happened(o["ready"]) for d in o["details"]]
    queue.sort(key=lambda q: (q[0], q[1], q[2]))
    runs = []
    for ready, _, _, o, d in queue:
        svc = SERVICE[d["service_id"]]
        for machines, duration in ((WASHERS, svc[4]), (DRYERS, svc[5])):
            machine = min(machines, key=lambda m: (free[m], m))
            start = next_open(max(ready, free[machine] + turnaround), rng)
            end = start + minutes(rng, *duration)
            if end >= END:
                break
            runs.append({"machine_id": machine, "order": o, "detail": d,
                         "start": start, "end": end})
            free[machine] = end
            d.setdefault("runs", []).append(end)
            ready = end + minutes(rng, 1, 5)
    runs.sort(key=lambda r: (r["start"], r["machine_id"]))
    for run_id, r in enumerate(runs, start=1):
        r["run_id"] = run_id
    return runs


def simulate_return(rng, orders):
    used_delivery = set()
    for o in orders:
        o["cleaning_done"] = None
        if happened(o["ready"]) and all(len(d.get("runs", [])) == 2 for d in o["details"]):
            o["cleaning_done"] = max(d["runs"][1] for d in o["details"])
        if o["cleaning_done"] and o["delivery"]:
            created = unique_time(o["cleaning_done"] + minutes(rng, 5, 30), used_delivery)
            o["delivery_created"] = created
            o["delivery_in_progress"] = next_open(created + minutes(rng, 10, 60), rng)
            o["delivery_done"] = o["delivery_in_progress"] + minutes(rng, 20, 60)

        # Order state as of END (events at or after END have not happened).
        o["completed_at"] = None
        if not happened(o["payment_time"]):
            o["status"] = "waiting_payment"
            o["payment_time"] = o["payment_method"] = None
        elif o["pickup"] and not happened(o.get("pickup_done")):
            o["status"] = "pickup"
        elif not happened(o["cleaning_done"]):
            o["status"] = "processing"
        elif not o["delivery"]:
            o["status"] = "completed"
            o["completed_at"] = o["cleaning_done"]
        elif not happened(o.get("delivery_created")):
            o["status"] = "processing"
        elif not happened(o["delivery_done"]):
            o["status"] = "delivery"
        else:
            o["status"] = "completed"
            o["completed_at"] = o["delivery_done"]

def build_shipments(orders):
    shipments = []
    for o in orders:
        for kind in ("pickup", "delivery"):
            created = o["payment_time"] if kind == "pickup" else o.get("delivery_created")
            if not o[kind] or not happened(created):
                continue
            if happened(o.get(f"{kind}_done")):
                status = "completed"
            elif happened(o.get(f"{kind}_in_progress")):
                status = "in_progress"
            else:
                status = "pending"
            shipments.append((o["order_id"], kind, status, created))
    shipments.sort(key=lambda s: (s[3], s[1]))
    return [(sid,) + s for sid, s in enumerate(shipments, start=1)]

def write_csv(name, header, rows):
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

def write_readings(runs):
    by_machine = {m[0]: [] for m in MACHINES}
    for r in runs:
        by_machine[r["machine_id"]].append(
            (r["start"].timestamp(), r["end"].timestamp(), r["detail"]["service_id"]))
    start_s = int(START.timestamp())
    steps = DAYS * 86400 // READING_STEP
    scale = READING_STEP / 30
    k_run = 1 - (1 - 0.12) ** scale
    k_idle = 1 - (1 - 0.03) ** scale
    noise = math.sqrt(scale)
    count = 0
    with open(OUT / "machine_readings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["machine_id", "recorded_at", "temperature_c", "power_w", "water_lpm", "rpm"])
        for machine_id, _, machine_type, _ in MACHINES:
            rng = random.Random(SEED * 1000 + machine_id)
            washer = machine_type == "washer"
            runs_m = by_machine[machine_id]
            i = 0
            temp = 28.0
            for step in range(steps):
                t = start_s + step * READING_STEP
                hour = (t % 86400) / 3600
                ambient = 28.0 + 1.5 * math.sin(2 * math.pi * (hour - 1) / 24)
                while i < len(runs_m) and runs_m[i][1] <= t:
                    i += 1
                running = i < len(runs_m) and runs_m[i][0] <= t
                if running:
                    run_start, run_end, sid = runs_m[i]
                    frac = (t - run_start) / (run_end - run_start)
                    if washer:
                        if frac < 0.10:      # fill with cold water
                            target, water, rpm = ambient - 2, rng.uniform(12, 15), rng.randint(30, 50)
                            power = rng.uniform(150, 300)
                        elif frac < 0.60:    # heat and wash
                            target, water, rpm = SERVICE[sid][6], rng.uniform(0, 0.5), rng.randint(40, 60)
                            power = rng.uniform(1900, 2200) if temp < target - 0.5 else rng.uniform(250, 400)
                        elif frac < 0.80:    # rinse
                            target, water, rpm = ambient - 2, rng.uniform(10, 14), rng.randint(40, 60)
                            power = rng.uniform(200, 350)
                        else:                # spin
                            target, water, rpm = ambient, 0.0, rng.randint(800, 1200)
                            power = rng.uniform(500, 700)
                    else:
                        water, rpm = None, rng.randint(45, 55)
                        if frac < 0.85:      # hot air
                            target = 70.0 if sid == 3 else 65.0
                            power = rng.uniform(2500, 3000)
                        else:                # cool-down
                            target = ambient + 10
                            power = rng.uniform(300, 500)
                    temp += (max(-1.5 * scale, min(1.0 * scale, (target - temp) * k_run))
                             + rng.gauss(0, 0.15 * noise))
                else:
                    water = 0.0 if washer else None
                    rpm = 0
                    power = rng.uniform(3, 6) if washer else rng.uniform(2, 5)
                    temp += (ambient - temp) * k_idle + rng.gauss(0, 0.1 * noise)
                w.writerow([
                    machine_id,
                    datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    f"{temp:.1f}",
                    f"{power:.1f}",
                    "" if water is None else f"{water:.1f}",
                    rpm,
                ])
                count += 1
    return count

def main():
    rng = random.Random(SEED)
    OUT.mkdir(exist_ok=True)

    customers = gen_customers(rng)
    orders = gen_orders(rng)
    simulate_intake(rng, orders)
    runs = schedule_runs(rng, orders)
    simulate_return(rng, orders)
    shipments = build_shipments(orders)

    write_csv("customers", ["customer_id", "name", "phone_number", "address"], customers)
    write_csv("services", ["service_id", "service_name", "price"],
              [(s[0], s[1], s[2]) for s in SERVICES])
    write_csv("machines", ["machine_id", "machine_name", "machine_type", "installed_at"], MACHINES)
    write_csv("orders",
              ["order_id", "customer_id", "status", "order_time", "completed_at",
               "total_amount", "payment_method", "payment_time"],
              [(o["order_id"], o["customer_id"], o["status"], ts(o["order_time"]),
                ts(o["completed_at"]) if o["completed_at"] else "",
                o["total_amount"], o["payment_method"] or "",
                ts(o["payment_time"]) if o["payment_time"] else "")
               for o in orders])
    write_csv("order_details",
              ["order_id", "detail_no", "service_id", "weight_kg", "subtotal"],
              [(o["order_id"], d["detail_no"], d["service_id"], d["weight"], d["subtotal"])
               for o in orders for d in o["details"]])
    write_csv("shipments",
              ["shipment_id", "order_id", "shipment_type", "shipment_status", "created_at"],
              [(s[0], s[1], s[2], s[3], ts(s[4])) for s in shipments])
    write_csv("wash_runs",
              ["run_id", "machine_id", "order_id", "detail_no", "start_time", "end_time"],
              [(r["run_id"], r["machine_id"], r["order"]["order_id"], r["detail"]["detail_no"],
                ts(r["start"]), ts(r["end"])) for r in runs])
    readings = write_readings(runs)

    statuses = {}
    for o in orders:
        statuses[o["status"]] = statuses.get(o["status"], 0) + 1
    print(f"seed={SEED}  period={ts(START)} .. {ts(END)}")
    print(f"customers={len(customers)} services={len(SERVICES)} machines={len(MACHINES)}")
    print(f"orders={len(orders)} order_details={sum(len(o['details']) for o in orders)} "
          f"shipments={len(shipments)} wash_runs={len(runs)} machine_readings={readings}")
    print("order status:", dict(sorted(statuses.items())))


if __name__ == "__main__":
    main()
