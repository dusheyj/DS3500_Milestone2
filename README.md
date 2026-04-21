# DS3500 Milestone 2

Jack Dushey

Pipeline that pulls oncology clinical trial data from ClinicalTrials.gov, enriches it with drug metadata from OpenFDA, tags sponsors as public pharma using a local xlsx file, and produces a cleaned dataset plus a set of charts showing what the oncology trial landscape actually looks like.

## Why this matters

ClinicalTrials.gov has 400,000+ trials behind a clunky search interface that's great for "show me this one trial" but useless for landscape questions. My pipeline turns the messy API into one clean, queryable table so you can ask bigger questions. A few examples of who would actually use this:

A cancer researcher deciding whether to write a grant. Before starting a new trial they want to know if 15 other groups are already testing the same drug, or whether a drug keeps dying in Phase 2 (warning sign), or whether nobody has tried it for pancreatic cancer (real gap).

An investor picking pharma stocks. A company with 12 active oncology trials advancing through phases is a healthy pipeline. A company with 4 trials and 3 terminations in Phase 2 is a collapsing one. My dataset lets you slice by sponsor and count completed vs terminated trials to spot the difference.

Someone running competitive intelligence at a pharma company. They want to know what Merck is testing, what nobody is testing, and which small biotechs are struggling (potential acquisitions). Grouping trials by sponsor and disease tells you all of that.

Basically: the raw database answers one-trial-at-a-time questions, my dataset answers landscape questions.

## What I actually found

The thing that surprised me most when I looked at the cleaned data: **academic cancer centers and the NCI run way more oncology trials than any single pharma company in my sample.** NCI alone sponsored 33 of the 500 trials. MD Anderson had 17. Memorial Sloan Kettering had 9. The biggest pharma name in the top 10 is Novartis, tied at 6. Only about 4% of the trials in the sample have a public pharma company as the lead sponsor - the other 96% are academic, government, or small private biotechs.

But here's the important caveat, and it's what I'd fix first if I had more time. The "sponsor" field from ClinicalTrials.gov is whoever *operationally* ran the trial, not whoever *paid for it*. Academic cancer centers don't fund most of their own trials: the money comes from NIH grants or from pharma companies paying them to run trials on pharma-owned drugs. ClinicalTrials.gov has a `collaborators` field that often lists the real funders, and my current pipeline only pulls `leadSponsor`. Adding `collaborators` to `fetch.py` would turn "who operationally ran the trial" into "who actually paid for it," which is the more useful question for every audience above.

## Data sources

- **ClinicalTrials.gov API v2** - paginated via nextPageToken. Source of every trial record (nct_id, sponsor, drug, phase, status, condition, dates).
- **OpenFDA drug label API** - rate limited, handles 429 with Retry-After. Source of drug metadata (generic/brand name, manufacturer, route, product type).
- **pharma_companies.xlsx** - a local Excel file I put together with a list of 26 public pharma companies and their tickers. I use it as a lookup to tag which sponsors in the trial data are public pharma companies vs academic/government/other. (The file has extra columns I ignore - I originally started with R&D spending numbers but the story ended up being about the trial landscape, not finance.)

## Dashboard (for the Wednesday presentation)

The dashboard is a Panel app that reads the cleaned CSV and lets you explore the trial landscape interactively. It follows the 3-layer template we use in class — `data_layer.py` for loading and filtering, `viz_layer.py` for plotly chart builders, and `dashboard.py` for the UI wiring with `pn.bind`.

```
pip install -r requirements.txt
python dashboard.py
```

It opens automatically in your default browser. Filters in the sidebar (date range, sponsor type, phase, status) update every tab live.

## How to run

```
pip install -r requirements.txt
python fetch.py
python clean.py
python combine.py
python preview.py
pytest -q
```

Final dataset ends up at `data/processed/pharma_master.csv`. `preview.py` prints a few summary tables and drops PNG charts plus a summary.txt into `figures/` so you can see what the pipeline produced without running the code yourself.

## What the charts show

The four charts in `figures/` are built around one question: **"What does the oncology clinical trial landscape actually look like?"**

1. **01_sponsor_type_split.png** - pie chart of "who's actually running oncology trials?" split into three buckets: academic/medical/govt, other (biotech/private), and public pharma. The story: big pharma is a tiny slice, academic centers dominate.
2. **02_top_sponsors.png** - top 10 sponsors by unique trial count, with public pharma bars colored differently. The story: NCI and academic cancer centers show up at the top, not big pharma.
3. **03_trials_by_phase.png** - bar chart of how many trials are in each phase. The story: most trials live in Phase 1 and Phase 2, late-stage trials are rarer and more expensive.
4. **04_trials_by_status.png** - bar chart of trials by current status (completed, recruiting, terminated, etc.) with terminated/withdrawn in red. The story: most trials complete, but a real chunk fail - that's the "failure" bucket worth studying.

## Cleaning notes

- Sponsor names are all over the place ("Pfizer Inc.", "PFIZER INC", "Pfizer, Inc") so I strip corporate suffixes and punctuation and uppercase everything to get a clean join key.
- Drug names get the same treatment. Strip stuff like "hydrochloride" and "monoclonal antibody" and lowercase so "Palbociclib Hydrochloride" matches "Palbociclib".
- A trial can have multiple drugs so I explode to one row per (trial, drug).
- If completion_date is before start_date it's obviously garbage, so I null out completion and keep the row.
- ClinicalTrials sometimes returns the same study twice during pagination. I dedupe on (nct_id, drug_key) after cleaning.
- The pharma xlsx gets turned into a simple (sponsor_key, ticker) lookup table.
- Sponsors are classified into three buckets with a keyword match: "Public pharma" (in the xlsx), "Academic / medical / govt" (name contains university / hospital / cancer center / NCI / etc.), or "Other".

## Merging

Two left joins:

1. trials left join pharma_companies on sponsor_key - attaches a ticker if the sponsor is a public pharma company in my xlsx
2. then left join openfda on drug_key - drug metadata

Left joins so I never lose a trial row just because one source is missing a match.

## Known issues

- **I only pull leadSponsor from ClinicalTrials, not collaborators.** That means "sponsor" in my data is whoever ran the trial, not whoever paid for it. Academic cancer centers usually run trials funded by pharma contracts or NIH grants, and that funding information lives in the `collaborators` field I'm not currently fetching. This is the single most impactful fix for next steps.
- My public-pharma list (xlsx file) only covers 26 of the biggest public pharma companies. So "sponsor_type = Public pharma" is a conservative bucket - there are definitely small public biotechs in the "Other" bucket that I just don't have in my list. Fix: expand the xlsx to a few hundred companies.
- Lots of investigational/early-stage drugs aren't in OpenFDA, so drug metadata columns are null for a good chunk of rows.

## Tests

12 tests in `test_pipeline.py` covering:

- **Fetching** - clinicaltrials pagination, 5xx retry, openfda 429 rate limit
- **Cleaning** - duplicate removal, sponsor/drug name normalization, bad date handling, pharma company name normalization, sponsor classification
- **Merging** - row preservation on left joins, correct tagging of public pharma vs academic sponsors
- **Validation** - passes on clean data, rejects missing required columns

No tests hit the real network: I use `requests_mock` for HTTP and hand-built fixtures for everything else.
