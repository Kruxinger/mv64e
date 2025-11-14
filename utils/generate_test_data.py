
from models import Case, Transmission, Constant
from datetime import datetime, date


# --- helper: ensure constants exist ------------------------------------------------

DEFAULT_CONSTANTS = {
    "submission_type": "initial",
    "submission_submitterId": "999950000",
    "submission_genomicDataCenterId": "GRZHD0003",
    "submission_clinicalDataNodeId": "KDKHD0006",
    "submission_diseaseType": "oncological",
    "mainDiagnosis_system": "ICD-10-GM",
    "mainDiagnosis_version": "icd10.gm-2019-10-04",
    "histology_system": "ICD-O-3-M",
    "histology_version": "icdo3morph.rev1de",
    "topography_system": "ICD-O-3-T",
    "topography_version": "icdo3topo.rev1de",
}


def ensure_constants():
    from app import db
    created = 0
    for k, v in DEFAULT_CONSTANTS.items():
        if Constant.query.filter_by(key=k).first() is None:
            db.session.add(Constant(key=k, value=v))
            created += 1
    if created:
        db.session.commit()
    print(f"[OK] Constants checked. Newly created: {created}")


# --- helper: consent builders ------------------------------------------------------

def build_mv_consent(presentation_date: date):
    return {
        "presentationDate": presentation_date.isoformat(),
        "version": "v1",
        "scope": [
            {"type": "permit", "date": presentation_date.isoformat(), "domain": "mvSequencing"},
            {"type": "permit", "date": presentation_date.isoformat(), "domain": "reIdentification"},
            {"type": "permit", "date": presentation_date.isoformat(), "domain": "caseIdentification"},
        ],
    }


# --- create case with all required fields -----------------------------------------

def create_case(
    case_id,
    pat_id,
    finalized=False,
    transmitted=False,
    gender="male",
):
    from app import db

    const = {c.key: c.value for c in Constant.query.all()}

    c = Case(
        case_id=case_id,
        pat_id=pat_id,
        gender=gender,
        birth_date=date(1970, 5, 20),
        address_ags="08215000",
        decision_to_include=True,
        molecular_board_decision_date=date(2024, 11, 10),
        rejection_justification="otherReason",
        main_diagnosis_date=date(2024, 11, 15),
        main_diagnosis_code="C34.1",
        ecog="1",
        coverage_type="GKV",
        germline_confirmed=False,
        histology_code="8140/3",
        topography_code="C34",
        library_type="wes",

        submission_type=const["submission_type"],
        submission_submitter_id=const["submission_submitterId"],
        submission_genomic_data_center_id=const["submission_genomicDataCenterId"],
        submission_clinical_data_node_id=const["submission_clinicalDataNodeId"],
        submission_disease_type=const["submission_diseaseType"],
        main_diagnosis_system=const["mainDiagnosis_system"],
        main_diagnosis_version=const["mainDiagnosis_version"],
        histology_system=const["histology_system"],
        histology_version=const["histology_version"],
        topography_system=const["topography_system"],
        topography_version=const["topography_version"],

        mv_consent=build_mv_consent(date(2024, 11, 7)),
        research_consent={"status": "pending"},

        is_finalized=finalized,
        transmitted=transmitted,
    )

    db.session.add(c)
    db.session.commit()

    if transmitted:
        t = Transmission(
            case_id=case_id,
            request={"dummy": "request_payload"},
            response={"status": "OK", "timestamp": datetime.utcnow().isoformat()},
        )
        db.session.add(t)
        db.session.commit()

    print(f"[OK] Created Case {case_id} — finalized={finalized}, transmitted={transmitted}")


# --- main -------------------------------------------------------------------------

def generate_test_data():

    print("[INFO] Preparing test data…")
    ensure_constants()

    # 1 transmitted + finalized
    create_case("TST-001", "PAT-001", finalized=True, transmitted=True)

    # 2 finalized
    create_case("TST-002", "PAT-002", finalized=True)
    create_case("TST-003", "PAT-003", finalized=True)

    # 2 nicht finalized
    create_case("TST-004", "PAT-004", finalized=False)
    create_case("TST-005", "PAT-005", finalized=False)

    print("\n[DONE] 5 Test Cases erzeugt.\n")
