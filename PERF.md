# LeaveDesk — Indexes and Query Plans (Capstone 3, Part B)

**Proves:** SPEC DB-31 ("each indexed query switches from a sequential scan") and the OFFSET vs
keyset comparison. **Indexes:** revision `0003_query_indexes`, explained in SCHEMA.md 5.2.

## 1. How to reproduce

```bash
docker compose up -d db
python scripts/perf.py          # writes the full plans to perf_results.txt
```

`scripts/perf.py` only touches the **test** database (`TEST_MIGRATION_DATABASE_URL`, its name must end in
`_test`). It migrates it to 0002 (no query indexes), empties it and seeds data with `generate_series`,
runs `ANALYZE`, captures `EXPLAIN (ANALYZE, BUFFERS)`, migrates to head (0003 adds the indexes),
`ANALYZE`s again and captures the plans again. The next test run empties the database again.

**Data:** 100,000 leave requests (10,000 pending) for 20,000 employees (200 managers with 99 reports
each). Five requests per person, 14 days apart, so the EXCLUDE rule is respected.

**The numbers below come from one run on a development machine** (PostgreSQL 16, warm cache). Absolute
timings differ per machine; the plan shapes and buffer counts are what matter. Re-run the script on the
review machine to get its own numbers.

**How "before" is measured:** the "no index" runs happen inside a transaction that is always rolled back:

```sql
BEGIN;
DROP INDEX ix_leave_requests_employee_id;                                  -- the Part A foreign key index
ALTER TABLE leave_requests DROP CONSTRAINT leave_requests_no_overlap;      -- its GiST index also holds employee_id
EXPLAIN (ANALYZE, BUFFERS) ...;
ROLLBACK;                                                                  -- nothing was really dropped
```

PostgreSQL DDL is transactional, so this shows the query with no supporting index without ever weakening
the real schema.

## 2. Results

**Buffers** = 8 KB pages the query touched (`hit` = from memory). Fewer buffers = less work, on any machine.

| Query | Before (no index) | After (revision 0003) |
|---|---|---|
| **Q1** Manager's pending queue | **Seq Scan** on leave_requests, 90,000 rows removed by filter · 2,242 buffers · 11.9 ms | **Index Scan** using `ix_leave_requests_pending` (partial) · 403 buffers · 0.53 ms |
| **Q2** An employee's history | **Seq Scan**, 99,995 rows removed, then Sort · 2,141 buffers · 7.8 ms | **Index Scan** using `ix_leave_requests_history`, **no Sort** · 9 buffers · 0.04 ms |
| **Q3** Name search `ILIKE '%aswam%'` | **Seq Scan** on employees, 19,980 rows removed · 290 buffers · 9.2 ms | **Bitmap Index Scan** on `ix_employees_name_trgm` · 29 buffers · 0.13 ms |
| **P1** OFFSET 50000 LIMIT 20 | Seq Scan + **external merge sort, 3.3 MB spilled to disk** · 96.9 ms | Index Scan reading **50,020 rows to return 20** · 26,898 buffers · 22.7 ms |
| **P2** Keyset, same page | Parallel Seq Scan + top-N sort · 2,154 buffers · 19.2 ms | Index Scan reading **20 rows** · 14 buffers · **0.03 ms** |

## 3. The queries, and why each index has its column order

### Q1 Manager's pending queue

```sql
SELECT r.public_id, e.name, r.start_date, r.end_date
FROM leave_requests r JOIN employees e ON e.id = r.employee_id
WHERE e.manager_id = :manager AND r.status = 'pending'
ORDER BY r.start_date, r.id LIMIT 20;
```

**Index:** `ix_leave_requests_pending (employee_id, start_date, id) WHERE status = 'pending'`

- **Partial:** it stores only the 10,000 pending rows. **416 KB**, against 3,984 KB for the full history
  index. Less to read, less to keep in memory, and cheaper for every write that doesn't touch a pending row.
- **Column order:** `employee_id` first, because the plan looks each of the manager's 99 reports up by
  equality (Nested Loop); then `start_date, id`, the sort order.
- **Reading the "after" plan aloud:** "Bitmap Index Scan on `ix_employees_manager_id` finds the manager's 99
  reports; for each one (`loops=99`) an Index Scan on the partial index fetches only their pending
  requests, with no 'Rows Removed by Filter' line; a top-N heapsort keeps the 20 oldest."
- **Honest finding (Part A indexes only):** with the foreign key index on `employee_id` that Part A
  requires, the planner already avoided the sequential scan (0.59 ms, 412 buffers) but had to filter out
  non-pending rows on every loop ("Rows Removed by Filter: 4"). The partial index removes that filter and
  is a quarter of the size. Its main win at this data shape is size and write cost; with more history per
  employee the filtering would grow and the gap would widen.

### Q2 An employee's history

```sql
SELECT public_id, start_date, end_date, status FROM leave_requests
WHERE employee_id = :employee ORDER BY start_date DESC, id DESC LIMIT 20;
```

**Index:** `ix_leave_requests_history (employee_id, start_date DESC, id DESC)`

- **Column order:** the equality column (`employee_id`) first, then the sort column, then `id` as the
  tie-breaker that keyset pagination needs. Rows come out of the index already in order, so the plan has
  **no Sort node**. Putting `start_date` first would scan every employee's rows in the date range.
- **No `tenant_id`:** `employee_id` is a globally unique bigint, so it already implies the tenant; a
  leading `tenant_id` would only make the index wider (SCHEMA.md 5.2).
- **It also covers the `employee_id` foreign key**, so revision 0003 drops the old single-column
  `ix_leave_requests_employee_id`. The new index is created first, so the foreign key is never unindexed.

### Q3 Employee name search

```sql
SELECT public_id, name FROM employees WHERE tenant_id = :tenant AND name ILIKE '%aswam%';
```

**Index:** `ix_employees_name_trgm USING gin (name gin_trgm_ops)` (extension `pg_trgm`)

- A B-tree can only use a fixed beginning (`'Ram%'`). A leading `%` means "anywhere in the name", so a
  B-tree is useless and PostgreSQL reads every row. pg_trgm splits names into three-letter pieces
  ("asw", "swa", "wam") and the GIN index finds the rows containing all of them.
- The search matches 20 of 20,000 people (selective), so the planner chooses the index. For a search
  matching most rows, a sequential scan would still win, and the planner would pick it.

### P1/P2 OFFSET vs keyset pagination

```sql
-- OFFSET: page 2,501
SELECT public_id, start_date FROM leave_requests ORDER BY start_date, id OFFSET 50000 LIMIT 20;
-- Keyset: the same page, using the last (start_date, id) of page 2,500 as the cursor
SELECT public_id, start_date FROM leave_requests
WHERE (start_date, id) > (:last_start_date, :last_id) ORDER BY start_date, id LIMIT 20;
```

**Index:** `ix_leave_requests_start_date_id (start_date, id)`, the list's sort order.

- **OFFSET** must produce and throw away 50,000 rows before returning 20. Even with the index it reads
  50,020 rows (26,898 buffers), and it gets slower with every page. Without an index it sorted all
  100,000 rows and **spilled 3.3 MB to disk** because the sort did not fit in `work_mem`.
- **Keyset** jumps straight to the cursor position in the index and reads exactly 20 rows (14 buffers),
  page 1 or page 2,501 alike. It also never repeats or skips a row when new rows are inserted between
  page loads (SPEC DB-33), because the cursor is a position in the data, not a row count.
- `id` is in the cursor because `start_date` alone is not unique: thousands of requests share a date.

## 4. Things to know

- **Every index has a write cost:** each insert or update maintains it. That is why the partial index is
  partial, and why the redundant single-column index is dropped.
- **On a live table** these indexes would be built with `CREATE INDEX CONCURRENTLY` in a
  non-transactional revision, so writes are not blocked while they build.
- **In the API:** `GET /leave-requests` filters, counts, sorts and pages in SQL
  (`PostgresLeaveRepository.page_requests`): `?cursor=` runs the keyset query above
  (`WHERE (start_date, id) > (:d, :i) ORDER BY start_date, id LIMIT n+1`, one extra row tells whether a
  next page exists), and `next_cursor` in the response is the opaque cursor for the next page. Plain
  `offset` still works as in v1.0 (SPEC DB-32 to DB-34, `tests/api/test_pagination_api.py`).
