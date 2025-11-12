import json
from datetime import date

def build_oncology_payload(case, consts):
    """
    Erzeugt das JSON, das an das BfArM (mv64_endpoint) geschickt wird.
    """
    return {
        "Oncology": {
            "metaData": {
                "submission": {
                    "submissionDate": str(date.today()),
                    "type": consts["submission.type"],
                    "submitterId": consts["submission.submitterId"],
                    "genomicDataCenterId": consts["submission.genomicDataCenterId"],
                    "clinicalDataNodeId": consts["submission.clinicalDataNodeId"],
                    "diseaseType": consts["submission.diseaseType"]
                },
                "mvConsent": json.loads(case["mvConsent"]),
                "researchConsents": [json.loads(case["researchConsent"])] if case["researchConsent"] else [],
                "coverageType": case["coverageType"],
                "tanC": case["tanC"],
                "gender": case["gender"],
                "birthDate": str(case["birthDate"]),
                "addressAGS": case["addressAGS"],
                "decsisionToInclude": case["decsisionToInclude"],
                "molecularBoardDescisionDate": str(case["molecularBoardDescisionDate"])
            },
            "case": {
                "diagnosisOD": {
                    "mainDiagnosis": {
                        "date": str(case["mainDiagnosis_date"]),
                        "code": case["mainDiagnosis_code"],
                        "system": consts["mainDiagnosis.system"],
                        "version": consts["mainDiagnosis.version"]
                    },
                    "ecogPerformanceStatusScore": str(case["ecog"]),
                    "germlineDiagnosisConfirmed": case["germlineConfirmed"],
                    "histology": {
                        "code": case["histology_code"],
                        "system": consts["histology.system"],
                        "version": consts["histology.version"]
                    },
                    "topography": {
                        "code": case["topography_code"],
                        "system": consts["topography.system"],
                        "version": consts["topography.version"]
                    },
                    "libraryType": case["libraryType"]
                }
            }
        }
    }
