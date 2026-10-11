from config import INFLUXDB_BUCKET as BUCKET, START, START_AT, STOP, STOP_AT

QUERY = {
    "title": "Jumlah total pemasukan per jenis layanan",
    "sql": """
        SELECT s.service_name, sum(od.subtotal)::bigint AS revenue
        FROM orders o
        JOIN order_details od ON o.order_id = od.order_id
        JOIN services s ON od.service_id = s.service_id
        WHERE o.order_time >= %(start)s AND o.order_time < %(stop)s
          AND o.payment_time IS NOT NULL
        GROUP BY s.service_name
        ORDER BY s.service_name
    """,
    "flux": f"""
        details = from(bucket: "{BUCKET}")
          |> range(start: {START}, stop: {STOP})
          |> filter(fn: (r) => r._measurement == "order_detail"
                               and (r._field == "order_id" or r._field == "subtotal"))
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> group()
          |> keep(columns: ["order_id", "service_name", "subtotal"])

        paid = from(bucket: "{BUCKET}")
          |> range(start: {START})
          |> filter(fn: (r) => r._measurement == "payment" and r._field == "order_id")
          |> group()
          |> map(fn: (r) => ({{order_id: r._value}}))

        join(tables: {{d: details, p: paid}}, on: ["order_id"])
          |> group(columns: ["service_name"])
          |> sum(column: "subtotal")
    """,
    "flux_columns": ["service_name", "subtotal"],
    "mongo": {
        "collection": "orders",
        "pipeline": [
            {"$match": {"order_time": {"$gte": START_AT, "$lt": STOP_AT}, "payment": {"$ne": None}}},
            {"$unwind": "$details"},
            {"$group": {"_id": "$details.service_name", "revenue": {"$sum": "$details.subtotal"}}},
            {"$project": {"_id": 0, "service_name": "$_id", "revenue": 1}},
            {"$sort": {"service_name": 1}},
        ],
    },
    "columns": ["service_name", "revenue"],
}
