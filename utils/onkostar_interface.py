import datetime
import logging
import os
import re

from flask import flash
from utils.logging import log_entry
from sqlalchemy import create_engine, text, Engine
from models import Case, Constant


class OnkostarInterface:

    def __init__(self):
        from app import get_constants
        self.personenstamm = get_constants()['onkostar_personenstamm']
        self.new_case = Case()
        self.os_pat_id: str = ""
        self.procedure_id: str = ""
        self.engine = self._create_engine()


    def _create_engine(self) -> Engine:
        os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
        host = os.environ.get("ONKOSTAR_DB_HOST")
        port = os.environ.get("ONKOSTAR_DB_PORT")
        name = os.environ.get("ONKOSTAR_DB_NAME")
        user = os.environ.get("ONKOSTAR_DB_USER")
        password = os.environ.get("ONKOSTAR_DB_PASSWORD")

        engine_string = f"mariadb://{user}:{password}@{host}:{port}/{name}"
        return create_engine(engine_string)

    def get_query_res_as_dict(self, query: str):
        with self.engine.begin() as conn:
            result = conn.execute(text(query))
            return [row for row in result.mappings()]

    def get_anamnese_procedures(self):
        return self.get_query_res_as_dict(
            f"SELECT id, beginndatum FROM prozedur WHERE patient_id={self.os_pat_id} AND html_schnipsel_detailiert "
            f"LIKE '%DNPM Klinik/Anamnese%' AND geloescht=0")

    def get_case_automized(self,pat_id: str, personenstamm: str):
        """
        Generiert einen Fall vollständig automatisiert. Ist sehr restriktiv!
        :param pat_id:
        :param personenstamm:
        :return:
        """
        if len(self.get_query_res_as_dict(f"SELECT * FROM personenstamm WHERE name='{personenstamm}'")) == 0:
            return False, f"Personenstamm '{personenstamm}' nicht gefunden!"
        res = self.get_query_res_as_dict(f"SELECT * FROM patient WHERE patienten_id='{pat_id}'")
        if len(res) > 1:
            return False, f"Es wurden mehrere Patienten mit Pat ID {pat_id} im Personenstamm {personenstamm} gefunden"
        if len(res) == 0:
            return False, f"Es wurde kein Patient mit Pat ID {pat_id} im Personenstamm {personenstamm} gefunden"

        self.personenstamm = personenstamm
        self.get_pat_data(pat_id)
        res = self.get_anamnese_procedures()
        if len(res) > 1:
            return False, f"Es wurden mehrere Prozeduren 'DNPM Klinik/Anamnese' (mit validem Datum) zum Patienten {pat_id} gefunden"
        if len(res) == 0:
            return False, f"Es wurden keine Prozeduren 'DNPM Klinik/Anamnese' (mit validem Datum) zum Patienten {pat_id} gefunden"

        self.get_dnpm_kpa_data()
        required = [
            self.new_case.main_diagnosis_date,
            self.new_case.main_diagnosis_code,
            self.new_case.case_id,
            self.new_case.histology_code,
            self.new_case.topography_code
        ]
        if not all(v not in (None, "") for v in required):
            return False, (f"Es konnten nicht alle notwendigen Werte aus dk_dnpm_kpa geladen werden (datumerstdiagnose, "
                           f"icd10, fallnummermv, artderkrankenkasse, icdo3histologie, icdo3lokalisation)")
        if not re.fullmatch("^(?:\d{8,9}|00\d{8,9})$", self.new_case.case_id):
            return False, f"Fallnummer entspricht nicht dem vorgegebenen Format. Found: {self.new_case.case_id}"
        self.get_mv_consent()
        if "presentationDate" not in self.new_case.mv_consent:
            return False, f"MV Consent konnte nicht geladen werden"
        if not self.get_ecog():
            return False, "ECOG konnte nicht ermittelt werden"
        self.get_decision_data()
        if not self.get_library_type():
            return False, "Library Type konnte nicht identifiziert werden!"
        return True, self.new_case

    def get_pat_data(self, pat_id_lmu: str) -> bool:
        res = self.get_query_res_as_dict(
            f"SELECT patient.id, geschlecht, geburtsdatum, GKZ, krankenkassennummer FROM patient JOIN personenstamm ON "
            f"patient.personenstamm=personenstamm.id WHERE patient.patienten_id={pat_id_lmu} "
            f"AND personenstamm.name='{self.personenstamm}'")
        if len(res) == 1:
            res = res[0]
            self.new_case.gender = "unknown"
            match res["geschlecht"]:
                case "m":
                    self.new_case.gender = "male"
                case "w":
                    self.new_case.gender = "female"
                case "d":
                    self.new_case.gender = "divers"
            self.new_case.pat_id = pat_id_lmu

            if res['krankenkassennummer'].startswith("10"):
                self.new_case.coverage_type = 'GKV'
            elif res['krankenkassennummer'].startswith("16"):
                self.new_case.coverage_type = 'PKV'

            self.new_case.birth_date = res['geburtsdatum']

            self.new_case.address_ags = res['GKZ'][:5] if len(res['GKZ']) >= 5 else ""
            self.os_pat_id = res['id']
            return True

        if len(res) == 0:
            self.log_and_flash(f"Es wurde kein Patient mit der id {pat_id_lmu} im Personenstamm '{self.personenstamm}' gefunden", "error")
            return False

        if len(res) > 0:
            self.log_and_flash(f"Es wurden mehr als ein kein Patient mit der id {pat_id_lmu} im Personenstamm '{self.personenstamm}' gefunden", "error")
            return False

    def get_dnpm_kpa_data(self):
        res = self.get_query_res_as_dict(
            f"SELECT anmeldedatummtb, datumerstdiagnose, icd10, icdo3histologie, icdo3lokalisation, mtb, "
            f"artderkrankenkasse, consentmv64e, fallnummermv FROM dk_dnpm_kpa WHERE id={self.procedure_id}")
        if len(res) == 1:
            res = res[0]
            self.new_case.main_diagnosis_date = res["datumerstdiagnose"]
            self.new_case.main_diagnosis_code = res["icd10"]
            self.new_case.case_id = res["fallnummermv"]
            self.new_case.histology_code = res["icdo3histologie"]
            self.new_case.topography_code = res["icdo3lokalisation"]
        else:
            self.log_and_flash("Es wurde kein oder mehrere Einträge in der Tablle 'dk_dnpm_kpa' gefunden", "error")

    def get_mv_consent(self):
        res = self.get_query_res_as_dict(
            f"SELECT beginndatum, html_schnipsel_komprimiert FROM prozedur WHERE id IN (SELECT consentmv64e FROM dk_dnpm_kpa WHERE id={self.procedure_id})")

        if len(res) != 1:
            return
        row = res[0]
        mapping = {
            "Teilnahme": "mvSequencing",
            "Fallidentifz.": "caseIdentifiaction",
            "Re-Identifiz": "reIdentifiaction"
        }
        dt = row["beginndatum"].strftime("%Y-%m-%d")
        html = row["html_schnipsel_komprimiert"]

        scopes = []
        for label, domain in mapping.items():
            if f"{label}: zugestimmt" in html:
                t = "permit"
            else:
                t = "deny"
            scopes.append({"type": t, "date": dt, "domain": domain})

        self.new_case.mv_consent = {
            "presentationDate": dt,
            "version": "Einwilligung Modellvorhaben 64e v1 (2025-03-03)",
            "scope": scopes
        }

    def get_ecog(self):
        res = self.get_query_res_as_dict(
            f"SELECT * FROM dk_dnpm_uf_ecog WHERE id IN (SELECT id FROM prozedur WHERE hauptprozedur_id={self.procedure_id})")

        if len(res) == 0:
            self.log_and_flash("Kein ECOG gefunden!", "error")
            return False

            # jüngsten Eintrag wählen
        last = max(res, key=lambda r: r["datum"])

        ecog = last.get("ecog")

        if ecog in {"0", "1", "2", "3", "4", "5"}:
            self.new_case.ecog = ecog
        elif ecog == "U":
            self.new_case.ecog = "unknown"
        else:
            self.new_case.ecog = "notApplicable"
        return True


    def get_decision_data(self):
        res = self.get_query_res_as_dict(
            f"SELECT datum, bemerkung FROM dk_tumorkonferenz WHERE id IN ((SELECT id FROM prozedur WHERE patient_id={self.os_pat_id})) "
            f"AND tk='indikation' AND datum > (SELECT beginndatum FROM prozedur WHERE id={self.procedure_id} LIMIT 1)")
        if len(res) == 0:
            self.log_and_flash("Kein Indikationsboard gefunden", "error")
            return False
        elif len(res) > 1:
            self.log_and_flash("Mehrere Indikationsboards gefunden", "error")
            return False

        self.new_case.molecular_board_decision_date = res[0]['datum']
        if re.fullmatch(r"LMU-\d{4,10}", res[0]['bemerkung']):
            self.new_case.local_case_id = res[0]['bemerkung']

        res = self.get_query_res_as_dict(f"SELECT tk FROM dk_tumorkonferenz WHERE id IN ("
                                         f"(SELECT id FROM prozedur WHERE patient_id={self.os_pat_id})) AND tk='mvgenomseq' "
                                         f"AND datum > {self.new_case.molecular_board_decision_date}")
        if len(res) == 1:
            self.new_case.decision_to_include = 1
            return True
        self.new_case.decision_to_include = len(res) == 1
        if not self.new_case.decision_to_include:
            self.new_case.rejection_justification = "otherReason"

    def get_case_data(self) -> Case:

        if not self.procedure_id or not self.os_pat_id:
            self.log_and_flash(
                f"Patienten ID und/oder Prozedur ID sind nicht gesetzt!",
                "error")
            return None

        self.get_dnpm_kpa_data()
        self.get_mv_consent()
        self.get_ecog()
        self.get_decision_data()
        self.get_library_type()
        return self.new_case

    def get_library_type(self):
        res = self.get_query_res_as_dict(
            f"SELECT artdersequenzierung FROM dk_molekulargenetik WHERE id IN (SELECT id FROM prozedur WHERE patient_id={self.os_pat_id})")
        if len(res) == 1:
            match res[0]['artdersequenzierung']:
                case 'WES':
                    self.new_case.library_type = 'wes'
                case 'genome-long-read':
                    self.new_case.library_type = 'wes_lr'
                case 'WGS':
                    self.new_case.library_type = 'wgs'
                case 'PanelKit':
                    self.new_case.library_type = 'panel'
            return True
        return False



    def log_and_flash(self, msg, category):
        category = 'danger' if category =='error' else category
        flash(msg, category)
        log_entry("","",category,msg)

