-- Drops the lab's tables so `make db` can rebuild them from scratch. Not part of the run order.
SET client_min_messages = warning;
DROP TABLE IF EXISTS rentals, items, customers CASCADE;
DROP TABLE IF EXISTS item_documents, customer_documents CASCADE;
