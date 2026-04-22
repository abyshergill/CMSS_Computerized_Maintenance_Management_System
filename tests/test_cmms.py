import pytest
from app import create_app, db
from app.models import User, Section, Component, AlertSettings, MaintenanceLog
from sqlalchemy.exc import IntegrityError
from config import Config
from datetime import datetime, timedelta, timezone

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://' # In-memory database for testing
    WTF_CSRF_ENABLED = False

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def init_db(app):
    with app.app_context():
        admin = User(username='admin', role='Admin')
        admin.set_password('adminpass')
        auth_user = User(username='authuser', role='Authorized')
        auth_user.set_password('authpass')
        db.session.add_all([admin, auth_user])
        db.session.commit()
        # Return IDs instead of objects to avoid DetachedInstanceError
        return {'admin_id': admin.id, 'auth_user_id': auth_user.id}

def test_authorized_user_cannot_access_admin_routes(client, init_db):
    # Login as authorized user
    client.post('/login', data={'username': 'authuser', 'password': 'authpass'})
    
    # Attempt to access register user (Admin only)
    response = client.get('/register')
    assert response.status_code == 403
    
    # Attempt to access manage sections (Admin only)
    response = client.get('/manage_sections')
    assert response.status_code == 403

def test_admin_can_access_admin_routes(client, init_db):
    # Login as admin user
    client.post('/login', data={'username': 'admin', 'password': 'adminpass'})
    
    # Attempt to access manage sections (Admin only)
    response = client.get('/manage_sections')
    assert response.status_code == 200

def test_unique_id_constraint(app, init_db):
    with app.app_context():
        section = Section(name='Test Section')
        db.session.add(section)
        db.session.commit()
        
        # Add first component
        comp1 = Component(unique_id='COMP-123', name='Pump', section_id=section.id)
        db.session.add(comp1)
        db.session.commit()
        
        # Attempt to add second component with same ID
        comp2 = Component(unique_id='COMP-123', name='Motor', section_id=section.id)
        db.session.add(comp2)
        
        with pytest.raises(IntegrityError):
            db.session.commit()

def test_dashboard_and_alert_hub_with_expiry_logic(client, app, init_db):
    with app.app_context():
        section = Section(name='HVAC')
        db.session.add(section)
        db.session.commit()
        
        # 1. Component that has EXPIRED (should be Bad)
        now_local = datetime.now()
        comp_bad = Component(unique_id='AC-BAD', name='Expired Unit', section_id=section.id, status='Good',
                             expiry_date=now_local - timedelta(hours=1))
        db.session.add(comp_bad)
        
        # 2. Component within LEAD TIME (should be Alert)
        # Expiry in 1 day, Lead time 2 days
        comp_alert = Component(unique_id='AC-ALERT', name='Expiring Soon', section_id=section.id, status='Good',
                               expiry_date=now_local + timedelta(days=1))
        db.session.add(comp_alert)
        db.session.flush()
        alert_settings = AlertSettings(component_id=comp_alert.id, interval_days=2, interval_hours=0)
        db.session.add(alert_settings)
        
        # 3. Component NOT within Lead Time (should be Good)
        # Expiry in 5 days, Lead time 2 days
        comp_good = Component(unique_id='AC-GOOD', name='Healthy Unit', section_id=section.id, status='Good',
                              expiry_date=now_local + timedelta(days=5))
        db.session.add(comp_good)
        db.session.flush()
        alert_settings_good = AlertSettings(component_id=comp_good.id, interval_days=2, interval_hours=0)
        db.session.add(alert_settings_good)
        
        db.session.commit()

    # Login as admin
    client.post('/login', data={'username': 'admin', 'password': 'adminpass'})
    
    # Check dashboard - triggers check_component_alerts
    response = client.get('/index')
    assert response.status_code == 200
    
    with app.app_context():
        c_bad = Component.query.filter_by(unique_id='AC-BAD').first()
        assert c_bad.status == 'Bad'
        
        c_alert = Component.query.filter_by(unique_id='AC-ALERT').first()
        assert c_alert.status == 'Alert'
        
        c_good = Component.query.filter_by(unique_id='AC-GOOD').first()
        assert c_good.status == 'Good'
    
    # Check alert hub - should show AC-BAD and AC-ALERT
    response = client.get('/alert_hub')
    assert response.status_code == 200
    assert b'AC-BAD' in response.data
    assert b'AC-ALERT' in response.data
    assert b'AC-GOOD' not in response.data

def test_section_rename_and_duplicate_prevention(client, app, init_db):
    with app.app_context():
        s1 = Section(name='Plumbing')
        s2 = Section(name='Electrical')
        db.session.add_all([s1, s2])
        db.session.commit()
        s2_id = s2.id

    # Login as admin
    client.post('/login', data={'username': 'admin', 'password': 'adminpass'})
    
    # Try to rename 'Electrical' to 'Plumbing' (already exists)
    response = client.post(f'/edit_section/{s2_id}', data={'name': 'Plumbing'}, follow_redirects=True)
    assert b'Error: Section name might already exist.' in response.data
    
    # Verify name is still 'Electrical'
    with app.app_context():
        sec = Section.query.get(s2_id)
        assert sec.name == 'Electrical'
        
    # Valid rename
    response = client.post(f'/edit_section/{s2_id}', data={'name': 'Solar'}, follow_redirects=True)
    assert b'Section renamed.' in response.data
    with app.app_context():
        sec = Section.query.get(s2_id)
        assert sec.name == 'Solar'

def test_section_cascade_delete(client, app, init_db):
    with app.app_context():
        s = Section(name='To Delete')
        db.session.add(s)
        db.session.commit()
        s_id = s.id
        
        c = Component(unique_id='DEL-1', name='Temp', section_id=s_id, status='Good')
        db.session.add(c)
        db.session.commit()
        c_id = c.id

    # Login as admin
    client.post('/login', data={'username': 'admin', 'password': 'adminpass'})
    
    # Delete section
    client.post(f'/delete_section/{s_id}', follow_redirects=True)
    
    with app.app_context():
        assert Section.query.get(s_id) is None
        assert Component.query.get(c_id) is None
