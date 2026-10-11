from config import INFLUXDB_BUCKET as BUCKET, START, STOP

QUERY = {
    "title": "Jumlah pesanan per status",
    "sql": """
        SELECT status, count(*) AS total_order
        FROM orders
        WHERE order_time >= %(start)s AND order_time < %(stop)s
        GROUP BY status
        ORDER BY status
    """,
    "flux": f"""
        from(bucket: "{BUCKET}")
          |> range(start: {START}, stop: {STOP})
          |> filter(fn: (r) => r._measurement == "order" and r._field == "status")
          |> duplicate(column: "_value", as: "status")
          |> group(columns: ["status"])
          |> count()
    """,
    "flux_columns": ["status", "_value"],
    "columns": ["status", "total_order"],
}
