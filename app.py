# app.py (SQLAlchemy-Variante)
import logging
# Standard library
from datetime import datetime, timedelta, date
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from flask import send_from_directory, jsonify
import os

from flask import Flask, render_template, request, redirect, flash, url_for, session
from sqlalchemy import func

from utils.check_services import check_services
from utils.consent import get_research_consent
from utils.logging import log_entry_and_flash
from utils.onkostar_interface import OnkostarInterface
from utils.tan_service import generate_tan
from utils.tasks import fetch_research_consent_async, generate_tan_async
from utils.transmit_utils import build_oncology_payload, send

from models import db, Case, Transmission, Constant, Log, ServiceStatus

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_secret_key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
DOKU_PASSWORD = os.environ.get("DOKU_PASSWORD", "changeme")

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
            session['logged_in_admin'] = True
            next_url = session.pop('next', url_for("dashboard"))
            return redirect(next_url)
        elif password == DOKU_PASSWORD:
            session['logged_in_doku'] = True
            next_url = session.pop('next', url_for("add_case"))
            return redirect(next_url)
        else:
            return render_template("login.html", error="Falsches Passwort")
    return render_template("login.html")


# ---- Before Request Hook ----
@app.before_request
def require_login():
    if request.endpoint in ("login", "static", "favicon"):
        return  # login-Seite und statische Dateien ausnehmen
    if not session.get('logged_in_admin') and not session.get('logged_in_doku'):
        session['next'] = request.path
        return redirect(url_for("login"))




@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )


@app.route("/cases")
def view_cases():
    cases = Case.query.order_by(Case.id.desc()).all()
    # columns from model
    columns = [c.name for c in Case.__table__.columns]
    # serialize for template (list of dicts)
    cases_serialized = [serialize_model_dates(c) for c in cases]
    return render_template("cases_table.html", cases=cases_serialized, columns=columns)

@app.route("/cases_overview")
def cases_overview():
    cases = Case.query.order_by(
        Case.transmitted.asc(),  # false zuerst
        Case.is_finalized.asc(),  # false zuerst
        Case.id.desc()
    ).all()

    cases_serialized = []
    for c in cases:
        d = serialize_model_dates(c)
        d["ready"] = d.get("tan_c") is not None
        cases_serialized.append(d)

    return render_template("cases_overview.html", cases=cases_serialized)

@app.route("/unlock_case/<case_id>", methods=["POST"])
def unlock_case(case_id):
    c = Case.query.filter_by(case_id=case_id).first_or_404()
    if c.is_finalized and not c.transmitted:
        c.is_finalized = False
        db.session.commit()
    return redirect(url_for("edit_case", case_id=c.case_id))


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


@app.route("/logout")
def logout():
    session.clear()  # oder: session.pop("logged_in", None)
    return redirect(url_for("login"))


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
        local_case_id = request.form.get("local_case_id")
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
            local_case_id=local_case_id,
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
        log_entry_and_flash(case_id, pat_id, "info", f"Case {case_id} wurde angelegt", True)
        executor.submit(fetch_research_consent_async, new_case.id, pat_id)
        executor.submit(generate_tan_async, new_case.id, case_id)

        return redirect("/")

    return render_template("add_case.html")


@app.route("/reload_consent_tan", methods=["POST"])
def reload_consent_tan():
    cases = Case.query.filter(Case.transmitted.is_(False)).all()
    for c in cases:
        if c.research_consent is None:
            executor.submit(fetch_research_consent_async, c.id, c.pat_id)
        if getattr(c, "tan_c", None) is None:
            executor.submit(generate_tan_async, c.id, c.case_id)
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
        log_entry_and_flash("","","success","Konstanten wurden aktualisiert", True)

        return redirect("/admin/constants")

    consts = get_constants()
    return render_template("edit_constants.html", constants=consts)





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
        case.local_case_id = request.form.get("local_case_id")
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
            return {"type": decision_field, "date": date_field, "domain": domain_name}

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
        try:
            db.session.commit()
            log_entry_and_flash(case.case_id, pat_id, "info", f"Änderungen gespeichert", True)
            executor.submit(fetch_research_consent_async, case.id, pat_id)
            executor.submit(generate_tan_async, case.id, case_id)
        except Exception as e:
            log_entry_and_flash(case.case_id, pat_id, "error", f"Änderungen konnten nicht gespeichert werden. Fehler: {str(e)}", True)
        return redirect("/cases_overview")

    case = Case.query.filter_by(case_id=case_id).first_or_404()
    case_serialized = serialize_model_dates(case)
    return render_template("add_case.html", case=case_serialized)





@app.route("/show_json/<case_id>", methods=["POST"])
def show_json(case_id):
    case = Case.query.filter_by(case_id=case_id).first()
    if not case:
        flash(f"Case {case_id} nicht gefunden.", "error")
        return redirect(url_for("cases_overview"))

    if getattr(case, "tan_c", None) is None:
        flash(f"Case {case_id} ist nicht bereit zum Senden.", "warning")
        return redirect(url_for("cases_overview"))

    consts = get_constants()
    payload = build_oncology_payload(serialize_model_dates(case), consts)
    return jsonify(payload)


@app.route("/transmissions/<int:index>")
def show_transmission(index=0):
    transmissions = Transmission.query.order_by(Transmission.timestamp).all()
    total = len(transmissions)

    if not transmissions:
        return render_template("transmissions.html", transmission=None, index=0, total=0)

    # Index begrenzen
    index = max(0, min(index, total - 1))
    transmission = transmissions[index]

    return render_template(
        "transmissions.html",
        transmission=transmission,
        index=index + 1,  # für Anzeige 1-basiert
        total=total
    )


@app.route("/send_case", methods=["POST"])
def send_case():
    case_id = request.args.get("case_id")
    endpoint = request.args.get("bfarm_endpoint")
    case = Case.query.filter_by(case_id=case_id).first()
    if not case:
        flash(f"Case {case_id} nicht gefunden.", "error")
        return redirect(url_for("cases_overview"))

    if getattr(case, "tan_c", None) is None:
        flash(f"Case {case_id} ist nicht bereit zum Senden.", "warning")
        return redirect(url_for("cases_overview"))

    consts = get_constants()
    payload = build_oncology_payload(serialize_model_dates(case), consts)
    if endpoint == 'TEST':
        payload['metaData']['submission']['type'] = "test"
    send(payload=payload, endpoint=endpoint, case=case)
    return redirect(url_for("cases_overview"))


@app.route("/upload_case_by_id", methods=["GET", "POST"])
def upload_case_by_id():
    if request.method == "POST":
        pat_id = request.args.get("pat_id")
        action = request.args.get("action")
        mode = request.args.get("mode")
        # TODO: Not implemented

    else:
        s = {
            "submission": {
                "submissionDate": "2025-11-05",
                "type": "initial",
                "submitterId": "999950000",
                "genomicDataCenterId": "GRZHD0003",
                "clinicalDataNodeId": "KDKHD0006",
                "diseaseType": "oncological"
            }
        }
        j = {
            "description": "With this endpoint, you can get a BfArM JSON, generate a new case and (optionally) send it."
                           "All based on a Pat ID."
                           "It will return error messages if anything is wrong.",
            "post_parameters": {
                "action": {
                    "description": "Defines, what will be done: \nCREATE_JSON: Creates a JSON in BaArM format and returns "
                                   "it. (Nothing will be sent to Köln or any other endpoint)"
                                   "\nCREATE_CASE: Creates a 'Case' on this applications context. It will only be created. "
                                   "You can check it in the frontend and send it manually\n"
                                   "CREATE_AND_SEND_CASE: 'fire and forget' - A new case will be created and sent to BfArM."
                                   "You will receive the response from the given endpoint",
                    "type": "enum[CREATE_JSON|CREATE_CASE|CREATE_AND_SEND_CASE]",
                    "required": True
                },
                "pat_id": {
                    "description": "The patient ID",
                    "type": "string",
                    "required": True,
                    "example": "0021335993"
                },
                "mode": {
                    "description": "Defines whether you want to test the app or send prod data",
                    "type": "enum[PROD|TEST]",
                    "required": False,
                    "default": "TEST"
                },
                "submission": {
                    "description": "You can define the submission data. If you do, you have to pass a complete submission set",
                    "type": "dict",
                    "required": False,
                    "default": "Set by the values in the db (you can set them via frontend)",
                    "example": json.dumps(s)
                }
            }
        }
        return jsonify(j)


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


@app.route("/onko_import_wiz_step_1", methods=["GET", "POST"])
def onko_import_wiz_step_1():
    if request.method == "POST":
        # Hole die pat_id aus Eingabemaske
        patient_id = request.form.get("patient_id")
        if not patient_id:
            flash("Bitte eine Patienten-ID eingeben.", "warning")
            return redirect(url_for("onko_import_wiz_step_1"))

        os_interface = OnkostarInterface()
        # Prüfen, ob es in der OS DB 1...1 Patient mit der ID gibt (und dem Personenstamm)
        if not os_interface.get_pat_data(patient_id):
            return redirect(url_for("onko_import_wiz_step_1"))

        # Nun suchen wir das "richtige" DNPM Klinik/Anamnese Formular
        prod_ids_dates = os_interface.get_anamnese_procedures()

        # Der Patient hat KEIN DNPM Klinik/Anamnese Formular
        if len(prod_ids_dates) == 0:
            os_interface.log_and_flash("Kein DNPM Klinik/Anamnese Formular gefunden.", "error")
            return redirect(url_for("onko_import_wiz_step_1"))

        # Nun prüfen auf Datum: Wir haben viele leere Formulare, meist durch Plugin angelegt
        # diese brauchen wir nicht, können diese aber am fehlenden Datum erkennen
        with_date = [p for p in prod_ids_dates if p["beginndatum"] is not None]

        # Der Patient hat KEIN DNPM Klinik/Anamnese Formular mit einem Datum != None => Nicht (richtig) dokumentiert
        if len(with_date) == 0:
            flash("Kein DNPM Klinik/Anamnese Formular hat ein valides Datum!", "error")
            return redirect(url_for("onko_import_wiz_step_1"))

        # Es gibt mehr als ein DNPM Klinik/Anamnese Formular mit validem Datum => Möglich, bei mehreren Einschlüssen
        # => Datum muss gewählt werden
        if len(with_date) > 1:
            dates = [p["beginndatum"].strftime('%d.%m.%Y') for p in prod_ids_dates]
            return redirect(url_for("onko_import_wiz_step_1_select", pat_id=patient_id, dates=dates))

        # Es gibt genau ein Formular mit datum => Best Case
        # Daten werden direkt geladen und in der Maske angezeigt
        # else
        os_interface.procedure_id = with_date[0]['id']
        new_case = os_interface.get_case_data()
        db.session.query()
        case = Case.query.filter_by(case_id=new_case.case_id, pat_id=new_case.pat_id).first()

        if case and case.transmitted:
            logging.error("**" * 20)
            flash(f"Der Patient {case.pat_id} mit der Fallnummer {case.case_id} wurde bereits ans BfArM "
                  f"übertragen und kann nicht erneut importiert werden!", "warning")
            return redirect(url_for("onko_import_wiz_step_1"))
        new_case.tan_c = generate_tan(case_id=new_case.case_id)
        new_case.research_consent = get_research_consent(new_case.pat_id)
        db.session.add(new_case)
        db.session.commit()
        if case:
            if case.is_finalized:
                flash("Hinweis: Der bereits existierende Fall ist bereits als abgeschlossen markiert!", "warning")
            return redirect(url_for("case_exists_handling", new_case_id=new_case.id, existing_case_id=case.id))

        return redirect(url_for("edit_case", case_id=new_case.case_id))

    return render_template("onko_import_wiz_step_1.html")

@app.route("/case_exists_handling", methods=["GET","POST"])
def case_exists_handling():
    if request.method == "POST":
        keep_case = Case.query.filter_by(id=request.form.get("keep")).first()
        remove_case = Case.query.filter_by(id=request.form.get("remove")).first()
        db.session.delete(remove_case)
        db.session.commit()
        return redirect(url_for("edit_case", case_id=keep_case.case_id))
    existing_case_id = request.args.get("existing_case_id")
    new_case_id = request.args.get("new_case_id")
    return render_template("case_exists_handling.html", existing_case_id=existing_case_id, new_case_id=new_case_id)


@app.post("/cases/<case_id>/delete")
def delete_case(case_id):
    case = Case.query.filter_by(case_id=case_id).first_or_404()
    db.session.delete(case)
    db.session.commit()
    flash("Fall wurde gelöscht.", "success")
    return redirect(url_for("cases_overview"))


@app.route("/onko_import_wiz_step_1_select")
def onko_import_wiz_step_1_select():
    if request.method == "POST":
        patient_id = request.form.get("patient_id")
        procedure_date = request.form.get("procedure_date")
        os_interface = OnkostarInterface()
        os_interface.get_pat_data(patient_id)
        prod_ids_dates = os_interface.get_anamnese_procedures()
        os_interface.procedure_id = next(p['id'] for p in prod_ids_dates if p['datum'] == procedure_date)
        case = os_interface.get_case_data()
        case.tan_c = generate_tan(case_id=case.case_id)
        case.research_consent = get_research_consent(case.pat_id)
        db.session.add(case)
        db.session.commit()

        return redirect(url_for("edit_case", case_id=case.id))

    return render_template("onko_import_wiz_step_1.html")


def init_constants():
    REQUIRED = {
        'submission_type': 'initial',
        'submission_submitterId': '260914050',
        'submission_genomicDataCenterId': 'GRZHD0003',
        'submission_clinicalDataNodeId': 'KDKK00007',
        'submission_diseaseType': 'oncological',
        'mainDiagnosis_system': 'ICD-10-GM',
        'mainDiagnosis_version': '2024',
        'histology_system': 'ICD-O-3',
        'histology_version': '2019',
        'topography_system': 'ICD-O-3',
        'topography_version': '2019',
        'onkostar_personenstamm': 'SAP'
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
        # if debug:
        #     db.drop_all()
        db.create_all()
        # if debug:
        #     generate_test_data()
        periodic_service_check()
        init_constants()

    print(f"Starting OncoApp on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)
