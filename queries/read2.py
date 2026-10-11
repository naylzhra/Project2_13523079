from config import INFLUXDB_BUCKET as BUCKET, START, START_AT, STOP, STOP_AT

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
    "mongo": {
        "collection": "orders",
        "pipeline": [
            {"$match": {"payment.time": {"$gte": START_AT, "$lt": STOP_AT}}},
            {"$group": {"_id": {"$dateTrunc": {"date": "$payment.time", "unit": "day", "timezone": "UTC"}}, "total_paid": {"$sum": "$total_amount"}}},
            {"$project": {"_id": 0, "day": "$_id", "total_paid": 1}},
            {"$sort": {"day": 1}},
        ],
    },
    "columns": ["day", "total_paid"],
}
