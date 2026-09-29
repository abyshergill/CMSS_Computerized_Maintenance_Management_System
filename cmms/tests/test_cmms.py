from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
from io import StringIO
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cmms.models import AlertSettings, Component, MaintenanceLog, PreventiveSchedule, Section, User, WorkOrder
from cmms.preventive import first_occurrence_on_or_after, generate_due_work_orders, is_excluded_occurrence, local_scheduled_datetime, next_occurrence_after
from cmms.services import refresh_component_statuses


class CmmsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="Strong-password-123", role=User.Roles.ADMIN)
        self.authorized = User.objects.create_user(username="worker", password="Strong-password-123", role=User.Roles.AUTHORIZED)
        self.section = Section.objects.create(name="HVAC")
        self.component = Component.objects.create(unique_id="AC-1", name="Unit", section=self.section, expiry_date=timezone.now() + timedelta(days=5))
        AlertSettings.objects.create(component=self.component, interval_days=2)

    def login(self, user):
        self.client.force_login(user)

    def test_anonymous_dashboard_redirects_to_login(self):
        response = self.client.get(reverse("cmms:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_default_django_login_url_compatibility_route(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome back")

    def test_dashboard_includes_safe_chart_data(self):
        self.login(self.admin)
        response = self.client.get(reverse("cmms:dashboard"))
        self.assertEqual(response.context["health_chart"]["labels"], ["Good", "Alert", "Bad"])
        self.assertEqual(response.context["health_chart"]["values"], [1, 0, 0])
        self.assertEqual(response.context["work_order_chart"]["values"], [0, 0, 0, 0, 0])
        self.assertContains(response, 'id="health-chart-data"')
        self.assertContains(response, "/static/cmms/dashboard.js")

    def test_login_and_post_only_logout(self):
        response = self.client.post(reverse("cmms:login"), {"username": "admin", "password": "Strong-password-123"})
        self.assertRedirects(response, reverse("cmms:dashboard"))
        self.assertEqual(self.client.get(reverse("cmms:logout")).status_code, 403)
        self.assertRedirects(self.client.post(reverse("cmms:logout")), reverse("cmms:login"))

    def test_login_rejects_external_redirect_and_throttles_failures(self):
        for _ in range(5):
            response = self.client.post(reverse("cmms:login") + "?next=https://evil.example/", {"username": "admin", "password": "wrong-password"})
            self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("cmms:login") + "?next=https://evil.example/", {"username": "admin", "password": "Strong-password-123"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many failed attempts")

        self.client.session.flush()
        response = self.client.post(reverse("cmms:login") + "?next=https://evil.example/", {"username": "admin", "password": "Strong-password-123"})
        self.assertRedirects(response, reverse("cmms:dashboard"))

    def test_authorized_user_cannot_access_admin_mutations(self):
        self.login(self.authorized)
        self.assertEqual(self.client.get(reverse("cmms:manage-sections")).status_code, 403)
        self.assertEqual(self.client.post(reverse("cmms:delete-component", args=[self.component.pk])).status_code, 403)

    def test_admin_can_add_section(self):
        self.login(self.admin)
        response = self.client.post(reverse("cmms:manage-sections"), {"name": "Boiler Room"})
        self.assertRedirects(response, reverse("cmms:manage-sections"))
        self.assertTrue(Section.objects.filter(name="Boiler Room").exists())

    def test_work_order_lifecycle_requires_completion_notes(self):
        self.login(self.admin)
        response = self.client.post(reverse("cmms:work-orders"), {
            "component": self.component.pk,
            "title": "Inspect pump seal",
            "description": "Check for leakage and replace if needed.",
            "kind": WorkOrder.Kind.PREVENTIVE,
            "priority": WorkOrder.Priority.HIGH,
            "status": WorkOrder.Status.OPEN,
            "assigned_to": self.authorized.pk,
            "planned_for": "2026-09-24T09:00",
            "due_at": "2026-09-25T17:00",
            "completion_notes": "",
        })
        self.assertRedirects(response, reverse("cmms:work-orders"))
        work_order = WorkOrder.objects.get(title="Inspect pump seal")
        self.assertEqual(work_order.requested_by, self.admin)
        self.assertEqual(work_order.assigned_to, self.authorized)

        self.login(self.authorized)
        response = self.client.post(reverse("cmms:work-order-detail", args=[work_order.pk]), {
            "component": self.component.pk,
            "title": work_order.title,
            "description": work_order.description,
            "kind": work_order.kind,
            "priority": work_order.priority,
            "status": WorkOrder.Status.COMPLETED,
            "assigned_to": self.authorized.pk,
            "planned_for": "2026-09-24T09:00",
            "due_at": "2026-09-25T17:00",
            "completion_notes": "Seal inspected and replaced.",
        })
        self.assertRedirects(response, reverse("cmms:work-order-detail", args=[work_order.pk]))
        work_order.refresh_from_db()
        self.assertIsNotNone(work_order.completed_at)

    def test_unrelated_user_cannot_update_work_order(self):
        work_order = WorkOrder.objects.create(component=self.component, title="Restricted", description="Private", requested_by=self.admin)
        other_user = User.objects.create_user(username="other", password="Strong-password-123", role=User.Roles.AUTHORIZED)
        self.login(other_user)
        self.assertEqual(self.client.get(reverse("cmms:work-order-detail", args=[work_order.pk])).status_code, 403)

    def test_admin_can_create_daily_recurring_schedule(self):
        self.login(self.admin)
        response = self.client.post(reverse("cmms:preventive-schedules"), {
            "component": self.component.pk,
            "title": "Daily lubrication",
            "description": "Lubricate conveyor bearings.",
            "kind": "Preventive",
            "priority": "High",
            "assigned_to": self.authorized.pk,
            "cadence": PreventiveSchedule.Cadence.DAILY,
            "run_time": "09:00",
            "timezone_name": "UTC",
            "starts_on": "2026-01-05",
            "ends_on": "",
            "weekday": "",
            "day_of_month": "",
            "month_of_year": "",
            "excluded_weekdays": ["6"],
            "excluded_days_of_month": "15, 31",
            "excluded_months": ["12"],
            "excluded_dates": "2026-12-25\n2026-12-31",
            "create_days_before": "1",
            "enabled": "on",
        })
        self.assertRedirects(response, reverse("cmms:preventive-schedules"))
        schedule = PreventiveSchedule.objects.get(title="Daily lubrication")
        self.assertEqual(schedule.created_by, self.admin)
        self.assertEqual(schedule.next_run_date, date(2026, 1, 5))
        self.assertEqual(schedule.excluded_weekdays, [6])
        self.assertEqual(schedule.excluded_days_of_month, [15, 31])
        self.assertEqual(schedule.excluded_months, [12])
        self.assertEqual(schedule.excluded_dates, ["2026-12-25", "2026-12-31"])

    def test_schedule_page_renders_month_exclusions_as_tappable_checkboxes(self):
        self.login(self.admin)
        response = self.client.get(reverse("cmms:preventive-schedules"))
        self.assertContains(response, 'type="checkbox"')
        self.assertContains(response, "January")
        self.assertContains(response, "December")
        self.assertNotContains(response, 'multiple="multiple"')

    def test_recurring_generator_creates_ahead_of_due_and_is_idempotent(self):
        schedule = PreventiveSchedule.objects.create(
            component=self.component,
            title="Daily inspection",
            description="Inspect the unit.",
            created_by=self.admin,
            cadence=PreventiveSchedule.Cadence.DAILY,
            run_time=time(9, 0),
            timezone_name="UTC",
            starts_on=date(2026, 1, 5),
            next_run_date=date(2026, 1, 5),
            create_days_before=1,
        )
        run_at = datetime(2026, 1, 4, 9, 0, tzinfo=datetime_timezone.utc)
        self.assertEqual(generate_due_work_orders(now=run_at - timedelta(minutes=1)), 0)
        output = StringIO()
        call_command("generate_preventive_work_orders", now=run_at.isoformat(), stdout=output)
        self.assertIn("Created 1 recurring work order", output.getvalue())
        self.assertEqual(generate_due_work_orders(now=run_at), 0)
        work_order = WorkOrder.objects.get(preventive_schedule=schedule)
        self.assertEqual(work_order.schedule_occurrence_date, date(2026, 1, 5))
        self.assertEqual(work_order.due_at, datetime(2026, 1, 5, 9, 0, tzinfo=datetime_timezone.utc))
        self.assertEqual(schedule.generated_work_orders.count(), 1)
        schedule.refresh_from_db()
        self.assertEqual(schedule.next_run_date, date(2026, 1, 6))

    def test_recurring_calendar_clamps_month_end_and_leap_day(self):
        monthly = PreventiveSchedule(
            cadence=PreventiveSchedule.Cadence.MONTHLY,
            starts_on=date(2026, 4, 1),
            day_of_month=31,
        )
        first_monthly_date = first_occurrence_on_or_after(monthly, monthly.starts_on)
        self.assertEqual(first_monthly_date, date(2026, 4, 30))
        self.assertEqual(next_occurrence_after(monthly, first_monthly_date), date(2026, 5, 31))

        yearly = PreventiveSchedule(
            cadence=PreventiveSchedule.Cadence.YEARLY,
            starts_on=date(2025, 1, 1),
            month_of_year=2,
            day_of_month=29,
        )
        leap_schedule_date = first_occurrence_on_or_after(yearly, yearly.starts_on)
        self.assertEqual(leap_schedule_date, date(2025, 2, 28))
        self.assertEqual(next_occurrence_after(yearly, leap_schedule_date), date(2026, 2, 28))
        self.assertEqual(next_occurrence_after(yearly, date(2027, 2, 28)), date(2028, 2, 29))

    def test_recurring_schedule_resolves_dst_gap_to_first_valid_local_minute(self):
        schedule = PreventiveSchedule(
            pk=1,
            timezone_name="America/New_York",
            run_time=time(2, 30),
        )
        scheduled = local_scheduled_datetime(schedule, date(2026, 3, 8))
        self.assertEqual(scheduled.hour, 3)
        self.assertEqual(scheduled.minute, 0)

    def test_recurring_schedule_skips_weekday_monthday_month_and_specific_date(self):
        schedule = PreventiveSchedule.objects.create(
            component=self.component,
            title="Skip exceptions",
            description="Run except excluded calendar days.",
            created_by=self.admin,
            cadence=PreventiveSchedule.Cadence.DAILY,
            run_time=time(9, 0),
            timezone_name="UTC",
            starts_on=date(2026, 1, 31),
            next_run_date=date(2026, 1, 31),
            create_days_before=0,
            excluded_weekdays=[0],
            excluded_days_of_month=[3],
            excluded_months=[1],
            excluded_dates=["2026-02-01"],
        )
        self.assertTrue(is_excluded_occurrence(schedule, date(2026, 1, 8)))
        self.assertTrue(is_excluded_occurrence(schedule, date(2026, 2, 1)))
        self.assertTrue(is_excluded_occurrence(schedule, date(2026, 2, 2)))
        self.assertTrue(is_excluded_occurrence(schedule, date(2026, 2, 3)))
        self.assertEqual(generate_due_work_orders(now=datetime(2026, 2, 4, 10, tzinfo=datetime_timezone.utc)), 1)
        generated = WorkOrder.objects.get(preventive_schedule=schedule)
        self.assertEqual(generated.schedule_occurrence_date, date(2026, 2, 4))
        schedule.refresh_from_db()
        self.assertEqual(schedule.next_run_date, date(2026, 2, 5))

    def test_alert_hub_ignores_empty_attachment_files(self):
        self.component.expiry_date = timezone.now() - timedelta(hours=1)
        self.component.save(update_fields=["expiry_date"])
        MaintenanceLog.objects.create(component=self.component, author=self.admin, notes="No picture attached.", file="")
        self.login(self.admin)
        response = self.client.get(reverse("cmms:alert-hub"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Latest update attachment")

    def test_authorized_user_cannot_manage_recurring_schedules(self):
        self.login(self.authorized)
        self.assertEqual(self.client.get(reverse("cmms:preventive-schedules")).status_code, 403)

    def test_admin_can_pause_and_resume_recurring_schedule(self):
        schedule = PreventiveSchedule.objects.create(
            component=self.component,
            title="Weekly check",
            description="Inspect equipment.",
            created_by=self.admin,
            cadence=PreventiveSchedule.Cadence.WEEKLY,
            run_time=time(9, 0),
            timezone_name="UTC",
            starts_on=date(2026, 1, 5),
            next_run_date=date(2026, 1, 5),
            weekday=0,
        )
        self.login(self.admin)
        response = self.client.post(reverse("cmms:toggle-preventive-schedule", args=[schedule.pk]))
        self.assertRedirects(response, reverse("cmms:preventive-schedules"))
        schedule.refresh_from_db()
        self.assertFalse(schedule.enabled)
        response = self.client.post(reverse("cmms:toggle-preventive-schedule", args=[schedule.pk]))
        self.assertRedirects(response, reverse("cmms:preventive-schedules"))
        schedule.refresh_from_db()
        self.assertTrue(schedule.enabled)

    def test_invalid_schedule_timezone_is_rejected(self):
        self.login(self.admin)
        response = self.client.post(reverse("cmms:preventive-schedules"), {
            "component": self.component.pk,
            "title": "Invalid timezone task",
            "description": "Not saved",
            "kind": "Preventive",
            "priority": "Medium",
            "cadence": PreventiveSchedule.Cadence.MONTHLY,
            "run_time": "09:00",
            "timezone_name": "Not/A_Timezone",
            "starts_on": "2026-01-01",
            "day_of_month": "99",
            "create_days_before": "1",
            "enabled": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid IANA timezone")
        self.assertFalse(PreventiveSchedule.objects.exists())

    def test_component_edit_creates_log_with_picture(self):
        self.login(self.admin)
        picture = SimpleUploadedFile("update.png", b"\x89PNG\r\n\x1a\nvalid", content_type="image/png")
        response = self.client.post(reverse("cmms:edit-component", args=[self.component.pk]), {
            "unique_id": self.component.unique_id,
            "name": "Updated unit",
            "section": self.section.pk,
            "expiry_date": "2026-09-30",
            "expiry_time": "14:30",
            "interval_days": "1",
            "interval_hours": "0",
            "notes": "Replaced worn belt.",
            "file": picture,
        })
        self.assertRedirects(response, reverse("cmms:manage-components"))
        log = MaintenanceLog.objects.get(component=self.component)
        self.assertEqual(log.notes, "Replaced worn belt.")
        self.assertIn("update", log.file.name)
        self.assertTrue(log.file.name.endswith(".png"))
        history = self.client.get(reverse("cmms:component-detail", args=[self.component.pk]))
        self.assertContains(history, log.file.url)
        self.component.expiry_date = timezone.now() - timedelta(hours=1)
        self.component.save(update_fields=["expiry_date"])
        alerts = self.client.get(reverse("cmms:alert-hub"))
        self.assertContains(alerts, log.file.url)

    def test_component_edit_without_notes_still_creates_log(self):
        self.login(self.admin)
        response = self.client.post(reverse("cmms:edit-component", args=[self.component.pk]), {
            "unique_id": self.component.unique_id,
            "name": "Updated without notes",
            "section": self.section.pk,
            "expiry_date": "2026-09-30",
            "expiry_time": "14:30",
            "interval_days": "1",
            "interval_hours": "0",
        })
        self.assertRedirects(response, reverse("cmms:manage-components"))
        self.assertEqual(MaintenanceLog.objects.get(component=self.component).notes, "Component details updated.")

    def test_history_download_respects_limit(self):
        for number in range(25):
            MaintenanceLog.objects.create(component=self.component, author=self.admin, notes=f"Update {number}")
        self.login(self.authorized)
        response = self.client.get(reverse("cmms:download-history", args=[self.component.pk]), {"limit": "10"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.content.decode().splitlines()), 11)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_admin_can_add_component_with_expiry_date_and_time(self):
        self.login(self.admin)
        response = self.client.post(reverse("cmms:manage-components"), {
            "unique_id": "EXP-1",
            "name": "Expiry test unit",
            "section": self.section.pk,
            "expiry_date": "2026-09-30",
            "expiry_time": "14:30",
            "interval_days": "1",
            "interval_hours": "0",
        })
        self.assertRedirects(response, reverse("cmms:manage-components"))
        component = Component.objects.get(unique_id="EXP-1")
        self.assertEqual(component.expiry_date.strftime("%Y-%m-%d %H:%M"), "2026-09-30 14:30")

    def test_csrf_rejects_missing_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(reverse("cmms:manage-sections"), {"name": "Unsafe"})
        self.assertEqual(response.status_code, 403)

    def test_alert_status_transitions_and_recovery(self):
        self.component.expiry_date = timezone.now() - timedelta(hours=1)
        self.component.save(update_fields=["expiry_date"])
        refresh_component_statuses()
        self.component.refresh_from_db()
        self.assertEqual(self.component.status, Component.Status.BAD)
        self.component.expiry_date = None
        self.component.save(update_fields=["expiry_date"])
        refresh_component_statuses()
        self.component.refresh_from_db()
        self.assertEqual(self.component.status, Component.Status.GOOD)

    def test_xss_is_escaped_by_template(self):
        self.login(self.admin)
        response = self.client.post(reverse("cmms:manage-sections"), {"name": "<script>alert(1)</script>"})
        self.assertRedirects(response, reverse("cmms:manage-sections"))
        page = self.client.get(reverse("cmms:manage-sections"))
        self.assertNotContains(page, "<script>alert(1)</script>", html=True)

    def test_valid_log_is_owned_by_authenticated_user(self):
        self.login(self.authorized)
        response = self.client.post(reverse("cmms:component-detail", args=[self.component.pk]), {"notes": "Inspected"})
        self.assertRedirects(response, reverse("cmms:component-detail", args=[self.component.pk]))
        log = MaintenanceLog.objects.get()
        self.assertEqual(log.author, self.authorized)

    def test_upload_signature_is_validated(self):
        self.login(self.authorized)
        fake = SimpleUploadedFile("photo.png", b"not-a-png", content_type="image/png")
        response = self.client.post(reverse("cmms:component-detail", args=[self.component.pk]), {"notes": "Bad", "file": fake})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MaintenanceLog.objects.count(), 0)

    def test_section_delete_cascades_component_history(self):
        MaintenanceLog.objects.create(component=self.component, author=self.admin, notes="old")
        self.login(self.admin)
        response = self.client.post(reverse("cmms:delete-section", args=[self.section.pk]))
        self.assertRedirects(response, reverse("cmms:manage-sections"))
        self.assertFalse(Component.objects.filter(pk=self.component.pk).exists())
        self.assertEqual(MaintenanceLog.objects.count(), 0)

    def test_seed_command_is_idempotent(self):
        with patch.dict("os.environ", {"CMMS_SEED_ADMIN_PASSWORD": "Seed-admin-password-123", "CMMS_SEED_AUTHORIZED_PASSWORD": "Seed-worker-password-123"}):
            call_command("seed_cmms")
            first_counts = (User.objects.count(), Section.objects.count(), Component.objects.count(), AlertSettings.objects.count(), MaintenanceLog.objects.count())
            call_command("seed_cmms")
        self.assertEqual(first_counts, (4, 4, 5, 5, 1))
        self.assertEqual(first_counts, (User.objects.count(), Section.objects.count(), Component.objects.count(), AlertSettings.objects.count(), MaintenanceLog.objects.count()))
