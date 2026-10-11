from config import INFLUXDB_BUCKET as BUCKET, START, STOP

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
    "columns": ["machine_id", "hour", "avg_temperature_c", "avg_power_w"],
    "tolerance": 1e-6,
}
