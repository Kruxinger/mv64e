import json
from datetime import date
import json
import os
from typing import Literal

import requests
from flask import flash

from models import Transmission, Case
from utils.logging import log_entry
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

        # Flash-Kategorie abhängig vom success-Flag
        if success_flag is False:
            flash_category = "warning"  # Gelb
        elif ok:
            flash_category = "success"  # Grün
        else:
            flash_category = "danger"  # Rot

        # Logging-Text
        if ok:
            msg = f"Case {case.case_id}: Erfolgreich an {target_name} übermittelt."
            if is_prod:
                case.transmitted = True
                db.session.add(case)
        else:
            msg = f"Case {case.case_id}: Übermittlung an {target_name} fehlgeschlagen (Status {status_code})."

        # Log schreiben
        log_entry(case.case_id, case.pat_id,
                  "info" if ok else "error",
                  msg)

        # Flash ausgeben – immer mit response_json
        flash(f"{msg}\n{response_json}", flash_category)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        log_entry(case.case_id, case.pat_id, "error", f"Case {case.case_id}: Konnte nicht an das BfArM übermittelt werden: {e}")
        flash(f"Fehler beim Senden von Case {case.case_id}: {e}", "danger")
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

