-- Two requests book the drill for overlapping dates. In the document design both are accepted (make demo-documents).
-- The relational model refuses the second with SQLSTATE 23P01; see 004_constraint_demo.sql.

-- Request A: Ada, Drill, 11-01 to 11-04. Two writes, one per copy, not atomic with each other across documents.
UPDATE item_documents
SET doc = jsonb_set(doc, '{booked}', doc->'booked' || '[{"rentalId": 1, "customerId": 1, "from": "2026-11-01", "to": "2026-11-04"}]')
WHERE item_id = 1;
UPDATE customer_documents
SET doc = jsonb_set(doc, '{rentals}', doc->'rentals' || '[{"rentalId": 1, "itemId": 1, "from": "2026-11-01", "to": "2026-11-04"}]')
WHERE customer_id = 1;

-- Request B: Bruno, Drill, 11-03 to 11-05. Nothing checks the ranges inside the array, so this succeeds too.
UPDATE item_documents
SET doc = jsonb_set(doc, '{booked}', doc->'booked' || '[{"rentalId": 2, "customerId": 2, "from": "2026-11-03", "to": "2026-11-05"}]')
WHERE item_id = 1;
UPDATE customer_documents
SET doc = jsonb_set(doc, '{rentals}', doc->'rentals' || '[{"rentalId": 2, "itemId": 1, "from": "2026-11-03", "to": "2026-11-05"}]')
WHERE customer_id = 2;

-- The drill is double booked. This is the check the application would have to write, and race on.
SELECT a.value->>'rentalId' AS first_rental,
       b.value->>'rentalId' AS second_rental,
       daterange((a.value->>'from')::date, (a.value->>'to')::date) *
       daterange((b.value->>'from')::date, (b.value->>'to')::date) AS overlapping_days
FROM item_documents d,
     jsonb_array_elements(d.doc->'booked') WITH ORDINALITY AS a(value, ord),
     jsonb_array_elements(d.doc->'booked') WITH ORDINALITY AS b(value, ord)
WHERE d.item_id = 1 AND a.ord < b.ord
  AND daterange((a.value->>'from')::date, (a.value->>'to')::date) &&
      daterange((b.value->>'from')::date, (b.value->>'to')::date);

-- A customer's history comes from one document, with no join: this is where documents are easier.
SELECT jsonb_array_length(doc->'rentals') AS adas_rentals FROM customer_documents WHERE customer_id = 1;
