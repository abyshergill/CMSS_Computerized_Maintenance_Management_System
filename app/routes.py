import os
from datetime import datetime
from flask import Blueprint, render_template, flash, redirect, url_for, request, current_app
from flask_login import current_user, login_user, logout_user, login_required
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
from app import db
from app.models import User, Section, Component, MaintenanceLog, AlertSettings
from app.forms import LoginForm, RegistrationForm, SectionForm, ComponentForm, MaintenanceLogForm
from app.utils import admin_required, sanitize_html, check_component_alerts

bp = Blueprint('main', __name__)

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    components = Component.query.all()
    check_component_alerts(components, db.session)
    
    sections = Section.query.all()
    dashboard_data = []
    for section in sections:
        section_comps = section.components.all()
        good = sum(1 for c in section_comps if c.status == 'Good')
        alert = sum(1 for c in section_comps if c.status == 'Alert')
        bad = sum(1 for c in section_comps if c.status == 'Bad')
        dashboard_data.append({
            'section_name': section.name,
            'data': [good, alert, bad]
        })
    
    return render_template('dashboard.html', title='Dashboard', dashboard_data=dashboard_data)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            current_app.logger.warning(f'Failed login attempt for username: {form.username.data}')
            flash('Invalid username or password', 'error')
            return redirect(url_for('main.login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/register', methods=['GET', 'POST'])
@login_required
@admin_required
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, role=form.role.data)
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
            flash('Congratulations, new user registered!', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Database error on registration: {e}')
            flash('An error occurred. Please try again.', 'error')
    return render_template('register.html', title='Register', form=form)

@bp.route('/manage_sections', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_sections():
    form = SectionForm()
    if form.validate_on_submit():
        section = Section(name=form.name.data)
        db.session.add(section)
        try:
            db.session.commit()
            flash('Section added.', 'success')
            return redirect(url_for('main.manage_sections'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding section. Might already exist.', 'error')
    sections = Section.query.all()
    return render_template('manage_sections.html', title='Manage Sections', form=form, sections=sections)

@bp.route('/manage_components', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_components():
    form = ComponentForm()
    form.section_id.choices = [(s.id, s.name) for s in Section.query.all()]
    if form.validate_on_submit():
        try:
            # Combine date and time
            expiry_dt = datetime.combine(form.expiry_date.data, form.expiry_time.data)
            component = Component(unique_id=form.unique_id.data, name=form.name.data, section_id=form.section_id.data, expiry_date=expiry_dt)
            db.session.add(component)
            db.session.flush() # get component id
            alert_settings = AlertSettings(component_id=component.id, interval_days=form.interval_days.data, interval_hours=form.interval_hours.data)
            db.session.add(alert_settings)
            db.session.commit()
            flash('Component added.', 'success')
            return redirect(url_for('main.manage_components'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding component. Ensure Unique ID is not a duplicate.', 'error')
            current_app.logger.error(f'Error adding component: {e}')
    components = Component.query.all()
    check_component_alerts(components, db.session)
    return render_template('manage_components.html', title='Manage Components', form=form, components=components)

@bp.route('/alert_hub')
@login_required
def alert_hub():
    components = Component.query.all()
    check_component_alerts(components, db.session)
    
    # Group by Section
    alert_components_by_section = {}
    for c in components:
        if c.status in ['Alert', 'Bad']:
            sec_name = c.section.name if c.section else 'Unknown'
            if sec_name not in alert_components_by_section:
                alert_components_by_section[sec_name] = []
            alert_components_by_section[sec_name].append(c)
            
    return render_template('alert_hub.html', title='Alert Hub', alert_data=alert_components_by_section)

@bp.route('/component/<int:id>', methods=['GET', 'POST'])
@login_required
def component_detail(id):
    component = Component.query.get_or_404(id)
    form = MaintenanceLogForm()
    if form.validate_on_submit():
        filename = None
        if form.file.data:
            f = form.file.data
            filename = secure_filename(f.filename)
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            f.save(file_path)
            
        safe_notes = sanitize_html(form.notes.data)
        log = MaintenanceLog(component_id=component.id, user_id=current_user.id, notes=safe_notes, file_path=filename)
        component.status = form.status_update.data
        db.session.add(log)
        try:
            db.session.commit()
            flash('Log added successfully.', 'success')
            return redirect(url_for('main.component_detail', id=component.id))
        except Exception as e:
            db.session.rollback()
            flash('Error adding log.', 'error')
            current_app.logger.error(f'Error adding log: {e}')
            
    logs = component.history.order_by(MaintenanceLog.date.desc()).all()
    return render_template('history.html', title=f'{component.name} History', component=component, form=form, logs=logs)

@bp.route('/edit_section/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_section(id):
    section = Section.query.get_or_404(id)
    form = SectionForm(obj=section)
    if form.validate_on_submit():
        section.name = form.name.data
        try:
            db.session.commit()
            flash('Section renamed.', 'success')
            return redirect(url_for('main.manage_sections'))
        except Exception as e:
            db.session.rollback()
            flash('Error: Section name might already exist.', 'error')
    return render_template('edit_section.html', title='Edit Section', form=form, section=section)

@bp.route('/delete_section/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_section(id):
    section = Section.query.get_or_404(id)
    db.session.delete(section)
    try:
        db.session.commit()
        flash('Section and its components deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting section.', 'error')
    return redirect(url_for('main.manage_sections'))
@bp.route('/edit_component/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_component(id):
    component = Component.query.get_or_404(id)
    form = ComponentForm(obj=component)
    form.section_id.choices = [(s.id, s.name) for s in Section.query.all()]

    # Pre-fill fields
    if request.method == 'GET':
        if component.expiry_date:
            form.expiry_date.data = component.expiry_date.date()
            form.expiry_time.data = component.expiry_date.time()
        if component.alert_settings:
            form.interval_days.data = component.alert_settings.interval_days
            form.interval_hours.data = component.alert_settings.interval_hours

    if form.validate_on_submit():
        component.unique_id = form.unique_id.data
        component.name = form.name.data
        component.section_id = form.section_id.data
        # Combine date and time
        component.expiry_date = datetime.combine(form.expiry_date.data, form.expiry_time.data)

        if component.alert_settings:
            component.alert_settings.interval_days = form.interval_days.data
            component.alert_settings.interval_hours = form.interval_hours.data
        else:
            alert_settings = AlertSettings(component_id=component.id, 
                                          interval_days=form.interval_days.data, 
                                          interval_hours=form.interval_hours.data)
            db.session.add(alert_settings)
            
        try:
            db.session.commit()
            flash('Component updated.', 'success')
            return redirect(url_for('main.manage_components'))
        except Exception as e:
            db.session.rollback()
            flash('Error: Component ID might already exist.', 'error')
            current_app.logger.error(f'Error updating component: {e}')
    return render_template('edit_component.html', title='Edit Component', form=form, component=component)

@bp.route('/delete_component/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_component(id):
    component = Component.query.get_or_404(id)
    db.session.delete(component)
    try:
        db.session.commit()
        flash('Component and its history deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting component.', 'error')
    return redirect(url_for('main.manage_components'))

@bp.app_errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

@bp.app_errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
