-- V1.1.2__create_raw_customer.sql
CREATE SCHEMA IF NOT EXISTS {{ database_name }}.{{ sf_schema }};

CREATE OR REPLACE TABLE {{ database_name }}.{{ sf_schema }}.CUSTOMER_RAW_BRONZE
(
    SALE_ID             VARCHAR,
    PRODUCT_ID          VARCHAR,
    SALE_DATE           DATE,
    QUANTITY            INT,
    UNIT_PRICE          FLOAT,
    STORE_ID            VARCHAR,
    _INSERTED_TIMESTAMP TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);
