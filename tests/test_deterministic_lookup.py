import json
import unittest
from datetime import date

from backend.app.deterministic_lookup import (
    DeterministicLookupService,
    DOCTOR_ROLE_MARKERS,
    LookupResult,
    NURSE_ROLE_MARKERS,
    STAFF_ROTA_QUERY_MARKERS,
    STOPWORDS,
    _best_search_term,
    _is_staff_rota_query,
    _name_search_terms,
    _requested_rota_dates,
    _requested_rota_role_groups,
    _rota_csv_filenames,
    _staff_rota_access_scopes,
    _terms,
    build_csv_semantic_metadata,
)
from backend.app.healthcare import HealthcareAccessControl, HealthcareSafetyGuard, HealthcareUserContext
from backend.app.healthcare_tools import build_healthcare_agent_tools


class FakeRetrieval:
    def search(self, query, *args, **kwargs):
        return []


class FakeDocuments:
    def list_documents(self):
        return []

    def lookup_table(self, query):
        return []


class FakeDeterministicLookup:
    def lookup(self, query, user, limit=10, csv_assets=None):
        return LookupResult(
            category="doctors",
            rows=[
                {
                    "doctor_id": "DOC-001",
                    "full_name": "Dr Aisha Malik",
                    "department_name": "Cardiology",
                    "phone": "020-5555-2101",
                    "access_level": "clinical",
                }
            ],
            access_scopes=("all_staff", "clinical"),
            message="Found 1 matching row(s).",
        )


class FakeSettings:
    deterministic_lookup_enabled = True


class FakeUploadedCsvLookup(DeterministicLookupService):
    def __init__(self):
        super().__init__(FakeSettings())
        self.queries = []
        self.count_queries = []

    def _query_uploaded_lookup_rows(self, query, scopes, limit, *, source_filenames=None, stopwords=None):
        self.queries.append({"query": query, "source_filenames": list(source_filenames or [])})
        return [
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 1,
                "row": {"asset_id": "A-001", "equipment_type": "Ventilator", "status": "Available"},
                "access_level": "all_staff",
            },
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 2,
                "row": {"asset_id": "A-002", "equipment_type": "Ventilator", "status": "In use"},
                "access_level": "all_staff",
            },
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 3,
                "row": {"asset_id": "A-003", "equipment_type": "Transport Ventilator", "status": "Available"},
                "access_level": "all_staff",
            },
        ]

    def _lookup_category(self, category, query, scopes, limit, *, stopwords=None):
        return []

    def _count_uploaded_lookup_rows(self, query, scopes, *, source_filenames, stopwords=None):
        self.count_queries.append({"query": query, "source_filenames": list(source_filenames or [])})
        return {"equipment_assets.csv": 3}


class FakeRowValueFallbackLookup(DeterministicLookupService):
    def __init__(self):
        super().__init__(FakeSettings())
        self.lookup_calls = []
        self.row_search_calls = []

    def _lookup_category(self, category, query, scopes, limit, *, stopwords=None):
        self.lookup_calls.append({"category": category, "query": query})
        return []

    def _query_uploaded_lookup_rows(self, query, scopes, limit, *, source_filenames=None, stopwords=None):
        self.row_search_calls.append({"query": query, "source_filenames": source_filenames})
        return [
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 4,
                "row": {"asset_id": "A-004", "equipment_type": "Transport Ventilator", "location": "ICU"},
                "access_level": "all_staff",
            }
        ]

    def _count_uploaded_lookup_rows(self, query, scopes, *, source_filenames=None, stopwords=None):
        return {"equipment_assets.csv": 1}


class FakeDistinctEquipmentTypeLookup(DeterministicLookupService):
    def __init__(self):
        super().__init__(FakeSettings())
        self.distinct_calls = []
        self.category_calls = []

    def _query_uploaded_distinct_field_values(
        self,
        scopes,
        field_candidates,
        *,
        source_filenames=None,
        limit=100,
        output_field="equipment_type",
        fallback_markers=("equipment", "asset", "device"),
    ):
        self.distinct_calls.append(
            {
                "field_candidates": list(field_candidates),
                "source_filenames": list(source_filenames or []),
                "limit": limit,
                "output_field": output_field,
                "fallback_markers": list(fallback_markers),
            }
        )
        if output_field == "medicine":
            return [
                {
                    "source_table": "uploaded_lookup_rows",
                    "source_filename": "medication_formulary.csv",
                    "row_number": 1,
                    "row": {"medicine": "Vancomycin"},
                    "access_level": "clinical",
                },
                {
                    "source_table": "uploaded_lookup_rows",
                    "source_filename": "medication_formulary.csv",
                    "row_number": 2,
                    "row": {"medicine": "Gentamicin"},
                    "access_level": "clinical",
                },
            ]
        return [
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 1,
                "row": {"equipment_type": "Ventilator"},
                "access_level": "all_staff",
            },
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 2,
                "row": {"equipment_type": "Infusion Pump"},
                "access_level": "all_staff",
            },
        ]

    def _lookup_category(self, category, query, scopes, limit, *, stopwords=None):
        self.category_calls.append({"category": category, "limit": limit})
        return [{"source_table": "directory", "name": "Cardiology Equipment fault Desk"}]


class FakeEquipmentCountLookup(DeterministicLookupService):
    def __init__(self):
        super().__init__(FakeSettings())
        self.category_calls = []
        self.row_search_calls = []
        self.count_calls = []

    def _query_uploaded_lookup_rows(self, query, scopes, limit, *, source_filenames=None, stopwords=None):
        self.row_search_calls.append(
            {
                "query": query,
                "limit": limit,
                "source_filenames": source_filenames,
                "stopwords": set(stopwords or set()),
            }
        )
        return [
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 1,
                "row": {"equipment_type": "ECG Machine", "location": "Cardiology Ward", "status": "Available"},
                "access_level": "all_staff",
            },
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 2,
                "row": {"equipment_type": "ECG Machine", "location": "Emergency Department", "status": "In use"},
                "access_level": "all_staff",
            },
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 3,
                "row": {"equipment_type": "Dialysis Machine", "location": "Renal Unit", "status": "Available"},
                "access_level": "all_staff",
            },
        ]

    def _count_uploaded_lookup_rows(self, query, scopes, *, source_filenames=None, stopwords=None):
        self.count_calls.append(
            {
                "query": query,
                "source_filenames": source_filenames,
                "stopwords": set(stopwords or set()),
            }
        )
        return {"equipment_assets.csv": 3}

    def _lookup_category(self, category, query, scopes, limit, *, stopwords=None):
        self.category_calls.append({"category": category, "limit": limit})
        return [{"source_table": "directory", "name": "Cardiology Equipment fault Desk"}]


class FakeNoRotaRowsLookup(DeterministicLookupService):
    def __init__(self):
        super().__init__(FakeSettings())
        self.category_calls = []

    def _query_staff_rota_rows(self, query, scopes, limit, *, source_filenames=None):
        return []

    def _lookup_category(self, category, query, scopes, limit, *, stopwords=None):
        self.category_calls.append({"category": category, "query": query})
        return [{"source_table": category, "full_name": "Fallback Doctor"}]


class FakePatientPreferredLookup(DeterministicLookupService):
    def __init__(self, patient_rows):
        super().__init__(FakeSettings())
        self.patient_rows = patient_rows
        self.category_calls = []
        self.row_search_calls = []

    def _lookup_category(self, category, query, scopes, limit, *, stopwords=None):
        self.category_calls.append({"category": category, "query": query})
        if category == "patients":
            return list(self.patient_rows)
        return []

    def _query_uploaded_lookup_rows(self, query, scopes, limit, *, source_filenames=None, stopwords=None):
        self.row_search_calls.append({"query": query, "source_filenames": list(source_filenames or [])})
        return [
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "equipment_assets.csv",
                "row_number": 1,
                "row": {
                    "equipment_type": "Patient hoist",
                    "location": "Paediatrics Ward",
                    "status": "Fault logged",
                },
                "access_level": "all_staff",
            }
        ]


class FakeRotaCsvLookup(DeterministicLookupService):
    def __init__(self):
        super().__init__(FakeSettings())
        self.rota_calls = []

    def _query_staff_rota_rows(self, query, scopes, limit, *, source_filenames=None):
        self.rota_calls.append({"query": query, "source_filenames": list(source_filenames or [])})
        return [
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "doctor_rota.csv",
                "row_number": 1,
                "row": {"date": "Today", "doctor": "Dr Aisha Malik", "status": "On call"},
                "access_level": "all_staff",
            }
        ]


class FakeGenericOnCallRowsLookup(DeterministicLookupService):
    def __init__(self):
        super().__init__(FakeSettings())
        self.local_csv_calls = []

    def _query_staff_rota_rows(self, query, scopes, limit, *, source_filenames=None):
        requested_dates = _requested_rota_dates(query)
        requested_groups = _requested_rota_role_groups(query)
        department_terms = [
            term
            for term in self._search_terms(
                query,
                STOPWORDS | STAFF_ROTA_QUERY_MARKERS | DOCTOR_ROLE_MARKERS | NURSE_ROLE_MARKERS,
            )
            if term not in {"list", "me", "available", "availability", "today", "tomorrow", "csv", "file"}
        ]
        return self._query_staff_rota_local_csv(
            query,
            scopes,
            limit,
            requested_dates=requested_dates,
            requested_groups=requested_groups,
            department_terms=department_terms,
        )

    def _query_staff_rota_local_csv(
        self,
        query,
        scopes,
        limit,
        *,
        requested_dates=None,
        requested_groups=None,
        department_terms=None,
    ):
        self.local_csv_calls.append(
            {
                "query": query,
                "department_terms": list(department_terms or []),
                "requested_dates": list(requested_dates or []),
                "requested_groups": set(requested_groups or set()),
            }
        )
        return [
            {
                "source_table": "uploaded_lookup_rows",
                "source_filename": "staff_rota.csv",
                "row_number": 1,
                "row": {
                    "staff_name": "Mina Patel",
                    "role": "Clinical Site Manager",
                    "department": "Paediatrics",
                    "on_call": "Yes",
                },
                "access_level": "clinical",
            }
        ]

    def _lookup_category(self, category, query, scopes, limit, *, stopwords=None):
        return []


class DeterministicLookupToolTests(unittest.TestCase):
    def test_postgres_lookup_tool_returns_structured_rows(self):
        tools = build_healthcare_agent_tools(
            retrieval=FakeRetrieval(),
            documents=FakeDocuments(),
            user=HealthcareUserContext(user_id="doctor", roles=("doctor",)),
            access=HealthcareAccessControl(),
            safety=HealthcareSafetyGuard(),
            deterministic_lookup=FakeDeterministicLookup(),
        )
        tool = {tool.name: tool for tool in tools}["postgres_deterministic_lookup"]

        payload = json.loads(tool.run("doctor contact for cardiology"))

        self.assertEqual(payload["category"], "doctors")
        self.assertEqual(payload["rows"][0]["full_name"], "Dr Aisha Malik")
        self.assertIn("clinical", payload["access_scopes_applied"])

    def test_patient_ward_question_classifies_as_patient_lookup(self):
        service = DeterministicLookupService(settings=None)

        self.assertEqual(service._classify("Leo Bennett is in which ward?"), "patients")
        self.assertEqual(service._classify("where in IPD is Leo Bennett"), "patients")
        self.assertEqual(_best_search_term(_terms("Leo Bennett is in which ward?")), "bennett")

    def test_ward_directory_question_still_classifies_as_wards(self):
        service = DeterministicLookupService(settings=None)

        self.assertEqual(service._classify("which ward is W07?"), "wards")

    def test_patient_appointment_question_uses_appointment_lookup_and_patient_name(self):
        service = DeterministicLookupService(settings=None)
        query = "Does patient Leo Bennett have any appointments?"

        self.assertEqual(service._classify(query), "appointments")
        self.assertEqual(_name_search_terms(_terms(query)), ["leo", "bennett"])

    def test_manifest_csv_assets_are_selected_from_filename_and_columns(self):
        service = DeterministicLookupService(settings=None)

        matches = service._matching_csv_assets(
            "Which doctor is on call today?",
            [
                {
                    "filename": "doctor_rota.csv",
                    "columns": ["date", "doctor", "status"],
                    "row_count": 12,
                },
                {
                    "filename": "department_contacts.csv",
                    "columns": ["department", "phone"],
                    "row_count": 3,
                },
            ],
        )

        self.assertEqual(matches[0]["filename"], "doctor_rota.csv")
        self.assertEqual(matches[0]["columns"], ["date", "doctor", "status"])
        self.assertEqual(matches[0]["row_count"], 12)

    def test_generic_on_call_query_selects_rota_like_csv_assets(self):
        service = FakeRotaCsvLookup()

        result = service.lookup(
            "who is on call",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            csv_assets=[
                {
                    "filename": "doctor_rota.csv",
                    "columns": ["date", "doctor", "status"],
                    "row_count": 12,
                }
            ],
        )

        self.assertEqual(result.rows[0]["row"]["doctor"], "Dr Aisha Malik")
        self.assertIn("doctor_rota.csv", service.rota_calls[0]["source_filenames"])

    def test_rota_csv_filenames_ignore_non_rota_selected_assets(self):
        filenames = _rota_csv_filenames(
            "who is on call",
            [
                {
                    "filename": "department_contacts.csv",
                    "columns": ["department", "contact_name", "role", "phone"],
                    "semantic_terms": ["staff absence", "duty manager"],
                },
                {
                    "filename": "audit_schedule.csv",
                    "columns": ["audit_id", "department", "lead", "status", "due_date"],
                    "semantic_terms": ["audit schedule"],
                },
                {
                    "filename": "staff_rota.csv",
                    "columns": ["date", "staff_name", "role", "on_call", "shift_start"],
                },
            ],
            ["department_contacts.csv", "audit_schedule.csv"],
        )

        self.assertEqual(filenames, ["staff_rota.csv"])

    def test_csv_semantic_metadata_includes_sampled_row_values(self):
        metadata = build_csv_semantic_metadata(
            "equipment_assets.csv",
            (
                b"asset_id,equipment_type,location,status\n"
                b"A-001,Ventilator,ICU,Available\n"
                b"A-002,Infusion Pump,Ward 7,In use\n"
            ),
        )

        self.assertIn("equipment_type", metadata["columns"])
        self.assertIn("ventilator", metadata["semantic_terms"])
        self.assertIn("ventilators", metadata["semantic_terms"])
        self.assertIn("Ventilator", metadata["categorical_values"]["equipment_type"])

    def test_manifest_csv_assets_are_selected_from_semantic_terms(self):
        service = DeterministicLookupService(settings=None)

        matches = service._matching_csv_assets(
            "How many ventilators do we have?",
            [
                {
                    "filename": "equipment_assets.csv",
                    "columns": ["asset_id", "equipment_type", "location", "status"],
                    "row_count": 30,
                    "semantic_terms": ["asset", "equipment", "ventilator", "icu"],
                    "categorical_values": {"equipment_type": ["Ventilator", "Infusion Pump"]},
                    "sample_values": ["equipment_type=Ventilator"],
                },
                {
                    "filename": "department_contacts.csv",
                    "columns": ["department", "phone"],
                    "row_count": 3,
                },
            ],
        )

        self.assertEqual(matches[0]["filename"], "equipment_assets.csv")
        self.assertGreater(matches[0]["match_score"], 0)

    def test_count_lookup_plan_records_uploaded_csv_aggregate_result(self):
        service = FakeUploadedCsvLookup()

        result = service.lookup(
            "How many ventilators do we have?",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            csv_assets=[
                {
                    "filename": "equipment_assets.csv",
                    "columns": ["asset_id", "equipment_type", "location", "status"],
                    "row_count": 30,
                    "semantic_terms": ["ventilator"],
                }
            ],
        )

        self.assertEqual(service.queries[0]["source_filenames"], ["equipment_assets.csv"])
        self.assertEqual(service.count_queries[0]["source_filenames"], ["equipment_assets.csv"])
        self.assertEqual(result.lookup_plan["aggregate_intent"], "count")
        self.assertEqual(result.lookup_plan["aggregate_result"]["matching_rows"], 3)
        self.assertEqual(result.lookup_plan["aggregate_result"]["counts_by_source"], {"equipment_assets.csv": 3})
        self.assertTrue(result.lookup_plan["row_value_search_used"])
        self.assertEqual(result.lookup_plan["matched_csv_sources"], ["equipment_assets.csv"])
        self.assertIn("ventilator", result.lookup_plan["matched_terms"])
        self.assertIn("equipment_type", result.lookup_plan["matched_columns"])

    def test_no_asset_match_falls_back_to_uploaded_row_value_search(self):
        service = FakeRowValueFallbackLookup()

        result = service.lookup(
            "How many transport ventilators do we have?",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            csv_assets=[],
        )

        self.assertEqual(service.row_search_calls[0]["source_filenames"], None)
        self.assertTrue(result.lookup_plan["row_value_search_used"])
        self.assertEqual(result.lookup_plan["matched_csv_sources"], ["equipment_assets.csv"])
        self.assertEqual(result.lookup_plan["aggregate_result"]["matching_rows"], 1)
        self.assertEqual(result.lookup_plan["aggregate_result"]["counts_by_source"], {"equipment_assets.csv": 1})
        self.assertIn("transport", result.lookup_plan["matched_terms"])
        self.assertIn("equipment_type", result.lookup_plan["matched_columns"])

    def test_equipment_type_list_uses_distinct_uploaded_rows_without_directory_fallback(self):
        service = FakeDistinctEquipmentTypeLookup()

        result = service.lookup(
            "list all equipment we have",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            limit=100,
            csv_assets=[
                {
                    "filename": "equipment_assets.csv",
                    "columns": ["asset_id", "equipment_type", "location", "status"],
                    "semantic_terms": ["asset", "equipment", "ventilator"],
                    "categorical_values": {"equipment_type": ["Ventilator", "Infusion Pump"]},
                    "row_count": 30,
                }
            ],
        )

        self.assertEqual([row["row"]["equipment_type"] for row in result.rows], ["Ventilator", "Infusion Pump"])
        self.assertEqual(service.category_calls, [])
        self.assertEqual(service.distinct_calls[0]["source_filenames"], ["equipment_assets.csv"])
        self.assertEqual(service.distinct_calls[0]["limit"], 100)
        self.assertTrue(result.lookup_plan["row_value_search_used"])
        self.assertEqual(result.lookup_plan["distinct_field"], "equipment_type")
        self.assertEqual(result.lookup_plan["matched_csv_sources"], ["equipment_assets.csv"])

    def test_equipment_type_list_ignores_non_equipment_selected_assets(self):
        service = FakeDistinctEquipmentTypeLookup()

        result = service.lookup(
            "list all equipment",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            limit=100,
            csv_assets=[
                {
                    "filename": "department_contacts.csv",
                    "columns": ["department", "contact_name", "role", "phone"],
                    "semantic_terms": ["equipment fault"],
                    "row_count": 30,
                },
                {
                    "filename": "equipment_assets.csv",
                    "columns": ["asset_id", "equipment_type", "location", "status"],
                    "semantic_terms": ["asset", "equipment"],
                    "row_count": 30,
                },
            ],
        )

        self.assertEqual([row["row"]["equipment_type"] for row in result.rows], ["Ventilator", "Infusion Pump"])
        self.assertEqual(service.distinct_calls[0]["source_filenames"], ["equipment_assets.csv"])

    def test_medicine_list_uses_distinct_formulary_rows_without_directory_fallback(self):
        service = FakeDistinctEquipmentTypeLookup()

        result = service.lookup(
            "list all drugs",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            limit=100,
            csv_assets=[
                {
                    "filename": "audit_schedule.csv",
                    "columns": ["audit_id", "topic", "status"],
                    "semantic_terms": ["medication safety"],
                    "row_count": 30,
                },
                {
                    "filename": "medication_formulary.csv",
                    "columns": ["medicine", "category", "restricted"],
                    "semantic_terms": ["medicine", "drug", "formulary"],
                    "row_count": 30,
                },
            ],
        )

        self.assertEqual([row["row"]["medicine"] for row in result.rows], ["Vancomycin", "Gentamicin"])
        self.assertEqual(service.category_calls, [])
        self.assertEqual(service.distinct_calls[0]["source_filenames"], ["medication_formulary.csv"])
        self.assertEqual(service.distinct_calls[0]["output_field"], "medicine")
        self.assertEqual(result.lookup_plan["distinct_field"], "medicine")
        self.assertEqual(result.lookup_plan["matched_csv_sources"], ["medication_formulary.csv"])

    def test_equipment_count_uses_uploaded_rows_before_directory_fallback(self):
        service = FakeEquipmentCountLookup()

        result = service.lookup(
            "how many ecg machine do we have",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            limit=100,
            csv_assets=[],
        )

        self.assertEqual(len(result.rows), 2)
        self.assertEqual(service.category_calls, [])
        self.assertEqual(service.row_search_calls[0]["limit"], 100)
        self.assertIn("machine", service.row_search_calls[0]["stopwords"])
        self.assertIn("machines", service.row_search_calls[0]["stopwords"])
        self.assertNotIn("ecg", service.row_search_calls[0]["stopwords"])
        self.assertIn("machine", service.count_calls[0]["stopwords"])
        self.assertNotIn("ecg", service.count_calls[0]["stopwords"])
        self.assertEqual(result.lookup_plan["aggregate_intent"], "count")
        self.assertEqual(result.lookup_plan["aggregate_result"]["matching_rows"], 2)
        self.assertEqual(result.lookup_plan["aggregate_result"]["counts_by_source"], {"equipment_assets.csv": 2})
        self.assertTrue(result.lookup_plan["row_value_search_used"])
        self.assertTrue(result.lookup_plan["strict_row_value_filter_applied"])
        self.assertEqual(result.lookup_plan["matched_csv_sources"], ["equipment_assets.csv"])
        self.assertEqual([row["row"]["equipment_type"] for row in result.rows], ["ECG Machine", "ECG Machine"])

    def test_specific_equipment_count_filters_selected_csv_to_requested_type(self):
        service = FakeEquipmentCountLookup()

        result = service.lookup(
            "how many ecg does the hospital have",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            limit=100,
            csv_assets=[
                {
                    "filename": "equipment_assets.csv",
                    "columns": ["asset_id", "equipment_type", "location", "status"],
                    "semantic_terms": ["asset", "equipment", "ecg", "dialysis"],
                    "categorical_values": {"equipment_type": ["ECG Machine", "Dialysis Machine"]},
                    "row_count": 30,
                }
            ],
        )

        self.assertEqual(result.lookup_plan["aggregate_result"]["matching_rows"], 2)
        self.assertEqual(result.lookup_plan["aggregate_result"]["counts_by_source"], {"equipment_assets.csv": 2})
        self.assertTrue(result.lookup_plan["strict_row_value_filter_applied"])
        self.assertEqual([row["row"]["equipment_type"] for row in result.rows], ["ECG Machine", "ECG Machine"])

    def test_domain_and_schema_words_remain_search_terms(self):
        service = DeterministicLookupService(settings=None)

        terms = service._search_terms("doctor physician consultant phone doctors cardiology", set())

        self.assertEqual(terms, ["doctor", "physician", "consultant", "phone", "doctors", "cardiology"])

    def test_staff_rota_availability_question_is_classified_for_rota_lookup(self):
        service = DeterministicLookupService(settings=None)

        query = "show me a list of available doctors and nurses for today and tomorrow"

        self.assertEqual(service._classify(query), "staff_rota")
        self.assertTrue(_is_staff_rota_query(query))
        self.assertEqual(_requested_rota_role_groups(query), {"doctor", "nurse"})
        self.assertEqual(
            _requested_rota_dates(query, today=date(2026, 6, 23)),
            ["2026-06-23", "2026-06-24"],
        )

    def test_generic_who_is_on_call_classifies_as_rota_lookup(self):
        service = DeterministicLookupService(settings=None)

        self.assertEqual(service._classify("who is on call"), "staff_rota")
        self.assertTrue(_is_staff_rota_query("who is on call"))
        self.assertEqual(_requested_rota_role_groups("who is on call"), set())

    def test_staff_rota_lookup_expands_general_staff_scope(self):
        scopes = _staff_rota_access_scopes(("all_staff",))

        self.assertIn("all_staff", scopes)
        self.assertIn("clinical", scopes)
        self.assertIn("manager", scopes)
        self.assertNotIn("pharmacy", scopes)

    def test_generic_who_is_on_call_does_not_filter_department_by_call(self):
        service = FakeGenericOnCallRowsLookup()

        result = service.lookup(
            "who is on call",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
        )

        self.assertEqual(result.rows[0]["row"]["staff_name"], "Mina Patel")
        self.assertEqual(service.local_csv_calls[0]["department_terms"], [])

    def test_generic_on_call_without_rota_rows_falls_back_to_doctors(self):
        service = FakeNoRotaRowsLookup()

        result = service.lookup(
            "who is on call",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
        )

        self.assertEqual(result.category, "staff_rota")
        self.assertEqual(result.rows[0]["full_name"], "Fallback Doctor")
        self.assertEqual(service.category_calls, [{"category": "doctors", "query": "doctor on call"}])

    def test_patient_lookup_prefers_patient_table_over_matching_uploaded_csv(self):
        service = FakePatientPreferredLookup(
            [
                {
                    "patient_id": "PAT-001",
                    "mrn": "MRN10001",
                    "full_name": "John Spencer",
                    "ward_code": "W02",
                    "access_level": "clinical",
                }
            ]
        )

        result = service.lookup(
            "details on patient John Spencer",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            csv_assets=[
                {
                    "filename": "equipment_assets.csv",
                    "columns": ["equipment_type", "location", "status"],
                    "semantic_terms": ["patient", "hoist", "john", "spencer"],
                    "row_count": 1,
                }
            ],
        )

        self.assertEqual(result.rows[0]["full_name"], "John Spencer")
        self.assertEqual(service.category_calls[0]["category"], "patients")
        self.assertEqual(service.row_search_calls, [])

    def test_patient_lookup_falls_back_to_uploaded_csv_when_patient_table_misses(self):
        service = FakePatientPreferredLookup([])

        result = service.lookup(
            "details on patient John Spencer",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
            csv_assets=[
                {
                    "filename": "equipment_assets.csv",
                    "columns": ["equipment_type", "location", "status"],
                    "semantic_terms": ["patient", "hoist", "john", "spencer"],
                    "row_count": 1,
                }
            ],
        )

        self.assertEqual(result.rows[0]["row"]["equipment_type"], "Patient hoist")
        self.assertEqual(service.row_search_calls[0]["source_filenames"], ["equipment_assets.csv"])

    def test_today_doctor_rota_query_does_not_fall_back_to_other_dates_or_tables(self):
        service = FakeNoRotaRowsLookup()

        result = service.lookup(
            "Which doctor is on call today?",
            HealthcareUserContext(user_id="admin", roles=("admin",)),
        )

        today = date.today().isoformat()
        self.assertEqual(result.category, "staff_rota")
        self.assertEqual(result.rows, [])
        self.assertEqual(service.category_calls, [])
        self.assertEqual(result.lookup_plan["resolved_today"], today)
        self.assertEqual(result.lookup_plan["requested_rota_dates"], [today])
        self.assertIn(f"No matching staff_rota.csv rows found for requested date(s): {today}", result.message)
        self.assertIn("Do not use rows from other dates as today's rota.", result.message)


if __name__ == "__main__":
    unittest.main()
