
CREATE TABLE IF NOT EXISTS cases (
    id SERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    pat_id TEXT NOT NULL,
    gender TEXT,
    birthDate DATE,
    addressAGS TEXT,
    decisionToInclude BOOLEAN,
    molecularBoardDescisionDate DATE,
    rejectionJustification TEXT,
    mainDiagnosis_date DATE,
    mainDiagnosis_code TEXT,
    coverageType TEXT,
    ecog TEXT,
    germlineConfirmed BOOLEAN,
    histology_code TEXT,
    topography_code TEXT,
    libraryType TEXT,
    submission_type TEXT,
    submission_submitterId TEXT,
    submission_genomicDataCenterId TEXT,
    submission_clinicalDataNodeId TEXT,
    submission_diseaseType TEXT,
    mvConsent_version TEXT,
    mainDiagnosis_system TEXT,
    mainDiagnosis_version TEXT,
    histology_system TEXT,
    histology_version TEXT,
    topography_system TEXT,
    topography_version TEXT,
    tanC TEXT,
    mvConsent JSONB,
    researchConsent JSONB,
    transmitted BOOLEAN DEFAULT FALSE,
    is_finalized BOOLEAN DEFAULT FALSE
);


ALTER TABLE cases
ALTER COLUMN researchConsent DROP NOT NULL;


CREATE TABLE IF NOT EXISTS transmissions (
    id SERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    request JSONB,
    response JSONB
);

CREATE TABLE IF NOT EXISTS constants (
    id SERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL
);


INSERT INTO constants (key, value) VALUES
('submission.type', 'initial'),
('submission.submitterId', '999950000'),
('submission.genomicDataCenterId', 'GRZHD0003'),
('submission.clinicalDataNodeId', 'KDKHD0006'),
('submission.diseaseType', 'oncological'),
('mvConsent.version', 'Einwilligung Modellvorhaben 64e v1 (2025-03-03)'),
('mainDiagnosis.system', 'ICD-10-GM'),
('mainDiagnosis.version', 'icd10.gm-2019-10-04'),
('histology.system', 'ICD-O-3-M'),
('histology.version', 'icdo3morph.rev1de'),
('topography.system', 'ICD-O-3-T'),
('topography.version', 'icdo3topo.rev1de');


CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    pat_id TEXT,
    case_id TEXT,
    type TEXT CHECK (type IN ('info', 'error')),
    text TEXT
);

CREATE TABLE IF NOT EXISTS service_status (
    id SERIAL PRIMARY KEY,
    service_name TEXT NOT NULL,
    status BOOLEAN NOT NULL,
    last_checked TIMESTAMP NOT NULL DEFAULT now()
);


