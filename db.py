import psycopg
from influxdb_client import InfluxDBClient
from pymongo import MongoClient

import config


def pg_connect():
    return psycopg.connect(
        host=config.PG_HOST,
        port=config.PG_PORT,
        dbname=config.PG_DB,
        user=config.PG_USER,
        password=config.PG_PASSWORD,
        options="-c TimeZone=UTC",
        prepare_threshold=None,
    )


def influx_client():
    return InfluxDBClient(
        url=config.INFLUXDB_URL,
        token=config.INFLUXDB_TOKEN,
        org=config.INFLUXDB_ORG,
        timeout=60_000,
    )

def mongo_client():
    return MongoClient(
        host=config.MONGO_HOST,
        port=config.MONGO_PORT,
        username=config.MONGO_USER,
        password=config.MONGO_PASSWORD,
        tz_aware=True,
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

    with mongo_client() as client:
        version = client.server_info()["version"]
        names = client[config.MONGO_DB].list_collection_names()
        print(f"MongoDB {version}: {len(names)} collections in {config.MONGO_DB}")
