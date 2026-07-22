import json
from datetime import date
import json
import os
from typing import Literal

import requests
from flask import flash

from models import Transmission, Case
from utils.logging import log_entry_and_flash, flash_msg
import logging


def send(payload: dict, endpoint: Literal["TEST","PROD"], case: Case):
    from app import db
    mv64_endpoint = os.environ.get(f"BFARM_ENDPOINT_{endpoint}")
    mv64_endpoint_api_key = os.environ.get(f"BFARM_API_KEY_{endpoint}",)
    try:
        headers = {
            "Authorization": f"X-API-KEY {mv64_endpoint_api_key}",
            "Content-Type": "application/json",
        }

        # Proxy eintragen
        proxies = {
            "http": os.environ.get("PROXY",""),
            "https": os.environ.get("PROXY",""),
        }
        # flash_msg(case.case_id, case.pat_id, 'info', str(payload))
        response = requests.post(mv64_endpoint, headers=headers, json=payload, proxies=proxies, timeout=30)
        status_code = response.status_code
        response_json = response.json() if response.text else {}

        # save transmission
        trans = Transmission(case_id=case.case_id, request=payload, response=response_json)
        db.session.add(trans)
        ok = status_code in (200, 202)
        is_prod = endpoint == "PROD"
        success_flag = response_json.get("success")
        target_name = "BfArM" if is_prod else "Testknoten"


        if not ok:
            msg = f"Fall {case.case_id}: Übermittlung an {target_name} fehlgeschlagen (Status {status_code}).\n{response_json}"
            log_entry_and_flash(case.case_id, case.pat_id, "error", msg, True)
        elif ok and not success_flag:
            msg = f"Fall {case.case_id}: Übermittlung an {target_name} erfolgreich (Status {status_code})."
            msg += f"\nNachricht konnte NICHT verarbeitet werden:\n{response_json}"
            log_entry_and_flash(case.case_id, case.pat_id, "error", msg, True)
        elif ok and success_flag:
            msg = f"Case {case.case_id}: Erfolgreich an {target_name} übermittelt.\n{response_json}"
            log_entry_and_flash(case.case_id, case.pat_id, "success", msg, True)
            if is_prod:
                case.transmitted = True
                db.session.add(case)
                db.session.commit()

    except Exception as e:
        log_entry_and_flash(case.case_id, case.pat_id, "error", f"Fall {case.case_id}: Konnte nicht an das BfArM übermittelt werden: {e}", True)
        response_json = {}

    return response_json

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
            "birthDate": str(case["birth_date"])[:7],
            "addressAGS": case["address_ags"],
            "decisionToInclude": case["decision_to_include"],
            "MolecularBoardDecisionDate": str(case["molecular_board_decision_date"]),
            "localCaseId":case["local_case_id"]
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

