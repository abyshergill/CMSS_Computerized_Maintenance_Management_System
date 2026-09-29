import os
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone

from cmms.models import AlertSettings, Component, MaintenanceLog, Section, User


class Command(BaseCommand):
    help = "Create repeatable demonstration data for local CMMS development."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report changes without saving them.")

    def handle(self, *args, **options):
        admin_password = os.environ.get("CMMS_SEED_ADMIN_PASSWORD")
        authorized_password = os.environ.get("CMMS_SEED_AUTHORIZED_PASSWORD")
        if not admin_password or not authorized_password:
            raise CommandError("Set CMMS_SEED_ADMIN_PASSWORD and CMMS_SEED_AUTHORIZED_PASSWORD before seeding.")
        for password in (admin_password, authorized_password):
            try:
                validate_password(password)
            except Exception as exc:
                raise CommandError("Seed passwords must satisfy Django password validation.") from exc
        with transaction.atomic():
            counts = self.seed(admin_password, authorized_password)
            if options["dry_run"]:
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS("Seed data ready: " + ", ".join(f"{key}={value}" for key, value in counts.items())))

    def seed(self, admin_password, authorized_password):
        counts = {"users": 0, "sections": 0, "components": 0, "alerts": 0, "logs": 0}
        users = {}
        for username, role, password in (("demo_admin", User.Roles.ADMIN, admin_password), ("demo_worker", User.Roles.AUTHORIZED, authorized_password)):
            user, created = User.objects.get_or_create(username=username, defaults={"role": role})
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
                counts["users"] += 1
            users[username] = user
        section_data = {"Production Floor": "Production Floor", "Utilities": "Utilities", "Workshop": "Workshop"}
        sections = {}
        for name in section_data:
            section, created = Section.objects.get_or_create(name=name)
            sections[name] = section
            counts["sections"] += int(created)
        now = timezone.now()
        component_data = [
            ("PUMP-001", "Cooling water pump", "Production Floor", Component.Status.GOOD, now + timedelta(days=180), 30),
            ("AIR-014", "Compressed air regulator", "Utilities", Component.Status.ALERT, now + timedelta(days=3), 7),
            ("MTR-022", "Conveyor motor", "Production Floor", Component.Status.BAD, now - timedelta(days=2), 0),
            ("WELD-005", "MIG welding station", "Workshop", Component.Status.GOOD, now + timedelta(days=90), 14),
        ]
        for unique_id, name, section_name, status, expiry, interval_days in component_data:
            component, created = Component.objects.get_or_create(unique_id=unique_id, defaults={"name": name, "section": sections[section_name], "status": status, "expiry_date": expiry})
            counts["components"] += int(created)
            _, created = AlertSettings.objects.update_or_create(component=component, defaults={"interval_days": interval_days, "interval_hours": 0})
            counts["alerts"] += int(created)
        pump = Component.objects.get(unique_id="PUMP-001")
        _, created = MaintenanceLog.objects.get_or_create(component=pump, author=users["demo_worker"], notes="Routine inspection completed. No defects found.", defaults={"date": now - timedelta(days=1)})
        counts["logs"] += int(created)
        return counts
