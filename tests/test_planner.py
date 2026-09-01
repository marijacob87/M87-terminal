import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from core.planner import DEFAULT_TAGS, PlannerStore, parse_terminal_task


class PlannerStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = PlannerStore(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_terminal_task_uses_next_empty_line_after_client_only_task(self):
        task_date = date(2026, 8, 24)
        week = self.store.get_week(task_date)
        week["days"]["SEG"][0]["client"] = "Cliente sem trabalho"

        self.store.add_task_for_date(task_date, "Konica", "100 unidades")

        self.assertEqual(week["days"]["SEG"][0]["client"], "Cliente sem trabalho")
        self.assertEqual(week["days"]["SEG"][1]["text"], "100 unidades")

    def test_corrupt_data_is_preserved_before_a_new_store_is_started(self):
        path = Path(self.temp_dir.name) / "planner.json"
        path.write_text("{dados inválidos", encoding="utf-8")

        recovered = PlannerStore(self.temp_dir.name)

        self.assertEqual(recovered.data["weeks"], {})
        backups = list(Path(self.temp_dir.name).glob("planner.corrompido-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{dados inválidos")

    def test_tag_migration_is_persisted_immediately(self):
        path = Path(self.temp_dir.name) / "planner.json"
        path.write_text(json.dumps({"weeks": {}, "tags": ["Financeiro"]}), encoding="utf-8")

        PlannerStore(self.temp_dir.name)

        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("Financeiro", saved["tags"])
        self.assertTrue(set(DEFAULT_TAGS).issubset(saved["tags"]))

    def test_terminal_syntax_accepts_known_categories_only(self):
        self.assertEqual(
            parse_terminal_task("KONICA - Certificados"),
            ("Konica", "Certificados"),
        )
        self.assertIsNone(parse_terminal_task("Financeiro - Boleto"))

    def test_scheduled_occurrence_uses_an_empty_line_without_overwriting(self):
        task_date = date(2026, 8, 31)
        week = self.store.get_week(task_date)
        week["days"]["SEG"][0].update({"text": "Já existe", "tag": "Arte"})
        self.store.add_scheduled_task(
            task_date,
            {"client": "Konica", "text": "Certificados", "tag": "Konica"},
        )

        self.store.apply_scheduled_tasks(task_date)

        self.assertEqual(week["days"]["SEG"][0]["text"], "Já existe")
        self.assertEqual(week["days"]["SEG"][1]["text"], "Certificados")

    def test_weekly_schedule_does_not_duplicate_an_existing_occurrence(self):
        task_date = date(2026, 8, 31)
        self.store.add_scheduled_task(
            task_date,
            {"text": "Reunião", "tag": "Pessoal"},
            "weekly",
        )

        first = self.store.apply_scheduled_tasks(task_date)
        second = self.store.apply_scheduled_tasks(task_date)

        first_count = sum(task["text"] == "Reunião" for task in first["days"]["SEG"])
        second_count = sum(task["text"] == "Reunião" for task in second["days"]["SEG"])
        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)

    def test_scheduled_task_in_approvals_is_not_recreated_in_the_day(self):
        task_date = date(2026, 8, 31)
        schedule_id = self.store.add_scheduled_task(
            task_date,
            {"text": "Aprovar prova", "tag": "Arte"},
        )
        self.store.data["approvals"].append({
            "text": "Aprovar prova",
            "tag": "Arte",
            "schedule_id": schedule_id,
            "scheduled_for": task_date.isoformat(),
        })

        week = self.store.apply_scheduled_tasks(task_date)

        self.assertFalse(any(task["text"] == "Aprovar prova" for task in week["days"]["SEG"]))

    def test_last_day_of_month_schedule_adapts_to_each_month(self):
        self.store.add_scheduled_task(
            date(2026, 8, 31),
            {"text": "Enviar contagens", "tag": "Konica"},
            "monthly_last_day",
        )

        february = self.store.apply_scheduled_tasks(date(2027, 2, 22))

        self.assertEqual(february["days"]["SEX"][0]["text"], "Enviar contagens")
        self.assertEqual(february["days"]["SEX"][0]["scheduled_for"], "2027-02-26")
