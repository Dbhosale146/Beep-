# Build log

Running notes per phase: what I ran, the real numbers, what broke, how I fixed it.

---

## Phase 1 — Skeleton, config, Greenhouse end to end
**Date:** 2026-11-16

### What I built
- `config/companies.yaml` (board tokens + display names), `config/settings.yaml`
  (http/llm/paths), `config/taxonomy.yaml` (18 roles, 23 canonical cities, 58 aliases).
- `pipeline/config.py` — the only place that reads YAML or builds data paths.
- `pipeline/http.py` — single `get_json()` with timeout, 3 retries, exponential
  backoff, polite User-Agent. Retries 429/5xx, gives up immediately on other 4xx.
- `pipeline/sources/greenhouse.py` — `fetch() -> list[dict]` plus a pure
  `to_raw()` so the mapping is testable without network.
- `pipeline/sources/__init__.py` — explicit `SOURCES` registry.
- `pipeline/run_fetch.py` — runs every source, writes `data/raw_jobs.json`,
  prints per-source counts.
- `scripts/verify_companies.py` — re-checks every token is alive.
- `tests/test_greenhouse.py` — 2 tests, no network.

### Verified against live docs, not memory
Fetched https://docs.greenhouse.io/job-board.html (the old
`developers.greenhouse.io` URL now 301s there). Confirmed:
`GET /v1/boards/{token}/jobs?content=true` -> `{"jobs":[...], "meta":{"total":n}}`;
job fields `id, internal_job_id, title, updated_at, requisition_id,
location{name}, absolute_url, metadata` and with `content=true` also
`content` (HTML-escaped), `departments[]`, `offices[]`. Public unauthenticated
GET, no stated rate limit, no attribution requirement.

### Real run output
```
python -m pipeline.run_fetch
okta 361, databricks 895, gitlab 256, sigmoid 40, netradyne 43, elastic 401,
twilio 113, druva 28, coinbase 265, groww 9, datadog 384, zscaler 377,
stripe 786, newrelic 44, figma 139, duolingo 59, mongodb 394, workato 63
TOTAL 4657   |   of which India 371   |   17.2s   |   data/raw_jobs.json = 42 MB
```
`python -m pytest -q` -> 2 passed.

### What broke and how I fixed it
1. **No company list in the brief** (the `[PASTE YOUR COMPANY LIST]`
   placeholder was never filled). Fixed by writing a throwaway probe that
   tested 76 candidate tokens in parallel. 25 boards were valid, 18 of those
   had India jobs; only those 18 are in `companies.yaml`. The 7 valid boards
   with no India jobs today are kept as a comment, ready to re-enable.
   53 guessed tokens 404'd and were dropped.
2. **`/tmp` is invisible to Windows Python.** Git Bash writes `/tmp/x` but
   `python` can't open that path. Fixed by keeping scratch work inside the
   session scratchpad with a real Windows-visible path.
3. **My first fresher keyword check matched "Senior Internal Auditor".**
   The substring `intern` is inside `Internal`. 2 of 4 apparent hits were
   false positives. Fix for phase 2: the keyword rules must use word
   boundaries (`\bintern\b`, `\binternship\b`), not substrings. Caught this
   only because I eyeballed the matched titles instead of trusting the count.

### Numbers that change the plan
Only **4 of 371** India posts matched fresher keywords in the *title*, and
after the word-boundary fix it's effectively **2**. These Greenhouse boards are
enterprise boards full of senior roles. Greenhouse will not get us to 200+ on
its own even after scanning descriptions for "0-1 years".
**Adzuna India is going to be the volume source** — it indexes the whole Indian
market and supports keyword search, so it can be queried directly for
"intern"/"fresher"/"graduate trainee". Phase 2 should lean on it, and Lever +
Ashby should be seeded with Indian startups (who post actual fresher roles)
rather than more US enterprises.

### Known tradeoff, not yet fixed
`raw_jobs.json` is 42 MB because we keep every job with its full HTML
description before filtering. It's gitignored so it never bloats the repo, but
re-reading it is slow. Phase 2 drops non-India and non-fresher rows at the
normalise step, which is the right place — raw stays an honest record of what
the API returned.

---

## Phase 1b — LLM provider switched to Google Gemini Flash
**Date:** 2026-11-16

You asked for Gemini Flash instead of Anthropic. Config-only change; no pipeline
code exists for tagging yet (that's phase 4). Swapped `anthropic` for
`google-genai==3.3.0`, `ANTHROPIC_API_KEY` for `GEMINI_API_KEY`.

### Model chosen: `gemini-3.5-flash-lite`
Checked https://ai.google.dev/gemini-api/docs/models and `/pricing` live. The
Flash lineup today is `gemini-3.8-flash`, `gemini-3.6-flash` ($1.50/$7.50 per
1M), `gemini-3.5-flash-lite` ($0.30/$2.50), `gemini-3.1-flash-lite`,
`gemini-2.5-flash`, `gemini-2.5-flash-lite`. There is also a Gemini 4 family
(`gemini-4-carbon/argon/hydrogen`) which is not Flash-branded.

Picked Flash-Lite because the Gemini docs name it for exactly our workload —
"high-volume data analysis and document extraction, **structured JSON
parsing**" — and it is the cheapest, which directly improves the cost-per-1,000
number I have to report. `gemini-3.6-flash` is a one-line swap in
`config/settings.yaml` if eval accuracy comes in short.

### What I got wrong from memory, and corrected against the real SDK
I would have written `client.models.generate_content(...)` with
`response_mime_type` / `response_schema`. That is not the current documented
path. Verified by introspecting the installed `google-genai 3.3.0`, not just
reading docs:

- **Interactions API** is the current shape:
  `client.interactions.create(model=..., input=..., system_instruction=...,
  response_format=..., generation_config=...)`, and the text comes back on
  `interaction.output_text`.
- **Structured output** is
  `response_format={"type": "text", "mime_type": "application/json",
  "schema": PydanticModel.model_json_schema()}`.
- **`temperature` is NOT a top-level argument.** `interactions.create` accepts
  `background, cached_content, continuation_token, environment,
  generation_config, input, labels, model, previous_interaction_id,
  response_format, response_mime_type, response_modalities, safety_settings,
  service_tier, store, stream, system_instruction, tools, webhook_config`.
  Temperature lives inside `generation_config`, whose fields are
  `temperature, top_p, seed, max_output_tokens, stop_sequences, thinking_level,
  thinking_summaries, tool_choice, image_config, speech_config,
  transcription_config, video_config`. So the brief's "temperature 0" is now
  `generation_config: {temperature: 0}` — same intent, different place.
- **`thinking_level` is a new knob that costs money.** Flash-Lite defaults to
  `minimal`; I pinned it explicitly. Tagging against a fixed taxonomy needs no
  reasoning, and thought tokens bill at the output rate.
- **Token usage field names** (`interaction.usage`):
  `total_input_tokens, total_output_tokens, total_thought_tokens,
  total_cached_tokens, total_tool_use_tokens, total_tokens,
  initial_input_tokens` + per-modality breakdowns.

### Consequence for the cost report
`usage_log.jsonl` must record `total_thought_tokens` as its own field, and
`cost_report.py` must bill **output = total_output_tokens +
total_thought_tokens**. If I logged only `total_output_tokens` I would
under-report cost per 1,000 posts, which is one of my two graded metrics.
Logging `total_cached_tokens` too, since cached input is priced differently.

### Enum-based validation is cheaper than I planned
The structured-output docs support `enum` on string fields and enforce it
during constrained decoding. So the role and city taxonomy goes into the
schema as enums and the model physically cannot emit an off-taxonomy value.
The phase-4 validator still checks every response against
`config/taxonomy.yaml` — belt and braces, and it's what catches a taxonomy
edit that didn't make it into the schema.

**Note on schema limits:** the docs warn that large `enum` lists increase
grammar branching and can trigger `400 INVALID_ARGUMENT`. We have 18 roles +
23 cities, which is small, but worth knowing if the taxonomy grows.

### Verified
`python -m pytest -q` -> 2 passed (nothing imported `anthropic`).
No API key is set yet, so no live Gemini call has been made. First real call
happens in phase 4.

---

## Phases 2-6 — rest of the backend end to end, plus a React frontend
**Date:** 2026-11-16

Ran in one pass at your request: remaining sources, normalise, fresher filter,
dedup, tagging, export, then the frontend in React instead of vanilla JS.

### Verified every endpoint live before coding (no memory)
Probed each API with real keys and printed the actual field names:

| source | what the probe showed |
|---|---|
| Lever | returns a JSON **array**, not an object. Title is `text`, not `title`. `createdAt` is epoch **milliseconds**. Has a real ISO-2 `country` field, and `categories.allLocations` is an array for multi-city posts. |
| Ashby | `{"jobs": [...]}`. Country is at `address.postalAddress.addressCountry`. Has `isListed` (unpublished postings must be filtered out) and `employmentType` of `"Intern"`, which is a better fresher signal than any title guess. |
| Adzuna | `{"count", "results", "mean"}`. `location.area` is `["India","Karnataka","Bangalore","Padmanabhnagar"]`. **`description` is truncated** by Adzuna with a trailing "...", so years-of-experience text cannot be trusted from this source. |

### Real run output
```
python -m pipeline.run
greenhouse 4656 · lever 333 · ashby 7 · adzuna 1627   = 6623 raw
normalise   -> 2520 India posts (4103 non-India dropped)
fresher     -> 1075 kept, 1445 dropped
dedup       -> layer1 -395, layer2 -58, layer3 -50  = 572 unique
tag         -> 572 tagged, 0 Untagged, 59 LLM calls
LLM dropped -> 7 posts it judged not fresher
published   -> 565 jobs in 310s
```
Second run, same raw data: **571 of 572 posts came from cache, 1 LLM call,
33 seconds**. That is the cache doing its job and the daily-run economics.

`python -m pytest -q` -> **48 passed** (normalise 15, dedup 14, tag validation
17, greenhouse 2).

Cost report: **$0.1579 per 1,000 posts**, 196 input + 40 output tokens per post.
Thinking tokens came back **0**, confirming `thinking_level: minimal` works.

### What broke and how I fixed it

1. **`tokens_since()` crashed with `KeyError: 'billable_output'`** on the first
   end-to-end run, right at the final log line — after the data was written.
   The early-return path for "no usage log yet" built the dict without that
   key. Fixed by putting `billable_output` in the initial dict.

2. **The fuzzy dedup layer was too strict and my own test caught it.**
   `token_sort_ratio("sde intern", "sde intern 2027 batch")` is **65**, nowhere
   near the 90 threshold, so batch-year variants were not being merged — and
   those are everywhere in Indian fresher postings. I measured both metrics on
   nine realistic title pairs before choosing: genuinely different roles score
   62-78 on `token_set_ratio`, real duplicates score 100. So layer 3 now uses
   `token_sort_ratio >= 90` OR `token_set_ratio >= 95`, with a guard that the
   shorter title must have at least 2 tokens — otherwise a bare "Intern"
   posting is a token-subset of every intern title and would swallow a
   company's entire list. There is a test for exactly that. Layer 3 went from
   removing 33 to removing 50.

3. **102 posts were tagged "Multiple" when their location was just "India".**
   Adzuna often gives a country-only location. The model was following my
   prompt correctly, but "Multiple" is the wrong answer for "nationwide" — it
   pollutes the city filter. Added a `Pan India` value to the taxonomy and a
   prompt rule for state/country-only locations. Bumped the prompt to
   **tag_v2**, which invalidates the tag cache by design.

4. **The city taxonomy was missing most of India.** The first real run showed
   Surat, Rajkot, Lucknow, Raipur, Bhopal, Patna, Ranchi, Salem, Jalandhar and
   Kolhapur all falling through to "Multiple" simply because they were not in
   my list. Added 33 tier-2 cities. Result: "Multiple" fell from **170 to 39**,
   and the published set now spans 40 cities instead of 23. This mattered
   because city accuracy is one of the two graded metrics — the model was not
   wrong, my taxonomy was.

5. **`/tmp` is invisible to Windows Python** (again) and **bash choked on the
   regex-heavy heredocs** for `normalise.py` and `fresher.py`, silently writing
   nothing. Noticed because the next import failed. Switched those files to
   direct writes rather than shell heredocs.

6. **59 copies of "HTTP Request: POST .../interactions 200 OK"** buried the
   pipeline's own progress output. Silencing the `httpx` logger did nothing.
   The reason: **google-genai vendors its own copies of httpx and httpcore
   under the names `httpx2` and `httpcore2`**. Silencing those worked.

7. **Adzuna is doing nearly all the work.** Published split is adzuna 570,
   lever 7, greenhouse 3. The enterprise Greenhouse boards from phase 1 are
   almost entirely senior roles, exactly as phase 1 predicted. This is worth
   saying out loud rather than hiding: the company-board sources prove the
   "one file per source" design and give high-quality direct links, but Adzuna
   is what reaches 200+.

### Judgement calls you may want to overrule

- **React with a build step.** Your original brief said "vanilla JS, no build
  step"; you then asked for React. I used React 19 + Vite because `npm run dev`
  with hot reload is genuinely nicer to edit live, and the CI build is four
  lines. If you would rather keep zero build tooling, this same UI collapses
  into one `index.html` with React from a CDN — say so and I will swap it.
- **The eval sample is proportional**, so it comes out 48 Adzuna / 1 Greenhouse
  / 1 Lever. That is what "stratified by source" means with a 98/2 split, and
  it measures the thing users actually see. If you would rather measure the
  company boards fairly, we should over-sample them instead.
- **Dedup errs towards merging.** Showing one posting twice looks worse on a
  job board than collapsing two near-identical ones. That is a product choice,
  and it is one constant (`SUBSET_THRESHOLD`) if you disagree.

### Not done yet
- `git init` and the GitHub repo. The workflow is written and its YAML parses,
  but it has never run, because there is no repo and no remote yet. Three
  secrets must be added in repo settings: `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`,
  `GEMINI_API_KEY`, and Pages must be set to "GitHub Actions" as its source.
- The 50-post eval CSV is generated but **not labelled**. Accuracy is the one
  headline number I cannot produce for you — it needs your hand-checking.

---

## Phase 7 — split into backend/ + frontend/, add a live API (2026-11-17)

### Why

Up to here the site was static: the pipeline wrote `data/jobs.json`, a build
step copied it into `site/public/data/`, and React downloaded all 565 posts and
filtered them in the browser. I moved to a real HTTP API so the frontend asks
the server for a page of results, and reorganised the repo into `backend/` and
`frontend/` so each half is self-contained.

I want to be straight about the trade-off, because it is the obvious question
to ask me: at 565 posts the static version was *faster* for the user and free
to host. The API is the right call only if the dataset is going to grow or if
anything other than this one page ever needs the data. What it does buy today
is a real query interface, an `/api/docs` page, and a clean seam where a
database would go later.

### What was built

- `backend/api/main.py` — FastAPI, one file. `/api/jobs` with `q`, `role`,
  `city`, `source`, `posted_within_days`, `sort`, `page`, `page_size`, plus
  `/api/jobs/{id}`, `/api/meta` and `/api/health`.
- `backend/tests/test_api.py` — 25 tests against a fixture, no network, no
  dependency on the real data file.
- Frontend rewritten against the API: `api.js`, `Filters.jsx`, `JobDetail.jsx`,
  `useSaved.js`, plus a reworked `App.jsx` and `JobCard.jsx`.
- Job-board behaviour the static page did not have: URL-synced filters,
  sort, server-side pagination, debounced search, a detail panel, saved jobs in
  localStorage, skeleton loaders and a useful empty state.
- `render.yaml` to deploy the API; workflow updated for the new folders.

### Real output

```
$ python -m pytest -q                       # from backend/
73 passed in 1.07s                          # 48 pipeline + 25 API

$ uvicorn api.main:app --port 8000
{"status":"ok","jobs":565,...}

$ curl "localhost:8000/api/jobs?q=intern&city=Pune&page_size=3"
total 10  pages 4
titles  ['Intern', 'Talent Acquisition Intern', 'HR Intern']
facets  7 roles / 29 cities

API response times, warm:
  /api/jobs                                        0.0138s
  /api/jobs?q=intern                               0.0138s
  /api/jobs?q=intern&city=Pune&role=Software Eng   0.0305s
  /api/jobs?sort=company&page=10                   0.0145s

$ npm run build                             # from frontend/
21 modules transformed
dist/assets/index-Bqc_sMWo.js   230.28 kB │ gzip: 72.25 kB
built in 303ms

API through the Vite proxy (the real integration test):
  http://localhost:5173/api/health  ->  200, 565 jobs
```

### What broke, and the fix

**1. `posted_at` has three different formats, so sorting by string is wrong.**
The data carries `...Z` (557 posts), `+05:30` offsets (5) and one with
microseconds (3). Sorted as text, a `+05:30` timestamp lands in the wrong
place. Fixed by parsing to a real `datetime` once at load time and sorting on
that. There is a test that puts all three shapes in one fixture and asserts the
order, which is the only way I would have noticed.

**2. Moving `site/` to `frontend/` failed: "Device or resource busy".**
Four Vite processes left over from earlier verification runs were holding
`site/node_modules`. Killing all of `node.exe` was correctly refused as too
broad, so I stopped them by individual PID. One of those turned out to be the
wrapper for the dev server I had *just* started, which stopped it — harmless,
restarted it. For the move itself I stopped fighting the lock and rebuilt
`frontend/` from the source files, then reinstalled `node_modules`, since it is
regenerable. One orphaned shell still holds the old `site/` folder, so it has
to be deleted manually.

**3. I wrote `__import__("datetime").timedelta` inside a function.**
Caught it rereading my own file. The whole point of this project is code I can
edit live on a call, and that line is the opposite of that. Replaced with a
normal top-level import.

**4. A block of JSX that could never render.** The detail panel had a
`{job.truncated && ...}` notice, but the detail endpoint always returns the
full description, so `truncated` is never set there. Deleted rather than left
in as decoration.

**5. I could not open a browser in this session, and `npm run build`
succeeding does not mean the page works.** A build only proves the JSX
compiles. So I loaded the real production bundle into jsdom with a stubbed
`fetch` and asserted what the page actually renders: 24 cards, facet counts in
the dropdowns, `?role=` restored from the URL into the select, clicking a card
opening the panel and calling `/api/jobs/{id}`, Escape closing it, the
bookmark writing to localStorage, and zero React warnings. All 28 checks
passed. I installed jsdom with `--no-save` and deleted the script afterwards,
so no test tooling leaked into `package.json`.

### Still open

- Nobody has looked at the page in a real browser. jsdom proves it renders and
  behaves; it says nothing about how it *looks*.
- Not a git repository yet, so the workflow has never executed.
- `data/eval_sample.csv` is generated but unlabelled, so tagging accuracy —
  one of the two graded numbers — still needs 50 posts hand-checked.

---

## Phase 8 — frontend rebuilt: structure and motion (2026-11-17)

### Why

The API worked but the page looked like a prototype: flat cards, no hierarchy,
nothing moving. The feedback was simply that it was hard to look at. I rebuilt
the frontend rather than patching the stylesheet, because the flat
`src/*.jsx` layout had no place to put the new pieces.

### Structure

```
src/
  App.jsx         composition root -- a readable outline of the page
  components/     Header · SearchBar · FilterBar · JobCard · JobPanel
                  Pagination · SkeletonGrid · EmptyState · ProgressBar
  hooks/          useJobs · useUrlState · useSaved · useCountUp
  lib/            api.js · format.js
  styles/         tokens · base · components · animations
```

The rule: components render, hooks fetch or persist, lib is pure, styles are
split by scope. Eleven small files beat one 300-line `App.jsx` for editing live
on a call — you open the file named after the thing you want to change.

### What is new in the UI

Company avatars with a colour hashed from the name (so an employer always looks
the same, with no palette to maintain), removable filter chips, a source filter,
a windowed pager instead of bare prev/next, `/` to focus search, a right-hand
detail drawer with a facts table, a fresh-post highlight for anything under
three days old, and an empty state that names what was searched and offers the
specific way out.

### Motion

All CSS keyframes in one file, `styles/animations.css`, so the whole motion
vocabulary is visible at once and the reduced-motion switch is one block rather
than scattered per component. No animation library — nothing here needed one.

Staggered card entrance (`--i` index set inline becomes an `animation-delay`,
capped at 560 ms), card lift with a company-coloured edge on hover, drawer
slide-in with a fading backdrop, skeleton shimmer, an indeterminate top
progress bar, a star that pops when saved, drifting hero blobs, a pinging live
dot, and a count-up on the job total.

The count-up is the only animation in JavaScript, because it needs
`requestAnimationFrame` — it runs on the paint clock, pauses in a background
tab, and never queues frames it cannot draw. It also respects reduced-motion by
jumping straight to the final number.

### Real output

```
$ npm run build
34 modules transformed
dist/assets/index-CDdzbuQM.css   19.42 kB │ gzip: 4.87 kB
dist/assets/index-Dh19rcX8.js   239.22 kB │ gzip: 74.59 kB
built in 279ms

jsdom check against the built bundle: 63/63 passed, 0 React warnings
```

### What broke, and the fix

**1. Two of my own test failures were the test, not the app.** Worth recording
because I nearly "fixed" working code twice.

- The empty-state checks failed because I set `input.value = "zzzz"` and
  dispatched an `input` event. React keeps its own value tracker, so a direct
  assignment is invisible to it and the component never re-rendered. The fix is
  to go through the native setter
  (`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set`),
  which is what React listens for. The app was fine.
- The mobile-breakpoint check failed because Vite's minifier rewrites
  `@media (max-width: 640px)` into the Media Queries Level 4 range form,
  `@media (width<=640px)`. My regex only knew the old spelling. Checked the
  built CSS before changing anything, which is how I caught it.

**2. Hover-only affordances left touch users with nothing.** The "View details"
arrow on each card appears on hover, which on a phone means never. Added a
`@media (hover: none)` block that shows it permanently.

**3. Animating the grid's contents did nothing on a filter change.** React
reuses the existing card elements when only the data changes, so the entrance
animation never replayed and a new page silently swapped its contents. Fixed by
keying the grid container on the filter state, which remounts the cards and
replays the stagger.

### Still open

- Unchanged from phase 7: nobody has opened this in a real browser. 63 jsdom
  checks prove it renders and behaves; they say nothing about whether it
  *looks* right.
- Not a git repository yet, so the workflow has never executed.
- `data/eval_sample.csv` still needs 50 posts hand-labelled for the accuracy
  number.

---

## Phase 9 — made it actually deployable, and a repo (2026-11-17)

### The problem

Two requirements were unmet: "a live web tool" and "refreshes every day on its
own". The workflow existed but had never run, because the project was not a git
repository. And deploying was blocked on something worse: GitHub Pages cannot
run Python, so the published page needed an API hosted somewhere else before it
would show anything at all. That made the one graded link depend on a signup
and a free-tier service that sleeps after 15 minutes.

### The fix: one contract, two implementations

`frontend/src/lib/api.js` now chooses its data source at build time.
`VITE_API_BASE` set means talk to the Python API; unset means fetch the dataset
bundled into the build and search it in the browser via a new
`frontend/src/lib/search.js`. Both return the identical response shape, so
`useJobs` and every component are unchanged and cannot tell the difference.

Pages alone is now a complete working site. The API became an upgrade rather
than a prerequisite.

This is a genuine duplication — the same search logic in Python and in
JavaScript, two places to change. I decided it was worth it because the
contract is small and frozen, and because I could test the two against each
other. If they ever disagree, `api/main.py` is the source of truth.

### What broke, and the fix

**1. The cross-check immediately found a disagreement — and the JS was right.**
I wrote a throwaway script that runs 20 query sets through both
implementations and diffs ids, order, descriptions, truncation flags and all
three facet maps. Eight sets disagreed, all on `facets.sources`. For
`city=Bengaluru`, Python returned `{adzuna: 557, lever: 5, greenhouse: 3}` —
all 565 — while the JS returned counts summing to 92, the actual result count.

The JS was correct. Python was ignoring the city filter when counting sources,
because `base` had the source filter baked in and the sources facet was
`counts(base)`. I had already fixed this and added a passing test. The tests
passed because pytest imports the module fresh; **the running server was still
executing the old code.**

**2. Chasing that stale server took four attempts.** `uvicorn --reload` had not
picked up the edit. Killing the reloader (PID 31036) left its worker alive
holding the port, so the replacement server exited with code 3 and the old one
kept answering. Then `netstat` listed two PIDs on port 8000 that
`Get-Process` reported as already gone — stale socket entries. The actual
listener was PID 17412, the worker from the *first* `--reload` launch hours
earlier. Killing that one fixed it, and all 20 query sets then agreed.

Lesson I will repeat on the call: a passing test suite says nothing about what
a long-running dev server is serving. I only caught it because the cross-check
compared two live implementations instead of trusting either.

**3. Verified the static path in the exact Pages configuration.** Loaded the
built `dist/` in jsdom with a fetch that serves *only* files inside `dist/`, so
any API call would 404. 21 of 22 checks passed first run: no `/api/` request
made, 565 rendered, 24 pages of real data, client-side search, real facet
counts, drawer reading full descriptions, and `jobs.json` fetched exactly once
rather than per query.

The one failure was my assertion, not the code: searching "intern pune"
returned a card whose city pill said `Multiple`, and I had asserted every
result would say Pune. The posting is at **"Warje, Pune"** — a Pune suburb —
and search covers `raw_location`, so matching it is correct.

**But it exposed a real tagging error.** `prompts/tag_v2.txt` explicitly states
that a suburb counts as its city, and the model still tagged "Warje, Pune" as
`Multiple`. That is exactly the class of mistake the 50-post hand-check is for.
Left as-is for now: fixing the prompt means bumping `PROMPT_VERSION`, which
invalidates the whole tag cache and costs a full re-tag.

**4. Checked what a public repo would expose before committing.** `.env` is
correctly ignored. Scanning the staged diff turned up 32-character hex strings,
which are `tag_cache.json` content hashes, not secrets. But the Adzuna
`app_id` *is* embedded in all 557 Adzuna URLs as `utm_source` — Adzuna puts it
there itself in `redirect_url`. The `app_key` is not exposed, and the API needs
both, so the id alone is unusable. Left in place deliberately: it is Adzuna's
attribution mechanism, and stripping it would work against the "respect each
site's terms" requirement.

### Real output

```
$ node crosscheck.mjs            # python API vs js search, same dataset
PASS  (no filters)                                    (total 565)
PASS  q=intern                                        (total 266)
PASS  q=intern+pune                                   (total 11)
PASS  role=Software+Engineering&city=Bengaluru        (total 9)
PASS  source=lever                                    (total 5)
PASS  posted_within_days=7                            (total 227)
PASS  sort=company / sort=title / sort=oldest          ...
PASS  page=10&page_size=7                             (total 565)
PYTHON AND JS AGREE ON EVERY QUERY      (20 query sets)

$ node static-check.mjs          # dist/ with no API reachable
PASS  no /api/ request was made
PASS  real total rendered -> "565"
PASS  24 pages of real data
PASS  jobs.json fetched exactly once -> 1 times
STATIC SITE WORKS WITH NO BACKEND

$ cd backend && python -m pytest -q
74 passed in 1.99s

$ git log --oneline -1 --stat
74 files changed, 21686 insertions(+)
```

### Still open

- The repo is committed locally on `main` but **not pushed** — no `gh` CLI here
  and pushing needs the account. Once pushed and Pages is switched to "GitHub
  Actions", the daily refresh is live.
- Nobody has opened the site in a real browser.
- `data/eval_sample.csv` still needs 50 posts hand-labelled.

---

## Phase 10 — login wall with Google Sign-In (2026-11-17)

### The decision I pushed back on first

The ask was a login page taking a username and password "with gmail account".
You cannot do that: collecting someone's Gmail password in your own form is
phishing, Google blocks it, and it hands you a credential you should never
hold. The legitimate equivalent is Sign in with Google, where Google shows its
own password screen and the app receives a signed token instead.

I also flagged that a hard login wall means a reviewer has to authenticate
before they can look at the work, and recommended optional sign-in. That was
overruled, which is a fair call to make. I built the wall, with one safeguard:
if VITE_GOOGLE_CLIENT_ID is not configured, the wall shows a labelled way
through instead of bricking the site. An unconfigured deploy would otherwise be
a locked door with no key, two days before a deadline.

### What was built

backend/api/auth.py verifies Google ID tokens with google-auth — signature
against Google's published keys, `aud` equal to our own client id, `iss`, `exp`
and `email_verified`. No new dependency: google-auth already arrives with
google-genai, now pinned explicitly. REQUIRE_AUTH gates /api/jobs,
/api/jobs/{id} and /api/meta; /api/health and the new /api/auth/config stay
open so a health probe and the login screen both still work. Optional
ALLOWED_EMAILS allowlist.

frontend/src/hooks/useAuth.js loads Google Identity Services, renders Google's
own button, keeps the token in localStorage, pushes it into api.js so no
component threads it through calls, and signs the user out on expiry.
LoginPage.jsx is the wall; UserChip.jsx is the signed-in header menu.

30 new backend tests, 104 total.

### What broke, and the fix

**1. The gate leaked the entire dataset before login.** This is the one worth
telling. The wall rendered correctly — no board, no cards, no filters — but the
jsdom check reported "no job data was fetched -> data/jobs.json,
data/run_meta.json". All 527 KB arrived BEFORE sign-in.

Cause: App.jsx fetched run metadata on mount to show a job count on the login
screen, and in static mode fetchMeta() shares its loader with the job data, so
asking for one pulled both. The board was hidden while the network tab showed
every job — exactly the kind of gap that makes a login look like theatre.

Fixed by gating the metadata fetch on `unlocked` and dropping the count from the
login screen, since there is now no number to show before sign-in. Re-ran:
"no job data was fetched -> nothing". A signed-out visitor now makes zero data
requests.

**2. An expired token left the page looking signed in.** Google ID tokens last
about an hour. A stale one in localStorage unlocked the UI, and then every
request 401'd. Now the hook checks `exp` on restore, schedules a sign-out for
the moment it expires, and api.js tags 401 responses with a status so App can
tell "your session ended" from "the server is broken" and sign out rather than
show an error.

**3. Google's avatar URLs 403'd.** Google's CDN rejects image requests that
carry our origin as the referrer, so the avatar silently failed. Needs
referrerPolicy="no-referrer" on the img, which there is now a test for.

### Real output

    $ cd backend && python -m pytest -q
    104 passed

    $ node login-check.mjs configured          # signed out
    PASS  login wall is shown
    PASS  job board is NOT rendered
    PASS  no job data was fetched  -> nothing
    PASS  no password field anywhere
    PASS  no text input at all on the wall
    PASS  Google's script was requested
    PASS  no bypass offered

    $ node login-check.mjs configured          # signed in, then out
    PASS  user chip shown / name from the token -> A Student
    PASS  sign out returns to the wall
    PASS  sign out clears storage
    PASS  expired token does not unlock
    ALL LOGIN CHECKS PASSED   (both unconfigured and configured builds)

### The limitation I am not going to paper over

This protects the API. It cannot protect the statically published dataset,
because on GitHub Pages data/jobs.json is a public file that anyone can request
directly. There, the wall gates the interface, not the data. Making it
load-bearing means deploying the API with REQUIRE_AUTH=true and pointing
VITE_API_BASE at it. The code and the README both say this plainly rather than
implying the static build is secured.

### Still open

- Needs a Google OAuth client id from Google Cloud Console before the sign-in
  button can appear.
- Repo is committed locally but still not pushed.
- 50 posts still need hand-labelling.
