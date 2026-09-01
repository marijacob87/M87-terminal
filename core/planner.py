"""Persistência local e operações de semana do Planner."""

from __future__ import annotations

import json
import os
import re
import calendar
from copy import deepcopy
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    from PySide6.QtCore import QStandardPaths
except ImportError:  # Permite testar a persistência sem inicializar o Qt.
    QStandardPaths = None


DAY_NAMES = ("SEG", "TER", "QUA", "QUI", "SEX")
LINES_PER_DAY = 32
DEFAULT_TAGS = ("Arte", "Duplo", "GTO", "Konica", "SM", "Pessoal")


def week_start(value=None):
    value = value or date.today()
    return value - timedelta(days=value.weekday())


def week_key(value):
    return week_start(value).isoformat()


def empty_task():
    return {"text": "", "done": False, "tag": ""}


def task_has_content(task):
    """Identifica uma linha ocupada, inclusive antes de o trabalho ser descrito."""
    return bool(
        task.get("client", "").strip()
        or task.get("text", "").strip()
    )


def parse_terminal_task(value):
    """Retorna a categoria e o texto de uma tarefa digitada no terminal."""
    match = re.match(r"^\s*([^\-–—:]+?)\s*[-–—:]\s*(.+?)\s*$", value)
    if not match:
        return None

    category, text = match.groups()
    categories = {tag.casefold(): tag for tag in DEFAULT_TAGS}
    tag = categories.get(category.strip().casefold())
    if not tag:
        return None

    return tag, text.strip()


def empty_week(start):
    return {
        "start": week_key(start),
        "priorities": [empty_task() for _ in range(4)],
        "days": {
            name: [empty_task() for _ in range(LINES_PER_DAY)]
            for name in DAY_NAMES
        },
        "approvals": [],
        "backlog": [empty_task() for _ in range(5)],
        "notes": [],
    }


class PlannerStore:
    def __init__(self, storage_dir=None):
        if storage_dir is not None:
            location = storage_dir
        elif QStandardPaths is not None:
            location = QStandardPaths.writableLocation(
                QStandardPaths.AppDataLocation
            )
        else:
            location = Path.home() / "Library/Application Support/M87Terminal"
        self.path = Path(location) / "planner.json"
        self._needs_save = False
        self.data = self._load()
        if self._needs_save:
            self.save()

    def _load(self):
        try:
            with self.path.open(encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict) and isinstance(data.get("weeks"), dict):
                tags = data.setdefault("tags", [])
                if "Financeiro" in tags:
                    tags.remove("Financeiro")
                    self._needs_save = True
                for tag in DEFAULT_TAGS:
                    if tag not in tags:
                        tags.append(tag)
                        self._needs_save = True
                if not isinstance(data.get("approvals"), list):
                    approvals = []
                    for week in data["weeks"].values():
                        legacy_approvals = week.get("approvals", [])
                        if isinstance(legacy_approvals, list):
                            approvals.extend(legacy_approvals)
                        week["approvals"] = []
                    data["approvals"] = approvals
                    self._needs_save = True
                if not isinstance(data.get("scheduled"), list):
                    data["scheduled"] = []
                    self._needs_save = True
                return data
        except json.JSONDecodeError:
            self._backup_corrupt_file()
        except OSError:
            pass
        return {
            "weeks": {},
            "tags": list(DEFAULT_TAGS),
            "approvals": [],
            "scheduled": [],
        }

    def _backup_corrupt_file(self):
        """Preserva a base inválida antes de iniciar uma nova, sem sobrescrevê-la."""
        if not self.path.exists():
            return
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(
            f"{self.path.stem}.corrompido-{suffix}{self.path.suffix}"
        )
        try:
            self.path.replace(backup)
        except OSError:
            # A base original continua intacta se não for possível criar o backup.
            pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(self.path)

    def get_week(self, start):
        key = week_key(start)
        if key not in self.data["weeks"]:
            self.data["weeks"][key] = empty_week(start)
            self.save()
        week = self.data["weeks"][key]
        changed = False
        for name in DAY_NAMES:
            lines = week.setdefault("days", {}).setdefault(name, [])
            while len(lines) < LINES_PER_DAY:
                lines.append(empty_task())
                changed = True
        if "approvals" not in week:
            week["approvals"] = []
            changed = True
        if changed:
            self.save()
        return week

    @staticmethod
    def _scheduled_task_matches(item, task_date):
        """Confere se uma agenda deve criar uma ocorrência nesta data."""
        try:
            first_date = date.fromisoformat(item["date"])
        except (KeyError, TypeError, ValueError):
            return False
        if task_date < first_date:
            return False
        recurrence = item.get("recurrence", "once")
        if recurrence == "weekly":
            return (task_date - first_date).days % 7 == 0
        if recurrence == "monthly":
            return task_date.day == min(
                first_date.day,
                calendar.monthrange(task_date.year, task_date.month)[1],
            )
        if recurrence == "monthly_last_day":
            last_day = date(
                task_date.year,
                task_date.month,
                calendar.monthrange(task_date.year, task_date.month)[1],
            )
            while last_day.weekday() >= len(DAY_NAMES):
                last_day -= timedelta(days=1)
            return task_date == last_day
        if recurrence == "yearly":
            return (
                task_date.month == first_date.month
                and task_date.day == min(
                    first_date.day,
                    calendar.monthrange(task_date.year, task_date.month)[1],
                )
            )
        return task_date == first_date

    def apply_scheduled_tasks(self, start):
        """Materializa as ocorrências da semana sem duplicar nem substituir linhas."""
        week = self.get_week(start)
        changed = False
        for offset, day_name in enumerate(DAY_NAMES):
            task_date = start + timedelta(days=offset)
            tasks = week["days"][day_name]
            for item in self.data.get("scheduled", []):
                if not self._scheduled_task_matches(item, task_date):
                    continue
                schedule_id = item.get("id")
                occurrence_exists = any(
                    task.get("schedule_id") == schedule_id
                    and task.get("scheduled_for") == task_date.isoformat()
                    for day_tasks in week["days"].values()
                    for task in day_tasks
                ) or any(
                    task.get("schedule_id") == schedule_id
                    and task.get("scheduled_for") == task_date.isoformat()
                    for task in self.data.get("approvals", [])
                )
                if not schedule_id or occurrence_exists:
                    continue
                occurrence = deepcopy(item.get("task", {}))
                occurrence.update({
                    "done": False,
                    "schedule_id": schedule_id,
                    "scheduled_for": task_date.isoformat(),
                })
                target = next(
                    (index for index, task in enumerate(tasks) if not task_has_content(task)),
                    None,
                )
                if target is None:
                    tasks.append(occurrence)
                else:
                    tasks[target] = occurrence
                changed = True
        if changed:
            self.save()
        return week

    def add_scheduled_task(self, task_date, task, recurrence="once"):
        """Guarda um agendamento; as ocorrências são criadas ao abrir a semana."""
        recurrence = recurrence if recurrence in {
            "once", "weekly", "monthly", "monthly_last_day", "yearly",
        } else "once"
        schedule_id = f"schedule-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self.data.setdefault("scheduled", []).append({
            "id": schedule_id,
            "date": task_date.isoformat(),
            "recurrence": recurrence,
            "task": deepcopy(task),
        })
        self.save()
        return schedule_id

    def add_task_for_date(self, task_date, tag, text):
        """Inclui uma tarefa na primeira linha livre do dia informado."""
        weekday = task_date.weekday()
        if weekday >= len(DAY_NAMES):
            return None

        week = self.get_week(task_date)
        day_name = DAY_NAMES[weekday]
        tasks = week["days"][day_name]
        task = next(
            (item for item in tasks if not task_has_content(item)),
            None,
        )
        if task is None:
            task = empty_task()
            tasks.append(task)

        task.update({"text": text, "done": False, "tag": tag})
        self.save()
        return day_name

    def duplicate_week(self, source_start, destination_start):
        source = deepcopy(self.get_week(source_start))
        source["start"] = week_key(destination_start)
        self.data["weeks"][source["start"]] = source
        self.save()
        return source
