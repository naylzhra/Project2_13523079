CREATE TABLE order_details (
    order_id BIGINT NOT NULL REFERENCES orders (order_id),
    detail_no INTEGER NOT NULL CHECK (detail_no > 0),
    service_id BIGINT NOT NULL REFERENCES services (service_id),
    weight_kg NUMERIC(10, 1) NOT NULL CHECK (weight_kg > 0),
    subtotal BIGINT NOT NULL CHECK (subtotal > 0),
    PRIMARY KEY (order_id, detail_no)
);
