# clean.py - step 2. cleans the raw files and writes tidy parquet to data/interim/
# the main thing this file does is sponsor/drug name normalization so the
# joins in combine.py actually work

import json
import os
import re

import pandas as pd


DATA_RAW = "data/raw"
DATA_INTERIM = "data/interim"
os.makedirs(DATA_INTERIM, exist_ok=True)

# only the phase values i'm allowing in the output. anything else gets
# turned into "NA"
ALLOWED_PHASES = {"EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"}


def normalize_sponsor(name):
    """pfizer inc. -> PFIZER so joins work"""

    if name is None or (isinstance(name, float) and pd.isna(name)):
        return None

    # i kept adding to this regex as i found new sponsor variants that
    # weren't matching my xlsx. started with just inc and llc, ended up
    # here. AG, GmbH, SE are european company suffixes that kept showing up.
    suffixes = r",?\s*(inc\.?|incorporated|ltd\.?|limited|llc|l\.l\.c\.|corp\.?|corporation|co\.?|plc|gmbh|ag|se)\b"
    s = str(name).strip()
    s = re.sub(suffixes, "", s, flags=re.IGNORECASE)
    # then strip remaining punctuation + collapse whitespace + uppercase
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s or None


def normalize_drug(name):
    """same idea as normalize_sponsor but for drugs"""
    # palbociclib hydrochloride and palbociclib should match, so strip the
    # salt/formulation tails
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return None
    tails = r"\b(hydrochloride|hcl|sulfate|phosphate|sodium|mesylate|tartrate|maleate|citrate|acetate|monoclonal antibody|injection|tablet|capsule)\b"
    s = str(name).strip().lower()
    s = re.sub(tails, "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^\w\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


# keywords for bucketing sponsors. if a sponsor name contains any of these
# and it wasn't already tagged as public pharma, it's academic/medical/govt.
ACADEMIC_KEYWORDS = (
    "UNIVERSITY", "HOSPITAL", "CANCER CENTER", "INSTITUTE", "MEDICAL CENTER",
    "SCHOOL OF MEDICINE", "CLINIC", "HEALTH", "FOUNDATION", "NATIONAL CANCER",
    "NCI", "CANCER INSTITUTE", "CANCER RESEARCH",
)


def classify_sponsor(sponsor_key, is_public_pharma):
    """put each sponsor into one of 3 buckets"""
    # i need 3 buckets because that's what my headline chart is about -
    # who actually runs oncology trials
    if is_public_pharma:
        return "Public pharma"
    if not sponsor_key:
        return "Other"
    if any(kw in sponsor_key for kw in ACADEMIC_KEYWORDS):
        return "Academic / medical / govt"
    return "Other (biotech, private, etc.)"


def clean_trials(raw_studies):
    """takes the raw clinicaltrials json list and returns a clean dataframe
    with one row per (trial, drug) pair"""

    rows = []
    for s in raw_studies:
        # clinicaltrials api responses are deeply nested. i just reach in
        # and grab the fields i care about
        proto = s.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status = proto.get("statusModule", {})
        sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
        design = proto.get("designModule", {})
        ivs = proto.get("armsInterventionsModule", {}).get("interventions", [])
        conditions = proto.get("conditionsModule", {}).get("conditions", [])

        # filter to DRUG-type interventions only. ignore placebo arms and
        # device arms - not what the assignment is about
        drug_names = [iv.get("name") for iv in ivs if iv.get("type") == "DRUG" and iv.get("name")]
        phases = design.get("phases") or ["NA"]

        # one row per drug. some trials test 3 or 4 drugs at once - this
        # is why the final csv has 1044 rows for 500 unique trials
        for drug in drug_names or [None]:
            rows.append({
                "nct_id": ident.get("nctId"),
                "sponsor_raw": (sponsor_mod.get("leadSponsor") or {}).get("name"),
                "drug_raw": drug,
                "phase": phases[0],
                "status": status.get("overallStatus"),
                "condition": "; ".join(conditions) if conditions else None,
                "start_date": pd.to_datetime((status.get("startDateStruct") or {}).get("date"), errors="coerce"),
                "completion_date": pd.to_datetime((status.get("completionDateStruct") or {}).get("date"), errors="coerce"),
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # make the normalized keys that combine.py joins on
    df["sponsor_key"] = df["sponsor_raw"].map(normalize_sponsor)
    df["drug_key"] = df["drug_raw"].map(normalize_drug)

    # phase cleanup. some trials have weird phase strings, whitelist anything
    # that's not in ALLOWED_PHASES and force it to NA
    df["phase"] = df["phase"].fillna("NA").str.upper().str.replace(" ", "_")
    df.loc[~df["phase"].isin(ALLOWED_PHASES), "phase"] = "NA"
    df["status"] = df["status"].fillna("UNKNOWN").str.upper()

    # drop rows that are missing the stuff i need. a trial with no id or
    # no sponsor is useless
    df = df.dropna(subset=["nct_id", "sponsor_key"])

    # dedupe. clinicaltrials api returns the same study twice sometimes,
    # idk why. i dedupe on (nct_id, drug_key) not just nct_id because i
    # don't want to collapse legit multi-drug trials
    df = df.drop_duplicates(subset=["nct_id", "drug_key"]).reset_index(drop=True)

    # found some rows where completion_date is before start_date which
    # obviously isn't real. i null out the completion instead of dropping
    # the whole row - start date is still useful
    bad = df["completion_date"].notna() & df["start_date"].notna() & (df["completion_date"] < df["start_date"])
    df.loc[bad, "completion_date"] = pd.NaT

    return df


def clean_openfda(records):
    df = pd.DataFrame(list(records))
    if df.empty:
        # return empty frame with the right columns so downstream merges
        # don't crash
        return pd.DataFrame(columns=["drug_key", "generic_name", "brand_name", "manufacturer_name", "route", "product_type"])
    df["drug_key"] = df["query_name"].map(normalize_drug)
    # dedupe on drug_key because i might have queried the same drug under
    # slightly different spellings
    df = df.drop_duplicates(subset=["drug_key"]).reset_index(drop=True)
    return df[["drug_key", "generic_name", "brand_name", "manufacturer_name", "route", "product_type"]]


def clean_pharma_companies(df):
    """turns my xlsx into a (sponsor_key, ticker) lookup"""
    # gotta normalize the company names the same way i normalize trial
    # sponsors, otherwise the keys won't match in combine.py
    df = df.copy()
    df["sponsor_key"] = df["company_name"].map(normalize_sponsor)
    df = df.dropna(subset=["sponsor_key"]).drop_duplicates(subset=["sponsor_key"])
    return df[["sponsor_key", "ticker"]].reset_index(drop=True)


if __name__ == "__main__":
    with open(f"{DATA_RAW}/clinicaltrials.json") as f:
        raw_trials = json.load(f)
    trials = clean_trials(raw_trials)
    trials.to_parquet(f"{DATA_INTERIM}/trials.parquet", index=False)
    print(f"trials: {len(trials)} rows")

    with open(f"{DATA_RAW}/openfda.json") as f:
        raw_fda = json.load(f)
    fda = clean_openfda(raw_fda)
    fda.to_parquet(f"{DATA_INTERIM}/openfda.parquet", index=False)
    print(f"openfda: {len(fda)} rows")

    raw_pharma = pd.read_parquet(f"{DATA_RAW}/pharma_companies.parquet")
    pharma = clean_pharma_companies(raw_pharma)
    pharma.to_parquet(f"{DATA_INTERIM}/pharma_companies.parquet", index=False)
    print(f"pharma_companies: {len(pharma)} rows")

    print("done. interim files are in data/interim/")
