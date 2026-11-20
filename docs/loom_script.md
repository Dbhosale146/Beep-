# Loom script — 5 minutes, face + screen

Not a script to read out. Beats to hit, with the numbers already checked so you
are not recalling them live. Rehearse once, then record in one take; a small
stumble reads as human, a monotone read-aloud does not.

**Have open before you start:** the live site, the repo, `/docs` on Render, a
terminal in `backend/`, and `docs/build_log.md`.

---

## 0:00 — 0:25 · What it is

Face on camera. No screen share yet.

> "I built a tool that collects fresher and internship postings in India from
> four public job-board APIs, removes duplicates, tags each one by role and city
> with Gemini, and publishes them to a page that refreshes itself every morning
> twice a day, 7am and 7pm IST. 562 postings live right now, de-duplicated
> from 6,600+ raw."

## 0:25 — 1:15 · Show it working

Share screen. The site.

- Search something real — `intern pune`.
- Change the role filter. Point out **the counts next to each option come from
  the data, not a hardcoded list** — and that picking a city does not empty the
  city menu.
- Open a job card → detail panel → the apply link goes to the original posting.
- Say the URL is shareable: the filters are in the query string.

## 1:15 — 2:15 · The architecture, in one pass

Say it as a funnel, not a diagram tour:

> "Fetch from four APIs — Greenhouse, Lever, Ashby, Adzuna. Official endpoints
> only, no scraping. 6,623 postings in. Normalise to one schema and filter to
> India: 2,520. Keyword rules for fresher roles: 1,075 — **and that happens
> before the LLM on purpose, so I never pay to tag a senior role.** Then three
> layers of de-duplication, 503 removed. Only then does Gemini see anything:
> 572 posts, tagged for role and city."

Worth landing: **the taxonomy goes into the request as a JSON schema with an
enum, so an off-taxonomy answer is impossible, not just unlikely — and I
validate the response in Python anyway.** Nothing is ever guessed; a post that
fails twice is published as `Untagged`.

## 2:15 — 3:15 · What broke

This is the section they actually asked for. Pick **two**, tell them properly.

**Recommended pair:**

1. **My keyword filter matched "Senior Internal Auditor" as an internship** —
   `intern` is a substring of `Internal`. Caught only because I printed the
   matched titles instead of trusting the count. Every pattern is word-bounded
   now, with a regression test named after the bug.

2. **170 posts tagged "Multiple" for city — and the model was right.** My
   taxonomy was missing most of India: Surat, Rajkot, Lucknow, Patna, Ranchi.
   Added 33 tier-2 cities and `Multiple` dropped to 39; coverage went 23 → 40
   cities. Adzuna also returns country-only locations like "India", which is not
   "Multiple" — that needed a new `Pan India` value and a prompt rule, which is
   why there is a `tag_v2`.

> The point to make out loud: **both were my bugs, not the model's.** That reads
> far better than "the LLM hallucinated".

If you have a spare 15s, the honest one: *"I'd have written the Gemini call
wrong from memory — the current SDK uses an Interactions API, not
`generate_content`. I checked the docs instead of trusting myself."*

## 3:15 — 4:00 · The two numbers

Terminal, live:

```
python scripts/cost_report.py --input-price 0.30 --output-price 2.50
python scripts/score_eval.py data/eval_sample.csv
```

> "**$0.158 per 1,000 posts.** Measured, not estimated — every call logs its
> tokens. Prices are arguments to the script, not constants, so the number is
> always computed from prices I checked today. And it bills thinking tokens as
> output, because Gemini charges them at the output rate."

Then accuracy, from your hand-check of the 50 posts.

> "A content-hash cache means a run only pays for postings it has not seen.
> Second run: 571 of 572 from cache, **cost zero**, 310 seconds down to 21."

## 4:00 — 4:35 · It runs itself

- GitHub Actions tab → the refresh workflow, 07:00 and 19:00 IST.
- Say the failure rule plainly: **if the pipeline fails, the site still
  redeploys with yesterday's data so the page never goes blank — and the job is
  then marked failed so the failure is visible.**
- 104 tests, none touching the network. Run `pytest -q` if there is time.

## 4:35 — 5:00 · Close, honestly

Face on camera. Name the weakness before they find it:

> "The real weakness is source concentration — 557 of 565 postings come from
> Adzuna. Greenhouse gave me 4,656 raw postings and only 3 survived, because
> most of those boards are US companies. That is not a code problem, it is a
> research problem: finding Indian companies that use these boards. It's the
> first thing I'd fix."

---

## Worth remembering

- **Say the numbers.** 6,623 → 565. 503 duplicates. $0.158. 104 tests. Specific
  numbers are the difference between "I built a scraper" and "I measured this".
- **Own the mistakes.** The two best stories are both bugs you wrote.
- **Don't read the architecture off a diagram.** Say the funnel.
- Screen share at 0:25, not 0:00 — let them see you first.
- If you overrun, cut the architecture section, not the "what broke" section.
