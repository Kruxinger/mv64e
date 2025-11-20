from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.dialects.postgresql import ARRAY

db = SQLAlchemy()


class Case(db.Model):
    __tablename__ = "cases"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.String, nullable=False)
    pat_id = db.Column(db.String, nullable=False)
    gender = db.Column(db.String)
    birth_date = db.Column(db.Date)
    address_ags = db.Column(db.String)
    decision_to_include = db.Column(db.Boolean)
    molecular_board_decision_date = db.Column(db.Date)
    rejection_justification = db.Column(db.Text)
    main_diagnosis_date = db.Column(db.Date)
    main_diagnosis_code = db.Column(db.String)
    coverage_type = db.Column(db.String)
    ecog = db.Column(db.String)
    germline_confirmed = db.Column(db.Boolean)
    histology_code = db.Column(db.String)
    local_case_id = db.Column(db.String)
    topography_code = db.Column(db.String)
    library_type = db.Column(db.String)
    submission_type = db.Column(db.String)
    submission_submitter_id = db.Column(db.String)
    submission_genomic_data_center_id = db.Column(db.String)
    submission_clinical_data_node_id = db.Column(db.String)
    submission_disease_type = db.Column(db.String)
    main_diagnosis_system = db.Column(db.String)
    main_diagnosis_version = db.Column(db.String)
    histology_system = db.Column(db.String)
    histology_version = db.Column(db.String)
    topography_system = db.Column(db.String)
    topography_version = db.Column(db.String)
    tan_c = db.Column(db.String)
    mv_consent = db.Column(db.JSON)
    research_consent = db.Column(ARRAY(db.JSON))
    transmitted = db.Column(db.Boolean, default=False)
    is_finalized = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Case {self.case_id} ({self.pat_id})>"


class Transmission(db.Model):
    __tablename__ = "transmissions"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.String, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    request = db.Column(db.JSON)
    response = db.Column(db.JSON)

    def __repr__(self):
        return f"<Transmission case_id={self.case_id} timestamp={self.timestamp}>"


class Constant(db.Model):
    __tablename__ = "constants"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String, unique=True, nullable=False)
    value = db.Column(db.String, nullable=False)

    def __repr__(self):
        return f"<Constant {self.key}={self.value}>"


class Log(db.Model):
    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime(timezone=True), default=datetime.now)
    pat_id = db.Column(db.String)
    case_id = db.Column(db.String)
    type = db.Column(db.String, nullable=False)  # info / error
    text = db.Column(db.Text)

    def __repr__(self):
        return f"<Log {self.type} {self.case_id}>"


class ServiceStatus(db.Model):
    __tablename__ = "service_status"

    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String, nullable=False)
    status = db.Column(db.Boolean, nullable=False)
    last_checked = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f"<ServiceStatus {self.service_name}: {self.status}>"
