from config import INFLUXDB_BUCKET as BUCKET, START, START_AT, STOP, STOP_AT

QUERY = {
    "title": "Jumlah pesanan per hari",
    "sql": """
        SELECT date_trunc('day', order_time, 'UTC') AS day, count(*) AS orders
        FROM orders
        WHERE order_time >= %(start)s AND order_time < %(stop)s
        GROUP BY day
        ORDER BY day
    """,
    "flux": f"""
        from(bucket: "{BUCKET}")
          |> range(start: {START}, stop: {STOP})
          |> filter(fn: (r) => r._measurement == "order" and r._field == "order_id")
          |> aggregateWindow(every: 1d, fn: count, timeSrc: "_start", createEmpty: false)
    """,
    "mongo": {
        "collection": "orders",
        "pipeline": [
            {"$match": {"order_time": {"$gte": START_AT, "$lt": STOP_AT}}},
            {"$group": {"_id": {"$dateTrunc": {"date": "$order_time", "unit": "day", "timezone": "UTC"}}, "orders": {"$sum": 1}}},
            {"$project": {"_id": 0, "day": "$_id", "orders": 1}},
            {"$sort": {"day": 1}},
        ],
    },
    "columns": ["day", "orders"],
}
