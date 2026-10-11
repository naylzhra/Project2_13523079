from config import INFLUXDB_BUCKET as BUCKET, START, START_AT, STOP, STOP_AT

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
    "mongo": {
        "collection": "orders",
        "pipeline": [
            {"$match": {"order_time": {"$gte": START_AT, "$lt": STOP_AT}}},
            {"$group": {"_id": "$status", "total_order": {"$sum": 1}}},
            {"$project": {"_id": 0, "status": "$_id", "total_order": 1}},
            {"$sort": {"status": 1}},
        ],
    },
    "columns": ["status", "total_order"],
}
