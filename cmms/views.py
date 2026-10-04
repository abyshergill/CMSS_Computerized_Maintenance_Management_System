from functools import wraps
import csv
import time

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import ComponentEditLogForm, ComponentForm, LoginForm, MaintenanceLogForm, PreventiveScheduleForm, RegistrationForm, SectionForm, WorkOrderForm
from .models import AlertSettings, Component, PreventiveSchedule, Section, User, WorkOrder
from .services import refresh_component_statuses


def cmms_admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_cmms_admin:
            return HttpResponseForbidden("Forbidden")
        return view(request, *args, **kwargs)
    return wrapped


def login_view(request):
    if request.user.is_authenticated:
        return redirect("cmms:dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        now = time.time()
        failed_at = request.session.get("login_failed_at", 0)
        failed_attempts = request.session.get("login_failed_attempts", 0)
        if failed_attempts >= 5 and now - failed_at < 300:
            form.add_error(None, "Too many failed attempts. Try again in a few minutes.")
            return render(request, "registration/login.html", {"form": form})
        user = authenticate(request, username=form.cleaned_data["username"], password=form.cleaned_data["password"])
        if user is not None:
            request.session.pop("login_failed_at", None)
            request.session.pop("login_failed_attempts", None)
            login(request, user)
            next_url = request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(next_url)
            return redirect("cmms:dashboard")
        request.session["login_failed_at"] = now
        request.session["login_failed_attempts"] = failed_attempts + 1
        form.add_error(None, "Invalid username or password.")
    return render(request, "registration/login.html", {"form": form})


@login_required
def logout_view(request):
    if request.method != "POST":
        return HttpResponseForbidden("Logout requires POST")
    logout(request)
    return redirect("cmms:login")


@cmms_admin_required
def register(request):
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"Account for {user.username} created.")
        return redirect("cmms:manage-users")
    return render(request, "cmms/register.html", {"form": form})


@cmms_admin_required
def manage_users(request):
    search_query = request.GET.get("q", "").strip()
    users = User.objects.all()
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )
    users = users.order_by("username")
    return render(
        request,
        "cmms/manage_users.html",
        {"users": users, "search_query": search_query, "user_count": users.count()},
    )


@login_required
def dashboard(request):
    refresh_component_statuses()
    data = []
    for section in Section.objects.prefetch_related("components"):
        statuses = [component.status for component in section.components.all()]
        data.append({"section_name": section.name, "good": statuses.count(Component.Status.GOOD), "alert": statuses.count(Component.Status.ALERT), "bad": statuses.count(Component.Status.BAD)})
    open_work_orders = WorkOrder.objects.exclude(status__in=[WorkOrder.Status.COMPLETED, WorkOrder.Status.CANCELLED])
    work_order_statuses = [status for status, _ in WorkOrder.Status.choices]
    work_order_counts = [WorkOrder.objects.filter(status=status).count() for status in work_order_statuses]
    health_chart = {"labels": ["Good", "Alert", "Bad"], "values": [sum(row["good"] for row in data), sum(row["alert"] for row in data), sum(row["bad"] for row in data)]}
    work_order_chart = {"labels": work_order_statuses, "values": work_order_counts}
    return render(request, "cmms/dashboard.html", {"dashboard_data": data, "open_work_orders": open_work_orders.count(), "overdue_work_orders": sum(order.is_overdue for order in open_work_orders), "schedule_count": PreventiveSchedule.objects.filter(enabled=True).count(), "health_chart": health_chart, "work_order_chart": work_order_chart})


@login_required
def alert_hub(request):
    refresh_component_statuses()
    components = Component.objects.filter(status__in=[Component.Status.ALERT, Component.Status.BAD]).select_related("section")
    grouped = {}
    for component in components:
        component.latest_file_log = component.history.exclude(file="").exclude(file__isnull=True).first()
        grouped.setdefault(component.section.name if component.section else "Unknown", []).append(component)
    return render(request, "cmms/alert_hub.html", {"alert_data": grouped})


@cmms_admin_required
def manage_sections(request):
    form = SectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Section added.")
        return redirect("cmms:manage-sections")
    return render(request, "cmms/manage_sections.html", {"form": form, "sections": Section.objects.all()})


@cmms_admin_required
def edit_section(request, pk):
    section = get_object_or_404(Section, pk=pk)
    form = SectionForm(request.POST or None, instance=section)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("cmms:manage-sections")
    return render(request, "cmms/edit_section.html", {"form": form, "section": section})


@cmms_admin_required
def delete_section(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden("Deletion requires POST")
    get_object_or_404(Section, pk=pk).delete()
    return redirect("cmms:manage-sections")


@cmms_admin_required
def manage_components(request):
    form = ComponentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            component = form.save(commit=False)
            component.expiry_date = form.cleaned_data["expiry_datetime"]
            component.save()
            AlertSettings.objects.update_or_create(component=component, defaults={"interval_days": form.cleaned_data["interval_days"], "interval_hours": form.cleaned_data["interval_hours"]})
        return redirect("cmms:manage-components")
    refresh_component_statuses()
    return render(request, "cmms/manage_components.html", {"form": form, "components": Component.objects.all()})


@cmms_admin_required
def edit_component(request, pk):
    component = get_object_or_404(Component, pk=pk)
    form = ComponentForm(request.POST or None, instance=component)
    log_form = ComponentEditLogForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid() and log_form.is_valid():
        with transaction.atomic():
            component = form.save(commit=False)
            component.expiry_date = form.cleaned_data["expiry_datetime"]
            component.save()
            AlertSettings.objects.update_or_create(component=component, defaults={"interval_days": form.cleaned_data["interval_days"], "interval_hours": form.cleaned_data["interval_hours"]})
            log = log_form.save(commit=False)
            log.component = component
            log.author = request.user
            log.notes = log.notes or "Component details updated."
            log.save()
        return redirect("cmms:manage-components")
    return render(request, "cmms/edit_component.html", {"form": form, "log_form": log_form, "component": component})


@cmms_admin_required
def delete_component(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden("Deletion requires POST")
    get_object_or_404(Component, pk=pk).delete()
    return redirect("cmms:manage-components")


@login_required
def component_detail(request, pk):
    component = get_object_or_404(Component, pk=pk)
    form = MaintenanceLogForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        log = form.save(commit=False)
        log.component = component
        log.author = request.user
        log.save()
        return redirect("cmms:component-detail", pk=component.pk)
    return render(request, "cmms/history.html", {"component": component, "form": form, "logs": component.history.select_related("author")})


@login_required
def download_history(request, pk):
    component = get_object_or_404(Component, pk=pk)
    requested_limit = request.GET.get("limit", "10")
    limits = {"10": 10, "20": 20, "50": 50, "all": None}
    limit = limits.get(requested_limit, 10)
    logs = component.history.select_related("author")
    if limit:
        logs = logs[:limit]

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{component.unique_id}-history.csv"'
    writer = csv.writer(response)
    writer.writerow(["Date", "Author", "Notes", "Attachment"])
    for log in logs:
        writer.writerow([
            log.date.isoformat(),
            log.author.username if log.author else "System",
            log.notes,
            log.file.url if log.file else "",
        ])
    return response


@login_required
def manage_work_orders(request):
    form = WorkOrderForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        work_order = form.save(commit=False)
        work_order.requested_by = request.user
        work_order.save()
        return redirect("cmms:work-orders")
    work_orders = WorkOrder.objects.select_related("component", "assigned_to", "requested_by")
    status_filter = request.GET.get("status")
    if status_filter in dict(WorkOrder.Status.choices):
        work_orders = work_orders.filter(status=status_filter)
    if request.GET.get("mine") == "1":
        work_orders = work_orders.filter(assigned_to=request.user)
    return render(request, "cmms/work_orders.html", {"form": form, "work_orders": work_orders, "status_choices": WorkOrder.Status.choices, "selected_status": status_filter})


@login_required
def work_order_detail(request, pk):
    work_order = get_object_or_404(WorkOrder.objects.select_related("component", "assigned_to", "requested_by"), pk=pk)
    can_edit = request.user.is_cmms_admin or request.user == work_order.requested_by or request.user == work_order.assigned_to
    if not can_edit:
        return HttpResponseForbidden("You do not have permission to update this work order.")
    form = WorkOrderForm(request.POST or None, instance=work_order)
    if request.method == "POST" and form.is_valid():
        work_order = form.save(commit=False)
        if work_order.status == WorkOrder.Status.COMPLETED and not work_order.completed_at:
            work_order.completed_at = timezone.now()
        elif work_order.status != WorkOrder.Status.COMPLETED:
            work_order.completed_at = None
        work_order.save()
        return redirect("cmms:work-order-detail", pk=work_order.pk)
    return render(request, "cmms/work_order_detail.html", {"form": form, "work_order": work_order})


@cmms_admin_required
def manage_preventive_schedules(request):
    form = PreventiveScheduleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        schedule = form.save(commit=False)
        schedule.created_by = request.user
        schedule.save()
        messages.success(request, "Recurring maintenance schedule created. The generator will create its work orders automatically.")
        return redirect("cmms:preventive-schedules")
    schedules = PreventiveSchedule.objects.select_related("component", "assigned_to", "created_by")
    return render(request, "cmms/preventive_schedules.html", {"form": form, "schedules": schedules})


@cmms_admin_required
def toggle_preventive_schedule(request, pk):
    if request.method != "POST":
        return HttpResponseForbidden("Schedule changes require POST")
    schedule = get_object_or_404(PreventiveSchedule, pk=pk)
    schedule.enabled = not schedule.enabled
    schedule.save(update_fields=["enabled"])
    messages.success(request, "Recurring schedule " + ("enabled." if schedule.enabled else "paused."))
    return redirect("cmms:preventive-schedules")
