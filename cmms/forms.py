import calendar
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import AlertSettings, Component, MaintenanceLog, PreventiveSchedule, Section, User, WorkOrder


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)


class RegistrationForm(UserCreationForm):
    role = forms.ChoiceField(choices=User.Roles.choices)

    class Meta:
        model = User
        fields = ("username", "role", "password1", "password2")


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ("name",)


class ComponentForm(forms.ModelForm):
    expiry_date = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    expiry_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M", "%H:%M:%S", "%I:%M %p"],
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    interval_days = forms.IntegerField(min_value=0, initial=0)
    interval_hours = forms.IntegerField(min_value=0, initial=0)

    class Meta:
        model = Component
        fields = ("unique_id", "name", "section")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        settings = getattr(self.instance, "alert_settings", None) if self.instance.pk else None
        if self.instance.expiry_date:
            self.initial["expiry_date"] = self.instance.expiry_date.date()
            self.initial["expiry_time"] = self.instance.expiry_date.time().replace(microsecond=0)
        if settings:
            self.initial["interval_days"] = settings.interval_days
            self.initial["interval_hours"] = settings.interval_hours

    def clean(self):
        cleaned = super().clean()
        expiry_date = cleaned.get("expiry_date")
        expiry_time = cleaned.get("expiry_time")
        if bool(expiry_date) != bool(expiry_time):
            raise ValidationError("Expiry date and time must be provided together.")
        expiry_datetime = datetime.combine(expiry_date, expiry_time) if expiry_date and expiry_time else None
        cleaned["expiry_datetime"] = timezone.make_aware(expiry_datetime) if expiry_datetime else None
        return cleaned


class MaintenanceLogForm(forms.ModelForm):
    class Meta:
        model = MaintenanceLog
        fields = ("notes", "file")
        widgets = {"notes": forms.Textarea}

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            return uploaded
        if uploaded.size > 5 * 1024 * 1024:
            raise ValidationError("The uploaded file is too large.")
        extension = Path(uploaded.name).suffix.lower()
        if extension not in {".jpg", ".jpeg", ".png", ".pdf"}:
            raise ValidationError("Only JPG, PNG, and PDF files are allowed.")
        header = uploaded.read(12)
        uploaded.seek(0)
        signatures = {
            ".jpg": (b"\xff\xd8\xff",),
            ".jpeg": (b"\xff\xd8\xff",),
            ".png": (b"\x89PNG\r\n\x1a\n",),
            ".pdf": (b"%PDF-",),
        }
        if not any(header.startswith(signature) for signature in signatures[extension]):
            raise ValidationError("The file content does not match its extension.")
        return uploaded


class ComponentEditLogForm(MaintenanceLogForm):
    notes = forms.CharField(required=False, widget=forms.Textarea)


class WorkOrderForm(forms.ModelForm):
    planned_for = forms.DateTimeField(required=False, input_formats=["%Y-%m-%dT%H:%M"], widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}))
    due_at = forms.DateTimeField(required=False, input_formats=["%Y-%m-%dT%H:%M"], widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}))

    class Meta:
        model = WorkOrder
        fields = ("component", "title", "description", "kind", "priority", "status", "assigned_to", "planned_for", "due_at", "completion_notes")
        widgets = {"description": forms.Textarea, "completion_notes": forms.Textarea}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(is_active=True).order_by("username")

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        due_at = cleaned.get("due_at")
        planned_for = cleaned.get("planned_for")
        if planned_for and due_at and planned_for > due_at:
            raise ValidationError("Planned time cannot be after the due time.")
        if status == WorkOrder.Status.COMPLETED and not cleaned.get("completion_notes"):
            raise ValidationError("Completion notes are required when closing a work order.")
        return cleaned


class PreventiveScheduleForm(forms.ModelForm):
    run_time = forms.TimeField(input_formats=["%H:%M", "%H:%M:%S"], widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}), initial=time(9, 0))
    starts_on = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    ends_on = forms.DateField(required=False, widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    timezone_name = forms.CharField(initial="UTC", help_text="Use an IANA timezone, such as Europe/London or America/New_York.")
    day_of_month = forms.IntegerField(required=False, min_value=1, max_value=31, widget=forms.NumberInput(attrs={"min": 1, "max": 31}))
    month_of_year = forms.IntegerField(required=False, min_value=1, max_value=12, widget=forms.NumberInput(attrs={"min": 1, "max": 12}))
    excluded_weekdays = forms.TypedMultipleChoiceField(required=False, choices=PreventiveSchedule.WEEKDAYS, coerce=int, widget=forms.CheckboxSelectMultiple, help_text="Tap each weekday to skip.")
    excluded_days_of_month = forms.CharField(required=False, help_text="Comma-separated calendar days to skip, such as 1, 15, 31.")
    excluded_months = forms.TypedMultipleChoiceField(required=False, choices=[(month, calendar.month_name[month]) for month in range(1, 13)], coerce=int, widget=forms.CheckboxSelectMultiple, help_text="Tap each month to skip. Selected months appear checked.")
    excluded_dates = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), help_text="Specific one-time dates to skip, comma or newline separated (YYYY-MM-DD).")
    create_days_before = forms.IntegerField(min_value=0, max_value=30, initial=1, help_text="Create each work order this many calendar days before its due date.")

    class Meta:
        model = PreventiveSchedule
        fields = ("component", "title", "description", "kind", "priority", "assigned_to", "cadence", "run_time", "timezone_name", "starts_on", "ends_on", "weekday", "day_of_month", "month_of_year", "excluded_weekdays", "excluded_days_of_month", "excluded_months", "excluded_dates", "create_days_before", "enabled")
        widgets = {"description": forms.Textarea, "weekday": forms.Select}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.fields["component"].queryset = Component.objects.select_related("section").order_by("unique_id")
        if self.instance.pk:
            self.initial["run_time"] = self.instance.run_time.strftime("%H:%M")

    def clean_timezone_name(self):
        name = self.cleaned_data["timezone_name"].strip()
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError("Enter a valid IANA timezone, such as Europe/London.") from exc
        return name

    def clean_excluded_days_of_month(self):
        raw = self.cleaned_data.get("excluded_days_of_month", "")
        if not raw.strip():
            return []
        try:
            values = sorted({int(value.strip()) for value in raw.replace("\n", ",").split(",") if value.strip()})
        except ValueError as exc:
            raise ValidationError("Enter excluded month days as comma-separated numbers from 1 to 31.") from exc
        if any(value < 1 or value > 31 for value in values):
            raise ValidationError("Excluded month days must be between 1 and 31.")
        return values

    def clean_excluded_dates(self):
        raw = self.cleaned_data.get("excluded_dates", "")
        if not raw.strip():
            return []
        values = set()
        try:
            for value in raw.replace(",", "\n").splitlines():
                value = value.strip()
                if value:
                    values.add(date.fromisoformat(value).isoformat())
        except ValueError as exc:
            raise ValidationError("Enter specific exception dates in YYYY-MM-DD format.") from exc
        return sorted(values)

    def clean(self):
        cleaned = super().clean()
        cadence = cleaned.get("cadence")
        if cadence == PreventiveSchedule.Cadence.WEEKLY and cleaned.get("weekday") is None:
            self.add_error("weekday", "Choose the weekday for this schedule.")
        if cadence in {PreventiveSchedule.Cadence.MONTHLY, PreventiveSchedule.Cadence.YEARLY} and not cleaned.get("day_of_month"):
            self.add_error("day_of_month", "Choose the day of the month.")
        if cadence == PreventiveSchedule.Cadence.YEARLY and not cleaned.get("month_of_year"):
            self.add_error("month_of_year", "Choose the month for this yearly schedule.")
        excluded_weekdays = cleaned.get("excluded_weekdays", [])
        excluded_months = cleaned.get("excluded_months", [])
        if cadence == PreventiveSchedule.Cadence.WEEKLY and cleaned.get("weekday") in excluded_weekdays:
            self.add_error("excluded_weekdays", "The scheduled weekday cannot also be excluded.")
        if cadence == PreventiveSchedule.Cadence.YEARLY and cleaned.get("month_of_year") in excluded_months:
            self.add_error("excluded_months", "The scheduled month cannot also be excluded for a yearly job.")
        if cadence == PreventiveSchedule.Cadence.DAILY and len(excluded_weekdays) == 7:
            self.add_error("excluded_weekdays", "At least one weekday must remain active for a daily schedule.")
        starts_on, ends_on = cleaned.get("starts_on"), cleaned.get("ends_on")
        if starts_on and ends_on and ends_on < starts_on:
            self.add_error("ends_on", "The end date cannot be before the start date.")
        return cleaned

    def save(self, commit=True):
        schedule = super().save(commit=False)
        from .preventive import first_occurrence_on_or_after
        schedule.next_run_date = first_occurrence_on_or_after(schedule, schedule.starts_on)
        if commit:
            schedule.save()
            self.save_m2m()
        return schedule
