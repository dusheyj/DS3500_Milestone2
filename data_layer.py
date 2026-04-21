"""
data layer for the dashboard.

this is the DATA LAYER part of the dashboard 3-layer architecture (data /
viz / app). all the logic for loading, filtering, and providing dropdown
options lives here. no charts, no widgets - just pandas.
"""

import pandas as pd


# file path as a global so i only change it in one place if anything moves
CSV_PATH = "data/processed/pharma_master.csv"

# column name constants. same reason - one place to change if a column gets renamed
NCT_COL = "nct_id"
SPONSOR_COL = "sponsor_raw"
SPONSOR_KEY_COL = "sponsor_key"
SPONSOR_TYPE_COL = "sponsor_type"
DRUG_COL = "drug_raw"
PHASE_COL = "phase"
STATUS_COL = "status"
CONDITION_COL = "condition"
START_DATE_COL = "start_date"
COMPLETION_DATE_COL = "completion_date"


def load_data(path):
    """read the csv into a dataframe"""
    df = pd.read_csv(path, parse_dates=[START_DATE_COL, COMPLETION_DATE_COL])
    # annoying pandas thing - it reads the literal string "NA" as NaN by
    # default. in my data "NA" is an actual phase category (trials that
    # never declared a phase) so i have to put it back or 24 trials silently
    # fall off the phase chart. took me a while to figure out this was
    # even happening
    df[PHASE_COL] = df[PHASE_COL].fillna("NA")
    return df


def clean_data(df):
    """light cleanup on the loaded df. the heavy cleaning already happened
    in clean.py - this just trims whitespace"""
    out = df.copy()
    for col in (SPONSOR_TYPE_COL, PHASE_COL, STATUS_COL):
        out[col] = out[col].astype(str).str.strip()
    return out


def get_sponsor_types(df):
    """dropdown options for sponsor type, with 'All' first as the default"""
    vals = sorted(df[SPONSOR_TYPE_COL].dropna().unique().tolist())
    return ["All"] + vals


def get_phases(df):
    """dropdown options for phase"""
    # hardcode the order so it reads early->late instead of alphabetical
    phase_order = ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"]
    present = df[PHASE_COL].dropna().unique().tolist()
    ordered = [p for p in phase_order if p in present]
    return ["All"] + ordered


def get_statuses(df):
    """dropdown options for status"""
    vals = sorted(df[STATUS_COL].dropna().unique().tolist())
    return ["All"] + vals


def filter_data(df, start_date=None, end_date=None, sponsor_type="All", phase="All", status="All"):
    """apply the sidebar filters. 'All' means no filter on that field."""
    out = df.copy()

    # date range
    if start_date is not None:
        out = out[out[START_DATE_COL] >= pd.to_datetime(start_date)]
    if end_date is not None:
        out = out[out[START_DATE_COL] <= pd.to_datetime(end_date)]

    # categorical filters - skip if 'All' is selected
    if sponsor_type and sponsor_type != "All":
        out = out[out[SPONSOR_TYPE_COL] == sponsor_type]
    if phase and phase != "All":
        out = out[out[PHASE_COL] == phase]
    if status and status != "All":
        out = out[out[STATUS_COL] == status]

    return out.reset_index(drop=True)


if __name__ == "__main__":
    # smoke test
    df = load_data(CSV_PATH)
    df = clean_data(df)
    print("rows:", len(df))
    print("sponsor types:", get_sponsor_types(df))
    print("phases:", get_phases(df))
    print("statuses:", get_statuses(df))
    print()
    print("filter test (Public pharma, PHASE3):")
    filt = filter_data(df, sponsor_type="Public pharma", phase="PHASE3")
    print(f"  {len(filt)} rows")
