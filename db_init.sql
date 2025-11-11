-- Fälle-Tabelle mit auto-increment ID
CREATE TABLE IF NOT EXISTS cases (
    id SERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    pat_id TEXT NOT NULL,
    gender TEXT,
    birthDate DATE,
    addressAGS TEXT,
    decsisionToInclude BOOLEAN,
    molecularBoardDescisionDate DATE,
    rejectionJustification TEXT,
    mainDiagnosis_date DATE,
    mainDiagnosis_code TEXT,
    ecog INTEGER,
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
    topography_version TEXT
);

-- Konstanten-Tabelle mit auto-increment ID
CREATE TABLE IF NOT EXISTS constants (
    id SERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL
);

-- Beispielwerte initial befüllen
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


ALTER TABLE cases
ADD COLUMN mvConsent JSONB;

ALTER TABLE cases
ADD COLUMN researchConsent JSONB;
