from datetime import timezone as datetime_timezone

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from cmms.preventive import generate_due_work_orders


class Command(BaseCommand):
    help = "Create work orders for recurring preventive schedules that are due for advance generation."

    def add_arguments(self, parser):
        parser.add_argument("--now", help="Optional ISO datetime for controlled runs/tests; defaults to current time.")

    def handle(self, *args, **options):
        now_value = options.get("now")
        now = parse_datetime(now_value) if now_value else timezone.now()
        if now is None:
            raise CommandError("--now must be a valid ISO datetime.")
        if timezone.is_naive(now):
            now = timezone.make_aware(now, datetime_timezone.utc)
        created = generate_due_work_orders(now=now)
        self.stdout.write(self.style.SUCCESS(f"Created {created} recurring work order(s)."))
