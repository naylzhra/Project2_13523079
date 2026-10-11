import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

PG_HOST = os.environ["PG_HOST"]
PG_PORT = int(os.environ["PG_PORT"])
PG_DB = os.environ["PG_DB"]
PG_USER = os.environ["PG_USER"]
PG_PASSWORD = os.environ["PG_PASSWORD"]

INFLUXDB_URL = os.environ["INFLUXDB_URL"]
INFLUXDB_TOKEN = os.environ["INFLUXDB_TOKEN"]
INFLUXDB_ORG = os.environ["INFLUXDB_ORG"]
INFLUXDB_BUCKET = os.environ["INFLUXDB_BUCKET"]

MONGO_HOST = os.environ["MONGO_HOST"]
MONGO_PORT = int(os.environ["MONGO_PORT"])
MONGO_DB = os.environ["MONGO_DB"]
MONGO_USER = os.environ["MONGO_USER"]
MONGO_PASSWORD = os.environ["MONGO_PASSWORD"]

START = "2026-09-01T00:00:00Z"
STOP = "2026-10-01T00:00:00Z"
START_AT = datetime.fromisoformat(START)
STOP_AT = datetime.fromisoformat(STOP)
