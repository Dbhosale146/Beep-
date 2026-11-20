# Beep — fresher jobs & internships in India

Collects fresher and internship posts in India from official public job-board
APIs, de-duplicates them, tags each one by role and city with an LLM, serves
them over an HTTP search API, and shows them on a React job board that
refreshes itself twice a day.

**Current numbers** (pipeline run of 2026-11-16, API measured 2026-11-17):

| | |
|---|---|
| Raw posts fetched | 6,623 across 4 sources |
| India posts after normalisation | 2,520 |
| Fresher/internship posts after filtering | 1,075 |
| Duplicates removed | 503 (layer 1: 395, layer 2: 58, layer 3: 50) |
| **Published posts** | **565** |
| Posts tagged `Untagged` | 0 |
| Model | `gemini-3.5-flash-lite` |
| **Cost per 1,000 posts** | **$0.158** |
| Full pipeline run / cached re-run | 310s / 21.5s |
| API response, warm | 13–30 ms |
| Tests | 73 (48 pipeline, 25 API) |

Build notes, including everything that broke: [docs/build_log.md](docs/build_log.md).

---

## Layout

Two halves, two folders, nothing shared between them except the HTTP contract.

```
backend/      Python: the refresh pipeline and the API that serves its output
frontend/     React + Vite: the job board
docs/         build log
```

```
backend/
  api/          main.py          the HTTP API
  config/       companies.yaml · taxonomy.yaml · fresher.yaml · settings.yaml
  pipeline/     config · http · run · normalise · fresher · dedup · tag · export
                sources/  greenhouse · lever · ashby · adzuna
  prompts/      tag_v1.txt · tag_v2.txt   (versioned, never inline strings)
  scripts/      verify_companies · sample_for_eval · score_eval · cost_report
  tests/        73 no-network tests
  data/         jobs.json · run_meta.json · tag_cache.json · usage_log.jsonl

frontend/
  src/
    App.jsx         composition root: state in, components out
    components/     Header · SearchBar · FilterBar · JobCard · JobPanel
                    Pagination · SkeletonGrid · EmptyState · ProgressBar
    hooks/          useJobs · useUrlState · useSaved · useCountUp
    lib/            api.js (every fetch) · format.js (pure display helpers)
    styles/         tokens · base · components · animations
  vite.config.js    dev proxy to the API
```

---

## Architecture

```
                 ┌──────────────────────────────────────────┐
  config/*.yaml  │ companies · taxonomy · fresher · settings │
                 └───────────────────┬──────────────────────┘
                                     │ read by every stage
 ┌───────────┐   ┌────────────┐   ┌──┴───────┐   ┌───────┐   ┌─────┐   ┌────────┐
 │  fetch    │──▶│ normalise  │──▶│ fresher  │──▶│ dedup │──▶│ tag │──▶│ export │
 └───────────┘   └────────────┘   └──────────┘   └───────┘   └─────┘   └────────┘
  greenhouse      one schema        keyword       3 layers    Gemini    jobs.json
  lever           India filter      rules         counted     + cache   run_meta.json
  ashby           city aliases      0-1 years                 + usage        │
  adzuna                                                        log          │
                                                                             ▼
                                                            ┌────────────────────┐
                                                            │  backend/api       │
                                                            │  FastAPI, in-memory│
                                                            │  search + facets   │
                                                            └─────────┬──────────┘
                                                                      │ JSON over HTTP
                                                                      ▼
                                                            ┌────────────────────┐
                                                            │  frontend (React)  │
                                                            └────────────────────┘
```

The pipeline runs once a day and writes files. The API reads those files and
answers search queries. The two never run at the same time and share nothing
but the file on disk, which is why a pipeline failure cannot take the site
down — the API keeps serving yesterday's `jobs.json`.

### fetch — `backend/pipeline/sources/`
One file per source, each exposing exactly `fetch() -> list[dict]`. Adding a
source is one new file plus one line in `pipeline/sources/__init__.py`. Every
source goes through the single `pipeline/http.py` helper, so timeout, retry and
backoff behaviour is identical everywhere and lives in one place.

| source | endpoint | auth | notes |
|---|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | none | 18 verified boards |
| Lever | `api.lever.co/v0/postings/{company}?mode=json` | none | returns a JSON **array**; `createdAt` is epoch **ms** |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{name}` | none | filter on `isListed` |
| Adzuna | `api.adzuna.com/v1/api/jobs/in/search/{page}` | app id + key | the volume source; `description` is **truncated** |

A source that fails is logged and skipped. The run continues.

### normalise — `backend/pipeline/normalise.py`
Everything becomes one schema: `id, source, source_id, title, company,
raw_location, city_guess, department, employment_type, description, url,
posted_at, fetched_at`. The India check trusts an explicit country field when
the source gives one (Lever `"IN"`, Ashby `"India"`, Adzuna `area[0]`) and only
falls back to string matching for Greenhouse, which gives nothing.
`city_guess` resolves aliases from `config/taxonomy.yaml` so the LLM confirms
a candidate rather than guessing from scratch.

### fresher filter — `backend/pipeline/fresher.py`
Keyword rules first, so we never pay to tag thousands of senior roles. Title
positives, title negatives, an explicit `employment_type` of `Intern`, then a
years-of-experience scan of the description keeping anything asking for ≤1
year. Every pattern is matched with `\b` word boundaries — without them,
`intern` matches "Senior **Intern**al Auditor". The LLM also returns
`is_fresher`, and posts it rejects are dropped afterwards.

### dedup — `backend/pipeline/dedup.py`
Three layers, each counted separately in `run_meta.json`:

1. **exact** — same `(source, source_id)`, or same URL ignoring query string.
   Catches one Adzuna job returned by several of our search queries.
2. **hash** — normalised company + title + city. Catches the same job on a
   company's own board *and* in the Adzuna index, where ids and URLs differ.
3. **fuzzy** — rapidfuzz within one company. `token_sort_ratio ≥ 90` for
   reordering and typos, plus `token_set_ratio ≥ 95` for "SDE Intern" vs
   "SDE Intern (2027 Batch)", guarded so a bare "Intern" cannot swallow a
   company's whole list.

### tag — `backend/pipeline/tag.py`
Google Gemini via the Interactions API, ~10 posts per call, `temperature: 0`
and `thinking_level: minimal`. The role and city taxonomies go into the JSON
schema as `enum`, so constrained decoding makes an off-taxonomy answer
*impossible* rather than merely unlikely. Every response is still validated
against `config/taxonomy.yaml`; one retry on failure, then the post is marked
`Untagged`. **Nothing is ever guessed.**

Results are cached in `data/tag_cache.json` by a hash of
title + company + location + description + prompt version, so a run only
pays for posts it has not seen. In practice: 571 of 572 posts came from cache
on the second run.

Prompts live in `prompts/` as versioned plain text (`tag_v1.txt`, `tag_v2.txt`).
Bumping `PROMPT_VERSION` invalidates the cache on purpose — answers from two
different prompts must never be mixed.

### export — `backend/pipeline/export.py`
`data/jobs.json` (an explicit field allow-list, so no internal field can leak)
and `data/run_meta.json` (run time, per-source counts, dedup counts, tagging
counts, token totals, role/city facets).

### API — `backend/api/main.py`
FastAPI. One file, ~200 lines including comments.

| endpoint | returns |
|---|---|
| `GET /api/jobs` | one page of results + facet counts + totals |
| `GET /api/jobs/{id}` | one job with its full description |
| `GET /api/meta` | the pipeline's `run_meta.json` |
| `GET /api/health` | status and loaded job count, for a host's health check |
| `GET /docs` | interactive API docs, generated by FastAPI |

`/api/jobs` takes `q`, `role`, `city`, `source`, `posted_within_days`, `sort`
(`recent` / `oldest` / `company` / `title`), `page` and `page_size`.

Three decisions worth explaining:

- **No database.** 565 posts is small enough that filtering a list of dicts
  takes about a millisecond; a warm request is 13–30 ms end to end. A database
  would add a service to run, a schema to migrate and a connection pool, and
  would not make one request faster at this size. If the dataset reached six
  figures, `_load()` is the single function to replace, and the routes would
  not change.
- **The file is reloaded when its mtime changes**, so a pipeline run appears
  without restarting the server, and a broken `run_meta.json` is caught and
  ignored rather than taking the API down.
- **Facets ignore their own dimension.** Selecting Bengaluru leaves the city
  menu showing every city, so the counts answer "how many would I get if I
  picked this?" rather than collapsing to one option. The role menu *does*
  respect the city filter. There is a test for exactly this.

Internal fields are prefixed `_` and stripped before any response, and the list
endpoint sends a 300-character snippet instead of the full 1,200, which is
about a third of the payload for a page of results.

### authentication — `backend/api/auth.py`, `frontend/src/hooks/useAuth.js`
Google Sign-In. The app has **no password field anywhere**, deliberately:
asking for someone's Gmail password in our own form is phishing, Google blocks
it, and it would hand us a credential we have no business holding. Google shows
its own sign-in screen and returns an ID token — a JWT it signed.

The API verifies that token with `google-auth`, which checks:

- the RS256 signature against Google's published keys (fetched and cached, so a
  rotated key is picked up automatically)
- `aud` equals our own client id — without this, a token minted for *any* other
  Google app would be accepted here
- `iss` is accounts.google.com, and `exp` has not passed
- `email_verified` is true, since a Google account can carry an unverified address

None of that is forgeable in the browser, because the browser does not hold
Google's signing key. That is what makes it real authentication rather than
decoration.

| env var | effect |
|---|---|
| `GOOGLE_CLIENT_ID` | the client id tokens must be addressed to (required) |
| `REQUIRE_AUTH=true` | `/api/jobs`, `/api/jobs/{id}` and `/api/meta` refuse anonymous callers |
| `ALLOWED_EMAILS` | optional allowlist; without it any Google account may sign in |

`/api/health` and `/api/auth/config` stay open either way — a host's health
probe has no token, and the login screen has to load before anyone has one.

**The honest limitation.** This protects the API. It cannot protect the
statically published dataset: on GitHub Pages `data/jobs.json` is a public file,
so there the login wall gates the *interface*, not the data. What it does do
correctly is fetch nothing at all until sign-in — with a client id configured,
a signed-out visitor triggers zero data requests. To make the gate load-bearing
over the data, deploy the API with `REQUIRE_AUTH=true` and point
`VITE_API_BASE` at it.

Client-side, `useAuth` decodes the token's payload only to show a name and
avatar, and the code says so: a JWT payload is just base64 and anyone can write
one. Nothing is trusted on the strength of it — the token still has to satisfy
the server. Tokens live about an hour; the hook signs the user out when one
expires rather than leaving a signed-in header above failing requests.

### frontend — `frontend/`
React 19 + Vite. No router, no state library, no UI kit, no animation library.

Split so each file has one job: `App.jsx` is a readable outline of how the page
behaves, everything that renders is a component, everything that fetches or
persists is a hook, and all the motion is in one stylesheet.

**Behaviour**

- **The URL is the state.** Filters live in the query string, so a search can
  be bookmarked, shared and reloaded and the back button works. `replaceState`,
  not `pushState`, or typing would add a history entry per keystroke.
- **Search is debounced 300 ms** and every request is abortable, because
  responses can arrive out of order — a slow request for "dev" must not land
  after the fast one for "devops" and overwrite the right results.
- **Removable filter chips** show what is applied; the selects carry live facet
  counts from the API.
- **Keyboard**: `/` focuses search, `Escape` clears it or closes the drawer.
- **Detail drawer** fetched per job, with the apply link out to the original
  posting and the page behind it scroll-locked.
- **Saved jobs** in `localStorage`, storing the whole job so the Saved tab
  needs no network and still works if the API is down. Every read and write is
  wrapped in try/catch, because private windows throw.
- Server-side pagination with a windowed page list (first, last, and the
  current page's neighbours — rendering all 24 numbers is noise).

**Motion** — all CSS keyframes in `styles/animations.css`, no JS animation
library. The one exception is the hero's count-up, which needs
`requestAnimationFrame` to run on the browser's paint clock.

| what | why |
|---|---|
| Cards stagger in, 35 ms apart | the grid assembles instead of appearing; delay capped at 560 ms so the last card does not lag |
| Card lift + company-coloured edge on hover | makes the grid feel responsive to the pointer |
| Drawer slides in, backdrop fades | reads as "same page, more detail" rather than a navigation |
| Skeleton shimmer | a gradient swept by `background-position`, cheaper than animating a pseudo-element |
| Indeterminate top bar | we do not know how long a request takes, and a fake percentage would be a lie |
| Count-up on the job total | `requestAnimationFrame` + easeOutCubic, with tabular figures so the width does not jitter |
| Star pops when saved | confirms the click without a toast |
| Hero blobs drift, live dot pings | a little life on an otherwise static header |

Every animation is disabled under `prefers-reduced-motion` from one block.
Hover-only affordances get a `@media (hover: none)` fallback so touch is not
left with hidden controls. Colours are CSS custom properties defined once in
`tokens.css`; dark mode redefines the same names, so no component knows which
theme is active.

---

## Setup

```bash
# backend
cd backend
python -m pip install -r requirements.txt
cp .env.example .env          # then fill in the three keys

# frontend
cd ../frontend
npm install
```

`backend/.env` needs `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` (free tier at
developer.adzuna.com) and `GEMINI_API_KEY` (aistudio.google.com/api-keys).
Secrets are only ever read from env vars; in CI they are GitHub Actions
secrets. `.env` is gitignored.

The frontend needs no configuration locally — `vite.config.js` proxies `/api`
to `127.0.0.1:8000`, so the browser sees one origin and CORS never comes into
it. `frontend/.env.example` covers the production case.

## Run

Two terminals. The pipeline has to have produced `backend/data/jobs.json` at
least once before the API has anything to serve.

```bash
# terminal 1 — the API
cd backend
uvicorn api.main:app --reload --port 8000

# terminal 2 — the site
cd frontend
npm run dev                 # http://localhost:5173
```

Everything else:

```bash
# backend, from backend/
python -m pipeline.run                      # full run: fetch -> export
python -m pipeline.run --no-llm             # everything except tagging (free)
python -m pipeline.run --limit 50           # tag only 50 posts, for a cheap test
python -m pipeline.run --raw data/raw_jobs.json   # reuse last fetch, skip the network
python scripts/verify_companies.py          # are all board tokens still alive?
python -m pytest -q                         # 73 tests

# frontend, from frontend/
npm run build                               # -> frontend/dist
npm run preview                             # serve the production build

# reporting, from backend/
python scripts/sample_for_eval.py                                  # 50-post CSV to label
python scripts/score_eval.py data/eval_sample.csv                  # accuracy
python scripts/cost_report.py --input-price 0.30 --output-price 2.50
```

The API picks up a new `jobs.json` on its own — no restart needed.

## Accuracy and cost reporting

`scripts/sample_for_eval.py` writes 50 posts stratified by source to
`data/eval_sample.csv`, with the model's answers in `model_*` columns and empty
`true_*` columns beside them. Fill those in, then `score_eval.py` prints role,
city and `is_fresher` accuracy plus the most common confusions.

`scripts/cost_report.py` takes prices as arguments rather than reading them
from config, so the number quoted is always computed from prices checked at the
time. It bills **output + thinking** tokens, because Gemini reports
`total_thought_tokens` separately and thinking is charged at the output rate.

## Deployment

The site and the API deploy independently, and **the site does not need the
API to work**.

`frontend/src/lib/api.js` picks its data source at build time:

| `VITE_API_BASE` | behaviour |
|---|---|
| not set | the page fetches the dataset bundled into the build and searches it in the browser (`lib/search.js`) |
| set | the page calls that HTTP API instead |

Both paths return the identical response shape, so no hook or component knows
which one answered.

**Why bother with two.** GitHub Pages cannot run Python. Without the local
path, the published link — the one thing actually being graded — would be dead
whenever the API is undeployed or asleep on a free tier. With it, Pages alone
is a complete, instant, self-refreshing site, and the API becomes an upgrade
switched on with one repository variable.

The cost is real and worth stating plainly: the search exists twice, in Python
and in JavaScript. That is only safe because the contract is small and frozen,
and because the two are diffed against each other over 20 query sets covering
filters, sorting, paging and all three facet maps. If they ever disagree,
`backend/api/main.py` is the source of truth.

**Publishing the site** (no server needed):

1. Push to GitHub.
2. Settings → Pages → Source: **GitHub Actions**.
3. Settings → Secrets and variables → Actions → add secrets `ADZUNA_APP_ID`,
   `ADZUNA_APP_KEY`, `GEMINI_API_KEY`.
4. Actions → *refresh job data* → **Run workflow**.

**Adding the live API** (optional): deploy `backend/` anywhere that runs
Python, starting `uvicorn api.main:app --host 0.0.0.0 --port $PORT` from
`backend/` with health check `/api/health`. Set `CORS_ORIGINS` to the Pages origin, then add a
repository **variable** `API_BASE_URL` pointing at it including `/api`. The next
build switches over. On a free tier the service sleeps when idle, which is why
the static path is the default rather than the fallback.

## Refresh schedule

`.github/workflows/refresh.yml` runs every 12 hours (`30 1,13 * * *` — 07:00
and 19:00 IST) and on manual trigger: install, test, run pipeline, commit the
data files, build the frontend, deploy to Pages.

**Why twice a day and not more often.** Each run makes 42 Adzuna calls
(7 queries × 6 pages) and Adzuna's free tier allows roughly 2,500 calls a
month. Two runs a day is 84 a day, ~2,520 a month — the most a full fetch can
sustain. Adzuna supplies ~98% of published posts, and `fetch.py` logs a warning
and continues when a call fails, so a throttled run would publish a nearly
empty page instead of failing loudly. Running more often needs either a paid
Adzuna plan or a thinner fetch that accumulates across runs.

Committing the data is what refreshes the API — it reads those files from the
repo, and the push makes the host redeploy it.

Failure rules it implements:
- One source failing is logged and skipped; the run continues.
- If the pipeline step fails, the site is still rebuilt and redeployed and the
  API keeps serving the previously committed `jobs.json`, so the page never
  goes blank — and the job is then marked failed so the failure is visible.
- A post that has disappeared from its source feed simply is not in the next
  run's output, which is how stale posts drop off.
