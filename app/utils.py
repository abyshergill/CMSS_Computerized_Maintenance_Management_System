from functools import wraps
from flask import abort
from flask_login import current_user
from datetime import datetime, timedelta, timezone
import bleach

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'Admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def sanitize_html(text):
    if not text: return ""
    return bleach.clean(text)

def check_component_alerts(components, db_session):
    updated = False
    now = datetime.now() # Use local time to match user input
    for comp in components:
        if comp.expiry_date:
            lead_time = timedelta(days=0, hours=0)
            if comp.alert_settings:
                lead_time = timedelta(days=comp.alert_settings.interval_days, hours=comp.alert_settings.interval_hours)
            
            # Critical Check (Expired)
            if now >= comp.expiry_date:
                if comp.status != 'Bad':
                    comp.status = 'Bad'
                    updated = True
            # Alert Check (Within Lead Time)
            elif now >= (comp.expiry_date - lead_time):
                if comp.status == 'Good':
                    comp.status = 'Alert'
                    updated = True
            # Recovery Check (If expiry date was extended)
            else:
                if comp.status in ['Alert', 'Bad']:
                    comp.status = 'Good'
                    updated = True
    if updated:
        db_session.commit()