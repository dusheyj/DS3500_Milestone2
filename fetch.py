# fetch.py
# step 1 - pulls data from clinicaltrials.gov + openfda + the xlsx and dumps
# everything into data/raw/ so clean.py can read it
#
# 3 sources: two apis and one local file i maintain by hand

import json
import os
import re
from time import sleep

import pandas as pd
import requests


DATA_RAW = "data/raw"
os.makedirs(DATA_RAW, exist_ok=True)

CT_URL = "https://clinicaltrials.gov/api/v2/studies"
FDA_URL = "https://api.fda.gov/drug/label.json"

CONDITION = "cancer"
MAX_STUDIES = 500
PAGE_SIZE = 100


def fetch_clinical_trials(condition=CONDITION, max_studies=MAX_STUDIES):
    """grabs oncology drug trials from clinicaltrials.gov, paginates until done"""

    # note to self: i only pull leadSponsor here. there's also a collaborators
    # field that lists actual funders which would be way more useful but i
    # didn't have time. that's my #1 thing to fix next time

    studies = []
    page_token = None

    base_params = {
        "query.cond": condition,
        "filter.advanced": "AREA[StudyType]INTERVENTIONAL AND AREA[InterventionType]DRUG",
        "pageSize": PAGE_SIZE,
        "format": "json",
    }

    while True:
        params = dict(base_params)
        if page_token:
            params["pageToken"] = page_token

        # retry loop. if the api is flaky i wait + try again. doubling the
        # wait each time so i don't hammer the server
        wait = 2
        data = None
        for i in range(5):
            try:
                response = requests.get(CT_URL, params=params)
            except requests.exceptions.ConnectionError:
                print("Connection issue, retrying...")
                sleep(wait)
                wait = wait * 2
                continue

            if response.status_code == 200:
                data = response.json()
                break
            elif response.status_code == 429:
                # rate limited, chill out
                print("Rate limited, waiting...")
                sleep(wait)
                wait = wait * 2
                continue
            else:
                print(f"Status code {response.status_code}, retrying...")
                sleep(wait)
                wait = wait * 2
                continue

        if data is None:
            # 5 tries failed, give up on pagination instead of crashing
            print("Failed after retries, stopping pagination")
            break

        studies.extend(data.get("studies", []))
        page_token = data.get("nextPageToken")
        if not page_token or len(studies) >= max_studies:
            break

    studies = studies[:max_studies]
    with open(f"{DATA_RAW}/clinicaltrials.json", "w") as f:
        json.dump(studies, f)
    print(f"got {len(studies)} studies from clinicaltrials.gov")
    return studies


def fetch_openfda(drug_names):
    """look up each drug in openfda to get metadata like generic/brand name"""

    # ok so the first time i ran this it crashed on a drug name with a comma
    # openfda's search parser apparently hates punctuation. this regex strips
    # anything that's not a letter/number/space/dash
    safe = re.compile(r"[^A-Za-z0-9 \-]")
    records = []

    for name in drug_names:
        q = safe.sub(" ", str(name)).strip()
        if not q:
            continue
        params = {
            "search": f'openfda.generic_name:"{q}" OR openfda.brand_name:"{q}"',
            "limit": 1,
        }

        # same retry thing as above
        wait = 2
        data = None
        for i in range(5):
            try:
                response = requests.get(FDA_URL, params=params)
            except requests.exceptions.ConnectionError:
                sleep(wait)
                wait = wait * 2
                continue

            if response.status_code == 200:
                data = response.json()
                break
            elif response.status_code == 429:
                sleep(wait)
                wait = wait * 2
                continue
            else:
                # 400/404 = no record for this drug, just skip it. lots of
                # investigational drugs just aren't in openfda
                break

        if not data or not data.get("results"):
            continue

        rec = data["results"][0]
        of = rec.get("openfda", {})
        # every openfda field is a list for some reason even when there's
        # only one value, so i grab [0]
        records.append({
            "query_name": name,
            "generic_name": (of.get("generic_name") or [None])[0],
            "brand_name": (of.get("brand_name") or [None])[0],
            "manufacturer_name": (of.get("manufacturer_name") or [None])[0],
            "route": (of.get("route") or [None])[0],
            "product_type": (of.get("product_type") or [None])[0],
        })

    with open(f"{DATA_RAW}/openfda.json", "w") as f:
        json.dump(records, f)
    print(f"got {len(records)} matched drugs from openfda")
    return records


def load_pharma_companies(path="pharma_companies.xlsx"):
    """reads my local xlsx file with the 26 public pharma companies"""
    # i made this file by hand. it has company name + ticker and used to
    # have r&d spending columns too but i ended up not using those
    df = pd.read_excel(path)
    df = df[["company_name", "ticker"]].dropna(subset=["company_name"])
    df.to_parquet(f"{DATA_RAW}/pharma_companies.parquet", index=False)
    print(f"loaded {len(df)} public pharma companies from {path}")
    return df


if __name__ == "__main__":
    studies = fetch_clinical_trials()

    # pull unique drug names out so i can hit openfda once per drug.
    # using a set to dedupe - lots of trials test the same drug
    drug_names = set()
    for s in studies:
        ivs = s.get("protocolSection", {}).get("armsInterventionsModule", {}).get("interventions", [])
        for iv in ivs:
            if iv.get("type") == "DRUG" and iv.get("name"):
                drug_names.add(iv["name"])
    fetch_openfda(sorted(drug_names))

    load_pharma_companies()

    print("done. raw files are in data/raw/")
