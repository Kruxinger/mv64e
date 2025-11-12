import json

from flask import Flask, render_template, request, redirect
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from utils.logging import log_entry
from concurrent.futures import ThreadPoolExecutor
from utils.logging import log_entry
from utils.tan_service import generate_tan
from utils.consent import get_research_consent



from utils.consent import get_research_consent

app = Flask(__name__)

executor = ThreadPoolExecutor(max_workers=4)

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
        coverageType = request.form["coverageType"]
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
             mvConsent, researchConsent, coverageType)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
            json.dumps(mvConsent_json), json.dumps(researchConsent_json, coverageType)
        ))
        conn.commit()
        cur.close()
        conn.close()

        # Log: Case angelegt
        log_entry(localCaseId, pat_id, "info", f"Case {localCaseId} wurde angelegt")

        # Hintergrundjobs starten
        executor.submit(fetch_research_consent_async, localCaseId, pat_id)
        executor.submit(generate_tan_async, localCaseId, pat_id)

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


@app.route("/transmit")
def transmit():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, case_id, pat_id, researchConsent, tanC, transmitted FROM cases WHERE transmitted = FALSE ORDER BY id DESC")
    cases = cur.fetchall()
    cur.close()
    conn.close()

    for c in cases:
        c["ready"] = (c["researchConsent"] is not None and c["tanC"] is not None)

    return render_template("transmit.html", cases=cases)


@app.route("/send_case/<case_id>", methods=["POST"])
def send_case(case_id):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Case laden
    cur.execute("SELECT * FROM cases WHERE case_id = %s", (case_id,))
    case = cur.fetchone()

    if not case:
        flash(f"Case {case_id} nicht gefunden.", "danger")
        return redirect(url_for("transmit"))

    if case["researchConsent"] is None or case["tanC"] is None:
        flash(f"Case {case_id} ist nicht bereit zum Senden.", "warning")
        return redirect(url_for("transmit"))

    consts = get_constants()
    payload = build_oncology_payload(case, consts)

    # Anfrage an mv64_endpoint senden
    mv64_endpoint = os.environ.get("MV64_ENDPOINT", "https://example.com/mv64")
    try:
        response = requests.post(
            mv64_endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        status_code = response.status_code
        response_json = response.json() if response.text else {}

        # In transmissions speichern
        cur.execute("""
            INSERT INTO transmissions (case_id, request, response)
            VALUES (%s, %s, %s)
        """, (case_id, json.dumps(payload), json.dumps(response_json)))

        if status_code in (200, 202):
            # Erfolg
            cur.execute("UPDATE cases SET transmitted = TRUE WHERE case_id = %s", (case_id,))
            cur.execute("""
                INSERT INTO log (pat_id, case_id, timestamp, type, text)
                VALUES (%s, %s, NOW(), %s, %s)
            """, (case["pat_id"], case_id, "info", f"Case {case_id}: Wurde erfolgreich an das BfArM übermittelt."))
            flash(f"Case {case_id} erfolgreich an das BfArM gesendet.", "success")
        else:
            cur.execute("""
                INSERT INTO log (pat_id, case_id, timestamp, type, text)
                VALUES (%s, %s, NOW(), %s, %s)
            """, (case["pat_id"], case_id, "error",
                  f"Case {case_id}: Konnte nicht an das BfArM übermittelt werden (Status {status_code})."))
            flash(f"Senden von Case {case_id} fehlgeschlagen (Status {status_code}).", "danger")

    except Exception as e:
        cur.execute("""
            INSERT INTO log (pat_id, case_id, timestamp, type, text)
            VALUES (%s, %s, NOW(), %s, %s)
        """, (case["pat_id"], case_id, "error",
              f"Case {case_id}: Konnte nicht an das BfArM übermittelt werden: {str(e)}"))
        flash(f"Fehler beim Senden von Case {case_id}: {e}", "danger")

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("transmit"))


@app.route("/logs")
def view_logs():
    case_id = request.args.get("case_id", "").strip()

    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if case_id:
        cur.execute("""
            SELECT id, timestamp, pat_id, case_id, type, text
            FROM logs
            WHERE case_id = %s
            ORDER BY timestamp DESC
        """, (case_id,))
    else:
        cur.execute("""
            SELECT id, timestamp, pat_id, case_id, type, text
            FROM logs
            ORDER BY timestamp DESC
            LIMIT 200
        """)

    logs = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("logs.html", logs=logs, case_id=case_id)

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

def update_case_field(case_id, field, value):
    """Helper to update one JSON/text field in cases table."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"UPDATE cases SET {field} = %s WHERE case_id = %s", (value, case_id))
    conn.commit()
    cur.close()
    conn.close()

def fetch_research_consent_async(case_id, pat_id):
    """Background task to fetch and save Research Consent."""
    try:
        consent_json = get_research_consent(pat_id)
        update_case_field(case_id, "researchConsent", json.dumps(consent_json))
        log_entry(case_id, pat_id, "info", f"Broad Consent erfolgreich geladen")
    except Exception as e:
        log_entry(case_id, pat_id, "error", f"Broad Consent konnte nicht abgerufen werden: {e}")

def generate_tan_async(case_id, pat_id):
    """Background task to generate TAN via gPAS."""
    try:
        tan_value = generate_tan(pat_id)
        update_case_field(case_id, "tan", tan_value)
        log_entry(case_id, pat_id, "info", f"TAN erfolgreich generiert")
    except Exception as e:
        log_entry(case_id, pat_id, "error", f"Pseudonym konnte nicht generiert werden: {e}")

