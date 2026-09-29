from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Component


@transaction.atomic
def refresh_component_statuses(components=None):
    """Refresh alert state without committing from a read-only view."""
    queryset = components if components is not None else Component.objects.select_related("alert_settings")
    now = timezone.now()
    changed = []
    for component in queryset:
        if not component.expiry_date:
            if component.status != Component.Status.GOOD:
                component.status = Component.Status.GOOD
                changed.append(component)
            continue
        lead_time = component.alert_settings.lead_time() if hasattr(component, "alert_settings") else timedelta()
        if now >= component.expiry_date:
            expected = Component.Status.BAD
        elif now >= component.expiry_date - lead_time:
            expected = Component.Status.ALERT
        else:
            expected = Component.Status.GOOD
        if component.status != expected:
            component.status = expected
            changed.append(component)
    if changed:
        Component.objects.bulk_update(changed, ["status"])
    return len(changed)
