from config import INFLUXDB_BUCKET as BUCKET, START, START_AT, STOP, STOP_AT

QUERY = {
    "title": "Total energi per jenis layanan",
    "sql": """
        WITH run_readings AS (
            SELECT s.service_name, m.recorded_at, m.power_w,
                   lead(m.recorded_at) OVER run AS next_at,
                   lead(m.power_w) OVER run AS next_power_w
            FROM wash_runs w
            JOIN order_details od ON od.order_id = w.order_id AND od.detail_no = w.detail_no
            JOIN services s ON s.service_id = od.service_id
            JOIN machine_readings m ON m.machine_id = w.machine_id
                                   AND m.recorded_at >= w.start_time
                                   AND m.recorded_at < w.end_time
            WHERE w.start_time >= %(start)s AND w.start_time < %(stop)s
            WINDOW run AS (PARTITION BY w.run_id ORDER BY m.recorded_at)
        )
        SELECT service_name,
               sum((power_w + next_power_w) / 2
                   * extract(epoch FROM next_at - recorded_at)::float8) / 3600000 AS energy_kwh
        FROM run_readings
        WHERE next_at IS NOT NULL
        GROUP BY service_name
        ORDER BY service_name
    """,
    "flux": f"""
        runs = from(bucket: "{BUCKET}")
          |> range(start: {START}, stop: {STOP})
          |> filter(fn: (r) => r._measurement == "wash_run"
                               and (r._field == "run_id" or r._field == "end_time"))
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> keep(columns: ["_start", "_stop", "_time", "machine_id", "service_name", "run_id", "end_time"])
          |> set(key: "kind", value: "0")

        readings = from(bucket: "{BUCKET}")
          |> range(start: {START}, stop: {STOP})
          |> filter(fn: (r) => r._measurement == "machine_reading" and r._field == "power_w")
          |> keep(columns: ["_start", "_stop", "_time", "machine_id", "_value"])
          |> set(key: "kind", value: "1")

        union(tables: [runs, readings])
          |> group(columns: ["machine_id"])
          |> sort(columns: ["_time", "kind"])
          |> fill(column: "run_id", usePrevious: true)
          |> fill(column: "end_time", usePrevious: true)
          |> fill(column: "service_name", usePrevious: true)
          |> filter(fn: (r) => r.kind == "1" and exists r.run_id
                               and int(v: r._time) < r.end_time * 1000000000)
          |> group(columns: ["_start", "_stop", "run_id", "service_name"])
          |> integral(unit: 1h)
          |> group(columns: ["service_name"])
          |> sum()
          |> map(fn: (r) => ({{service_name: r.service_name, energy_kwh: r._value / 1000.0}}))
    """,
    "flux_columns": ["service_name", "energy_kwh"],
    "mongo": {
        "collection": "wash_runs",
        "pipeline": [
            {"$match": {"start_time": {"$gte": START_AT, "$lt": STOP_AT}}},
            {"$lookup": {
                "from": "machine_readings",
                "localField": "machine_id",
                "foreignField": "machine.machine_id",
                "let": {"start": "$start_time", "end": "$end_time"},
                "pipeline": [
                    {"$match": {"$expr": {"$and": [{"$gte": ["$recorded_at", "$$start"]},
                                                   {"$lt": ["$recorded_at", "$$end"]}]}}},
                    {"$project": {"_id": 0, "recorded_at": 1, "power_w": 1}},
                ],
                "as": "readings"}},
            {"$unwind": "$readings"},
            {"$setWindowFields": {
                "partitionBy": "$_id",
                "sortBy": {"readings.recorded_at": 1},
                "output": {"next_at": {"$shift": {"output": "$readings.recorded_at", "by": 1}},
                           "next_power_w": {"$shift": {"output": "$readings.power_w", "by": 1}}}}},
            {"$match": {"next_at": {"$ne": None}}},
            {"$group": {"_id": "$service_name", "energy_ws": {"$sum": {"$multiply": [
                {"$divide": [{"$add": ["$readings.power_w", "$next_power_w"]}, 2]},
                {"$divide": [{"$subtract": ["$next_at", "$readings.recorded_at"]}, 1000]}]}}}},
            {"$project": {"_id": 0, "service_name": "$_id",
                          "energy_kwh": {"$divide": ["$energy_ws", 3600000]}}},
            {"$sort": {"service_name": 1}},
        ],
    },
    "columns": ["service_name", "energy_kwh"],
    "tolerance": 1e-6,
}
