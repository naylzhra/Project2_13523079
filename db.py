import psycopg
from influxdb_client import InfluxDBClient

import config


def pg_connect():
    return psycopg.connect(
        host=config.PG_HOST,
        port=config.PG_PORT,
        dbname=config.PG_DB,
        user=config.PG_USER,
        password=config.PG_PASSWORD,
        options="-c TimeZone=UTC",
    )


def influx_client():
    return InfluxDBClient(
        url=config.INFLUXDB_URL,
        token=config.INFLUXDB_TOKEN,
        org=config.INFLUXDB_ORG,
        timeout=60_000,
    )


if __name__ == "__main__":
    with pg_connect() as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
        tables = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchone()[0]
        print(f"PostgreSQL {version}: {tables} tables in {config.PG_DB}")

    with influx_client() as client:
        bucket = client.buckets_api().find_bucket_by_name(config.INFLUXDB_BUCKET)
        print(f"InfluxDB {client.version()}: bucket {bucket.name if bucket else 'MISSING'}")
