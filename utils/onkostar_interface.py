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

        self.consentmv64e_id = ""

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


    def get_pat_data(self, pat_id_lmu: str) -> bool:
        res = self.get_query_res_as_dict(
            f"SELECT id, geschlecht, geburtsdatum, GKZ FROM patient JOIN personenstamm ON "
            f"patient.personenstamm=personenstamm.id WHERE patient.patienten_id={pat_id_lmu} "
            f"AND personenstamm.name='{self.personenstamm}'")
        if len(res) == 1:
            res = res[0]
            self.new_case.gender = "unknown"
            match res["geschlecht"]:
                case "m":
                    self.new_case.gender = "male"
                case "w":
                    self.new_case.gender = "male"
                case "d":
                    self.new_case.gender = "divers"

            self.new_case.birth_date = res['geburtsdatum'].strftime('%d.%m.%Y')
            self.new_case.address_ags = res['GKZ'][:4] if len(res['GKZ']) >= 5 else ""
            self.os_pat_id = res['id']
            return True

        if len(res) == 0:
            self.log_and_flash(f"Es wurde kein Patient mit der id {pat_id_lmu} im Personenstamm '{self.personenstamm}' gefunden", "error")
            return False

        if len(res) > 0:
            self.log_and_flash(f"Es wurden mehr als ein kein Patient mit der id {pat_id_lmu} im Personenstamm '{self.personenstamm}' gefunden", "error")
            return False

    def get_case_data(self) -> Case:

        def get_dnpm_kpa_data():
            res = self.get_query_res_as_dict(
                f"SELECT anmeldedatummtb, datumerstdiagnose, icd10, icdo3histologie, icdo3lokalisation, mtb, "
                f"artderkrankenkasse, consentmv64e, fallnummermv FROM dk_dnpm_kpa WHERE id={self.procedure_id}")
            res = res[0]
            self.consentmv64e_id = res["consentmv64e"]
            self.new_case.main_diagnosis_date = res["datumerstdiagnose"]
            self.new_case.main_diagnosis_code = res["icd10"]
            self.new_case.case_id = res["fallnummermv"]
            self.new_case.coverage_type = res["artderkrankenkasse"]
            self.new_case.histology_codepat_data["histology_code"] = res["icdo3histologie"]
            self.new_case.topography_code = res["icdo3lokalisation"]

        def get_mv_consent():
            res = self.get_query_res_as_dict(
                f"SELECT beginndatum, html_schnipsel_komprimiert FROM prozedur WHERE id={self.consentmv64e_id}")
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

        def get_ecog():
            res = self.get_query_res_as_dict(
                f"SELECT * FROM dk_dnpm_uf_ecog WHERE id IN (SELECT id FROM prozedur WHERE hauptprozedur_id={self.procedure_id})")
            if not res:
                self.new_case.ecog = "notApplicable"

                # jüngsten Eintrag wählen
            last = max(res, key=lambda r: r["datum"])
            ecog = last.get("ecog")

            if ecog in {"0", "1", "2", "3", "4", "5"}:
                self.new_case.ecog = ecog
            if ecog == "U":
                self.new_case.ecog = "unknown"
            self.new_case.ecog = "notApplicable"

        def get_decision_data():
            res = self.get_query_res_as_dict(
                f"SELECT datum, bemerkung FROM dk_tumorkonferenz WHERE id IN ((SELECT id FROM prozedur WHERE patient_id=0)) "
                f"AND tk='indikation' AND datum > (SELECT beginndatum FROM prozedur WHERE id={self.procedure_id} LIMIT 1)")
            if len(res) == 0:
                self.log_and_flash("Kein Indikationsboard gefunden", "error")
                return
            elif len(res) > 1:
                self.log_and_flash("Mehrere Indikationsboards gefunden", "error")
                return

            self.new_case.molecular_board_decision_date = res[0]['datum']
            if re.fullmatch(r"LMU-\d{4,10}", res[0]['bemerkung']):
                self.new_case.local_case_id = res[0]['bemerkung']

            res = self.get_query_res_as_dict(f"SELECT tk FROM dk_tumorkonferenz WHERE id IN ("
                                             f"(SELECT id FROM prozedur WHERE patient_id=0)) AND tk='mvgenomseq' "
                                             f"AND datum > {self.new_case.molecular_board_decision_date }")
            self.new_case.decision_to_include = len(res) == 1

        if not self.procedure_id or not self.os_pat_id:
            self.log_and_flash(
                f"Patienten ID und/oder Prozedur ID sind nicht gesetzt!",
                "error")
            return None

        get_dnpm_kpa_data()
        get_mv_consent()
        get_ecog()
        get_decision_data()
        return self.new_case



    def log_and_flash(self, msg, category):
        category = 'danger' if category =='error' else category
        flash(msg, category)
        log_entry("","",category,msg)

