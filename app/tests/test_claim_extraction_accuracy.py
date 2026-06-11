from app.intake.form_classifier import detect_document_type
from app.intake.form_normalizer import fix_split_dates, normalize_fields
from app.intake.service_extractor import extract_services_from_tables
from app.services.field_normalizer import _apply_field_map
from app.utils.confidence import claim_confidence_status


def test_detect_document_type_indicators():
    assert detect_document_type("HEALTH INSURANCE CLAIM FORM NUCC") == "CMS1500"
    assert detect_document_type("UB-04 TYPE OF BILL") == "UB04"
    assert detect_document_type("plain clinical note") == "GENERIC"


def test_normalize_fields_maps_synonyms_and_split_dates():
    normalized = normalize_fields({
        "Patient": "Jane Doe",
        "Birth": "08 09 59",
        "Policy": "POL123",
        "Provider Name": "Clinic A",
        "Payer": "Aetna",
    })

    assert normalized["patient.name"] == "Jane Doe"
    assert normalized["patient.dob"] == "08/09/1959"
    assert normalized["insurance.member_id"] == "POL123"
    assert normalized["provider.name"] == "Clinic A"
    assert normalized["insurance.payer"] == "Aetna"
    assert fix_split_dates("08/09/1959") == "08/09/1959"

    nested = _apply_field_map({"Patient": "Jane Doe", "Policy ID": "POL123"})
    assert nested["patient"]["name"] == "Jane Doe"
    assert nested["insurance"]["member_id"] == "POL123"


def test_extract_services_from_ub04_tables_filters_bad_rows():
    tables = [{
        "rows": [
            ["REV", "Description", "CPT", "Date", "Units", "Charge"],
            ["0300", "Lab panel", "80053", "01 02 26", "1", "$120.00"],
            ["0300", "Lab panel", "80053", "01 02 26", "1", "$120.00"],
            ["", "", "", "", "", ""],
            ["bad", "missing columns"],
            ["0450", "ER visit", "99284", "01/03/2026", "2", "350.50"],
        ],
    }]

    services = extract_services_from_tables(tables)

    assert services == [
        {
            "description": "Lab panel",
            "cpt": "80053",
            "cpt_code": "80053",
            "date": "01/02/2026",
            "date_of_service": "01/02/2026",
            "units": 1,
            "charge": 120.0,
            "source": "textract_table",
        },
        {
            "description": "ER visit",
            "cpt": "99284",
            "cpt_code": "99284",
            "date": "01/03/2026",
            "date_of_service": "01/03/2026",
            "units": 2,
            "charge": 350.5,
            "source": "textract_table",
        },
    ]


def test_claim_confidence_status_thresholds():
    assert claim_confidence_status(0.95) == "AUTO_APPROVED"
    assert claim_confidence_status(75) == "VALIDATION_REQUIRED"
    assert claim_confidence_status(0.6) == "HUMAN_REVIEW_REQUIRED"
