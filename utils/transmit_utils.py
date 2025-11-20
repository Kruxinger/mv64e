import json
from datetime import date

def build_oncology_payload(case, consts):
    """
    Erzeugt das JSON, das an das BfArM (mv64_endpoint) geschickt wird.
    """
    j = {
        "metaData": {
            "submission": {
                "date": str(date.today()),
                "type": consts["submission_type"],
                "submitterId": consts["submission_submitterId"],
                "genomicDataCenterId": consts["submission_genomicDataCenterId"],
                "clinicalDataNodeId": consts["submission_clinicalDataNodeId"],
                "diseaseType": consts["submission_diseaseType"]
            },
            "mvConsent": case["mv_consent"],
            "coverageType": case["coverage_type"],
            "tanC": case["tan_c"],
            "gender": case["gender"],
            "birthDate": str(case["birth_date"]),
            "addressAGS": case["address_ags"],
            "decisionToInclude": case["decision_to_include"],
            "MolecularBoardDecisionDate": str(case["molecular_board_decision_date"])
        },
        "case": {
            "diagnosisOD": {
                "mainDiagnosis": {
                    "date": str(case["main_diagnosis_date"]),
                    "code": case["main_diagnosis_code"],
                    "system": consts["mainDiagnosis_system"],
                    "version": consts["mainDiagnosis_version"]
                },
                "ecogPerformanceStatusScore": str(case["ecog"]),
                "germlineDiagnosisConfirmed": case["germline_confirmed"],
                "histology": {
                    "code": case["histology_code"],
                    "system": consts["histology_system"],
                    "version": consts["histology_version"]
                },
                "topography": {
                    "code": case["topography_code"],
                    "system": consts["topography_system"],
                    "version": consts["topography_version"]
                },
                "libraryType": case["library_type"]
            }
        }
    }
    if case["research_consent"] != None and case["research_consent"] != []:
        j["metaData"]["researchConsents"] = case["research_consent"]
    return j

