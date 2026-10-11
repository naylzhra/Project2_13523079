from config import INFLUXDB_BUCKET as BUCKET, START, START_AT, STOP, STOP_AT

QUERY = {
    "title": "Rata-rata suhu dan daya per mesin per jam",
    "sql": """
        SELECT machine_id, date_trunc('hour', recorded_at, 'UTC') AS hour,
               avg(temperature_c) AS avg_temperature_c, avg(power_w) AS avg_power_w
        FROM machine_readings
        WHERE recorded_at >= %(start)s AND recorded_at < %(stop)s
        GROUP BY machine_id, hour
        ORDER BY machine_id, hour
    """,
    "flux": f"""
        from(bucket: "{BUCKET}")
          |> range(start: {START}, stop: {STOP})
          |> filter(fn: (r) => r._measurement == "machine_reading"
                               and (r._field == "temperature_c" or r._field == "power_w"))
          |> aggregateWindow(every: 1h, fn: mean, timeSrc: "_start", createEmpty: false)
          |> group(columns: ["machine_id"])
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> map(fn: (r) => ({{r with machine_id: int(v: r.machine_id)}}))
    """,
    "flux_columns": ["machine_id", "_time", "temperature_c", "power_w"],
    "mongo": {
        "collection": "machine_readings",
        "pipeline": [
            {"$match": {"recorded_at": {"$gte": START_AT, "$lt": STOP_AT}}},
            {"$group": {
                "_id": {"machine_id": "$machine.machine_id",
                        "hour": {"$dateTrunc": {"date": "$recorded_at", "unit": "hour", "timezone": "UTC"}}},
                "avg_temperature_c": {"$avg": "$temperature_c"},
                "avg_power_w": {"$avg": "$power_w"}}},
            {"$project": {"_id": 0, "machine_id": "$_id.machine_id", "hour": "$_id.hour",
                          "avg_temperature_c": 1, "avg_power_w": 1}},
            {"$sort": {"machine_id": 1, "hour": 1}},
        ],
    },
    "columns": ["machine_id", "hour", "avg_temperature_c", "avg_power_w"],
    "tolerance": 1e-6,
}
