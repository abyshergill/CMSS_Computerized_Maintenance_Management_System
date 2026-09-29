import calendar
from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import PreventiveSchedule, WorkOrder

MAX_OCCURRENCES_PER_SCHEDULE = 100


def _date_in_month(year, month, requested_day):
    return date(year, month, min(requested_day, calendar.monthrange(year, month)[1]))


def first_occurrence_on_or_after(schedule, start_date):
    if schedule.cadence == PreventiveSchedule.Cadence.DAILY:
        return start_date
    if schedule.cadence == PreventiveSchedule.Cadence.WEEKLY:
        weekday = schedule.weekday if schedule.weekday is not None else start_date.weekday()
        return start_date + timedelta(days=(weekday - start_date.weekday()) % 7)
    if schedule.cadence == PreventiveSchedule.Cadence.MONTHLY:
        candidate = _date_in_month(start_date.year, start_date.month, schedule.day_of_month)
        if candidate < start_date:
            year, month = (start_date.year + 1, 1) if start_date.month == 12 else (start_date.year, start_date.month + 1)
            candidate = _date_in_month(year, month, schedule.day_of_month)
        return candidate
    month = schedule.month_of_year
    candidate = _date_in_month(start_date.year, month, schedule.day_of_month)
    if candidate < start_date:
        candidate = _date_in_month(start_date.year + 1, month, schedule.day_of_month)
    return candidate


def next_occurrence_after(schedule, occurrence_date):
    if schedule.cadence == PreventiveSchedule.Cadence.DAILY:
        return occurrence_date + timedelta(days=1)
    if schedule.cadence == PreventiveSchedule.Cadence.WEEKLY:
        return occurrence_date + timedelta(days=7)
    if schedule.cadence == PreventiveSchedule.Cadence.MONTHLY:
        year, month = (occurrence_date.year + 1, 1) if occurrence_date.month == 12 else (occurrence_date.year, occurrence_date.month + 1)
        return _date_in_month(year, month, schedule.day_of_month)
    return _date_in_month(occurrence_date.year + 1, schedule.month_of_year, schedule.day_of_month)


def local_scheduled_datetime(schedule, occurrence_date):
    zone = ZoneInfo(schedule.timezone_name)
    local_naive = datetime.combine(occurrence_date, schedule.run_time)
    candidate = local_naive.replace(tzinfo=zone, fold=0)
    round_trip = candidate.astimezone(datetime_timezone.utc).astimezone(zone)
    if round_trip.replace(tzinfo=None) == local_naive:
        return candidate
    # If the selected local time falls in a spring-forward gap, use the first valid minute after it.
    for minute in range(1, 181):
        adjusted = local_naive + timedelta(minutes=minute)
        candidate = adjusted.replace(tzinfo=zone, fold=0)
        if candidate.astimezone(datetime_timezone.utc).astimezone(zone).replace(tzinfo=None) == adjusted:
            return candidate
    raise ValueError(f"Could not resolve local time for schedule {schedule.pk} on {occurrence_date}.")


def is_excluded_occurrence(schedule, occurrence_date):
    """Return whether a local calendar occurrence is explicitly excluded."""
    excluded_dates = {str(value) for value in (schedule.excluded_dates or [])}
    return (
        occurrence_date.isoformat() in excluded_dates
        or occurrence_date.weekday() in (schedule.excluded_weekdays or [])
        or occurrence_date.day in (schedule.excluded_days_of_month or [])
        or occurrence_date.month in (schedule.excluded_months or [])
    )


def generate_due_work_orders(now=None, max_per_schedule=MAX_OCCURRENCES_PER_SCHEDULE):
    now = now or timezone.now()
    generated = 0
    for schedule_id in PreventiveSchedule.objects.filter(enabled=True).values_list("pk", flat=True):
        for _ in range(max_per_schedule):
            attempted_date = None
            try:
                with transaction.atomic():
                    schedule = PreventiveSchedule.objects.select_for_update().select_related("component", "assigned_to", "created_by").get(pk=schedule_id)
                    if not schedule.enabled:
                        break
                    occurrence_date = schedule.next_run_date
                    if schedule.ends_on and occurrence_date > schedule.ends_on:
                        schedule.enabled = False
                        schedule.save(update_fields=["enabled"])
                        break
                    attempted_date = occurrence_date
                    due_at = local_scheduled_datetime(schedule, occurrence_date)
                    create_at = due_at - timedelta(days=schedule.create_days_before)
                    if create_at > now:
                        break
                    if is_excluded_occurrence(schedule, occurrence_date):
                        schedule.next_run_date = next_occurrence_after(schedule, occurrence_date)
                        if schedule.ends_on and schedule.next_run_date > schedule.ends_on:
                            schedule.enabled = False
                        schedule.save(update_fields=["next_run_date", "enabled"])
                        continue
                    WorkOrder.objects.create(
                        component=schedule.component,
                        title=schedule.title,
                        description=schedule.description,
                        kind=schedule.kind,
                        priority=schedule.priority,
                        status=WorkOrder.Status.OPEN,
                        requested_by=schedule.created_by,
                        assigned_to=schedule.assigned_to,
                        planned_for=due_at,
                        due_at=due_at,
                        preventive_schedule=schedule,
                        schedule_occurrence_date=occurrence_date,
                    )
                    schedule.next_run_date = next_occurrence_after(schedule, occurrence_date)
                    if schedule.ends_on and schedule.next_run_date > schedule.ends_on:
                        schedule.enabled = False
                    schedule.save(update_fields=["next_run_date", "enabled"])
                generated += 1
            except IntegrityError:
                # The unique schedule/date constraint protects against concurrent command invocations.
                schedule = PreventiveSchedule.objects.get(pk=schedule_id)
                if attempted_date is None or not WorkOrder.objects.filter(preventive_schedule=schedule, schedule_occurrence_date=attempted_date).exists():
                    raise
                if schedule.next_run_date == attempted_date:
                    schedule.next_run_date = next_occurrence_after(schedule, attempted_date)
                    if schedule.ends_on and schedule.next_run_date > schedule.ends_on:
                        schedule.enabled = False
                    schedule.save(update_fields=["next_run_date", "enabled"])
    return generated
