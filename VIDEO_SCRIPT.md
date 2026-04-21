# Video Script — 10-Minute Screencast

## Before You Hit Record

1. Open VS Code with the project folder
2. Set font size to 16-18pt (Cmd+= a few times) so code is readable in the recording
3. Hide these files from the explorer (files.exclude in VS Code settings): VIDEO_SCRIPT.md, Dockerfile, docker-compose.yml, .dockerignore
4. Open these tabs in order: fetch.py, clean.py, combine.py, data_layer.py, viz_layer.py, dashboard.py, test_pipeline.py
5. Have a terminal panel open at the bottom (Ctrl+`)
6. Dashboard is NOT running yet
7. Browser ready but minimized
8. Record with Zoom (Share Screen > record), Loom, or OBS
9. Practice once. Time yourself.

---

## SEGMENT 1: Architecture Overview (0:00 – 2:00)

> Rubric: "Data flow from sources → cleaning → storage → dashboard" — 2 minutes

---

### 0:00 – 0:40 — The pipeline

[File explorer sidebar visible]

"This project is a data pipeline for oncology clinical trials and it goes through three stages."

[Click `fetch.py` tab]

"fetch.py is the first step. It pulls raw data from three different sources and saves everything into data/raw."

[Click `clean.py` tab]

"Then clean.py normalizes names, removes duplicates, and fixes bad dates. It writes clean parquet files to data/interim."

[Click `combine.py` tab]

"And then combine.py joins the three cleaned sources into one master CSV in data/processed. That CSV is what the dashboard reads from."

[Expand `data/` folder in sidebar to show `raw/`, `interim/`, `processed/`]

---

### 0:40 – 1:15 — The three data sources

[`fetch.py` visible, scrolled so lines 27, 94, 157 are showing]

"So the three sources are ClinicalTrials.gov, OpenFDA, and a hand-curated Excel file. fetch_clinical_trials on line 27 paginates through the ClinicalTrials.gov API and pulls 500 oncology drug trials. fetch_openfda on line 94 queries the FDA drug label API for metadata on each unique drug. And load_pharma_companies on line 157 reads an Excel file I put together with 26 public pharma companies that I use as a lookup for classifying sponsors."

---

### 1:15 – 2:00 — The dashboard layers

[Click `data_layer.py`, scrolled to `filter_data` on line 70]

"For the dashboard I used the three-layer pattern from class. data_layer.py loads the CSV and has one filter function that all the chart callbacks share."

[Click `viz_layer.py`, scrolled to show the four function names on lines 11, 31, 47, 68]

"viz_layer.py has four chart builder functions. Each one takes a dataframe and a column name and returns a Plotly figure. There's no filtering logic in here, it just builds charts."

[Click `dashboard.py`, scrolled to `pn.bind` calls on lines 143-148]

"And dashboard.py is the app layer. It sets up the Panel widgets in the sidebar and uses pn.bind to connect them to the chart callbacks. So whenever you change a filter, pn.bind reruns the callback and the chart updates. The nice thing about splitting it this way is I can add a new chart without touching the filter logic, or add a new filter without rewriting any of the charts."

---

## SEGMENT 2: Key Implementation Decisions (2:00 – 5:00)

> Rubric: "How you handled data quality issues, merge strategy and why, challenges and solutions" — 3 minutes

---

### 2:00 – 2:50 — Data quality: sponsor name normalization

[`clean.py` visible, lines 21-36 showing]

"The biggest data quality problem was sponsor names. ClinicalTrials.gov gives you things like 'Pfizer Inc.', 'PFIZER INC', and 'Pfizer, Inc.' Those are all the same company but they're different strings, so they won't match when you try to join."

[Point at line 21]

"normalize_sponsor on line 21 fixes that. The regex on line 31 strips out corporate suffixes like Inc, LLC, and Corp. Then line 34 removes punctuation and line 35 uppercases everything. So all three Pfizer variants just become the string 'PFIZER.'"

[Point at lines 31, 34, 35, then scroll to `clean_pharma_companies` on line 155]

"And both sides of the join go through this same function. Line 160 normalizes the company names from the Excel file the same way. Same function on both sides so the keys actually match when combine.py does the join."

---

### 2:50 – 3:30 — Merge strategy: why left joins

[`combine.py` visible, lines 17-44 showing]

"combine.py does two left joins. Line 30 joins trials to the pharma lookup on sponsor_key, and line 33 joins that result to OpenFDA on drug_key. I used left joins because only about 4 percent of the 500 trials have a big pharma lead sponsor. The other 96 percent are academic cancer centers and government labs that aren't in my 26-company Excel file. An inner join would have dropped all of those."

[Point at `how="left"` on lines 30 and 33]

"After the joins, line 36 creates is_public_pharma which is true wherever the sponsor matched my pharma list. And lines 40 and 41 classify each sponsor into three buckets: Public pharma, Academic or medical or government, and Other. That classification is what drives the headline chart in the dashboard."

---

### 3:30 – 4:00 — Key finding and caveat

[`clean.py` visible, scrolled to `ACADEMIC_KEYWORDS` on line 55 and `classify_sponsor` on line 62]

"What surprised me is that academic centers and the NCI run way more oncology trials than any single pharma company. NCI alone had 33 out of the 500. But there is a caveat worth mentioning. The sponsor field in ClinicalTrials.gov is whoever operationally ran the trial, not necessarily who funded it. A lot of the time academic centers are running trials that pharma companies are paying for. That funding info lives in the collaborators field which I'm not pulling yet, and that would be the first thing I would want to add."

---

### 4:00 – 4:25 — Challenge: API reliability

[`fetch.py` visible, scrolled to the retry loop on lines 51-76]

"One challenge I ran into was API reliability. ClinicalTrials.gov sometimes throws 503 errors and OpenFDA rate limits you with 429s. So I set up exponential backoff where line 51 starts the wait at 2 seconds and line 59 doubles it each retry, up to 5 attempts. If all 5 fail, line 79 stops pagination gracefully so I keep whatever data I already collected."

[Point at `wait = 2` on line 51, `for i in range(5)` on line 53]

---

### 4:25 – 5:00 — Other data quality fixes

[`clean.py` visible, scrolled to lines 128-137]

"Two more data quality things. Line 131 deduplicates on nct_id and drug_key together, not just nct_id, because a trial testing three drugs has three legitimate rows and I don't want to collapse those. And line 136 handles bad dates where the completion date is before the start date. Instead of throwing the row away I just null out the completion and keep the start date since it's still useful for the time series."

[Point at `drop_duplicates` on line 131, then the `bad` mask on line 136]

---

## SEGMENT 3: Testing Approach (5:00 – 7:00)

> Rubric: "Show test suite, explain key tests (briefly)" — 2 minutes

---

### 5:00 – 5:25 — Run the tests

[In terminal, run `python test_pipeline.py`. Wait for output showing 15 passed.]

"I have 15 tests covering fetch, clean, and combine. None of them hit the real network. I use MagicMock to fake the HTTP responses so the tests run in under a second and don't depend on the APIs being up. Let me walk through a few of the important ones."

---

### 5:25 – 5:55 — test_sponsor_name_cleanup (line 181)

[Scroll to `test_sponsor_name_cleanup` on line 181]

"This one tests the normalization I just talked about. My fixture data has 'Pfizer Inc.' and 'PFIZER INC' as two different strings. After cleaning, both should map to one key which is just 'PFIZER.' If normalization broke, they'd stay as two separate keys and the join would silently miss matches."

---

### 5:55 – 6:20 — test_left_join_keeps_all_rows (line 271)

[Scroll to `test_left_join_keeps_all_rows` on line 271, point at `assert len(master) == len(trials)` on line 277]

"This one guards the merge strategy. It runs build_master and checks that the output has the same number of rows as the input. If I ever accidentally changed a left join to an inner join, the Memorial Sloan Kettering trial would get dropped because it's not in my pharma list, and this test would catch it."

---

### 6:20 – 6:40 — test_empty_sponsor_gets_dropped (line 220)

[Scroll to `test_empty_sponsor_gets_dropped` on line 220]

"This one is an edge case. What happens if a trial has a blank sponsor name? The test checks that normalize_sponsor returns None for None, empty string, and whitespace. Then it builds a fake trial with an empty sponsor and makes sure it actually gets dropped from the output. You can't join on nothing, so the pipeline needs to handle that instead of blowing up."

---

### 6:40 – 7:00 — Remaining tests

"The rest of the tests cover pagination, retry logic for 503s and 429s, drug name normalization, bad date correction, sponsor classification, and validation for missing columns. All 15 passing."

---

## SEGMENT 4: Dashboard Design (7:00 – 10:00)

> Rubric: "Demo interactivity, explain visualization choices" — 3 minutes

---

### 7:00 – 7:10 — Start the dashboard

[In terminal, run `python dashboard.py`. Wait for browser to open. Switch to browser.]

---

### 7:10 – 7:35 — Tab 1: Sponsor Type (donut chart)

[Sponsor Type tab showing, donut chart with three slices]

"This is the headline chart showing who is actually running oncology trials. I used a donut chart because it's really about proportions of a whole. You can see academic and medical centers are the biggest slice and pharma is actually pretty small."

---

### 7:35 – 7:50 — Tab 2: Top Sponsors (horizontal bar)

[Click "Top sponsors" tab]

"Top 10 sponsors by trial count. I used horizontal bars here so the long sponsor names like 'Memorial Sloan Kettering Cancer Center' are actually readable. Those would get cut off on vertical bars."

---

### 7:50 – 8:15 — Tabs 3 through 6

[Click "By phase" tab, pause 3 seconds]

"Phase distribution shows most trials are Phase 1 and 2."

[Click "By status" tab, pause 3 seconds]

"Status uses color coding with green for completed and red for terminated or withdrawn so the failure states jump out."

[Click "Over time" tab, pause 2 seconds. Click "Trial table" tab, pause 2 seconds.]

"Then we have trials over time and the raw data table."

---

### 8:15 – 9:30 — Demonstrate interactivity

[Click back to "Sponsor type" tab]

"All six tabs share the same sidebar filters. Let me show how that works."

[Change "Sponsor type" dropdown to "Public pharma", wait for update]

"Now I've filtered to just public pharma."

[Click "Top sponsors" tab]

"And you can see the top sponsors are all pharma company names now instead of academic centers."

[Click "By status" tab]

"And here you can see how many of those pharma trials completed versus got terminated. That ratio tells you a lot about pipeline health."

[Change "Phase" dropdown to "PHASE3"]

"Now I've also filtered to Phase 3, so we're looking at just the late-stage pharma trials. Much smaller subset since most drugs don't make it this far."

[Reset "Phase" to "All" and "Sponsor type" to "All". Set start date to 2025+ so nothing matches.]

"And if the filters return no data, every tab handles it gracefully with a message instead of crashing."

[Reset all filters]

---

### 9:30 – 10:00 — Wrap up

"So to wrap up, three data sources go into a fetch, clean, and combine pipeline that produces one master CSV. Name normalization makes the joins work, left joins keep every trial in the dataset, and the dashboard uses the three-layer pattern with pn.bind for reactivity. 15 tests all passing. Thanks for watching."

---

## Grading Checklist

### Clarity of explanation (2 points)
- [ ] Technical terms explained on first use (left join, exponential backoff, MagicMock, pn.bind)
- [ ] "Say then show" — narrate what's on screen

### Technical depth and understanding (3 points)
- [ ] WHY left join not inner (96% would be dropped)
- [ ] WHY dedupe on (nct_id, drug_key) pair (multi-drug trials)
- [ ] WHY both sides of the join use the same normalize function
- [ ] Flagged the sponsor vs funder caveat (collaborators field)

### Presentation quality (2 points)
- [ ] Font readable in recording (16-18pt)
- [ ] Code visible when referenced
- [ ] Dashboard demo shows real filter interactions
- [ ] Video is ~10 minutes

### Team explains technical decisions coherently (2 points)
- [ ] Each decision explained with a reason, not just described
- [ ] Retry logic rationale (APIs are flaky)
- [ ] Chart type choices explained (donut for proportions, horizontal bar for long names, color coding for status)

### All members demonstrate understanding of the project (1 point)
- [ ] Touched every file in the project
- [ ] Referenced cross-file connections (normalize_sponsor used by both clean.py and combine.py's join)

---

## If You Run Long

Cut first:
1. Drop the Phase 3 filter combo (save ~20 sec)
2. Skip per-tab narration on tabs 3 through 6, just click through silently (save ~15 sec)

Do NOT cut:
- Left join explanation
- Sponsor normalization
- Running tests and showing 15 passed

## If You Run Short

Add:
1. Open data_layer.py line 36 and explain the pandas "NA" gotcha where the string "NA" was read as NaN
2. Add one more filter combo in the dashboard demo, like filtering by status "TERMINATED"
