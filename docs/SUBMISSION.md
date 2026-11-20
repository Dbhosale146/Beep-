# Beep — Gen AI & Engineering task

**Dnyaneshwar Bhosale** · submitted November 2026

A tool that collects fresher and internship postings in India from official
public job-board APIs, removes duplicates, tags each post by role and city with
an LLM, and publishes them to a searchable page that refreshes itself twice a day.

---

## 1. Links

| | |
|---|---|
| Live site | `<PASTE GITHUB PAGES URL>` |
| Repository | https://github.com/Dbhosale146/Beep- |
| Live API | https://beep-6fn4.onrender.com |
| Interactive API docs | https://beep-6fn4.onrender.com/docs |
| Build log (everything that broke) | [docs/build_log.md](build_log.md) |

---

## 2. The numbers

One run, 2026-11-16:

| stage | in | out | notes |
|---|---|---|---|
| Fetch | — | **6,623** | 4 sources, 25 company boards + 7 Adzuna queries |
| Normalise | 6,623 | 2,520 | 4,103 dropped as not-India |
| Fresher filter | 2,520 | 1,075 | keyword rules, before any LLM spend |
| De-duplicate | 1,075 | 572 | **503 duplicates removed** |
| LLM `is_fresher` check | 572 | 565 | 7 more dropped by the model |
| **Published** | | **565** | 0 untagged |

**Duplicates removed, by layer:** exact id/URL 395 · company+title+city hash 58 ·
fuzzy title within a company 50.

**Where the published posts came from:** Adzuna 557 · Lever 5 · Greenhouse 3.

**Coverage:** 18 role categories, 40 distinct cities in the output (from a
57-city taxonomy).

| top roles | | top cities | |
|---|---|---|---|
| Operations & Support | 127 | Pan India | 114 |
| Software Engineering | 83 | Bengaluru | 92 |
| Marketing & Growth | 76 | Mumbai | 48 |
| Sales & Business Dev | 63 | Hyderabad | 33 |
| Human Resources | 59 | Pune | 29 |

---

## 3. Tagging accuracy

> **TO COMPLETE BEFORE SUBMITTING.** `backend/data/eval_sample.csv` holds 50
> posts sampled stratified by source with a fixed seed. Fill in the `true_role`,
> `true_city` and `true_is_fresher` columns, then run:
>
> ```
> cd backend && python scripts/score_eval.py data/eval_sample.csv
> ```
>
> Paste the output here: role accuracy, city accuracy, is_fresher accuracy,
> and the confusion list it prints.

**How the sample was drawn.** `scripts/sample_for_eval.py` takes 50 posts
stratified by source with `--seed 42`, so the sample is reproducible and anyone
can regenerate exactly the same 50. Without stratification Adzuna would supply
~98% of the sample and it would say nothing about the company boards.

The CSV puts the model's answers in `model_*` columns and leaves `true_*`
columns blank beside them, so the two can never get mixed up. `score_eval.py`
scores only the rows that were actually labelled and reports the rest as
unlabelled rather than counting them as correct.

**One error already known.** A posting located at *"Warje, Pune"* is tagged
`city: Multiple`. Warje is a Pune suburb, and the prompt explicitly says a
suburb counts as its city, so the model got this one wrong. It was found by
accident while testing search. The hand-check is how you find the rest.

---

## 4. Cost

Measured from `data/usage_log.jsonl`, which records input, output and thinking
tokens for every single LLM call.

| | |
|---|---|
| Model | `gemini-3.5-flash-lite` |
| Posts tagged | 1,175 across 119 calls |
| Input tokens | 230,571 (196 per post) |
| Output tokens | 46,550 (40 per post) |
| Prices used | $0.30 / 1M input, $2.50 / 1M output |
| **Cost per 1,000 posts** | **$0.1579** |

Reproduce with:

```
cd backend && python scripts/cost_report.py --input-price 0.30 --output-price 2.50
```

Prices are **arguments, not constants**, so the figure is always computed from
prices checked at the time rather than a number that has gone stale in a config
file. The script bills `output + thinking` tokens, because Gemini reports
thinking separately and it is charged at the output rate — counting only output
would understate the real cost.

**Two things keep this number low:**

1. **Keyword rules run before the LLM.** 6,623 postings were fetched; only 572
   ever reached the model. Tagging all 6,623 would have cost about 11× more for
   no benefit, because most were senior or non-India roles.
2. **A content-hash cache.** Results are keyed on
   `title + company + location + description + prompt version`, so a run
   only pays for posts it has not seen. On the second run, **571 of 572 posts
   came from cache and the run cost $0.00** — 310s down to 21.5s.

Bumping the prompt version invalidates the cache on purpose: answers from two
different prompts must never be mixed in one dataset.

---

## 5. Sources, and respecting their terms

Official public API endpoints only. **No HTML scraping anywhere** — nothing
parses a careers page or works around a robots.txt.

| source | endpoint | auth | what it gave |
|---|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | none | 18 boards, 4,656 raw |
| Lever | `api.lever.co/v0/postings/{company}?mode=json` | none | 6 boards, 333 raw |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{name}` | none | 1 board, 7 raw |
| Adzuna | `api.adzuna.com/v1/api/jobs/in/search/{page}` | app id + key | 7 queries, 1,627 raw |

Each request sends a polite identifying User-Agent, with a 20s timeout, 3
retries and exponential backoff, all through one shared helper so the behaviour
is identical everywhere. Adzuna's attribution parameters are preserved on every
outbound link rather than stripped, because that is how their terms expect
their index to be used.

Company board tokens are in `config/companies.yaml`, each one verified to
actually return postings — `scripts/verify_companies.py` re-checks them.

---

## 6. Prompts

Prompts live in `backend/prompts/` as **versioned plain-text files**, never as
inline strings, so a change is visible in a diff and the cache key can include
the version.

`tag_v1.txt` → `tag_v2.txt` is a real change made after seeing real output, not
a tidy-up. See §7.

### The live prompt — `prompts/tag_v2.txt`

```
You classify Indian fresher job and internship posts. You will be given a
numbered list of posts. Return one object per post, in the same order, using
the index number you were given.

For each post decide three things.

1. role -- the single best match from this list and nothing else:
{ROLES}

2. city -- the work location, from this list and nothing else:
{CITIES}
   Rules for city, in priority order:
   - If the post names one city, answer that city, using the canonical name
     exactly as written above. "Bangalore" is "Bengaluru". "Gurgaon" is
     "Gurugram". "Trichy" is "Tiruchirappalli".
   - A neighbourhood or suburb counts as its city: "Padmanabhnagar, Bangalore"
     is "Bengaluru", "Powai" is "Mumbai".
   - If only a state or the country is given with no city -- for example
     "India", "Karnataka, India", "West Bengal" -- answer "Pan India".
   - If the post is fully remote or work-from-home, answer "Remote".
   - If the post names two or more different cities, answer "Multiple".
   - If a single city is named but is genuinely not in the list above, answer
     "Multiple" rather than inventing a name.

3. is_fresher -- true only if this post is genuinely open to someone with no
   more than one year of experience, or is an internship, apprenticeship,
   trainee or new-graduate role. Set it to false for anything asking for two
   or more years, and for senior, lead, staff, principal or manager roles,
   even if the title contains the word "intern" as part of another word such
   as "internal".

Judge only from the text given. Do not use outside knowledge about the
company. Do not guess at a value you cannot support from the post.

Posts:
{POSTS}
```

`{ROLES}` and `{CITIES}` are injected from `config/taxonomy.yaml` at call time,
so the prompt and the validator can never disagree about what is allowed.

### How the output is constrained

- The taxonomy goes into the request as a **JSON Schema with `enum`** on the
  role and city fields. Constrained decoding makes an off-taxonomy answer
  *impossible*, not merely unlikely.
- `temperature: 0`, `thinking_level: minimal`.
- ~10 posts per call, with short property names (`i`, `r`, `c`, `f`) because
  long names and large enums grow the decoding grammar.
- **Every response is still validated** against the taxonomy in Python, because
  trusting the schema alone would be trusting a vendor promise. One retry on
  failure, then the post is marked `Untagged`.
- **Nothing is ever guessed.** A post that cannot be validated twice is
  published as `Untagged` rather than given a plausible answer. On this run:
  0 untagged.

---

## 7. What I found

> *Raw material — rewrite this section in your own words before submitting.*

**Most of the work is not the LLM.** The model only ever saw 572 of 6,623
postings, and it never made a mistake the validator caught. Almost everything
that determined output quality was ordinary engineering: filtering to India,
filtering to fresher roles, and de-duplicating. The LLM is one stage, and
cheaply the least troublesome one.

**My own keyword filter had a bug the model would never have made.** The
fresher check matched `intern` as a substring, so *"Senior Internal Auditor"*
came through as an internship. I only caught it because I printed the matched
titles instead of trusting the count. Every pattern is now word-boundary
matched, and there is a regression test named after the exact bug.

**"Multiple" was hiding a config problem, not a model problem.** 170 posts were
tagged `Multiple` for their city. The model was following my prompt correctly —
my taxonomy was simply missing most of India. Surat, Rajkot, Lucknow, Raipur,
Patna, Ranchi, Jalandhar and others had no entry to match. After adding 33
tier-2 cities, `Multiple` fell from 170 to 39 and coverage went from 23 to 40
cities. Separately, Adzuna returns country-only locations like "India", which
is not "Multiple" — that needed a new `Pan India` value and a prompt rule. That
change is why `tag_v2` exists.

**Duplicates arrive in three different shapes**, which is why one check is not
enough: the same Adzuna job returned by several of my own search queries
(same id), the same job on a company's board *and* in the Adzuna index (different
id and URL, same company/title/city), and batch-year variants like
*"SDE Intern"* vs *"SDE Intern (2027 Batch)"*. I measured both rapidfuzz metrics
across nine realistic pairs before choosing thresholds: genuinely distinct roles
score 62–78 on `token_set_ratio`, real duplicates score 100. Layer 3 went from
33 to 50 removals once the subset rule was added.

**Source concentration is the real weakness.** 557 of 565 published posts come
from Adzuna. Greenhouse contributed 4,656 raw postings and **3** survived,
because most of those boards are US companies. Ashby contributed zero. If Adzuna
has a bad day, this site is nearly empty. Fixing it means finding Indian
companies that use these boards, not writing more code.

**Checking the current docs mattered more than once.** I would have written the
Gemini call from memory using `models.generate_content`; the current SDK uses an
Interactions API and `temperature` lives inside `generation_config`. I also
assumed I could detect Indian postings by string-matching "india" — that
reported zero India jobs on Lever, because the locations say "Noida, Uttar
Pradesh". Using each source's real country field revealed 316.

---

## 8. Architecture

```
config/*.yaml  ── companies · taxonomy · fresher rules · settings
                         │ read by every stage
  fetch → normalise → fresher filter → dedup → tag → export
    │         │            │             │       │       │
  4 APIs   one schema   keyword       3 layers  Gemini  jobs.json
           India filter  rules        counted   + cache run_meta.json
           city aliases  0–1 years              + usage log
                                                           │
                                     ┌─────────────────────┴──────┐
                                     │  FastAPI search API        │
                                     │  (Render, Google Sign-In)  │
                                     └─────────────┬──────────────┘
                                                   │ JSON over HTTP
                                     ┌─────────────┴──────────────┐
                                     │  React 19 + Vite           │
                                     │  (GitHub Pages)            │
                                     └────────────────────────────┘
```

**One source file per job board**, each exposing exactly `fetch() -> list[dict]`.
Adding a source is one new file and one line in a registry — no framework, no
plugin discovery.

**The frontend works with or without the API.** With `VITE_API_BASE` set it
calls the HTTP API; unset, it searches the dataset bundled into the build in the
browser. Both return the identical response shape, so no component knows which
answered. This means the published site cannot be taken down by the API being
asleep or undeployed. The cost is that the search logic exists twice, in Python
and JavaScript — which is only safe because I diff the two against each other
across 20 query sets covering filters, sorting, paging and all three facet maps.

**104 tests**, none of which touch the network:

| file | tests | covers |
|---|---|---|
| `test_api.py` | 26 | filtering, facets, sorting, paging, error codes |
| `test_auth.py` | 18 | token verification, the REQUIRE_AUTH switch, allowlist |
| `test_tag_validation.py` | 18 | schema building, response validation, cache keys |
| `test_dedup.py` | 14 | all three layers and the fuzzy thresholds |
| `test_normalise.py` | 14 | city aliases, India detection, HTML cleaning |
| `test_greenhouse.py` | 2 | response-shape parsing |

---

## 9. How the refresh works

`.github/workflows/refresh.yml` runs **every 12 hours** (`30 1,13 * * *` —
07:00 and 19:00 IST) and on manual trigger:

1. install → run 104 tests → run the pipeline
2. commit the refreshed data files
3. build the frontend → deploy to GitHub Pages

**Failure rules it actually implements:**

- One source failing is logged and skipped; the run continues with the rest.
- If the whole pipeline step fails, the site is **still rebuilt and redeployed**
  from the previously committed `jobs.json`, so the page never goes blank — and
  the job is *then* marked failed so the failure is still visible.
- A post that has disappeared from its source feed is simply absent from the
  next run's output. That is how stale postings drop off.

**Why twice a day rather than hourly — the constraint that set the schedule.**
Each run makes 42 Adzuna calls (7 queries × 6 pages). Adzuna's published terms
no longer state free-tier numbers (they are shown in the account); the commonly
cited figure is ~2,500 calls a month. That pays for ~59 full fetches a month,
so two a day (~2,520) is the ceiling. This matters more than it looks: Adzuna
supplies ~98% of published posts, and `fetch.py` logs a warning and continues
when a call fails — so exceeding the quota would not crash the run, it would
quietly publish a near-empty page. Going more frequent needs either a paid plan
or a thinner fetch that accumulates across runs instead of replacing.

Secrets are only ever read from environment variables — GitHub Actions secrets
in CI, a gitignored `.env` locally. No key is in the repository.

---

## 10. AI tools used

Declared in full, since the brief allows any AI tool but asks that the thinking
be mine.

| tool | what it was used for |
|---|---|
| **Google Gemini** (`gemini-3.5-flash-lite`) | the product itself — tagging role, city and `is_fresher` |
| **Claude Code** (Anthropic) | pair-programming the implementation: writing modules, tests and docs, probing the four APIs for their real response shapes, and debugging |

Decisions I made and had to defend: which sources to use and why no scraping,
the three-layer dedup design and its thresholds, running keyword rules before
the LLM to control cost, constraining the model with an enum schema and
validating anyway, caching on a content hash that includes the prompt version,
and choosing a static fallback so the published site cannot be taken down by a
sleeping backend.

Everything that broke, and how it was fixed, is logged as it happened in
[docs/build_log.md](build_log.md) — 11 phases, including the mistakes that were
mine rather than the model's.

---

## 11. Screenshots to insert

> Replace each line with the image.

1. **The live site** — search box, role/city filters with counts, job cards.
2. **A filtered search** — e.g. `Software Engineering` + `Bengaluru`, showing
   the result count and facet counts updating.
3. **The job detail panel** — full description and the apply link.
4. **Google Sign-In** — the login screen, and the signed-in header.
5. **`/docs`** — the interactive API documentation on Render.
6. **GitHub Actions** — a green "refresh job data" run.
7. **Terminal: `python -m pytest -q`** — 104 passed.
8. **Terminal: `python scripts/cost_report.py ...`** — the cost per 1,000 posts.
9. **Terminal: `python scripts/score_eval.py data/eval_sample.csv`** — the
   accuracy output, once the 50 posts are labelled.

---

## 12. What I would do next

1. **Fix source concentration.** Find Indian companies using Greenhouse, Lever
   and Ashby. This is research, not code, and it is the single biggest quality
   win available.
2. **Use the accuracy result.** The hand-check tells you whether the remaining
   errors are prompt problems, taxonomy gaps, or genuinely ambiguous postings.
   The last `Multiple` investigation turned out to be a config gap, not a model
   failure — the next one may too.
3. **Salary and experience extraction.** The descriptions contain both; neither
   is currently parsed.
4. **Deduplicate across companies.** The same staffing agency posts the same
   role under several client names; layer 3 only compares within one company.
