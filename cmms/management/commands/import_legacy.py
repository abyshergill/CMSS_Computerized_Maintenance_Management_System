import sqlite3
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from cmms.models import AlertSettings, Component, MaintenanceLog, Section, User


class Command(BaseCommand):
    help = "Import legacy Flask SQLAlchemy data from an SQLite database."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="app.db")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        database = options["database"]
        try:
            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise CommandError(f"Could not open legacy database: {exc}") from exc
        try:
            with transaction.atomic():
                counts = self.import_rows(connection, options["dry_run"])
                if options["dry_run"]:
                    transaction.set_rollback(True)
        finally:
            connection.close()
        self.stdout.write(self.style.SUCCESS("Imported: " + ", ".join(f"{key}={value}" for key, value in counts.items())))

    def import_rows(self, connection, dry_run):
        counts = {"users": 0, "sections": 0, "components": 0, "alerts": 0, "logs": 0}
        for row in connection.execute("SELECT id, username, password_hash, role FROM user"):
            user, created = User.objects.get_or_create(id=row["id"], defaults={"username": row["username"], "role": row["role"] or User.Roles.AUTHORIZED})
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password", "role"])
                counts["users"] += 1
        for row in connection.execute("SELECT id, name FROM section"):
            _, created = Section.objects.get_or_create(id=row["id"], defaults={"name": row["name"]})
            counts["sections"] += int(created)
        for row in connection.execute("SELECT id, unique_id, name, section_id, status, expiry_date FROM component"):
            expiry = self.parse_datetime(row["expiry_date"])
            _, created = Component.objects.get_or_create(id=row["id"], defaults={"unique_id": row["unique_id"], "name": row["name"], "section_id": row["section_id"], "status": row["status"] or Component.Status.GOOD, "expiry_date": expiry})
            counts["components"] += int(created)
        for row in connection.execute("SELECT id, component_id, interval_days, interval_hours FROM alert_settings"):
            _, created = AlertSettings.objects.get_or_create(id=row["id"], defaults={"component_id": row["component_id"], "interval_days": max(row["interval_days"] or 0, 0), "interval_hours": max(row["interval_hours"] or 0, 0)})
            counts["alerts"] += int(created)
        for row in connection.execute("SELECT id, component_id, user_id, date, notes, file_path FROM maintenance_log"):
            _, created = MaintenanceLog.objects.get_or_create(id=row["id"], defaults={"component_id": row["component_id"], "author_id": row["user_id"], "date": self.parse_datetime(row["date"]) or timezone.now(), "notes": row["notes"] or ""})
            counts["logs"] += int(created)
        return counts

    @staticmethod
    def parse_datetime(value):
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
