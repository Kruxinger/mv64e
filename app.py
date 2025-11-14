# app.py (SQLAlchemy-Variante)

# Standard library
from datetime import datetime, timedelta, date
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Third-party libraries
import requests
from flask import Flask, render_template, request, redirect, flash, url_for, session
from sqlalchemy import func

# Local modules
from utils.check_services import check_services
from utils.generate_test_data import generate_test_data
from utils.logging import log_entry
from utils.tasks import fetch_research_consent_async, generate_tan_async
from utils.transmit_utils import build_oncology_payload

# Models (assumes models.py defines db, Case, Transmission, Constant, Log, ServiceStatus)
from models import db, Case, Transmission, Constant, Log, ServiceStatus

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_secret_key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

executor = ThreadPoolExecutor(max_workers=4)

# DB config from env
DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_NAME = os.environ.get("POSTGRES_DB", "onco")
DB_USER = os.environ.get("POSTGRES_USER", "onco_user")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "onco_pass")

# Flask/SQLAlchemy config
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:5432/{DB_NAME}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


@app.context_processor
def inject_current_year():
    return {'year': datetime.today().year}


# ---------------------
# Helper utilities
# ---------------------
def serialize_model_dates(obj):
    """
    Return a dict of all column names -> values.
    Date/datetime values are converted to 'YYYY-MM-DD' strings.
    """
    result = {}
    for col in obj.__table__.columns:
        name = col.name
        val = getattr(obj, name)
        if isinstance(val, (date, datetime)):
            result[name] = val.strftime('%Y-%m-%d')
        else:
            result[name] = val
    return result


def get_constants():
    rows = Constant.query.all()
    return {row.key: row.value for row in rows}



def update_case_field(case_id, field, value):
    """Update one field on Case (commits)"""
    with app.app_context():
        case = Case.query.filter_by(case_id=case_id).first()
        if not case:
            return False
        # basic safety: only update if attribute exists on model
        if hasattr(case, field):
            setattr(case, field, value)
            db.session.commit()
            return True
        else:
            # fallback: try raw SQL for arbitrary column names
            db.session.execute(
                f"UPDATE cases SET {field} = :value WHERE case_id = :case_id",
                {"value": value, "case_id": case_id}
            )
            db.session.commit()
            return True


def periodic_service_check(interval_hours=4):
    from utils.check_services import check_services

    def loop():
        from app import app
        with app.app_context():  # App Context starten
            while True:
                check_services()
                time.sleep(interval_hours * 3600)

    t = threading.Thread(target=loop, daemon=True)
    t.start()



# ---------------------
# Routes
# ---------------------

# ---- Login-Seite ----
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            next_url = session.pop('next', url_for("index"))
            return redirect(next_url)
        else:
            return render_template("login.html", error="Falsches Passwort")
    return render_template("login.html")

# ---- Before Request Hook ----
@app.before_request
def require_login():
    if request.endpoint in ("login", "static"):
        return  # login-Seite und statische Dateien ausnehmen
    if not session.get('logged_in'):
        session['next'] = request.path
        return redirect(url_for("login"))

@app.route("/cases")
def view_cases():
    cases = Case.query.order_by(Case.id.desc()).all()
    # columns from model
    columns = [c.name for c in Case.__table__.columns]
    # serialize for template (list of dicts)
    cases_serialized = [serialize_model_dates(c) for c in cases]
    return render_template("cases_table.html", cases=cases_serialized, columns=columns)


@app.route("/dashboard")
def dashboard():
    # --- Services ---
    current_status = check_services()  # {service_name: True/False}

    # --- Historical service_status (last 4 weeks) ---
    four_weeks_ago = datetime.now() - timedelta(weeks=4)
    historical_rows = (
        ServiceStatus.query
        .filter(ServiceStatus.last_checked >= four_weeks_ago)
        .order_by(ServiceStatus.last_checked.asc())
        .all()
    )
    historical_data = [
        {"service_name": r.service_name, "status": r.status, "last_checked": r.last_checked.isoformat()}
        for r in historical_rows
    ]

    # delete old entries (>4 weeks)
    ServiceStatus.query.filter(ServiceStatus.last_checked < four_weeks_ago).delete()
    db.session.commit()

    # --- Cases statistics ---
    total_cases = db.session.query(func.count(Case.id)).scalar() or 0
    finalized_cases = db.session.query(func.count()).filter(Case.is_finalized.is_(True)).scalar() or 0
    transmitted_cases = db.session.query(func.count()).filter(Case.transmitted.is_(True)).scalar() or 0

    finalized_percent = round(finalized_cases / total_cases * 100, 1) if total_cases else 0
    transmitted_percent = round(transmitted_cases / total_cases * 100, 1) if total_cases else 0

    return render_template(
        "dashboard.html",
        current_status=current_status,
        historical_data=historical_data,
        total_cases=total_cases,
        finalized_cases=finalized_cases,
        transmitted_cases=transmitted_cases,
        finalized_percent=finalized_percent,
        transmitted_percent=transmitted_percent
    )


@app.route("/", methods=["GET", "POST"])
def add_case():
    consts = get_constants()

    if request.method == "POST":
        pat_id = request.form["pat_id"]
        case_id = request.form["case_id_display"]  # angepasst an neues Feld
        gender = request.form.get("gender")
        birth_date = request.form.get("birth_date") or None
        address_ags = request.form.get("address_ags")
        decision_to_include = request.form.get("decision_to_include") == "true"
        molecular_board_decision_date = request.form.get("molecular_board_decision_date") or None
        rejection_justification = request.form.get("rejection_justification", "otherReason")
        main_diagnosis_date = request.form.get("main_diagnosis_date") or None
        main_diagnosis_code = request.form.get("main_diagnosis_code")
        ecog = request.form.get("ecog")
        coverage_type = request.form.get("coverage_type")
        germline_confirmed = request.form.get("germline_confirmed") == "true"
        histology_code = request.form.get("histology_code")
        topography_code = request.form.get("topography_code")
        library_type = request.form.get("library_type")
        is_finalized = request.form.get("is_finalized", "false") == "true"

        # ---- MV Consent JSON ----
        def build_scope(domain_key, domain_name):
            date_field = request.form.get(f"mv_consent_scope_{domain_key}_date", "").strip()
            decision_field = request.form.get(f"mv_consent_scope_{domain_key}_decision", "").strip().lower()
            if decision_field not in ("permit", "deny"):
                decision_field = "permit"
            return {"type": decision_field, "date": date_field, "domain": domain_name}

        mv_consent_version = request.form.get("mv_consent_version", consts.get('mvConsent.version'))

        mv_consent_json = {
            "presentationDate": request.form.get("mv_consent_presentation_date", "").strip(),
            "version": mv_consent_version,
            "scope": [
                build_scope("mvSequencing", "mvSequencing"),
                build_scope("reIdentification", "reIdentification"),
                build_scope("caseIdentification", "caseIdentification")
            ]
        }

        # ---- Case anlegen ----
        new_case = Case(
            case_id=case_id,
            pat_id=pat_id,
            gender=gender,
            birth_date=birth_date if birth_date else None,
            address_ags=address_ags,
            decision_to_include=decision_to_include,
            molecular_board_decision_date=molecular_board_decision_date if molecular_board_decision_date else None,
            rejection_justification=rejection_justification,
            main_diagnosis_date=main_diagnosis_date if main_diagnosis_date else None,
            main_diagnosis_code=main_diagnosis_code,
            ecog=ecog,
            germline_confirmed=germline_confirmed,
            histology_code=histology_code,
            topography_code=topography_code,
            library_type=library_type,
            submission_type=consts.get("submission_type"),
            submission_submitter_id=consts.get("submission_submitterId"),
            submission_genomic_data_center_id=consts.get("submission_genomicDataCenterId"),
            submission_clinical_data_node_id=consts.get("submission_clinicalDataNodeId"),
            submission_disease_type=consts.get("submission_diseaseType"),
            main_diagnosis_system=consts.get("mainDiagnosis_system"),
            main_diagnosis_version=consts.get("mainDiagnosis_version"),
            histology_system=consts.get("histology_system"),
            histology_version=consts.get("histology_version"),
            topography_system=consts.get("topography_system"),
            topography_version=consts.get("topography_version"),
            mv_consent=mv_consent_json,
            research_consent=None,
            coverage_type=coverage_type,
            is_finalized=is_finalized,
        )

        db.session.add(new_case)
        db.session.commit()

        # ---- Logging & Hintergrundjobs ----
        log_entry(case_id, pat_id, "info", f"Case {case_id} wurde angelegt")
        executor.submit(fetch_research_consent_async, case_id, pat_id)
        executor.submit(generate_tan_async, case_id, pat_id)

        return redirect("/")

    return render_template("add_case.html")



@app.route("/reload_consent_tan", methods=["POST"])
def reload_consent_tan():
    cases = Case.query.filter(Case.transmitted.is_(False)).all()
    for c in cases:
        if c.research_consent is None:
            executor.submit(fetch_research_consent_async, c.case_id, c.pat_id)
        if getattr(c, "tan_c", None) is None:
            executor.submit(generate_tan_async, c.case_id, c.pat_id)
    return ("", 204)


@app.route("/admin/constants", methods=["GET", "POST"])
def edit_constants():
    if request.method == "POST":
        for key, value in request.form.items():
            row = Constant.query.filter_by(key=key).first()
            if row:
                row.value = value
            else:
                db.session.add(Constant(key=key, value=value))
        db.session.commit()
        return redirect("/admin/constants")

    consts = get_constants()
    return render_template("edit_constants.html", constants=consts)


@app.route("/drafts")
def drafts():
    cases = Case.query.filter(Case.is_finalized.is_(False)).order_by(Case.id.desc()).all()
    cases_serialized = [serialize_model_dates(c) for c in cases]
    return render_template("drafts.html", cases=cases_serialized)


@app.route("/edit_case/<case_id>", methods=["GET", "POST"])
def edit_case(case_id):
    if request.method == "POST":
        # POST: update existing case
        form_case_id = request.form["case_id"]  # hidden field
        pat_id = request.form["pat_id"]

        case = Case.query.filter_by(case_id=form_case_id).first_or_404()

        # assign fields (snake_case wie in add_case)
        case.gender = request.form.get("gender")
        case.birth_date = request.form.get("birth_date") or None
        case.address_ags = request.form.get("address_ags")
        case.decision_to_include = request.form.get("decision_to_include") == "true"
        case.molecular_board_decision_date = request.form.get("molecular_board_decision_date") or None
        case.rejection_justification = request.form.get("rejection_justification", "otherReason")
        case.main_diagnosis_date = request.form.get("main_diagnosis_date") or None
        case.main_diagnosis_code = request.form.get("main_diagnosis_code")
        case.ecog = request.form.get("ecog")
        case.coverage_type = request.form.get("coverage_type")
        case.germline_confirmed = request.form.get("germline_confirmed") == "true"
        case.histology_code = request.form.get("histology_code")
        case.topography_code = request.form.get("topography_code")
        case.library_type = request.form.get("library_type")
        case.is_finalized = request.form.get("is_finalized", "false") == "true"

        consts = get_constants()
        mv_consent_version = request.form.get("mv_consent_version", consts.get('mvConsent.version'))

        # ---- MV Consent JSON ----
        def build_scope(domain_key, domain_name):
            date_field = request.form.get(f"mv_consent_scope_{domain_key}_date", "").strip()
            decision_field = request.form.get(f"mv_consent_scope_{domain_key}_decision", "").strip().lower()
            if decision_field not in ("permit", "deny"):
                decision_field = "deny"
            return {"type": decision_field,"date": date_field, "domain": domain_name}

        mv_consent_json = {
            "presentationDate": request.form.get("mv_consent_presentation_date", "").strip(),
            "version": mv_consent_version,
            "scope": [
                build_scope("mvSequencing", "mvSequencing"),
                build_scope("reIdentification", "reIdentification"),
                build_scope("caseIdentification", "caseIdentification"),
            ],
        }

        case.mv_consent = mv_consent_json

        db.session.commit()

        # ---- Logging & Hintergrundjobs ----
        log_entry(case.case_id, pat_id, "info", f"Case {case.case_id} wurde aktualisiert")
        executor.submit(fetch_research_consent_async, case.case_id, pat_id)
        executor.submit(generate_tan_async, case.case_id, pat_id)

        return redirect("/drafts")

    else:
        # GET: render edit form
        case = Case.query.filter_by(case_id=case_id).first_or_404()
        case_serialized = serialize_model_dates(case)
        return render_template("add_case.html", case=case_serialized)



@app.route("/transmit")
def transmit():
    cases = (
        Case.query
        .filter(Case.transmitted.is_(False), Case.is_finalized.is_(True))
        .order_by(Case.id.desc())
        .all()
    )
    cases_serialized = []
    for c in cases:
        d = serialize_model_dates(c)
        d["ready"] = (c.research_consent is not None and getattr(c, "tan_c", None) is not None)
        cases_serialized.append(d)
    return render_template("transmit.html", cases=cases_serialized)


@app.route("/send_case/<case_id>", methods=["POST"])
def send_case(case_id):
    case = Case.query.filter_by(case_id=case_id).first()
    if not case:
        flash(f"Case {case_id} nicht gefunden.", "danger")
        return redirect(url_for("transmit"))

    if case.research_consent is None or getattr(case, "tan_c", None) is None:
        flash(f"Case {case_id} ist nicht bereit zum Senden.", "warning")
        return redirect(url_for("transmit"))

    consts = get_constants()
    payload = build_oncology_payload(serialize_model_dates(case), consts)

    mv64_endpoint = os.environ.get("MV64_ENDPOINT", "https://example.com/mv64")
    try:
        response = requests.post(mv64_endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        status_code = response.status_code
        response_json = response.json() if response.text else {}

        # save transmission
        trans = Transmission(case_id=case_id, request=payload, response=response_json)
        db.session.add(trans)

        if status_code in (200, 202):
            case.transmitted = True
            db.session.add(case)
            log_entry(case.case_id, case.pat_id, "info", f"Case {case.case_id}: Wurde erfolgreich an das BfArM übermittelt.")
            flash(f"Case {case_id} erfolgreich an das BfArM gesendet.", "success")
        else:
            log_entry(case.case_id, case.pat_id, "error", f"Case {case.case_id}: Konnte nicht an das BfArM übermittelt werden (Status {status_code}).")
            flash(f"Senden von Case {case_id} fehlgeschlagen (Status {status_code}).", "danger")

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log_entry(case.case_id, case.pat_id, "error", f"Case {case.case_id}: Konnte nicht an das BfArM übermittelt werden: {e}")
        flash(f"Fehler beim Senden von Case {case_id}: {e}", "danger")

    return redirect(url_for("transmit"))


@app.route("/logs")
def view_logs():
    case_id = request.args.get("case_id", "").strip()
    if case_id:
        logs = Log.query.filter_by(case_id=case_id).order_by(Log.timestamp.desc()).all()
    else:
        logs = Log.query.order_by(Log.timestamp.desc()).limit(200).all()

    # serialize logs for template (isoformat timestamps)
    logs_serialized = [
        {"id": l.id, "timestamp": l.timestamp.isoformat() if l.timestamp else None,
         "pat_id": l.pat_id, "case_id": l.case_id, "type": l.type, "text": l.text}
        for l in logs
    ]

    return render_template("logs.html", logs=logs_serialized, case_id=case_id)



def init_constants():
    REQUIRED = {
        'submission_type': 'initial',
        'submission_submitterId': '999950000',
        'submission_genomicDataCenterId': 'GRZHD0003',
        'submission_clinicalDataNodeId': 'KDKHD0006',
        'submission_diseaseType': 'oncological',
        'mainDiagnosis_system': 'ICD-10-GM',
        'mainDiagnosis_version': 'icd10.gm-2019-10-04',
        'histology_system': 'ICD-O-3-M',
        'histology_version': 'icdo3morph.rev1de',
        'topography_system': 'ICD-O-3-T',
        'topography_version': 'icdo3topo.rev1de'
    }

    for key, value in REQUIRED.items():
        existing = Constant.query.filter_by(key=key).first()
        if not existing:
            db.session.add(Constant(key=key, value=value))

    db.session.commit()

if __name__ == "__main__":
    host = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_RUN_PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"

    # ensure tables exist
    with app.app_context():
        if debug:
            db.drop_all()
        db.create_all()
        if debug:
            generate_test_data()
        periodic_service_check()
        init_constants()

    print(f"Starting OncoApp on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)

