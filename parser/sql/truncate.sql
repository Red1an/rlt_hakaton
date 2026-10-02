-- parser/sql/truncate.sql
TRUNCATE TABLE
    lot_recommendations,
    bids,
    lots,
    announcements,
    suppliers,
    okpd
RESTART IDENTITY CASCADE;