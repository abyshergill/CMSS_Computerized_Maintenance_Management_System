from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, TextAreaField, IntegerField, DateField, TimeField
from wtforms.validators import DataRequired, ValidationError, NumberRange
from flask_wtf.file import FileField, FileAllowed
from app.models import User

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = SelectField('Role', choices=[('Authorized', 'Authorized'), ('Admin', 'Admin')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

class SectionForm(FlaskForm):
    name = StringField('Section Name', validators=[DataRequired()])
    submit = SubmitField('Save')

class ComponentForm(FlaskForm):
    unique_id = StringField('Unique ID', validators=[DataRequired()])
    name = StringField('Component Name', validators=[DataRequired()])
    section_id = SelectField('Section', coerce=int, validators=[DataRequired()])
    expiry_date = DateField('Expiry Date', validators=[DataRequired()])
    expiry_time = TimeField('Expiry Time', validators=[DataRequired()])
    interval_days = IntegerField('Alert Lead Time (Days before expiry)', default=0, validators=[NumberRange(min=0, message="Cannot be negative.")])
    interval_hours = IntegerField('Alert Lead Time (Hours before expiry)', default=0, validators=[NumberRange(min=0, message="Cannot be negative.")])
    submit = SubmitField('Save')

class MaintenanceLogForm(FlaskForm):
    notes = TextAreaField('Notes', validators=[DataRequired()])
    status_update = SelectField('Update Status To', choices=[('Good', 'Good'), ('Alert', 'Alert'), ('Bad', 'Bad')])
    file = FileField('Upload Image/Doc', validators=[FileAllowed(['jpg', 'png', 'pdf'], 'Images and PDFs only!')])
    submit = SubmitField('Add Log')