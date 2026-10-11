from config import INFLUXDB_BUCKET as BUCKET, START, STOP

QUERY = {
    "title": "Jumlah total pembayaran per hari",
    "sql": """
        SELECT date_trunc('day', payment_time, 'UTC') AS day, sum(total_amount)::bigint AS total_paid
        FROM orders
        WHERE payment_time >= %(start)s AND payment_time < %(stop)s
        GROUP BY day
        ORDER BY day
    """,
    "flux": f"""
        from(bucket: "{BUCKET}")
          |> range(start: {START}, stop: {STOP})
          |> filter(fn: (r) => r._measurement == "payment" and r._field == "amount")
          |> group()
          |> aggregateWindow(every: 1d, fn: sum, timeSrc: "_start", createEmpty: false)
    """,
    "columns": ["day", "total_paid"],
}
