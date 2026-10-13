# VROS performance baseline

Slice 7.5. What was measured, what changed, and what is still slow. Measure again after any
change to a list, report or the follow-up engine, with the same data and the same script.

## How it was measured

- **Data:** a throwaway database generated in SQL, about a few years of a busy agency:
  - 10 people and 20,000 accounts, 4,000 of them clients;
  - 30,000 contacts, 15,000 opportunities, 4,000 deals and 60,000 tasks;
  - 160,000 activities and 200,000 timeline events;
  - 20,000 research runs with 200,000 evidence rows and 200,000 observations;
  - 4,900 monitoring alerts.

  The real database is far smaller; this is the scale it should still be comfortable at.
- **Load:** every endpoint below was called 40 times with 8 requests in flight. The first group signed in as an admin (sees everything) and the second as a salesperson (sees their own accounts). Rate limits were off for the run. Figures are p50 and p95 response times as the client saw them.
- **Machine:** Docker Desktop on a Windows laptop with 7.7 GB of memory, with other stacks running and less than 1 GB free. A Linux server of the size in `DEPLOY_HETZNER.md` will be faster, so read these as relative figures, not promises.
- **Queries:** `pg_stat_statements` was on, and the slow queries were checked with `EXPLAIN ANALYZE`.

## What changed

| Change | Why |
| --- | --- |
| The follow-up engine filters, orders, counts and cuts in SQL: each kind returns its 100 most urgent flags (`limit`, up to 500) and the exact count | It loaded every overdue task, opportunity and deal into Python on every read: 12,000 overdue tasks and 15,000 opportunities each time |
| "No next action" is decided in SQL (`crm.attention_statement`) | It read every open opportunity and filtered in Python |
| Index `tasks.opportunity_id` (migration `0032`) | "Last touched" looks up each opportunity's latest completed task; without the index each lookup scanned every task |
| Several API processes (`VROS_API_WORKERS`, default 2) with Prometheus multi-process metrics | Heavy requests are CPU-bound Python, so with one process every request queued behind them |
| `VROS_WORKER_CONCURRENCY` (default 2) for the worker | How many research runs and monitoring checks run at once, without editing the image |
| `limit` on `/clients`, `/monitoring/watched` and `/config/{kind}/versions`; a test (`tests/unit/test_list_limits.py`) that fails if a list endpoint has neither a capped `limit` nor a recorded reason it is bounded | No list endpoint returns every row of a growing table |

## Results

p50 / p95, admin unless marked:

| Endpoint | Before | After the fixes, 1 process | After, 4 processes |
| --- | --- | --- | --- |
| `/follow-ups` | 52.6 s / 89.5 s | 2.9 s / 3.3 s | 2.5 s / 3.5 s |
| `/follow-ups` (salesperson) | not measured | 0.7 s / 1.1 s | |
| `/accounts?limit=50` | 311 / 849 ms | 467 / 1,062 ms | 133 / 537 ms |
| account page (`/accounts/{id}`) | 319 / 384 ms | 823 / 1,019 ms | 208 / 287 ms |
| `/tasks?limit=100` | 193 / 562 ms | 233 / 1,879 ms | 159 / 275 ms |
| `/leads/top?limit=20` | 136 / 199 ms | 143 / 222 ms | 97 / 158 ms |
| `/deals` | | 1.9 / 2.3 s | 1.0 / 1.4 s |
| `/clients` (4,000 clients) | | 15.5 / 22.5 s | 8.2 / 13.4 s |
| `/reports/sales` | | 20.5 / 28.4 s | |
| `/reports/management` | | 30.7 / 33.6 s | |

Notes on the results:
- **Earlier slow-down:** the "Before" run stopped at `/follow-ups`, so the rows after it were measured only once it was fixed. The "1 process" column was slower than "Before" for some endpoints because they shared the one process with the much heavier requests in that run.
- **Follow-ups on their own:** the list takes **0.6 s** for 20,000 accounts.
- **Unfinished run:** the 4-process run stopped at the reports once the machine ran out of memory.

## Client health and the dashboards (after 7.5)

Client health is still worked out from the records on every read, so it is never out of date; it is now cheap enough to stay that way. Measured on its own with the same data plus client work for the 4,000 clients (12,000 projects, 48,000 milestones, 3,900 risks, 12,000 pieces of feedback):

| | Before | After |
| --- | --- | --- |
| Client list (`/clients`, 4,000 clients) | 2.5 to 2.9 s | 1.0 to 1.2 s |
| Management dashboard | 8.9 to 10.6 s | 1.5 to 1.6 s |
| Sales dashboard (unchanged) | 1.6 to 2.6 s | 1.6 to 2.7 s |

Three warm runs each, one after another, before and after the change on the same data; the spread is this laptop, not the code (the sales dashboard's code did not change). The management dashboard was so slow because client work (projects, milestones, risks) made each health read heavier, and it read every client's health twice.

What changed:
- **Scoped in the database:** each query behind client health used to carry the id of every client (4,000 parameters, then 10,000 project ids). They now filter by the same query that chose the clients.
- **The relationship read in SQL:** latest contact and unanswered messages are folded per account in one query (`crm.activities.account_relationships`) instead of reading every activity the clients ever had. A test checks it gives exactly what the Python fold gives, ties and notes included.
- **Only the columns needed:** projects, milestones and risks are read as columns; only each client's latest feedback is read.
- **Once per dashboard:** the management dashboard worked out every client's health twice (clients at risk, then clients with expansion potential); it now does it once.

Before and after gave identical results for all 4,000 clients: colour, every reason, latest contact, projects, feedback and expansion.

**Not cached, on purpose.** A short cache was considered for the dashboards. Of the sales dashboard's time, about half is reading the open deals with their accounts (0.6 s for the 4,000 open deals here, far more than an agency's pipeline) and about a third is the follow-up counts; both grow with the records rather than the number of people looking. A cache would show a deal someone has just won up to a minute late, which costs more trust than the time it saves at this size.

## Still slow, and why

- **Admin `/follow-ups` across every account:** 2.5 s under load at this size. Salespeople, who see their own accounts, get it in under a second.
- **Dashboards with thousands of open deals:** each reads every open deal with its account. If a pipeline ever grows that large, read only the columns the figures use.

## Sizing

- **API processes:** `VROS_API_WORKERS` defaults to 2. Use about one per CPU core, keeping memory in mind: each process is a full copy of the API, roughly 150 to 200 MB.
- **Worker concurrency:** `VROS_WORKER_CONCURRENCY` defaults to 2. Raise it if research waits in the queue, which shows as `vros_celery_queue_length` and the `VrosQueueBacklog` alert. Each concurrent run can start a headless browser.
- **Keep one worker container:** it runs the daily schedule.
