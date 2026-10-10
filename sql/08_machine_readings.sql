CREATE TABLE machine_readings (
    machine_id BIGINT NOT NULL REFERENCES machines (machine_id),
    recorded_at TIMESTAMPTZ NOT NULL,
    temperature_c DOUBLE PRECISION NOT NULL,
    power_w DOUBLE PRECISION NOT NULL CHECK (power_w >= 0),
    water_lpm DOUBLE PRECISION CHECK (water_lpm >= 0),
    rpm INTEGER NOT NULL CHECK (rpm >= 0),
    PRIMARY KEY (machine_id, recorded_at)
);
