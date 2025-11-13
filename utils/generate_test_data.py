import json
import random
from datetime import date, datetime, timedelta
from psycopg2.extras import Json

def generate_dummy_data():
    from app import get_conn
    conn = get_conn()
    cur = conn.cursor()

    # ---- Services ----
    services = ["keycloak", "DIZ", "gPAS"]
    now = datetime.now()
    for service in services:
        # zwei Datenpunkte pro Service: vor 2 Wochen und gestern
        for delta_days in [14, 1]:
            timestamp = now - timedelta(days=delta_days)
            status = random.choice([True, True, True, False])  # 75% up
            cur.execute("""
                INSERT INTO service_status (service_name, status, last_checked)
                VALUES (%s, %s, %s)
            """, (service, status, timestamp))

    # ---- Cases ----
    total_cases = 24
    transmitted_ids = random.sample(range(1, total_cases + 1), 8)  # 11 transmitted
    finalized_ids = random.sample([i for i in range(1, total_cases + 1) if i not in transmitted_ids], 4)  # 12 finalized

    for i in range(1, total_cases + 1):
        case_id = f"DUMMY{i:03d}"
        pat_id = f"P{i:03d}"
        is_transmitted = i in transmitted_ids
        is_finalized = i in transmitted_ids or i in finalized_ids
        insert_dummy_case(cur, case_id, pat_id, transmitted=is_transmitted, is_finalized=is_finalized)

        # ---- Transmissions ----
        if is_transmitted:
            cur.execute("""
                INSERT INTO transmissions (case_id, request, response)
                VALUES (%s, %s, %s)
            """, (
                case_id,
                Json({"dummy_request": True}),
                Json({"dummy_response": True})
            ))

        # ---- Logs ----
        for _ in range(random.randint(1, 3)):
            log_type = random.choice(["info", "error"])
            log_text = f"Dummy log entry for {case_id}"
            cur.execute("""
                INSERT INTO logs (pat_id, case_id, type, text)
                VALUES (%s, %s, %s, %s)
            """, (pat_id, case_id, log_type, log_text))

    conn.commit()
    cur.close()
    conn.close()
    print("Dummy data generated successfully.")


def insert_dummy_case(cur, case_id, pat_id, transmitted=False, is_finalized=False):
    import json
    from app import get_constants
    consts = get_constants()

    # Dummy mvConsent ähnlich wie in add_case
    mvConsent_json = {
        "presentationDate": "2025-01-01",
        "version": consts.get('mvConsent.version', "1.0"),
        "scope": [
            {"type": "permit", "date": "2025-01-01", "domain": "mvSequencing"},
            {"type": "permit", "date": "2025-01-01", "domain": "reIdentification"},
            {"type": "permit", "date": "2025-01-01", "domain": "caseIdentification"},
        ]
    }

    cur.execute("""
        INSERT INTO cases
        (case_id, pat_id, gender, birthDate, addressAGS, decisionToInclude,
         molecularBoardDescisionDate, rejectionJustification,
         mainDiagnosis_date, mainDiagnosis_code, ecog, germlineConfirmed,
         histology_code, topography_code, libraryType,
         submission_type, submission_submitterId, submission_genomicDataCenterId,
         submission_clinicalDataNodeId, submission_diseaseType,
         mvConsent_version,
         mainDiagnosis_system, mainDiagnosis_version,
         histology_system, histology_version,
         topography_system, topography_version,
         mvConsent, researchConsent, coverageType, is_finalized)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        case_id, pat_id, "unknown", "1970-01-01", "00000", True,
        "2025-01-01", "otherReason",
        "2025-01-01", "C00", "unknown", False,
        "H00", "T00", "none",
        consts['submission.type'], consts['submission.submitterId'], consts['submission.genomicDataCenterId'],
        consts['submission.clinicalDataNodeId'], consts['submission.diseaseType'],
        consts['mvConsent.version'],
        consts['mainDiagnosis.system'], consts['mainDiagnosis.version'],
        consts['histology.system'], consts['histology.version'],
        consts['topography.system'], consts['topography.version'],
        json.dumps(mvConsent_json), None, "UNK", is_finalized
    ))

