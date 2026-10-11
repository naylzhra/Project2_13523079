from config import INFLUXDB_BUCKET as BUCKET, START, START_AT, STOP, STOP_AT

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
    "mongo": {
        "collection": "orders",
        "pipeline": [
            {"$match": {"order_time": {"$gte": START_AT, "$lt": STOP_AT}}},
            {"$unwind": "$details"},
            {"$group": {"_id": {"$dateTrunc": {"date": "$order_time", "unit": "day", "timezone": "UTC"}}, "total_weight": {"$sum": "$details.weight_kg"}}},
            {"$project": {"_id": 0, "day": "$_id", "total_weight": 1}},
            {"$sort": {"day": 1}},
        ],
    },
    "columns": ["day", "total_weight"],
    "tolerance": 1e-6,
}
