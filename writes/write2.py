from .common import SECOND, at, epoch, flux_records, influx_delete, influx_write, rfc

PAY_TIME = at("2026-10-01T02:00:00Z")
METHOD = "qris"


def setup(conn):
    """The lowest-numbered unpaid order, so every run pays the same one."""
    order_id, order_time, total = conn.execute(
        "SELECT order_id, order_time, total_amount FROM orders "
        "WHERE status = 'waiting_payment' ORDER BY order_id LIMIT 1").fetchone()
    shipment_id = conn.execute("SELECT max(shipment_id) + 1 FROM shipments").fetchone()[0]
    return {"order_id": order_id, "order_time": order_time, "total": total, "shipment_id": shipment_id}

def pg(conn, ctx):
    with conn.transaction():
        updated = conn.execute(
            "UPDATE orders SET status = 'pickup', payment_time = %s, payment_method = %s "
            "WHERE order_id = %s AND status = 'waiting_payment'",
            (PAY_TIME, METHOD, ctx["order_id"])).rowcount
        if updated != 1:
            raise RuntimeError(f"order {ctx['order_id']} is not waiting for payment")
        conn.execute(
            "INSERT INTO shipments (shipment_id, order_id, shipment_type, shipment_status, created_at) "
            "VALUES (%s, %s, 'pickup', 'pending', %s)",
            (ctx["shipment_id"], ctx["order_id"], PAY_TIME))


def flux(client, ctx):
    found = flux_records(client, f"""range(start: 0)
  |> filter(fn: (r) => r._measurement == "order" and r._field == "order_id"
                       and r._value == {ctx["order_id"]})
  |> keep(columns: ["_time"])""")
    if len(found) != 1:
        raise RuntimeError(f"order {ctx['order_id']} not found in InfluxDB")
    order_t, pay_t = epoch(found[0]["_time"]), epoch(PAY_TIME)
    influx_write(client, [
        f'payment,payment_method={METHOD} order_id={ctx["order_id"]}i,amount={ctx["total"]}i {pay_t}',
        f'order status="pickup" {order_t}',
        f'shipment,shipment_type=pickup shipment_id={ctx["shipment_id"]}i,'
        f'order_id={ctx["order_id"]}i,shipment_status="pending" {pay_t}',
    ])

def pg_undo(conn, ctx):
    with conn.transaction():
        conn.execute("DELETE FROM shipments WHERE shipment_id = %s", (ctx["shipment_id"],))
        conn.execute(
            "UPDATE orders SET status = 'waiting_payment', payment_time = NULL, payment_method = NULL "
            "WHERE order_id = %s", (ctx["order_id"],))

def flux_undo(client, ctx):
    influx_write(client, [f'order status="waiting_payment" {epoch(ctx["order_time"])}'])
    influx_delete(client, "payment", PAY_TIME, PAY_TIME + SECOND)
    influx_delete(client, "shipment", PAY_TIME, PAY_TIME + SECOND)

def pg_state(conn, ctx):
    return conn.execute(
        "SELECT status, payment_method, "
        "       (SELECT count(*) FROM shipments s WHERE s.order_id = o.order_id) "
        "FROM orders o WHERE order_id = %s", (ctx["order_id"],)).fetchone()

def flux_state(client, ctx):
    t = ctx["order_time"]
    status = flux_records(client, f"""range(start: {rfc(t)}, stop: {rfc(t + SECOND)})
  |> filter(fn: (r) => r._measurement == "order" and r._field == "status")""")
    payment = flux_records(client, f"""range(start: 0)
  |> filter(fn: (r) => r._measurement == "payment" and r._field == "order_id"
                       and r._value == {ctx["order_id"]})""")
    shipments = flux_records(client, f"""range(start: 0)
  |> filter(fn: (r) => r._measurement == "shipment" and r._field == "order_id"
                       and r._value == {ctx["order_id"]})""")
    return (status[0]["_value"] if status else None,
            payment[0]["payment_method"] if payment else None,
            len(shipments))


WRITE = {
    "title": "Catat pembayaran pesanan",
    "state": "(status, payment_method, shipments) of the order",
    "setup": setup, "pg": pg, "flux": flux, "pg_undo": pg_undo, "flux_undo": flux_undo,
    "pg_state": pg_state, "flux_state": flux_state,
}
