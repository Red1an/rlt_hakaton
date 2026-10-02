INSERT INTO okpd (code, name)
SELECT code, mode() WITHIN GROUP (ORDER BY product_name)
FROM (
    SELECT
        pg_temp.clean_text(okpd2_code)   AS code,
        pg_temp.clean_text(product_name) AS product_name
    FROM stg_products
) p
WHERE code IS NOT NULL
GROUP BY code
ON CONFLICT (code) DO UPDATE SET name = coalesce(okpd.name, EXCLUDED.name);

INSERT INTO announcements (
    lot_id, procedure_name, publish_date, start_price, subject,
    is_smp, customer_inn, customer_kpp, is_eshop_or_aisgz, dataset
)
SELECT DISTINCT ON (lot_id)
    lot_id,
    coalesce(procedure_name, ''),
    publish_date,
    coalesce(start_price, 0),
    coalesce(subject, procedure_name, ''),
    coalesce(is_smp, false),
    coalesce(customer_inn, ''),
    coalesce(customer_kpp, ''),
    platform = 'ЭМ',
    current_setting('app.dataset')
FROM (
    SELECT
        pg_temp.clean_text(lot_id)::int            AS lot_id,
        pg_temp.clean_text(procedure_name)         AS procedure_name,
        pg_temp.clean_text(publish_date)::date     AS publish_date,
        pg_temp.clean_text(start_price)::float     AS start_price,
        pg_temp.clean_text(subject)                AS subject,
        pg_temp.clean_text(is_smp)::boolean        AS is_smp,
        pg_temp.clean_text(customer_inn)           AS customer_inn,
        pg_temp.clean_text(customer_kpp)           AS customer_kpp,
        pg_temp.clean_text(is_eshop_or_aisgz)      AS platform
    FROM stg_lots
) l
WHERE lot_id IS NOT NULL AND publish_date IS NOT NULL
ORDER BY lot_id, publish_date DESC
ON CONFLICT (lot_id) DO NOTHING;

INSERT INTO lots (lot_id, product_name, okpd_code)
SELECT p.lot_id, coalesce(p.product_name, ''), p.okpd_code
FROM (
    SELECT
        pg_temp.clean_text(lot_id)::int   AS lot_id,
        pg_temp.clean_text(product_name)  AS product_name,
        pg_temp.clean_text(okpd2_code)    AS okpd_code
    FROM stg_products
) p
WHERE EXISTS (SELECT 1 FROM announcements a WHERE a.lot_id = p.lot_id)
  AND NOT EXISTS (SELECT 1 FROM lots existing WHERE existing.lot_id = p.lot_id);

INSERT INTO suppliers (inn, kpp, sum_price, is_smp, okpds)
SELECT inn, mode() WITHIN GROUP (ORDER BY kpp), 0, false, '{}'
FROM (
    SELECT
        pg_temp.clean_text(supplier_inn) AS inn,
        pg_temp.clean_text(supplier_kpp) AS kpp
    FROM stg_bids
) b
WHERE inn ~ '^\d{10}(\d{2})?$'
GROUP BY inn
ON CONFLICT (inn) DO UPDATE SET kpp = EXCLUDED.kpp;

INSERT INTO bids (lot_id, supplier_inn, is_winner)
SELECT b.lot_id, b.inn, bool_or(b.is_winner)
FROM (
    SELECT
        pg_temp.clean_text(lot_id)::int                       AS lot_id,
        pg_temp.clean_text(supplier_inn)                      AS inn,
        coalesce(pg_temp.clean_text(is_winner)::boolean, false) AS is_winner
    FROM stg_bids
) b
WHERE EXISTS (SELECT 1 FROM announcements a WHERE a.lot_id = b.lot_id)
  AND EXISTS (SELECT 1 FROM suppliers s WHERE s.inn = b.inn)
GROUP BY b.lot_id, b.inn
ON CONFLICT (lot_id, supplier_inn) DO NOTHING;

ANALYZE okpd, announcements, lots, suppliers, bids;
