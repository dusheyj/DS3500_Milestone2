# test_pipeline.py
# tests for fetch, clean, and combine. nothing hits the real network,
# i mock all the http stuff with MagicMock

import sys
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

import fetch
import clean
import combine


# ---- fixtures ----

@pytest.fixture
def sample_studies():
    # 4 fake trials: normal, name variant, duplicate, bad date
    return [
        {"protocolSection": {
            "identificationModule": {"nctId": "NCT00000001"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Pfizer Inc."}},
            "designModule": {"phases": ["PHASE2"]},
            "statusModule": {
                "overallStatus": "COMPLETED",
                "startDateStruct": {"date": "2020-01-15"},
                "completionDateStruct": {"date": "2022-06-01"},
            },
            "conditionsModule": {"conditions": ["Lung Cancer"]},
            "armsInterventionsModule": {"interventions": [
                {"type": "DRUG", "name": "Palbociclib Hydrochloride"},
            ]},
        }},
        {"protocolSection": {
            "identificationModule": {"nctId": "NCT00000002"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "PFIZER INC"}},
            "designModule": {"phases": ["PHASE3"]},
            "statusModule": {
                "overallStatus": "RECRUITING",
                "startDateStruct": {"date": "2023-03-01"},
                "completionDateStruct": {"date": "2025-12-31"},
            },
            "conditionsModule": {"conditions": ["Breast Cancer"]},
            "armsInterventionsModule": {"interventions": [
                {"type": "DRUG", "name": "Palbociclib"},
            ]},
        }},
        # this one is a duplicate of NCT00000001 on purpose
        {"protocolSection": {
            "identificationModule": {"nctId": "NCT00000001"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Pfizer Inc."}},
            "designModule": {"phases": ["PHASE2"]},
            "statusModule": {
                "overallStatus": "COMPLETED",
                "startDateStruct": {"date": "2020-01-15"},
                "completionDateStruct": {"date": "2022-06-01"},
            },
            "conditionsModule": {"conditions": ["Lung Cancer"]},
            "armsInterventionsModule": {"interventions": [
                {"type": "DRUG", "name": "Palbociclib Hydrochloride"},
            ]},
        }},
        # completion is before start — obviously wrong data
        {"protocolSection": {
            "identificationModule": {"nctId": "NCT00000003"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Memorial Sloan Kettering Cancer Center"}},
            "designModule": {"phases": ["PHASE1"]},
            "statusModule": {
                "overallStatus": "ACTIVE_NOT_RECRUITING",
                "startDateStruct": {"date": "2022-10-01"},
                "completionDateStruct": {"date": "2021-01-01"},
            },
            "conditionsModule": {"conditions": ["Melanoma"]},
            "armsInterventionsModule": {"interventions": [
                {"type": "DRUG", "name": "Pembrolizumab"},
            ]},
        }},
    ]


@pytest.fixture
def sample_pharma():
    # small pharma lookup for testing the join
    return pd.DataFrame({
        "sponsor_key": ["PFIZER", "MERCK SHARP DOHME"],
        "ticker": ["PFE", "MRK"],
    })


@pytest.fixture
def sample_openfda_records():
    # fake openfda results
    return [
        {"query_name": "Palbociclib Hydrochloride", "generic_name": "palbociclib",
         "brand_name": "IBRANCE", "manufacturer_name": "Pfizer", "route": "ORAL",
         "product_type": "HUMAN PRESCRIPTION DRUG"},
        {"query_name": "Pembrolizumab", "generic_name": "pembrolizumab",
         "brand_name": "KEYTRUDA", "manufacturer_name": "Merck",
         "route": "INTRAVENOUS", "product_type": "HUMAN PRESCRIPTION DRUG"},
    ]


# ---- fetch tests ----

@patch('fetch.requests.get')
def test_fetch_pagination(mock_get):
    # two pages, second has no nextPageToken so it stops
    page1 = MagicMock()
    page1.status_code = 200
    page1.json.return_value = {
        "studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT1"}}}],
        "nextPageToken": "tok2",
    }

    page2 = MagicMock()
    page2.status_code = 200
    page2.json.return_value = {
        "studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT2"}}}],
    }

    mock_get.side_effect = [page1, page2]

    studies = fetch.fetch_clinical_trials(max_studies=10)

    assert len(studies) == 2
    nct_ids = [s["protocolSection"]["identificationModule"]["nctId"] for s in studies]
    assert nct_ids == ["NCT1", "NCT2"]
    assert mock_get.call_count == 2


@patch('fetch.sleep')  # so the test doesn't actually wait
@patch('fetch.requests.get')
def test_fetch_retries_after_error(mock_get, mock_sleep):
    # first call 503, second call works
    bad = MagicMock()
    bad.status_code = 503

    good = MagicMock()
    good.status_code = 200
    good.json.return_value = {"studies": [], "nextPageToken": None}

    mock_get.side_effect = [bad, good]

    studies = fetch.fetch_clinical_trials(max_studies=10)

    assert studies == []
    assert mock_get.call_count == 2


@patch('fetch.sleep')
@patch('fetch.requests.get')
def test_openfda_retry_on_429(mock_get, mock_sleep):
    # 429 = rate limited, should retry and then get the real data
    rate_limited = MagicMock()
    rate_limited.status_code = 429

    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {
        "results": [{"openfda": {"generic_name": ["pembro"], "brand_name": ["KEY"]}}],
    }

    mock_get.side_effect = [rate_limited, ok]

    recs = fetch.fetch_openfda(["Pembrolizumab"])

    assert len(recs) == 1
    assert recs[0]["generic_name"] == "pembro"


# ---- clean tests ----

def test_no_duplicate_trials(sample_studies):
    # NCT00000001 is in there twice, should only show up once after cleaning
    df = clean.clean_trials(sample_studies)
    assert df.duplicated(subset=["nct_id", "drug_key"]).sum() == 0
    assert (df["nct_id"] == "NCT00000001").sum() == 1


def test_sponsor_name_cleanup(sample_studies):
    # "Pfizer Inc." and "PFIZER INC" should both become "PFIZER"
    # this is the whole reason normalize_sponsor exists
    df = clean.clean_trials(sample_studies)
    pfizer_keys = df.loc[
        df["sponsor_raw"].str.contains("Pfizer", case=False, na=False),
        "sponsor_key"  # not sponsor_raw — that tripped me up at first
    ].unique()
    assert len(pfizer_keys) == 1
    assert pfizer_keys[0] == "PFIZER"


def test_bad_date_gets_nulled(sample_studies):
    # NCT00000003 has completion before start, should null completion but keep row
    df = clean.clean_trials(sample_studies)
    nct3 = df[df["nct_id"] == "NCT00000003"].iloc[0]
    assert pd.isna(nct3["completion_date"])
    assert not pd.isna(nct3["start_date"])


def test_pharma_name_cleanup():
    # xlsx names need the same normalization as sponsor names or the join breaks
    raw = pd.DataFrame({
        "company_name": ["Pfizer Inc.", "MERCK SHARP & DOHME LLC"],
        "ticker": ["PFE", "MRK"],
    })
    cleaned = clean.clean_pharma_companies(raw)
    assert set(cleaned["sponsor_key"]) == {"PFIZER", "MERCK SHARP DOHME"}
    assert set(cleaned["ticker"]) == {"PFE", "MRK"}


def test_sponsor_buckets():
    # three buckets: public pharma, academic/medical/govt, other
    assert clean.classify_sponsor("PFIZER", True) == "Public pharma"
    assert clean.classify_sponsor("MEMORIAL SLOAN KETTERING CANCER CENTER", False) == "Academic / medical / govt"
    assert clean.classify_sponsor("NATIONAL CANCER INSTITUTE NCI", False) == "Academic / medical / govt"
    assert clean.classify_sponsor("SOME BIOTECH CO", False) == "Other (biotech, private, etc.)"


def test_empty_sponsor_gets_dropped():
    # if a trial has no sponsor name, normalize_sponsor returns None
    # and clean_trials drops that row (can't join on nothing)
    assert clean.normalize_sponsor(None) is None
    assert clean.normalize_sponsor("") is None
    assert clean.normalize_sponsor("   ") is None

    studies = [{"protocolSection": {
        "identificationModule": {"nctId": "NCT99999"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": ""}},
        "designModule": {"phases": ["PHASE1"]},
        "statusModule": {"overallStatus": "RECRUITING",
                         "startDateStruct": {"date": "2023-01-01"}},
        "conditionsModule": {"conditions": ["Leukemia"]},
        "armsInterventionsModule": {"interventions": [
            {"type": "DRUG", "name": "SomeDrug"},
        ]},
    }}]
    df = clean.clean_trials(studies)
    # row should be gone because sponsor_key is null
    assert len(df) == 0


def test_trial_with_no_drugs():
    # some trials have no DRUG interventions (device-only, etc.)
    # clean_trials should still produce a row with drug_raw = None
    studies = [{"protocolSection": {
        "identificationModule": {"nctId": "NCT88888"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Mayo Clinic"}},
        "designModule": {"phases": ["PHASE2"]},
        "statusModule": {"overallStatus": "COMPLETED",
                         "startDateStruct": {"date": "2021-06-01"},
                         "completionDateStruct": {"date": "2023-06-01"}},
        "conditionsModule": {"conditions": ["Lymphoma"]},
        "armsInterventionsModule": {"interventions": []},
    }}]
    df = clean.clean_trials(studies)
    assert len(df) == 1
    assert pd.isna(df.iloc[0]["drug_raw"])


def test_drug_normalization_strips_salt():
    # "Palbociclib Hydrochloride" and "Palbociclib" should become the same key
    # this is what makes the openfda join actually work
    key1 = clean.normalize_drug("Palbociclib Hydrochloride")
    key2 = clean.normalize_drug("Palbociclib")
    assert key1 == key2


# ---- merge tests ----

def test_left_join_keeps_all_rows(sample_studies, sample_pharma, sample_openfda_records):
    # the whole point of left join is we don't lose trials just because
    # the sponsor isn't in the pharma xlsx
    trials = clean.clean_trials(sample_studies)
    fda = clean.clean_openfda(sample_openfda_records)
    master = combine.build_master(trials, sample_pharma, fda)
    assert len(master) == len(trials)


def test_pfizer_is_public_pharma(sample_studies, sample_pharma, sample_openfda_records):
    # pfizer should get tagged as public pharma, MSK should be academic
    trials = clean.clean_trials(sample_studies)
    fda = clean.clean_openfda(sample_openfda_records)
    master = combine.build_master(trials, sample_pharma, fda)

    pfizer_rows = master[master["sponsor_key"] == "PFIZER"]
    assert pfizer_rows["is_public_pharma"].all()
    assert (pfizer_rows["sponsor_type"] == "Public pharma").all()

    mskcc = master[master["sponsor_key"].str.contains("SLOAN KETTERING", na=False)]
    assert not mskcc["is_public_pharma"].any()
    assert (mskcc["sponsor_type"] == "Academic / medical / govt").all()


def test_validation_passes(sample_studies, sample_pharma, sample_openfda_records):
    # should not raise on clean data
    trials = clean.clean_trials(sample_studies)
    fda = clean.clean_openfda(sample_openfda_records)
    master = combine.build_master(trials, sample_pharma, fda)
    combine.validate_master(master)


def test_validation_catches_missing_col(sample_studies, sample_pharma, sample_openfda_records):
    # drop a required column, validation should catch it
    trials = clean.clean_trials(sample_studies)
    fda = clean.clean_openfda(sample_openfda_records)
    master = combine.build_master(trials, sample_pharma, fda)
    broken = master.drop(columns=["sponsor_type"])
    with pytest.raises(ValueError):
        combine.validate_master(broken)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
