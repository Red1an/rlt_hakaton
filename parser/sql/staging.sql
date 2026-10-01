CREATE TEMP TABLE stg_lots (
    publish_date      text,
    procedure_id      text,
    lot_id            text,
    start_price       text,
    reqnum            text,
    procedure_name    text,
    subject           text,
    is_smp            text,
    customer_inn      text,
    customer_kpp      text,
    is_eshop_or_aisgz text
);

CREATE TEMP TABLE stg_bids (
    lot_id       text,
    supplier_inn text,
    supplier_kpp text,
    is_winner    text
);

CREATE TEMP TABLE stg_products (
    lot_id       text,
    product_name text,
    okpd2_code   text
);

CREATE FUNCTION pg_temp.clean_text(t text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT NULLIF(btrim(regexp_replace(t, '\s+', ' ', 'g')), '')
$$;
