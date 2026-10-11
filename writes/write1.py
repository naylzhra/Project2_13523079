from decimal import Decimal

from load import tag
from .common import SECOND, at, epoch, flux_count, influx_delete, influx_write

ORDER_TIME = at("2026-10-01T01:00:00Z")
CUSTOMER_ID = 1
DETAILS = [("Regular wash & fold", Decimal("3.5")), ("Express wash & fold", Decimal("2.0"))]


def setup(conn):
    prices = {name: (sid, price) for sid, name, price in conn.execute("SELECT service_id, service_name, price FROM services")}
    details = []
    for no, (name, kg) in enumerate(DETAILS, start=1):
        service_id, price = prices[name]
        details.append((no, name, service_id, kg, int(kg * price)))
    order_id = conn.execute("SELECT max(order_id) + 1 FROM orders").fetchone()[0]
    return {"order_id": order_id, "details": details,
            "total": sum(d[4] for d in details)}


def pg(conn, ctx):
    with conn.transaction():
        conn.execute(
            "INSERT INTO orders (order_id, customer_id, status, order_time, total_amount) "
            "VALUES (%s, %s, 'waiting_payment', %s, %s)",
            (ctx["order_id"], CUSTOMER_ID, ORDER_TIME, ctx["total"]))
        conn.cursor().executemany(
            "INSERT INTO order_details (order_id, detail_no, service_id, weight_kg, subtotal) "
            "VALUES (%s, %s, %s, %s, %s)",
            [(ctx["order_id"], no, sid, kg, sub) for no, _, sid, kg, sub in ctx["details"]])


def flux(client, ctx):
    t = epoch(ORDER_TIME)
    lines = [f'order order_id={ctx["order_id"]}i,customer_id={CUSTOMER_ID}i,'
             f'total_amount={ctx["total"]}i,status="waiting_payment" {t}']
    for no, name, _, kg, sub in ctx["details"]:
        lines.append(f'order_detail,detail_no={no},service_name={tag(name)} '
                     f'order_id={ctx["order_id"]}i,weight_kg={float(kg)},subtotal={sub}i {t}')
    influx_write(client, lines)


def pg_undo(conn, ctx):
    with conn.transaction():
        conn.execute("DELETE FROM order_details WHERE order_id = %s", (ctx["order_id"],))
        conn.execute("DELETE FROM orders WHERE order_id = %s", (ctx["order_id"],))

def flux_undo(client, ctx):
    influx_delete(client, "order", ORDER_TIME, ORDER_TIME + SECOND)
    influx_delete(client, "order_detail", ORDER_TIME, ORDER_TIME + SECOND)

def pg_state(conn, ctx):
    return conn.execute(
        "SELECT (SELECT count(*) FROM orders WHERE order_id = %(id)s),"
        "       (SELECT count(*) FROM order_details WHERE order_id = %(id)s)",
        {"id": ctx["order_id"]}).fetchone()

def flux_state(client, ctx):
    end = ORDER_TIME + SECOND
    return (flux_count(client, "order", "order_id", ORDER_TIME, end, ctx["order_id"]),
            flux_count(client, "order_detail", "order_id", ORDER_TIME, end, ctx["order_id"]))

def mongo(db, ctx):
    db.orders.insert_one({
        "_id": ctx["order_id"], "customer_id": CUSTOMER_ID, "status": "waiting_payment",
        "order_time": ORDER_TIME, "completed_at": None, "total_amount": ctx["total"],
        "payment": None, "shipments": [],
        "details": [{"detail_no": no, "service_id": sid, "service_name": name,
                     "weight_kg": float(kg), "subtotal": sub}
                    for no, name, sid, kg, sub in ctx["details"]]})

def mongo_undo(db, ctx):
    db.orders.delete_one({"_id": ctx["order_id"]})

def mongo_state(db, ctx):
    doc = db.orders.find_one({"_id": ctx["order_id"]})
    return (1, len(doc["details"])) if doc else (0, 0)


WRITE = {
    "title": "Tambah pesanan beserta detailnya",
    "state": "(orders, order_details) of the new order",
    "setup": setup, "pg": pg, "flux": flux, "pg_undo": pg_undo, "flux_undo": flux_undo,
    "pg_state": pg_state, "flux_state": flux_state,
    "mongo": mongo, "mongo_undo": mongo_undo, "mongo_state": mongo_state,
}
