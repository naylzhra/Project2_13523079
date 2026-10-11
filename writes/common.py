from datetime import datetime, timedelta
from influxdb_client import WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from config import INFLUXDB_BUCKET as BUCKET, INFLUXDB_ORG as ORG

SECOND = timedelta(seconds=1)


def at(iso):
    return datetime.fromisoformat(iso)

def epoch(dt):
    return int(dt.timestamp())

def rfc(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def influx_write(client, lines):
    client.write_api(write_options=SYNCHRONOUS).write(
        BUCKET, ORG, record=lines, write_precision=WritePrecision.S)

def influx_delete(client, measurement, start, stop):
    last = (stop - SECOND).strftime("%Y-%m-%dT%H:%M:%S.999999999Z")
    client.delete_api().delete(rfc(start), last, f'_measurement="{measurement}"', bucket=BUCKET, org=ORG)

def influx_rebuild(client):
    from load import influx_load
    buckets = client.buckets_api()
    old = buckets.find_bucket_by_name(BUCKET)
    buckets.delete_bucket(old)
    buckets.create_bucket(bucket_name=BUCKET, org_id=old.org_id, retention_rules=[])
    return influx_load(client)

def flux_records(client, body):
    flux = f'from(bucket: "{BUCKET}")\n  |> {body}'
    return [rec.values for table in client.query_api().query(flux) for rec in table.records]

def flux_count(client, measurement, field, start, stop, value=None):
    match = f" and r._value == {value}" if value is not None else ""
    rows = flux_records(client, f"""range(start: {rfc(start)}, stop: {rfc(stop)})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}"{match})
  |> group()
  |> count()""")
    return rows[0]["_value"] if rows else 0
