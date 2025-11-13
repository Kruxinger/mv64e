import threading
from models import db, Case, Log

def generate_tan_async(case_id):
    def task():
        # z. B. HTTP-Request oder API-Call
        print(f"Generating TAN for case {case_id}")
        # hier evtl. Log-Eintrag:
        log = Log(case_id=case_id, type="info", text="TAN generated")
        db.session.add(log)
        db.session.commit()

    threading.Thread(target=task).start()


def fetch_research_consent_async(case_id):
    def task():
        print(f"Fetching research consent for case {case_id}")
        # Daten extern abrufen …
        # z. B. Ergebnis speichern:
        case = Case.query.filter_by(case_id=case_id).first()
        if case:
            case.research_consent = {"consent": "fetched"}
            db.session.commit()

    threading.Thread(target=task).start()