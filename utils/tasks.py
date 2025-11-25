import threading
from models import db, Case, Log
from utils.consent import get_research_consent
from utils.data_server_interface import upsert_consent
from utils.tan_service import generate_tan


def generate_tan_async(id, case_id):
    from app import app
    def task():
        with app.app_context():
            case: Case = Case.query.filter_by(id=id).first()
            if case and case.tan_c in (None, ""):
                case.tan_c = generate_tan(case_id)
                db.session.commit()
    threading.Thread(target=task).start()


def fetch_research_consent_async(id, pat_id):
    from app import app
    def task():
        with app.app_context():
            research_consent = get_research_consent(pat_id)
            case: Case = Case.query.filter_by(id=id).first()
            if case:
                case.research_consent = research_consent
                db.session.commit()
                if case.is_finalized:
                    upsert_consent(case.mv_consent, research_consent, pat_id, case.case_id)

    threading.Thread(target=task).start()