from config import INFLUXDB_BUCKET as BUCKET, START, STOP

QUERY = {
    "title": "Jumlah total berat cucian per hari",
    "sql": """
        SELECT date_trunc('day', o.order_time, 'UTC') AS day, sum(od.weight_kg)::float8 AS total_weight
        FROM orders o
        JOIN order_details od ON o.order_id = od.order_id
        WHERE o.order_time >= %(start)s AND o.order_time < %(stop)s
        GROUP BY day
        ORDER BY day
    """,
    "flux": f"""
        from(bucket: "{BUCKET}")
          |> range(start: {START}, stop: {STOP})
          |> filter(fn: (r) => r._measurement == "order_detail" and r._field == "weight_kg")
          |> group()
          |> aggregateWindow(every: 1d, fn: sum, timeSrc: "_start", createEmpty: false)
    """,
    "columns": ["day", "total_weight"],
    "tolerance": 1e-6,
}
