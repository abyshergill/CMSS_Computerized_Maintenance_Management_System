from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class User(AbstractUser):
    class Roles(models.TextChoices):
        ADMIN = "Admin", "Admin"
        AUTHORIZED = "Authorized", "Authorized"

    role = models.CharField(max_length=20, choices=Roles.choices, default=Roles.AUTHORIZED)

    @property
    def is_cmms_admin(self):
        return self.is_superuser or self.role == self.Roles.ADMIN


class Section(models.Model):
    name = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Component(models.Model):
    class Status(models.TextChoices):
        GOOD = "Good", "Good"
        ALERT = "Alert", "Alert"
        BAD = "Bad", "Bad"

    unique_id = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=128)
    section = models.ForeignKey(Section, null=True, blank=True, on_delete=models.CASCADE, related_name="components")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.GOOD)
    expiry_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["unique_id"]

    def __str__(self):
        return f"{self.unique_id} - {self.name}"


class AlertSettings(models.Model):
    component = models.OneToOneField(Component, on_delete=models.CASCADE, related_name="alert_settings")
    interval_days = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    interval_hours = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    def lead_time(self):
        from datetime import timedelta
        return timedelta(days=self.interval_days, hours=self.interval_hours)


class MaintenanceLog(models.Model):
    component = models.ForeignKey(Component, null=True, blank=True, on_delete=models.CASCADE, related_name="history")
    author = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="maintenance_logs")
    date = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField()
    file = models.FileField(upload_to="maintenance/%Y/%m/", null=True, blank=True)

    class Meta:
        ordering = ["-date"]


class PreventiveSchedule(models.Model):
    class Cadence(models.TextChoices):
        DAILY = "Daily", "Every day"
        WEEKLY = "Weekly", "Every week"
        MONTHLY = "Monthly", "Every month"
        YEARLY = "Yearly", "Every year"

    WEEKDAYS = [(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday")]
    PRIORITIES = [("Low", "Low"), ("Medium", "Medium"), ("High", "High"), ("Critical", "Critical")]
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name="preventive_schedules")
    title = models.CharField(max_length=160)
    description = models.TextField()
    kind = models.CharField(max_length=20, choices=[("Preventive", "Preventive"), ("Inspection", "Inspection")], default="Preventive")
    priority = models.CharField(max_length=20, choices=PRIORITIES, default="Medium")
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="preventive_schedules")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_preventive_schedules")
    cadence = models.CharField(max_length=12, choices=Cadence.choices, default=Cadence.DAILY)
    run_time = models.TimeField(default="09:00")
    timezone_name = models.CharField(max_length=64, default="UTC")
    starts_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS, null=True, blank=True)
    day_of_month = models.PositiveSmallIntegerField(null=True, blank=True)
    month_of_year = models.PositiveSmallIntegerField(null=True, blank=True)
    excluded_weekdays = models.JSONField(default=list, blank=True)
    excluded_days_of_month = models.JSONField(default=list, blank=True)
    excluded_months = models.JSONField(default=list, blank=True)
    excluded_dates = models.JSONField(default=list, blank=True)
    create_days_before = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(0)])
    next_run_date = models.DateField()
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["enabled", "next_run_date", "title"]

    def __str__(self):
        return f"{self.title} ({self.get_cadence_display()})"


class WorkOrder(models.Model):
    class Kind(models.TextChoices):
        CORRECTIVE = "Corrective", "Corrective"
        PREVENTIVE = "Preventive", "Preventive"
        INSPECTION = "Inspection", "Inspection"

    class Priority(models.TextChoices):
        LOW = "Low", "Low"
        MEDIUM = "Medium", "Medium"
        HIGH = "High", "High"
        CRITICAL = "Critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "Open", "Open"
        IN_PROGRESS = "In progress", "In progress"
        ON_HOLD = "On hold", "On hold"
        COMPLETED = "Completed", "Completed"
        CANCELLED = "Cancelled", "Cancelled"

    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name="work_orders")
    title = models.CharField(max_length=160)
    description = models.TextField()
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CORRECTIVE)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="requested_work_orders")
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_work_orders")
    planned_for = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True)
    preventive_schedule = models.ForeignKey(PreventiveSchedule, null=True, blank=True, on_delete=models.SET_NULL, related_name="generated_work_orders")
    schedule_occurrence_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "-priority", "due_at", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["preventive_schedule", "schedule_occurrence_date"], condition=Q(preventive_schedule__isnull=False, schedule_occurrence_date__isnull=False), name="unique_preventive_schedule_occurrence")]

    def __str__(self):
        return f"WO-{self.pk}: {self.title}"

    @property
    def is_overdue(self):
        return bool(self.due_at and self.status not in {self.Status.COMPLETED, self.Status.CANCELLED} and timezone.now() > self.due_at)
