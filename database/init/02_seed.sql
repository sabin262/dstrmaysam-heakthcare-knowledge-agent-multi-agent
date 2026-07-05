INSERT INTO departments VALUES
('DEP-ED','Emergency Department','Urgent and Emergency Care','Level 1, East Wing','020-5555-1001','ed@example.nhs','Dr Marcus Reed','Duty Manager 020-5555-1505','all_staff'),
('DEP-CARD','Cardiology','Medicine','Level 3, North Wing','020-5555-1002','cardiology@example.nhs','Dr Aisha Malik','Cardiology Registrar Bleep 2301','clinical'),
('DEP-RESP','Respiratory','Medicine','Level 4, North Wing','020-5555-1003','respiratory@example.nhs','Dr Laura Evans','Respiratory Registrar Bleep 2302','clinical'),
('DEP-ICU','Intensive Care Unit','Critical Care','Level 2, West Wing','020-5555-1004','icu@example.nhs','Dr Helen Carter','ICU Outreach 020-5555-1101','clinical'),
('DEP-PHAR','Pharmacy','Medicines Management','Level 0, South Wing','020-5555-1005','pharmacy@example.nhs','Priya Shah','Pharmacy Lead 020-5555-1202','all_staff'),
('DEP-MAT','Maternity','Women and Children','Level 5, Maternity Block','020-5555-1006','maternity@example.nhs','Grace Morgan','Obstetric Emergency Bleep 2401','clinical'),
('DEP-PAED','Paediatrics','Women and Children','Level 5, Children Block','020-5555-1007','paediatrics@example.nhs','Dr Omar Hussain','Paediatric Registrar Bleep 2402','clinical'),
('DEP-ONC','Oncology','Cancer Services','Level 6, North Wing','020-5555-1008','oncology@example.nhs','Dr Emily Turner','Oncology Hotline 020-5555-1808','clinical'),
('DEP-RAD','Radiology','Diagnostics','Level 0, Imaging Suite','020-5555-1009','radiology@example.nhs','Dr James Wilson','Urgent Radiology Bleep 2601','clinical'),
('DEP-HR','Human Resources','Corporate Services','Admin Block, Floor 2','020-5555-1010','hr@example.nhs','Sofia Grant','HR Advice 020-5555-1404','hr_manager')
ON CONFLICT (department_id) DO NOTHING;

INSERT INTO doctors VALUES
('DOC-001','Dr Aisha Malik','Consultant Physician','Cardiology','DEP-CARD','Cardiology','020-5555-2101','aisha.malik@example.nhs','2301',true,'clinical'),
('DOC-002','Dr Marcus Reed','Consultant Physician','Emergency Medicine','DEP-ED','Emergency Department','020-5555-2102','marcus.reed@example.nhs','2201',true,'clinical'),
('DOC-003','Dr Helen Carter','Consultant Intensivist','Critical Care','DEP-ICU','Intensive Care Unit','020-5555-2103','helen.carter@example.nhs','2501',true,'clinical'),
('DOC-004','Dr Laura Evans','Respiratory Consultant','Respiratory','DEP-RESP','Respiratory','020-5555-2104','laura.evans@example.nhs','2302',false,'clinical'),
('DOC-005','Dr Omar Hussain','Paediatric Consultant','Paediatrics','DEP-PAED','Paediatrics','020-5555-2105','omar.hussain@example.nhs','2402',true,'clinical'),
('DOC-006','Dr Emily Turner','Oncology Consultant','Oncology','DEP-ONC','Oncology','020-5555-2106','emily.turner@example.nhs','2801',false,'clinical'),
('DOC-007','Dr James Wilson','Radiology Consultant','Radiology','DEP-RAD','Radiology','020-5555-2107','james.wilson@example.nhs','2601',true,'clinical'),
('DOC-008','Dr Fatima Khan','Obstetric Consultant','Maternity','DEP-MAT','Maternity','020-5555-2108','fatima.khan@example.nhs','2401',true,'clinical'),
('DOC-009','Dr Ravi Singh','Medical Registrar','General Medicine','DEP-ED','Emergency Department','020-5555-2109','ravi.singh@example.nhs','2202',false,'clinical'),
('DOC-010','Dr Hannah Lewis','Cardiology Registrar','Cardiology','DEP-CARD','Cardiology','020-5555-2110','hannah.lewis@example.nhs','2303',false,'clinical'),
('DOC-011','Dr Yusuf Ahmed','ICU Registrar','Critical Care','DEP-ICU','Intensive Care Unit','020-5555-2111','yusuf.ahmed@example.nhs','2502',false,'clinical'),
('DOC-012','Dr Chloe Ward','Respiratory Registrar','Respiratory','DEP-RESP','Respiratory','020-5555-2112','chloe.ward@example.nhs','2304',true,'clinical')
ON CONFLICT (doctor_id) DO NOTHING;

INSERT INTO wards VALUES
('W01','Emergency Assessment Unit','DEP-ED','Emergency Department','1',28,4,'Daniel Price','020-6666-2201','all_staff'),
('W02','Cardiology Ward A','DEP-CARD','Cardiology','3',24,3,'Mina Patel','020-6666-2202','all_staff'),
('W03','Respiratory Ward B','DEP-RESP','Respiratory','4',26,5,'Nadia Ali','020-6666-2203','all_staff'),
('W04','Intensive Care Unit','DEP-ICU','Intensive Care Unit','2',18,1,'Grace Morgan','020-6666-2204','clinical'),
('W05','Pharmacy Medicines Unit','DEP-PHAR','Pharmacy','0',8,2,'Priya Shah','020-6666-2205','all_staff'),
('W06','Maternity Triage','DEP-MAT','Maternity','5',16,4,'Ella Cooper','020-6666-2206','all_staff'),
('W07','Paediatric Assessment Unit','DEP-PAED','Paediatrics','5',20,3,'Lucy Hall','020-6666-2207','all_staff'),
('W08','Oncology Day Unit','DEP-ONC','Oncology','6',22,6,'Maya Roberts','020-6666-2208','clinical'),
('W09','Radiology Recovery','DEP-RAD','Radiology','0',10,2,'Ben Morris','020-6666-2209','clinical'),
('W10','HR Occupational Health Suite','DEP-HR','Human Resources','Admin 2',6,1,'Sofia Grant','020-6666-2210','hr_manager')
ON CONFLICT (ward_code) DO NOTHING;

INSERT INTO patients VALUES
('PAT-001','MRN10001','9000000001','John Spencer','1958-04-14','W02','DEP-CARD','Cardiology','Dr Aisha Malik','Inpatient','Falls risk','clinical'),
('PAT-002','MRN10002','9000000002','Mary Collins','1971-09-22','W03','DEP-RESP','Respiratory','Dr Laura Evans','Inpatient','Oxygen therapy','clinical'),
('PAT-003','MRN10003','9000000003','Ahmed Rahman','1984-01-05','W04','DEP-ICU','Intensive Care Unit','Dr Helen Carter','Critical care','Sepsis watch','clinical'),
('PAT-004','MRN10004','9000000004','Susan Walker','1949-11-30','W01','DEP-ED','Emergency Department','Dr Marcus Reed','Assessment','High NEWS2','clinical'),
('PAT-005','MRN10005','9000000005','Patricia Young','1992-03-18','W06','DEP-MAT','Maternity','Dr Fatima Khan','Maternity review','Postpartum observation','clinical'),
('PAT-006','MRN10006','9000000006','Leo Bennett','2018-07-02','W07','DEP-PAED','Paediatrics','Dr Omar Hussain','Inpatient','Paediatric observation','clinical'),
('PAT-007','MRN10007','9000000007','Robert Green','1966-12-12','W08','DEP-ONC','Oncology','Dr Emily Turner','Day case','Neutropenic risk','clinical'),
('PAT-008','MRN10008','9000000008','Linda Hughes','1955-06-25','W09','DEP-RAD','Radiology','Dr James Wilson','Recovery','Contrast reaction history','clinical'),
('PAT-009','MRN10009','9000000009','George Clarke','1978-10-09','W02','DEP-CARD','Cardiology','Dr Hannah Lewis','Inpatient','Anticoagulation','clinical'),
('PAT-010','MRN10010','9000000010','Maya Roberts','1989-05-16','W03','DEP-RESP','Respiratory','Dr Chloe Ward','Inpatient','Isolation precautions','clinical'),
('PAT-011','MRN10011','9000000011','Thomas Green','1961-02-28','W04','DEP-ICU','Intensive Care Unit','Dr Yusuf Ahmed','Critical care','Ventilated','clinical'),
('PAT-012','MRN10012','9000000012','Ella Cooper','2001-08-04','W01','DEP-ED','Emergency Department','Dr Ravi Singh','Assessment','Safeguarding note','clinical')
ON CONFLICT (patient_id) DO NOTHING;

INSERT INTO organization_contacts VALUES
('CON-001','Clinical escalation','DEP-ICU','Intensive Care Unit','ICU Outreach','ICU Outreach Team','020-5555-1101','icu.outreach@example.nhs','24/7','urgent','clinical'),
('CON-002','Medication safety','DEP-PHAR','Pharmacy','Pharmacy Lead','Chief Pharmacist Office','020-5555-1202','pharmacy.lead@example.nhs','08:00-20:00','urgent','clinical'),
('CON-003','Data breach','DEP-ED','Emergency Department','Information Governance Helpdesk','Information Governance','020-5555-1303','ig@example.nhs','24/7 urgent line','urgent','all_staff'),
('CON-004','Staff absence','DEP-HR','Human Resources','HR Advice','HR Advisory Team','020-5555-1404','hr.advice@example.nhs','09:00-17:00','routine','hr_manager'),
('CON-005','Duty manager','DEP-ED','Emergency Department','Duty Manager','Site Operations','020-5555-1505','duty.manager@example.nhs','24/7','urgent','all_staff'),
('CON-006','Safeguarding','DEP-PAED','Paediatrics','Safeguarding Lead','Safeguarding Team','020-5555-1606','safeguarding@example.nhs','24/7 urgent line','urgent','all_staff'),
('CON-007','Obstetric emergency','DEP-MAT','Maternity','Obstetric Emergency Team','Maternity Emergency Response','020-5555-1707','obs.emergency@example.nhs','24/7','urgent','clinical'),
('CON-008','Oncology hotline','DEP-ONC','Oncology','Oncology Hotline','Acute Oncology Service','020-5555-1808','oncology.hotline@example.nhs','08:00-22:00','urgent','clinical'),
('CON-009','Radiology urgent report','DEP-RAD','Radiology','Urgent Radiology Desk','Radiology Coordinator','020-5555-1909','urgent.radiology@example.nhs','08:00-20:00','urgent','clinical'),
('CON-010','Cardiology advice','DEP-CARD','Cardiology','Cardiology Registrar','Cardiology On-call','020-5555-1910','cardiology.oncall@example.nhs','24/7','urgent','clinical'),
('CON-011','Respiratory advice','DEP-RESP','Respiratory','Respiratory Registrar','Respiratory On-call','020-5555-1911','respiratory.oncall@example.nhs','24/7','urgent','clinical'),
('CON-012','Occupational health','DEP-HR','Human Resources','Occupational Health','Occupational Health Team','020-5555-1912','occupational.health@example.nhs','09:00-17:00','routine','hr_manager')
ON CONFLICT (contact_id) DO NOTHING;

INSERT INTO appointments VALUES
('APT-001','MRN10001','John Spencer','Cardiology Follow-up','DEP-CARD','Cardiology','2026-06-24','09:00','Dr Aisha Malik','Booked','Routine','clinical'),
('APT-002','MRN10002','Mary Collins','Respiratory Review','DEP-RESP','Respiratory','2026-06-24','10:30','Dr Laura Evans','Booked','Urgent','clinical'),
('APT-003','MRN10003','Ahmed Rahman','ICU Stepdown Review','DEP-ICU','Intensive Care Unit','2026-06-25','11:00','Dr Helen Carter','Booked','Urgent','clinical'),
('APT-004','MRN10004','Susan Walker','ED Safety Net Clinic','DEP-ED','Emergency Department','2026-06-25','14:00','Dr Marcus Reed','Booked','Post-discharge','clinical'),
('APT-005','MRN10005','Patricia Young','Maternity Follow-up','DEP-MAT','Maternity','2026-06-26','09:30','Dr Fatima Khan','Booked','Routine','clinical'),
('APT-006','MRN10006','Leo Bennett','Paediatric Review','DEP-PAED','Paediatrics','2026-06-26','13:30','Dr Omar Hussain','Booked','Urgent','clinical'),
('APT-007','MRN10007','Robert Green','Oncology Day Unit','DEP-ONC','Oncology','2026-06-27','08:30','Dr Emily Turner','Booked','Two-week wait','clinical'),
('APT-008','MRN10008','Linda Hughes','Radiology Contrast Review','DEP-RAD','Radiology','2026-06-27','15:00','Dr James Wilson','Booked','Routine','clinical')
ON CONFLICT (appointment_id) DO NOTHING;

INSERT INTO formulary VALUES
('MED-001','Vancomycin','Antibiotic',true,'Consultant approval and pharmacist verification','Per protocol by levels','Therapeutic drug monitoring','clinical'),
('MED-002','Gentamicin','Antibiotic',true,'Consultant approval and pharmacist verification','Dose by weight and renal function','Drug levels and renal function','clinical'),
('MED-003','Insulin infusion','Endocrine',true,'Two staff checks and protocol','Protocol dependent','Hourly glucose monitoring','clinical'),
('MED-004','Warfarin','Anticoagulant',true,'Prescriber and pharmacist verification','Dose by INR','INR monitoring','clinical'),
('MED-005','Paracetamol','Analgesic',false,'No special approval','1 g every 4-6 hours, max 4 g/day','Check combined products','all_staff'),
('MED-006','Salbutamol','Respiratory',false,'No special approval','Per inhaler or nebuliser protocol','Observe response','all_staff'),
('MED-007','Noradrenaline','Critical care',true,'ICU consultant approval','Protocol dependent','Continuous blood pressure monitoring','clinical'),
('MED-008','Meropenem','Antibiotic',true,'Microbiology or consultant approval','Dose by renal function','Renal function and cultures','clinical')
ON CONFLICT (medicine_id) DO NOTHING;

INSERT INTO departments VALUES
('DEP-RENAL','Renal','Medicine','Level 4, East Wing','020-5555-1011','renal@example.nhs','Dr Nadia Ali','Renal Registrar Bleep 2701','clinical'),
('DEP-SURG','Surgery','Surgical Services','Level 2, East Wing','020-5555-1012','surgery@example.nhs','Dr Adam White','Surgical Registrar Bleep 2702','clinical'),
('DEP-MH','Mental Health','Community and Mental Health','Level 1, South Wing','020-5555-1013','mental.health@example.nhs','Dr Fatima Khan','Mental Health Liaison 020-5555-1701','clinical'),
('DEP-COMM','Community Care','Community Services','Community Hub','020-5555-1014','community@example.nhs','Laura Evans','Community Coordinator 020-5555-1702','all_staff'),
('DEP-PATH','Pathology','Diagnostics','Level 0, Laboratory Block','020-5555-1015','pathology@example.nhs','Dr Mina Patel','Critical Results 020-5555-1703','clinical'),
('DEP-FIN','Finance','Corporate Services','Admin Block, Floor 1','020-5555-1016','finance@example.nhs','Nadia Brooks','Finance Helpdesk 020-5555-1704','manager')
ON CONFLICT (department_id) DO NOTHING;

INSERT INTO doctors VALUES
('DOC-013','Dr Nadia Ali','Consultant Nephrologist','Renal','DEP-RENAL','Renal','020-5555-2113','nadia.ali@example.nhs','2701',true,'clinical'),
('DOC-014','Dr Adam White','Consultant Surgeon','Surgery','DEP-SURG','Surgery','020-5555-2114','adam.white@example.nhs','2702',true,'clinical'),
('DOC-015','Dr Priya Shah','Consultant Psychiatrist','Mental Health','DEP-MH','Mental Health','020-5555-2115','priya.shah@example.nhs','2703',false,'clinical'),
('DOC-016','Dr Ben Morris','Community Consultant','Community Care','DEP-COMM','Community Care','020-5555-2116','ben.morris@example.nhs','2704',false,'clinical'),
('DOC-017','Dr Mina Patel','Consultant Pathologist','Pathology','DEP-PATH','Pathology','020-5555-2117','mina.patel@example.nhs','2705',true,'clinical'),
('DOC-018','Dr Daniel Price','Emergency Registrar','Emergency Medicine','DEP-ED','Emergency Department','020-5555-2118','daniel.price@example.nhs','2203',true,'clinical'),
('DOC-019','Dr Grace Morgan','Maternity Registrar','Maternity','DEP-MAT','Maternity','020-5555-2119','grace.morgan@example.nhs','2403',false,'clinical'),
('DOC-020','Dr Liam Scott','Oncology Registrar','Oncology','DEP-ONC','Oncology','020-5555-2120','liam.scott@example.nhs','2802',true,'clinical')
ON CONFLICT (doctor_id) DO NOTHING;

INSERT INTO wards VALUES
('W11','Renal Ward C','DEP-RENAL','Renal','4',28,7,'Noah Brooks','020-6666-2211','all_staff'),
('W12','Surgical Assessment Unit','DEP-SURG','Surgery','2',30,6,'Aisha Malik','020-6666-2212','all_staff'),
('W13','Mental Health Liaison Suite','DEP-MH','Mental Health','1',12,2,'Fatima Khan','020-6666-2213','clinical'),
('W14','Community Discharge Lounge','DEP-COMM','Community Care','G',18,5,'Laura Evans','020-6666-2214','all_staff'),
('W15','Pathology Sample Reception','DEP-PATH','Pathology','0',8,1,'Mina Patel','020-6666-2215','clinical'),
('W16','Short Stay Unit','DEP-ED','Emergency Department','1',32,8,'Marcus Reed','020-6666-2216','all_staff')
ON CONFLICT (ward_code) DO NOTHING;

INSERT INTO patients VALUES
('PAT-013','MRN10013','9000000013','Peter Hughes','1975-03-12','W11','DEP-RENAL','Renal','Dr Nadia Ali','Inpatient','Fluid restriction','clinical'),
('PAT-014','MRN10014','9000000014','Nadia Brooks','1981-01-28','W12','DEP-SURG','Surgery','Dr Adam White','Pre-op','Consent pending','clinical'),
('PAT-015','MRN10015','9000000015','Lucy Hall','1938-05-19','W13','DEP-MH','Mental Health','Dr Priya Shah','Liaison review','Falls risk','clinical'),
('PAT-016','MRN10016','9000000016','Marcus Reed','1969-07-07','W14','DEP-COMM','Community Care','Dr Ben Morris','Discharge planning','Package of care','clinical'),
('PAT-017','MRN10017','9000000017','Sofia Grant','1999-09-14','W15','DEP-PATH','Pathology','Dr Mina Patel','Day case','Critical sample follow-up','clinical'),
('PAT-018','MRN10018','9000000018','Noah Brooks','1952-02-03','W16','DEP-ED','Emergency Department','Dr Daniel Price','Assessment','Chest pain pathway','clinical'),
('PAT-019','MRN10019','9000000019','Daniel Price','1973-10-23','W02','DEP-CARD','Cardiology','Dr Aisha Malik','Inpatient','Telemetry','clinical'),
('PAT-020','MRN10020','9000000020','Grace Morgan','1987-12-18','W06','DEP-MAT','Maternity','Dr Grace Morgan','Maternity review','Hypertension monitoring','clinical'),
('PAT-021','MRN10021','9000000021','Liam Scott','1964-06-02','W08','DEP-ONC','Oncology','Dr Liam Scott','Day case','Chemotherapy observation','clinical'),
('PAT-022','MRN10022','9000000022','Nadia Ali','1979-04-21','W03','DEP-RESP','Respiratory','Dr Chloe Ward','Inpatient','Nebuliser therapy','clinical')
ON CONFLICT (patient_id) DO NOTHING;

INSERT INTO organization_contacts VALUES
('CON-013','Renal escalation','DEP-RENAL','Renal','Renal Registrar','Renal On-call','020-5555-1913','renal.oncall@example.nhs','24/7','urgent','clinical'),
('CON-014','Surgical escalation','DEP-SURG','Surgery','Surgical Registrar','Surgical On-call','020-5555-1914','surgery.oncall@example.nhs','24/7','urgent','clinical'),
('CON-015','Mental health liaison','DEP-MH','Mental Health','Mental Health Liaison','Liaison Team','020-5555-1915','mh.liaison@example.nhs','24/7','urgent','clinical'),
('CON-016','Community discharge','DEP-COMM','Community Care','Community Coordinator','Discharge Support','020-5555-1916','community.discharge@example.nhs','08:00-20:00','routine','all_staff'),
('CON-017','Pathology critical result','DEP-PATH','Pathology','Critical Results Desk','Biomedical Scientist','020-5555-1917','critical.results@example.nhs','24/7','urgent','clinical'),
('CON-018','Patient finance','DEP-FIN','Finance','Patient Accounts','Finance Team','020-5555-1918','patient.accounts@example.nhs','09:00-17:00','routine','manager')
ON CONFLICT (contact_id) DO NOTHING;

INSERT INTO appointments VALUES
('APT-009','MRN10009','George Clarke','Cardiology Echo Review','DEP-CARD','Cardiology','2026-06-28','09:15','Dr Hannah Lewis','Booked','Routine','clinical'),
('APT-010','MRN10010','Maya Roberts','Respiratory Virtual Ward','DEP-RESP','Respiratory','2026-06-28','10:45','Dr Chloe Ward','Booked','Urgent','clinical'),
('APT-011','MRN10011','Thomas Green','ICU Family Update','DEP-ICU','Intensive Care Unit','2026-06-28','12:00','Dr Yusuf Ahmed','Booked','Urgent','clinical'),
('APT-012','MRN10012','Ella Cooper','ED Review Clinic','DEP-ED','Emergency Department','2026-06-29','14:30','Dr Ravi Singh','Booked','Post-discharge','clinical'),
('APT-013','MRN10013','Peter Hughes','Renal Review','DEP-RENAL','Renal','2026-06-29','15:00','Dr Nadia Ali','Booked','Routine','clinical'),
('APT-014','MRN10014','Nadia Brooks','Surgical Pre-assessment','DEP-SURG','Surgery','2026-06-30','08:45','Dr Adam White','Booked','Urgent','clinical'),
('APT-015','MRN10015','Lucy Hall','Mental Health Liaison Review','DEP-MH','Mental Health','2026-06-30','11:30','Dr Priya Shah','Booked','Urgent','clinical'),
('APT-016','MRN10016','Marcus Reed','Community Discharge Review','DEP-COMM','Community Care','2026-07-01','13:00','Dr Ben Morris','Booked','Routine','clinical'),
('APT-017','MRN10017','Sofia Grant','Pathology Follow-up','DEP-PATH','Pathology','2026-07-01','16:00','Dr Mina Patel','Booked','Routine','clinical'),
('APT-018','MRN10018','Noah Brooks','Chest Pain Clinic','DEP-ED','Emergency Department','2026-07-02','09:40','Dr Daniel Price','Booked','Urgent','clinical')
ON CONFLICT (appointment_id) DO NOTHING;

INSERT INTO staff_schedule VALUES
('SCH-001','2026-06-28','DEP-CARD','Cardiology','Consultant Physician','Ravi Singh','07:00','07:00',true,'cardiology.oncall@example.nhs','clinical'),
('SCH-002','2026-06-28','DEP-PAED','Paediatrics','Clinical Site Manager','Aisha Malik','08:00','15:00',true,'paediatrics.oncall@example.nhs','clinical'),
('SCH-003','2026-06-28','DEP-RESP','Respiratory','Registrar','Ella Cooper','09:00','17:00',true,'respiratory.oncall@example.nhs','clinical'),
('SCH-004','2026-06-28','DEP-ED','Emergency Department','Staff Nurse','Marcus Reed','08:00','15:00',true,'emergency_department.oncall@example.nhs','clinical'),
('SCH-005','2026-06-28','DEP-ICU','Intensive Care Unit','Consultant Intensivist','Helen Carter','19:00','07:00',true,'icu.oncall@example.nhs','clinical'),
('SCH-006','2026-06-28','DEP-PHAR','Pharmacy','Pharmacist','Chloe Ward','07:00','15:00',true,'pharmacy.oncall@example.nhs','clinical'),
('SCH-007','2026-06-29','DEP-RENAL','Renal','Therapist','Nadia Ali','08:00','15:00',true,'renal.oncall@example.nhs','clinical'),
('SCH-008','2026-06-29','DEP-SURG','Surgery','Pharmacist','Adam White','09:00','17:00',true,'surgery.oncall@example.nhs','clinical'),
('SCH-009','2026-06-29','DEP-ONC','Oncology','Staff Nurse','Ben Morris','19:00','20:00',true,'oncology.oncall@example.nhs','clinical'),
('SCH-010','2026-06-29','DEP-MAT','Maternity','Senior Nurse','Liam Scott','08:00','15:00',true,'maternity.oncall@example.nhs','clinical'),
('SCH-011','2026-06-30','DEP-PATH','Pathology','Ward Manager','Mina Patel','09:00','17:00',true,'pathology.oncall@example.nhs','manager'),
('SCH-012','2026-06-30','DEP-RAD','Radiology','Biomedical Scientist','Priya Shah','19:00','20:00',true,'radiology.oncall@example.nhs','clinical')
ON CONFLICT (schedule_id) DO NOTHING;

INSERT INTO clinic_sessions VALUES
('CLN-001','Emergency Department Follow-up Clinic','2026-06-20','08:30','Helen Carter',10,0,'Routine','clinical'),
('CLN-002','Cardiology Follow-up Clinic','2026-06-21','09:00','Omar Hussain',11,1,'Urgent','clinical'),
('CLN-003','Respiratory Follow-up Clinic','2026-06-22','13:00','Laura Evans',12,2,'Two-week wait','clinical'),
('CLN-004','ICU Follow-up Clinic','2026-06-23','14:00','James Wilson',13,3,'Post-discharge','clinical'),
('CLN-005','Pharmacy Follow-up Clinic','2026-06-24','08:30','Fatima Khan',14,4,'Routine','clinical'),
('CLN-006','Maternity Follow-up Clinic','2026-06-25','09:00','Ravi Singh',15,5,'Urgent','clinical'),
('CLN-007','Paediatrics Follow-up Clinic','2026-06-26','13:00','Emily Turner',16,0,'Two-week wait','clinical'),
('CLN-008','Oncology Follow-up Clinic','2026-06-27','14:00','Grace Morgan',17,1,'Post-discharge','clinical'),
('CLN-009','Renal Follow-up Clinic','2026-06-28','08:30','Liam Scott',10,2,'Routine','clinical'),
('CLN-010','Surgery Follow-up Clinic','2026-06-29','09:00','Nadia Ali',11,3,'Urgent','clinical')
ON CONFLICT (clinic_id) DO NOTHING;

INSERT INTO equipment_assets VALUES
('EQ-0001','Infusion pump','Emergency Department Ward','Available','2026-05-21','2026-07-20','clinical.engineering@example.nhs','all_staff'),
('EQ-0002','Defibrillator','Cardiology Ward','In use','2026-05-16','2026-07-24','clinical.engineering@example.nhs','all_staff'),
('EQ-0003','Ventilator','Respiratory Ward','Fault logged','2026-05-11','2026-07-28','clinical.engineering@example.nhs','all_staff'),
('EQ-0004','ECG machine','ICU Ward','Maintenance due','2026-05-06','2026-08-01','clinical.engineering@example.nhs','all_staff'),
('EQ-0005','Syringe driver','Pharmacy Ward','Available','2026-05-01','2026-08-05','clinical.engineering@example.nhs','all_staff'),
('EQ-0006','Blood pressure monitor','Maternity Ward','In use','2026-04-26','2026-08-09','clinical.engineering@example.nhs','all_staff'),
('EQ-0007','Patient hoist','Paediatrics Ward','Fault logged','2026-04-21','2026-08-13','clinical.engineering@example.nhs','all_staff'),
('EQ-0008','Ultrasound','Oncology Ward','Maintenance due','2026-04-16','2026-08-17','clinical.engineering@example.nhs','all_staff'),
('EQ-0009','Oxygen concentrator','Renal Ward','Available','2026-04-11','2026-08-21','clinical.engineering@example.nhs','all_staff'),
('EQ-0010','Dialysis machine','Renal Ward','In use','2026-04-06','2026-08-25','clinical.engineering@example.nhs','all_staff'),
('EQ-0011','Defibrillator','Pathology Ward','Maintenance due','2026-04-01','2026-08-29','clinical.engineering@example.nhs','all_staff'),
('EQ-0012','Ventilator','Mental Health Ward','Available','2026-03-22','2026-09-06','clinical.engineering@example.nhs','all_staff')
ON CONFLICT (asset_id) DO NOTHING;

INSERT INTO finance_records VALUES
('FIN-001','MRN10001','John Spencer','DEP-CARD','Cardiology','Insured care','Private insurer',1250.00,800.00,450.00,'Part paid','2026-06-20','manager'),
('FIN-002','MRN10002','Mary Collins','DEP-RESP','Respiratory','NHS recharge','NHS internal',420.00,420.00,0.00,'Paid','2026-06-21','manager'),
('FIN-003','MRN10003','Ahmed Rahman','DEP-ICU','Intensive Care Unit','Critical care package','Private insurer',6200.00,3000.00,3200.00,'Pre-authorisation pending','2026-06-22','manager'),
('FIN-004','MRN10006','Leo Bennett','DEP-PAED','Paediatrics','Paediatric review','NHS internal',180.00,0.00,180.00,'Pending','2026-06-23','manager'),
('FIN-005','MRN10007','Robert Green','DEP-ONC','Oncology','Oncology day case','Private insurer',2400.00,2400.00,0.00,'Paid','2026-06-24','manager'),
('FIN-006','MRN10013','Peter Hughes','DEP-RENAL','Renal','Renal procedure','Self-pay',950.00,200.00,750.00,'Part paid','2026-06-25','manager'),
('FIN-007','MRN10014','Nadia Brooks','DEP-SURG','Surgery','Surgical pre-assessment','Private insurer',780.00,0.00,780.00,'Pending','2026-06-26','manager'),
('FIN-008','MRN10016','Marcus Reed','DEP-COMM','Community Care','Community package','NHS internal',320.00,320.00,0.00,'Paid','2026-06-27','manager')
ON CONFLICT (finance_id) DO NOTHING;

INSERT INTO formulary VALUES
('MED-009','Amikacin','Antibiotic',true,'Consultant approval and pharmacist verification','Dose by renal function','Drug levels and renal function','clinical'),
('MED-010','Heparin infusion','Anticoagulant',true,'Two staff checks and prescriber verification','Protocol dependent','APTT and platelets','clinical'),
('MED-011','Morphine','Analgesic',false,'No special approval','Dose by renal function','Sedation and respiratory rate','all_staff'),
('MED-012','Oxycodone','Analgesic',false,'No special approval','See formulary notes','Sedation score','all_staff'),
('MED-013','Fentanyl patch','Analgesic',false,'No special approval','Per protocol','Respiratory rate','clinical'),
('MED-014','Chemotherapy agent A','Oncology',true,'Oncology consultant approval','Dose by body surface area','FBC and renal function','clinical')
ON CONFLICT (medicine_id) DO NOTHING;

INSERT INTO departments VALUES
('DEP-DERM','Dermatology','Medicine','Level 3, East Wing','020-5555-1017','dermatology@example.nhs','Dr Isla Moore','Dermatology Advice 020-5555-1717','clinical'),
('DEP-ENDO','Endocrinology','Medicine','Level 4, West Wing','020-5555-1018','endocrinology@example.nhs','Dr Ethan Clarke','Diabetes Registrar Bleep 2718','clinical'),
('DEP-GASTRO','Gastroenterology','Medicine','Level 4, South Wing','020-5555-1019','gastro@example.nhs','Dr Olivia Hayes','GI Bleed Bleep 2719','clinical'),
('DEP-NEURO','Neurology','Neurosciences','Level 5, East Wing','020-5555-1020','neurology@example.nhs','Dr Samuel King','Stroke Registrar Bleep 2720','clinical'),
('DEP-ORTH','Orthopaedics','Surgical Services','Level 2, West Wing','020-5555-1021','orthopaedics@example.nhs','Dr Mia Foster','Trauma Coordinator 020-5555-1721','clinical'),
('DEP-URO','Urology','Surgical Services','Level 2, North Wing','020-5555-1022','urology@example.nhs','Dr Jacob Ellis','Urology Registrar Bleep 2722','clinical'),
('DEP-RHEUM','Rheumatology','Medicine','Level 3, South Wing','020-5555-1023','rheumatology@example.nhs','Dr Amara Khan','Rheumatology Advice 020-5555-1723','clinical'),
('DEP-HAEM','Haematology','Cancer Services','Level 6, East Wing','020-5555-1024','haematology@example.nhs','Dr Lucas Brown','Haematology Registrar Bleep 2724','clinical'),
('DEP-DIAB','Diabetes Service','Medicine','Level 4, West Wing','020-5555-1025','diabetes@example.nhs','Nurse Zoe Turner','Diabetes Specialist Nurse 020-5555-1725','clinical'),
('DEP-THER','Therapies','Rehabilitation','Level 1, West Wing','020-5555-1026','therapies@example.nhs','Amelia Scott','Therapies Coordinator 020-5555-1726','all_staff')
ON CONFLICT (department_id) DO NOTHING;

INSERT INTO doctors VALUES
('DOC-021','Dr Isla Moore','Consultant Dermatologist','Dermatology','DEP-DERM','Dermatology','020-5555-2121','isla.moore@example.nhs','2721',true,'clinical'),
('DOC-022','Dr Ethan Clarke','Consultant Endocrinologist','Endocrinology','DEP-ENDO','Endocrinology','020-5555-2122','ethan.clarke@example.nhs','2722',true,'clinical'),
('DOC-023','Dr Olivia Hayes','Consultant Gastroenterologist','Gastroenterology','DEP-GASTRO','Gastroenterology','020-5555-2123','olivia.hayes@example.nhs','2723',false,'clinical'),
('DOC-024','Dr Samuel King','Consultant Neurologist','Neurology','DEP-NEURO','Neurology','020-5555-2124','samuel.king@example.nhs','2724',true,'clinical'),
('DOC-025','Dr Mia Foster','Consultant Orthopaedic Surgeon','Orthopaedics','DEP-ORTH','Orthopaedics','020-5555-2125','mia.foster@example.nhs','2725',true,'clinical'),
('DOC-026','Dr Jacob Ellis','Consultant Urologist','Urology','DEP-URO','Urology','020-5555-2126','jacob.ellis@example.nhs','2726',false,'clinical'),
('DOC-027','Dr Amara Khan','Consultant Rheumatologist','Rheumatology','DEP-RHEUM','Rheumatology','020-5555-2127','amara.khan@example.nhs','2727',false,'clinical'),
('DOC-028','Dr Lucas Brown','Consultant Haematologist','Haematology','DEP-HAEM','Haematology','020-5555-2128','lucas.brown@example.nhs','2728',true,'clinical'),
('DOC-029','Dr Zoe Turner','Diabetes Consultant','Diabetes','DEP-DIAB','Diabetes Service','020-5555-2129','zoe.turner@example.nhs','2729',true,'clinical'),
('DOC-030','Dr Amelia Scott','Rehabilitation Consultant','Therapies','DEP-THER','Therapies','020-5555-2130','amelia.scott@example.nhs','2730',false,'clinical')
ON CONFLICT (doctor_id) DO NOTHING;

INSERT INTO wards VALUES
('W17','Dermatology Treatment Unit','DEP-DERM','Dermatology','3',14,5,'Isla Moore','020-6666-2217','all_staff'),
('W18','Endocrine Assessment Bay','DEP-ENDO','Endocrinology','4',16,4,'Zoe Turner','020-6666-2218','all_staff'),
('W19','Gastroenterology Ward','DEP-GASTRO','Gastroenterology','4',24,6,'Olivia Hayes','020-6666-2219','clinical'),
('W20','Neurology Stroke Unit','DEP-NEURO','Neurology','5',22,3,'Samuel King','020-6666-2220','clinical'),
('W21','Orthopaedic Trauma Ward','DEP-ORTH','Orthopaedics','2',30,7,'Mia Foster','020-6666-2221','all_staff'),
('W22','Urology Day Unit','DEP-URO','Urology','2',18,5,'Jacob Ellis','020-6666-2222','all_staff'),
('W23','Rheumatology Infusion Suite','DEP-RHEUM','Rheumatology','3',12,3,'Amara Khan','020-6666-2223','clinical'),
('W24','Haematology Day Unit','DEP-HAEM','Haematology','6',20,4,'Lucas Brown','020-6666-2224','clinical'),
('W25','Diabetes Education Room','DEP-DIAB','Diabetes Service','4',10,2,'Zoe Turner','020-6666-2225','all_staff'),
('W26','Therapy Gym','DEP-THER','Therapies','1',15,8,'Amelia Scott','020-6666-2226','all_staff')
ON CONFLICT (ward_code) DO NOTHING;

INSERT INTO patients VALUES
('PAT-023','MRN10023','9000000023','Isabella Turner','1990-01-11','W17','DEP-DERM','Dermatology','Dr Isla Moore','Outpatient','Biologic therapy review','clinical'),
('PAT-024','MRN10024','9000000024','Henry Adams','1968-05-03','W18','DEP-ENDO','Endocrinology','Dr Ethan Clarke','Assessment','Insulin titration','clinical'),
('PAT-025','MRN10025','9000000025','Olivia Carter','1976-08-19','W19','DEP-GASTRO','Gastroenterology','Dr Olivia Hayes','Inpatient','Endoscopy planned','clinical'),
('PAT-026','MRN10026','9000000026','Samuel Wright','1959-12-07','W20','DEP-NEURO','Neurology','Dr Samuel King','Stroke unit','Swallow assessment','clinical'),
('PAT-027','MRN10027','9000000027','Mia Phillips','1982-02-14','W21','DEP-ORTH','Orthopaedics','Dr Mia Foster','Post-op','Mobility plan','clinical'),
('PAT-028','MRN10028','9000000028','Jacob Hill','1947-09-27','W22','DEP-URO','Urology','Dr Jacob Ellis','Day case','Catheter review','clinical'),
('PAT-029','MRN10029','9000000029','Amara Bell','1995-11-08','W23','DEP-RHEUM','Rheumatology','Dr Amara Khan','Day case','Infusion monitoring','clinical'),
('PAT-030','MRN10030','9000000030','Lucas Wood','1970-04-30','W24','DEP-HAEM','Haematology','Dr Lucas Brown','Day case','Transfusion observation','clinical'),
('PAT-031','MRN10031','9000000031','Zoe Martin','1988-06-21','W25','DEP-DIAB','Diabetes Service','Dr Zoe Turner','Education','Pump training','clinical'),
('PAT-032','MRN10032','9000000032','Amelia Cook','1962-10-16','W26','DEP-THER','Therapies','Dr Amelia Scott','Rehabilitation','Falls prevention','clinical')
ON CONFLICT (patient_id) DO NOTHING;

INSERT INTO organization_contacts VALUES
('CON-019','Dermatology advice','DEP-DERM','Dermatology','Dermatology Nurse Advice','Specialist Nurse','020-5555-1919','derm.advice@example.nhs','09:00-17:00','routine','clinical'),
('CON-020','Diabetes escalation','DEP-DIAB','Diabetes Service','Diabetes Specialist Nurse','Specialist Nurse','020-5555-1920','diabetes.nurse@example.nhs','08:00-20:00','urgent','clinical'),
('CON-021','GI bleed escalation','DEP-GASTRO','Gastroenterology','GI Registrar','Gastroenterology On-call','020-5555-1921','gi.oncall@example.nhs','24/7','urgent','clinical'),
('CON-022','Stroke thrombolysis','DEP-NEURO','Neurology','Stroke Registrar','Stroke Team','020-5555-1922','stroke.team@example.nhs','24/7','urgent','clinical'),
('CON-023','Trauma coordinator','DEP-ORTH','Orthopaedics','Trauma Coordinator','Orthopaedic Team','020-5555-1923','trauma.coord@example.nhs','07:00-19:00','urgent','clinical'),
('CON-024','Urology advice','DEP-URO','Urology','Urology Registrar','Urology On-call','020-5555-1924','urology.oncall@example.nhs','24/7','urgent','clinical'),
('CON-025','Rheumatology biologics','DEP-RHEUM','Rheumatology','Biologics Nurse','Specialist Nurse','020-5555-1925','biologics@example.nhs','09:00-17:00','routine','clinical'),
('CON-026','Haematology transfusion','DEP-HAEM','Haematology','Transfusion Practitioner','Haematology Team','020-5555-1926','transfusion@example.nhs','08:00-20:00','urgent','clinical'),
('CON-027','Therapies discharge','DEP-THER','Therapies','Therapy Coordinator','Therapies Team','020-5555-1927','therapies@example.nhs','08:00-18:00','routine','all_staff'),
('CON-028','Endocrine advice','DEP-ENDO','Endocrinology','Endocrine Registrar','Endocrinology On-call','020-5555-1928','endo.oncall@example.nhs','24/7','urgent','clinical')
ON CONFLICT (contact_id) DO NOTHING;

INSERT INTO appointments VALUES
('APT-019','MRN10023','Isabella Turner','Dermatology Biologics Review','DEP-DERM','Dermatology','2026-07-02','10:00','Dr Isla Moore','Booked','Routine','clinical'),
('APT-020','MRN10024','Henry Adams','Endocrine Diabetes Review','DEP-ENDO','Endocrinology','2026-07-02','11:00','Dr Ethan Clarke','Booked','Urgent','clinical'),
('APT-021','MRN10025','Olivia Carter','Gastro Endoscopy Planning','DEP-GASTRO','Gastroenterology','2026-07-03','09:20','Dr Olivia Hayes','Booked','Routine','clinical'),
('APT-022','MRN10026','Samuel Wright','Stroke Follow-up Clinic','DEP-NEURO','Neurology','2026-07-03','13:40','Dr Samuel King','Booked','Urgent','clinical'),
('APT-023','MRN10027','Mia Phillips','Orthopaedic Trauma Review','DEP-ORTH','Orthopaedics','2026-07-04','08:45','Dr Mia Foster','Booked','Post-discharge','clinical'),
('APT-024','MRN10028','Jacob Hill','Urology Catheter Review','DEP-URO','Urology','2026-07-04','12:10','Dr Jacob Ellis','Booked','Routine','clinical'),
('APT-025','MRN10029','Amara Bell','Rheumatology Infusion Review','DEP-RHEUM','Rheumatology','2026-07-05','09:00','Dr Amara Khan','Booked','Routine','clinical'),
('APT-026','MRN10030','Lucas Wood','Haematology Day Unit Review','DEP-HAEM','Haematology','2026-07-05','14:15','Dr Lucas Brown','Booked','Urgent','clinical'),
('APT-027','MRN10031','Zoe Martin','Diabetes Pump Training','DEP-DIAB','Diabetes Service','2026-07-06','10:30','Dr Zoe Turner','Booked','Routine','clinical'),
('APT-028','MRN10032','Amelia Cook','Therapies Falls Review','DEP-THER','Therapies','2026-07-06','15:00','Dr Amelia Scott','Booked','Routine','clinical')
ON CONFLICT (appointment_id) DO NOTHING;

INSERT INTO formulary VALUES
('MED-015','Apixaban','Anticoagulant',false,'Renal function check required','Dose by indication and renal function','Renal function and bleeding risk','clinical'),
('MED-016','Dapagliflozin','Endocrine',false,'Diabetes or heart failure indication','10 mg once daily where appropriate','Renal function and ketones if unwell','clinical'),
('MED-017','Prednisolone','Steroid',false,'No special approval','Dose by indication','Glucose and infection risk','all_staff'),
('MED-018','Methotrexate','Rheumatology',true,'Specialist initiation and shared-care agreement','Weekly dose only','FBC, LFT and renal function','clinical'),
('MED-019','Adalimumab','Biologic',true,'Specialist biologics approval','Per specialist protocol','TB screen and infection monitoring','clinical'),
('MED-020','Levetiracetam','Neurology',false,'No special approval','Dose by renal function','Seizure frequency and renal function','clinical'),
('MED-021','Omeprazole','Gastroenterology',false,'No special approval','20-40 mg once daily','Review long-term need','all_staff'),
('MED-022','Tranexamic acid','Haematology',false,'No special approval','Dose by indication','Thrombosis risk','clinical'),
('MED-023','Tamsulosin','Urology',false,'No special approval','400 micrograms once daily','Postural hypotension','all_staff'),
('MED-024','Diclofenac gel','Analgesic',false,'No special approval','Apply as directed','Skin reaction','all_staff')
ON CONFLICT (medicine_id) DO NOTHING;

INSERT INTO staff_schedule VALUES
('SCH-013','2026-06-29','DEP-RAD','Radiology','Consultant Radiologist','Dr James Wilson','08:00','20:00',true,'radiology.oncall@example.nhs','clinical'),
('SCH-014','2026-06-29','DEP-ED','Emergency Department','Consultant Physician','Dr Marcus Reed','07:00','19:00',true,'emergency_department.oncall@example.nhs','clinical'),
('SCH-015','2026-06-29','DEP-DERM','Dermatology','Specialist Nurse','Isla Moore','09:00','17:00',false,'derm.advice@example.nhs','clinical'),
('SCH-016','2026-06-30','DEP-ENDO','Endocrinology','Consultant Endocrinologist','Dr Ethan Clarke','08:00','18:00',true,'endo.oncall@example.nhs','clinical'),
('SCH-017','2026-06-30','DEP-GASTRO','Gastroenterology','Registrar','Dr Olivia Hayes','19:00','07:00',true,'gi.oncall@example.nhs','clinical'),
('SCH-018','2026-07-01','DEP-NEURO','Neurology','Stroke Registrar','Dr Samuel King','07:00','19:00',true,'stroke.team@example.nhs','clinical'),
('SCH-019','2026-07-01','DEP-ORTH','Orthopaedics','Trauma Coordinator','Mia Foster','08:00','20:00',true,'trauma.coord@example.nhs','clinical'),
('SCH-020','2026-07-02','DEP-URO','Urology','Registrar','Dr Jacob Ellis','19:00','07:00',true,'urology.oncall@example.nhs','clinical'),
('SCH-021','2026-07-02','DEP-HAEM','Haematology','Consultant Haematologist','Dr Lucas Brown','08:00','20:00',true,'haematology@example.nhs','clinical'),
('SCH-022','2026-07-03','DEP-THER','Therapies','Senior Physiotherapist','Amelia Scott','08:00','16:00',false,'therapies@example.nhs','all_staff')
ON CONFLICT (schedule_id) DO NOTHING;

INSERT INTO staff_schedule
    (schedule_id, shift_date, department_id, department_name, role, staff_name,
     shift_start, shift_end, on_call, contact, access_level)
VALUES
('SCH-DYN-TODAY-ED', CURRENT_DATE, 'DEP-ED', 'Emergency Department', 'Clinical Site Manager', 'Aisha Malik', '08:00', '20:00', true, 'emergency_department.oncall@example.nhs', 'clinical'),
('SCH-DYN-TODAY-ICU', CURRENT_DATE, 'DEP-ICU', 'Intensive Care Unit', 'Consultant Intensivist', 'Helen Carter', '20:00', '08:00', true, 'icu.oncall@example.nhs', 'clinical'),
('SCH-DYN-TOMORROW-RAD', CURRENT_DATE + 1, 'DEP-RAD', 'Radiology', 'Consultant Radiologist', 'Dr James Wilson', '08:00', '20:00', true, 'radiology.oncall@example.nhs', 'clinical'),
('SCH-DYN-TOMORROW-PHAR', CURRENT_DATE + 1, 'DEP-PHAR', 'Pharmacy', 'Pharmacist', 'Chloe Ward', '09:00', '17:00', true, 'pharmacy.oncall@example.nhs', 'clinical'),
('SCH-DYN-NEXTWEEK-PAED', CURRENT_DATE + 7, 'DEP-PAED', 'Paediatrics', 'Consultant Paediatrician', 'Dr Omar Hussain', '08:00', '18:00', true, 'paediatrics.oncall@example.nhs', 'clinical'),
('SCH-DYN-NEXTWEEK-RESP', CURRENT_DATE + 8, 'DEP-RESP', 'Respiratory', 'Registrar', 'Ella Cooper', '19:00', '07:00', true, 'respiratory.oncall@example.nhs', 'clinical')
ON CONFLICT (schedule_id) DO UPDATE SET
    shift_date = EXCLUDED.shift_date,
    department_id = EXCLUDED.department_id,
    department_name = EXCLUDED.department_name,
    role = EXCLUDED.role,
    staff_name = EXCLUDED.staff_name,
    shift_start = EXCLUDED.shift_start,
    shift_end = EXCLUDED.shift_end,
    on_call = EXCLUDED.on_call,
    contact = EXCLUDED.contact,
    access_level = EXCLUDED.access_level;

INSERT INTO clinic_sessions VALUES
('CLN-011','Dermatology Biologics Clinic','2026-07-01','10:00','Dr Isla Moore',14,6,'Routine','clinical'),
('CLN-012','Endocrine Diabetes Clinic','2026-07-01','13:00','Dr Ethan Clarke',16,4,'Urgent','clinical'),
('CLN-013','Gastroenterology Endoscopy Clinic','2026-07-02','08:30','Dr Olivia Hayes',12,2,'Routine','clinical'),
('CLN-014','Neurology Stroke Clinic','2026-07-02','14:00','Dr Samuel King',10,1,'Urgent','clinical'),
('CLN-015','Orthopaedic Trauma Clinic','2026-07-03','09:00','Dr Mia Foster',18,7,'Post-discharge','clinical'),
('CLN-016','Urology Review Clinic','2026-07-03','11:30','Dr Jacob Ellis',15,5,'Routine','clinical'),
('CLN-017','Rheumatology Infusion Clinic','2026-07-04','09:30','Dr Amara Khan',10,3,'Routine','clinical'),
('CLN-018','Haematology Day Unit Clinic','2026-07-04','13:30','Dr Lucas Brown',12,4,'Urgent','clinical'),
('CLN-019','Diabetes Education Clinic','2026-07-05','10:00','Dr Zoe Turner',20,10,'Routine','clinical'),
('CLN-020','Therapies Rehabilitation Clinic','2026-07-05','15:00','Dr Amelia Scott',18,8,'Routine','all_staff')
ON CONFLICT (clinic_id) DO NOTHING;

INSERT INTO equipment_assets VALUES
('EQ-0013','Defibrillator','Emergency Department Resus','Available','2026-06-01','2026-09-01','clinical.engineering@example.nhs','all_staff'),
('EQ-0014','Ventilator','ICU Bay 3','Available','2026-06-02','2026-09-02','clinical.engineering@example.nhs','all_staff'),
('EQ-0015','Infusion pump','Oncology Day Unit','In use','2026-06-03','2026-09-03','clinical.engineering@example.nhs','all_staff'),
('EQ-0016','Portable ultrasound','Maternity Triage','Available','2026-06-04','2026-09-04','clinical.engineering@example.nhs','all_staff'),
('EQ-0017','ECG machine','Cardiology Ward A','Available','2026-06-05','2026-09-05','clinical.engineering@example.nhs','all_staff'),
('EQ-0018','Dialysis machine','Renal Ward C','Maintenance due','2026-06-06','2026-09-06','clinical.engineering@example.nhs','all_staff'),
('EQ-0019','Patient monitor','Neurology Stroke Unit','In use','2026-06-07','2026-09-07','clinical.engineering@example.nhs','all_staff'),
('EQ-0020','Syringe driver','Paediatric Assessment Unit','Available','2026-06-08','2026-09-08','clinical.engineering@example.nhs','all_staff'),
('EQ-0021','Patient hoist','Therapy Gym','Available','2026-06-09','2026-09-09','clinical.engineering@example.nhs','all_staff'),
('EQ-0022','Blood pressure monitor','Dermatology Treatment Unit','Available','2026-06-10','2026-09-10','clinical.engineering@example.nhs','all_staff')
ON CONFLICT (asset_id) DO NOTHING;

INSERT INTO finance_records VALUES
('FIN-009','MRN10023','Isabella Turner','DEP-DERM','Dermatology','Biologics review','NHS internal',360.00,360.00,0.00,'Paid','2026-06-28','manager'),
('FIN-010','MRN10024','Henry Adams','DEP-ENDO','Endocrinology','Diabetes review','NHS internal',240.00,0.00,240.00,'Pending','2026-06-29','manager'),
('FIN-011','MRN10025','Olivia Carter','DEP-GASTRO','Gastroenterology','Endoscopy planning','Private insurer',890.00,400.00,490.00,'Part paid','2026-06-30','manager'),
('FIN-012','MRN10026','Samuel Wright','DEP-NEURO','Neurology','Stroke follow-up','NHS internal',520.00,520.00,0.00,'Paid','2026-07-01','manager'),
('FIN-013','MRN10027','Mia Phillips','DEP-ORTH','Orthopaedics','Trauma review','Private insurer',1150.00,0.00,1150.00,'Pending','2026-07-02','manager'),
('FIN-014','MRN10028','Jacob Hill','DEP-URO','Urology','Catheter review','Self-pay',260.00,260.00,0.00,'Paid','2026-07-03','manager'),
('FIN-015','MRN10029','Amara Bell','DEP-RHEUM','Rheumatology','Infusion review','NHS internal',440.00,0.00,440.00,'Pending','2026-07-04','manager'),
('FIN-016','MRN10030','Lucas Wood','DEP-HAEM','Haematology','Transfusion day case','Private insurer',1320.00,800.00,520.00,'Part paid','2026-07-05','manager'),
('FIN-017','MRN10031','Zoe Martin','DEP-DIAB','Diabetes Service','Pump education','NHS internal',300.00,300.00,0.00,'Paid','2026-07-06','manager'),
('FIN-018','MRN10032','Amelia Cook','DEP-THER','Therapies','Falls rehabilitation','NHS internal',380.00,0.00,380.00,'Pending','2026-07-07','manager')
ON CONFLICT (finance_id) DO NOTHING;

INSERT INTO compliance_audits VALUES
('AUD-001','Data retention evidence audit','DEP-ED','Emergency Department','Information Governance Helpdesk','2026-07-15','Scheduled',88,'manager'),
('AUD-002','Medicines fridge temperature audit','DEP-PHAR','Pharmacy','Pharmacy Lead','2026-07-16','In progress',91,'manager'),
('AUD-003','Safeguarding referral audit','DEP-PAED','Paediatrics','Safeguarding Lead','2026-07-17','Scheduled',84,'manager'),
('AUD-004','Radiology report turnaround audit','DEP-RAD','Radiology','Urgent Radiology Desk','2026-07-18','Scheduled',79,'manager'),
('AUD-005','ICU central line bundle audit','DEP-ICU','Intensive Care Unit','ICU Outreach','2026-07-19','Complete',94,'manager'),
('AUD-006','Maternity escalation audit','DEP-MAT','Maternity','Obstetric Emergency Team','2026-07-20','In progress',87,'manager'),
('AUD-007','Finance billing accuracy audit','DEP-FIN','Finance','Patient Accounts','2026-07-21','Scheduled',90,'manager'),
('AUD-008','Therapies discharge documentation audit','DEP-THER','Therapies','Therapy Coordinator','2026-07-22','Scheduled',82,'manager'),
('AUD-009','Haematology transfusion consent audit','DEP-HAEM','Haematology','Transfusion Practitioner','2026-07-23','In progress',89,'manager'),
('AUD-010','Emergency equipment availability audit','DEP-ED','Emergency Department','Duty Manager','2026-07-24','Scheduled',93,'manager')
ON CONFLICT (audit_id) DO NOTHING;

INSERT INTO training_records VALUES
('TRN-001','Ravi Singh','Consultant Physician','DEP-CARD','Cardiology','Information Governance Annual Update','2026-05-01','2027-05-01','Compliant','manager'),
('TRN-002','Aisha Malik','Clinical Site Manager','DEP-PAED','Paediatrics','Safeguarding Level 3','2026-05-02','2027-05-02','Compliant','manager'),
('TRN-003','Ella Cooper','Registrar','DEP-RESP','Respiratory','Fire Safety','2026-05-03','2027-05-03','Compliant','manager'),
('TRN-004','Marcus Reed','Staff Nurse','DEP-ED','Emergency Department','Manual Handling','2026-05-04','2027-05-04','Compliant','manager'),
('TRN-005','Helen Carter','Consultant Intensivist','DEP-ICU','Intensive Care Unit','Sepsis Pathway Training','2026-05-05','2027-05-05','Compliant','manager'),
('TRN-006','Chloe Ward','Pharmacist','DEP-PHAR','Pharmacy','Medicines Safety','2026-05-06','2027-05-06','Compliant','manager'),
('TRN-007','Nadia Ali','Therapist','DEP-RENAL','Renal','Infection Prevention','2026-05-07','2027-05-07','Compliant','manager'),
('TRN-008','Adam White','Pharmacist','DEP-SURG','Surgery','Controlled Drugs Awareness','2026-05-08','2027-05-08','Compliant','manager'),
('TRN-009','Ben Morris','Staff Nurse','DEP-ONC','Oncology','Chemotherapy Safety','2026-05-09','2027-05-09','Compliant','manager'),
('TRN-010','Mina Patel','Ward Manager','DEP-PATH','Pathology','Incident Reporting','2026-05-10','2027-05-10','Compliant','manager')
ON CONFLICT (training_id) DO NOTHING;
