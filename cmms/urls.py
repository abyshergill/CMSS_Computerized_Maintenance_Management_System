from django.urls import path

from . import views

app_name = "cmms"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("accounts/login/", views.login_view, name="accounts-login-compat"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard-alias"),
    path("register/", views.register, name="register"),
    path("alerts/", views.alert_hub, name="alert-hub"),
    path("sections/", views.manage_sections, name="manage-sections"),
    path("sections/<int:pk>/edit/", views.edit_section, name="edit-section"),
    path("sections/<int:pk>/delete/", views.delete_section, name="delete-section"),
    path("components/", views.manage_components, name="manage-components"),
    path("components/<int:pk>/edit/", views.edit_component, name="edit-component"),
    path("components/<int:pk>/delete/", views.delete_component, name="delete-component"),
    path("components/<int:pk>/", views.component_detail, name="component-detail"),
    path("components/<int:pk>/history/download/", views.download_history, name="download-history"),
    path("work-orders/", views.manage_work_orders, name="work-orders"),
    path("work-orders/<int:pk>/", views.work_order_detail, name="work-order-detail"),
    path("preventive-schedules/", views.manage_preventive_schedules, name="preventive-schedules"),
    path("preventive-schedules/<int:pk>/toggle/", views.toggle_preventive_schedule, name="toggle-preventive-schedule"),
]
