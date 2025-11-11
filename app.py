import json

from flask import Flask, render_template, request, redirect
import psycopg2
from psycopg2.extras import RealDictCursor
import os

from utils.consent import get_research_consent

app = Flask(__name__)

DB_HOST = os.environ.get("POSTGRES_HOST", "db")
DB_NAME = os.environ.get("POSTGRES_DB", "onco")
DB_USER = os.environ.get("POSTGRES_USER", "onco_user")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "onco_pass")

@app.route("/dashboard")
def dashboard():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, case_id, pat_id, gender, birthDate as birthdate, libraryType as librarytype
        FROM cases ORDER BY id DESC
    """)
    cases = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("dashboard.html", cases=cases)


def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def get_constants():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT key, value FROM constants ORDER BY key")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {row['key']: row['value'] for row in rows}

@app.route("/", methods=["GET", "POST"])
def add_case():
    consts = get_constants()  # Konstanten laden

    if request.method == "POST":
        pat_id = request.form["pat_id"]
        localCaseId = request.form["localCaseId"]
        gender = request.form["gender"]
        birthDate = request.form["birthDate"]
        addressAGS = request.form["addressAGS"]
        decsisionToInclude = request.form["decsisionToInclude"] == "Ja"
        molecularBoardDescisionDate = request.form["molecularBoardDescisionDate"]
        rejectionJustification = request.form.get("rejectionJustification", "")
        mainDiagnosis_date = request.form["mainDiagnosis_date"]
        mainDiagnosis_code = request.form["mainDiagnosis_code"]
        ecog = request.form["ecog"]
        germlineConfirmed = request.form["germlineConfirmed"] == "Ja"
        histology_code = request.form["histology_code"]
        topography_code = request.form["topography_code"]
        libraryType = request.form["libraryType"]

        # mvConsent JSON zusammenstellen
        mvConsent_json = {
            "presentationDate": request.form.get("mvConsent_presentationDate", ""),
            "version": consts['mvConsent.version'],
            "scope": [
                {"type": "permit", "date": request.form.get("mvConsent_scope_mvSequencing", ""), "domain": "mvSequencing"},
                {"type": "permit", "date": request.form.get("mvConsent_scope_reIdentification", ""), "domain": "reIdentification"},
                {"type": "permit", "date": request.form.get("mvConsent_scope_caseIdentification", ""), "domain": "caseIdentification"}
            ]
        }

        # researchConsent holen
        researchConsent_json = get_research_consent(pat_id)

        # in DB speichern
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cases
            (case_id, pat_id, gender, birthDate, addressAGS, decsisionToInclude,
             molecularBoardDescisionDate, rejectionJustification,
             mainDiagnosis_date, mainDiagnosis_code, ecog, germlineConfirmed,
             histology_code, topography_code, libraryType,
             submission_type, submission_submitterId, submission_genomicDataCenterId,
             submission_clinicalDataNodeId, submission_diseaseType,
             mvConsent_version,
             mainDiagnosis_system, mainDiagnosis_version,
             histology_system, histology_version,
             topography_system, topography_version,
             mvConsent, researchConsent)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            localCaseId, pat_id, gender, birthDate, addressAGS, decsisionToInclude,
            molecularBoardDescisionDate, rejectionJustification,
            mainDiagnosis_date, mainDiagnosis_code, ecog, germlineConfirmed,
            histology_code, topography_code, libraryType,
            consts['submission.type'], consts['submission.submitterId'], consts['submission.genomicDataCenterId'],
            consts['submission.clinicalDataNodeId'], consts['submission.diseaseType'],
            consts['mvConsent.version'],
            consts['mainDiagnosis.system'], consts['mainDiagnosis.version'],
            consts['histology.system'], consts['histology.version'],
            consts['topography.system'], consts['topography.version'],
            json.dumps(mvConsent_json), json.dumps(researchConsent_json)
        ))
        conn.commit()
        cur.close()
        conn.close()
        return redirect("/")

# Admin-Seite für Konstanten
@app.route("/admin/constants", methods=["GET", "POST"])
def edit_constants():
    if request.method == "POST":
        conn = get_conn()
        cur = conn.cursor()
        for key, value in request.form.items():
            cur.execute("UPDATE constants SET value=%s WHERE key=%s", (value, key))
        conn.commit()
        cur.close()
        conn.close()
        return redirect("/admin/constants")

    consts = get_constants()
    return render_template("edit_constants.html", constants=consts)
