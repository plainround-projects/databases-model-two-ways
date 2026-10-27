-- Lesson step 4: let the database refuse a double booking.
-- Adding the constraint validates the existing rows, so it fails if any item already has overlapping rentals;
-- on a table that has had none, it is a single statement. Building the GiST index locks writes to `rentals`
-- while it runs; on a big live table you would plan that window.

-- An exclusion constraint mixes `=` on an integer and `&&` on a range in one GiST index, and GiST has no
-- operator class for plain integers until this extension adds one. Without it the ALTER fails with
-- "data type integer has no default operator class for access method gist".
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- No two rows may have the same item and overlapping ranges. A violation is SQLSTATE 23P01.
-- The constraint's GiST index also answers "is item X free on these dates" with an index scan.
ALTER TABLE rentals
    ADD CONSTRAINT rentals_item_id_during_excl EXCLUDE USING gist (item_id WITH =, during WITH &&);

COMMENT ON CONSTRAINT rentals_item_id_during_excl ON rentals IS 'An item is never rented twice for overlapping dates (SQLSTATE 23P01).';
