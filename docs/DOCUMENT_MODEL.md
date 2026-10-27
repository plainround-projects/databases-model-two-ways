# The same shop as documents (lesson step 3)

The design on paper, and a runnable version of it in `sql/document_model/` that stores the documents as JSONB in the same PostgreSQL, so the one thing the lesson needs to show (what a document model cannot enforce) can be run without a second database.

## The two collections

```json
// customers collection: history is easy, availability is awkward
{ "_id": 1, "name": "Ada",
  "rentals": [ { "rentalId": 1, "itemId": 1, "from": "2026-11-01", "to": "2026-11-04" },
               { "rentalId": 3, "itemId": 2, "from": "2026-11-02", "to": "2026-11-09" } ] }

// items collection: availability is easy because the booked ranges live here, and then history is awkward
{ "_id": 1, "name": "Drill", "dailyRate": 10,
  "booked": [ { "rentalId": 1, "customerId": 1, "from": "2026-11-01", "to": "2026-11-04" } ] }
```

Embed or reference, per access pattern:

| Pattern | Choice | Why |
| --- | --- | --- |
| Customer's history | Embed recent rentals in the customer | Read together with the customer; one document, no join |
| Is the item free | Embed the booked ranges in the item | Read per item over dates; one document |
| Today's returns | Neither embeds well | The date is inside many documents; needs an index on a field inside an array, or a separate collection of rentals |
| Revenue per item and month | Aggregation pipeline over items (or a separate collection) | Reporting across documents |
| Never rented | Items whose `booked` is empty | Easy once the booked ranges live in the item |

## What is easier and what is awkward

- **Easier:** a customer's history. It is one document read; the relational version joins `rentals` to `items`.
- **Awkward:** the availability check across customers, and keeping the two copies of a rental in step. Each rental is written twice (into the item and into the customer), and no database rule makes those two writes atomic across documents without extra machinery (a multi-document transaction, or a saga with repair jobs).
- **Missing:** a rule that spans the booked ranges. A key, foreign key, check or exclusion constraint cannot look inside an array, so the application has to read the ranges, compare them and write, and two requests can both read "free".

## Run it

```bash
make demo-documents     # sql/document_model/001_documents.sql, then 002_double_booking.sql
```

The second script books the drill twice for overlapping dates. Both writes succeed; the query that follows finds the double booking after the fact (`overlapping_days = [2026-11-03,2026-11-04)`). The relational model refuses the second booking with SQLSTATE `23P01` ([sql/004_constraint_demo.sql](../sql/004_constraint_demo.sql)).

## What this is not

It is not a document database. JSONB in PostgreSQL has a `jsonb_path` language and GIN indexes, and PostgreSQL could be made to enforce the rule with a trigger, but a document store such as MongoDB has neither a join nor a cross-document constraint. The stretch goal "build the document version in a document store" is not built here.
