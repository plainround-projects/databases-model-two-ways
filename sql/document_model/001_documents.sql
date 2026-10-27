-- Lesson step 3, made runnable: the document design, stored as JSONB so no second database is needed.
-- Each row is one document, the way a document store keeps it. The point of the file is what is missing from it:
-- no key, foreign key, check or exclusion constraint can see inside the `booked` and `rentals` arrays.

CREATE TABLE item_documents (
    item_id integer PRIMARY KEY,
    doc     jsonb   NOT NULL
);

CREATE TABLE customer_documents (
    customer_id integer PRIMARY KEY,
    doc         jsonb   NOT NULL
);

COMMENT ON TABLE item_documents IS 'Items collection: availability is easy because the booked ranges live here.';
COMMENT ON TABLE customer_documents IS 'Customers collection: history is easy because the rentals live here.';

-- The two copies of each rental the design needs: one in the item, one in the customer.
INSERT INTO item_documents VALUES
    (1, '{"name": "Drill", "dailyRate": 10, "booked": []}'),
    (2, '{"name": "Ladder", "dailyRate": 8, "booked": []}');

INSERT INTO customer_documents VALUES
    (1, '{"name": "Ada", "rentals": []}'),
    (2, '{"name": "Bruno", "rentals": []}');
