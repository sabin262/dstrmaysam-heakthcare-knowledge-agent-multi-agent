CREATE TABLE IF NOT EXISTS departments (
    department_id TEXT PRIMARY KEY,
    department_name TEXT NOT NULL,
    specialty_group TEXT NOT NULL,
    location TEXT NOT NULL,
    main_phone TEXT NOT NULL,
    email TEXT NOT NULL,
    service_lead TEXT NOT NULL,
    escalation_contact TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'all_staff'
);

CREATE TABLE IF NOT EXISTS doctors (
    doctor_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    grade TEXT NOT NULL,
    specialty TEXT NOT NULL,
    department_id TEXT REFERENCES departments(department_id),
    department_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    bleep TEXT NOT NULL,
    on_call_today BOOLEAN NOT NULL DEFAULT false,
    access_level TEXT NOT NULL DEFAULT 'clinical'
);

CREATE TABLE IF NOT EXISTS wards (
    ward_code TEXT PRIMARY KEY,
    ward_name TEXT NOT NULL,
    department_id TEXT REFERENCES departments(department_id),
    department_name TEXT NOT NULL,
    floor TEXT NOT NULL,
    bed_capacity INTEGER NOT NULL,
    beds_available INTEGER NOT NULL,
    nurse_in_charge TEXT NOT NULL,
    phone TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'all_staff'
);

CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    mrn TEXT UNIQUE NOT NULL,
    nhs_number TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    date_of_birth DATE NOT NULL,
    ward_code TEXT REFERENCES wards(ward_code),
    department_id TEXT REFERENCES departments(department_id),
    department_name TEXT NOT NULL,
    named_consultant TEXT NOT NULL,
    care_status TEXT NOT NULL,
    risk_flags TEXT NOT NULL DEFAULT '',
    access_level TEXT NOT NULL DEFAULT 'clinical'
);

CREATE TABLE IF NOT EXISTS organization_contacts (
    contact_id TEXT PRIMARY KEY,
    contact_type TEXT NOT NULL,
    department_id TEXT REFERENCES departments(department_id),
    department_name TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    role TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    available_hours TEXT NOT NULL,
    escalation_level TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'all_staff'
);

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id TEXT PRIMARY KEY,
    patient_mrn TEXT NOT NULL REFERENCES patients(mrn),
    patient_name TEXT NOT NULL,
    clinic_name TEXT NOT NULL,
    department_id TEXT REFERENCES departments(department_id),
    department_name TEXT NOT NULL,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    clinician_name TEXT NOT NULL,
    status TEXT NOT NULL,
    referral_priority TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'clinical'
);

CREATE TABLE IF NOT EXISTS staff_schedule (
    schedule_id TEXT PRIMARY KEY,
    shift_date DATE NOT NULL,
    department_id TEXT REFERENCES departments(department_id),
    department_name TEXT NOT NULL,
    role TEXT NOT NULL,
    staff_name TEXT NOT NULL,
    shift_start TIME NOT NULL,
    shift_end TIME NOT NULL,
    on_call BOOLEAN NOT NULL DEFAULT false,
    contact TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'clinical'
);

CREATE TABLE IF NOT EXISTS clinic_sessions (
    clinic_id TEXT PRIMARY KEY,
    clinic_name TEXT NOT NULL,
    clinic_date DATE NOT NULL,
    start_time TIME NOT NULL,
    consultant TEXT NOT NULL,
    slots_total INTEGER NOT NULL,
    slots_available INTEGER NOT NULL,
    referral_priority TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'clinical'
);

CREATE TABLE IF NOT EXISTS formulary (
    medicine_id TEXT PRIMARY KEY,
    medicine_name TEXT NOT NULL,
    category TEXT NOT NULL,
    restricted BOOLEAN NOT NULL DEFAULT false,
    approval_required TEXT NOT NULL,
    max_adult_dose TEXT NOT NULL,
    monitoring_required TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'all_staff'
);

CREATE TABLE IF NOT EXISTS equipment_assets (
    asset_id TEXT PRIMARY KEY,
    equipment_type TEXT NOT NULL,
    location TEXT NOT NULL,
    status TEXT NOT NULL,
    last_service_date DATE,
    next_service_due DATE,
    clinical_engineering_contact TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'all_staff'
);

CREATE TABLE IF NOT EXISTS finance_records (
    finance_id TEXT PRIMARY KEY,
    patient_mrn TEXT REFERENCES patients(mrn),
    patient_name TEXT NOT NULL,
    department_id TEXT REFERENCES departments(department_id),
    department_name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    payer_type TEXT NOT NULL,
    amount_due NUMERIC(12,2) NOT NULL DEFAULT 0,
    amount_paid NUMERIC(12,2) NOT NULL DEFAULT 0,
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    invoice_status TEXT NOT NULL,
    last_invoice_date DATE,
    access_level TEXT NOT NULL DEFAULT 'manager'
);

CREATE TABLE IF NOT EXISTS compliance_audits (
    audit_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    department_id TEXT REFERENCES departments(department_id),
    department_name TEXT NOT NULL,
    lead TEXT NOT NULL,
    due_date DATE NOT NULL,
    status TEXT NOT NULL,
    last_score_percent INTEGER NOT NULL DEFAULT 0,
    access_level TEXT NOT NULL DEFAULT 'manager'
);

CREATE TABLE IF NOT EXISTS training_records (
    training_id TEXT PRIMARY KEY,
    staff_name TEXT NOT NULL,
    role TEXT NOT NULL,
    department_id TEXT REFERENCES departments(department_id),
    department_name TEXT NOT NULL,
    training_module TEXT NOT NULL,
    completion_date DATE,
    expiry_date DATE,
    status TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'manager'
);

CREATE INDEX IF NOT EXISTS idx_patients_name ON patients (lower(full_name));
CREATE INDEX IF NOT EXISTS idx_patients_mrn ON patients (lower(mrn));
CREATE INDEX IF NOT EXISTS idx_doctors_name ON doctors (lower(full_name));
CREATE INDEX IF NOT EXISTS idx_doctors_department ON doctors (lower(department_name));
CREATE INDEX IF NOT EXISTS idx_contacts_department ON organization_contacts (lower(department_name));
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments (lower(patient_name), lower(patient_mrn));
CREATE INDEX IF NOT EXISTS idx_staff_schedule_department ON staff_schedule (lower(department_name), shift_date);
CREATE INDEX IF NOT EXISTS idx_staff_schedule_name ON staff_schedule (lower(staff_name));
CREATE INDEX IF NOT EXISTS idx_clinic_sessions_date ON clinic_sessions (clinic_date);
CREATE INDEX IF NOT EXISTS idx_formulary_name ON formulary (lower(medicine_name));
CREATE INDEX IF NOT EXISTS idx_equipment_assets_type ON equipment_assets (lower(equipment_type));
CREATE INDEX IF NOT EXISTS idx_equipment_assets_status ON equipment_assets (lower(status));
CREATE INDEX IF NOT EXISTS idx_finance_records_patient ON finance_records (lower(patient_name), lower(patient_mrn));
