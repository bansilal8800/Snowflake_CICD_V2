CREATE SCHEMA IF NOT EXISTS {{ database_name }}.{{ sf_schema }};
CREATE TABLE {{ database_name }}.{{ sf_schema }}.EMPLOYEE (
    employee_id      INT,
    first_name       VARCHAR(50)  NOT NULL,
    last_name        VARCHAR(50)  NOT NULL,
    email            VARCHAR(100) NOT NULL UNIQUE,
    phone_number     VARCHAR(30),
    hire_date        DATE         NOT NULL,
    job_title        VARCHAR(100),
    salary           DECIMAL(12,2),
    manager_id       INT,
    department_id    INT,
    location_id      INT
);


CREATE TABLE {{ database_name }}.{{ sf_schema }}.DEPARTMENT (
    department_id   INT          ,
    department_name VARCHAR(100) NOT NULL,
    manager_id      INT
);


CREATE TABLE {{ database_name }}.{{ sf_schema }}.LOCATION (
    location_id     INT          ,
    street_address  VARCHAR(200),
    postal_code     VARCHAR(20),
    city            VARCHAR(100) NOT NULL,
    state_province  VARCHAR(100),
    country         VARCHAR(100) NOT NULL
);
