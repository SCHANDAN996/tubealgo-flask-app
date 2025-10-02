# Filepath: tubealgo/forms.py

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField, FloatField, IntegerField, DateField, TextAreaField, DateTimeLocalField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional

class SignupForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(message="Please enter a valid email.")])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8, message="Password must be at least 8 characters long.")])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message="Passwords must match.")])
    submit = SubmitField('Create Account')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')

# --- यह नया फॉर्म जोड़ें ---
class PlaylistForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=150)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=5000)])
    privacy_status = SelectField(
        'Visibility', 
        choices=[('public', 'Public'), ('unlisted', 'Unlisted'), ('private', 'Private')],
        validators=[DataRequired()]
    )
    submit = SubmitField('Save Playlist')
# --- यहाँ तक ---

class VideoForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=5000)])
    tags = StringField('Tags', validators=[Optional(), Length(max=500)])
    thumbnail = FileField('Thumbnail', validators=[Optional(), FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')])
    visibility = SelectField(
        'Visibility', 
        choices=[
            ('private', 'Private'), 
            ('unlisted', 'Unlisted'), 
            ('public', 'Public'),
            ('schedule', 'Schedule / Premiere')
        ], 
        validators=[DataRequired()]
    )
    publish_at = DateTimeLocalField('Premiere / Schedule At', format='%Y-%m-%dT%H:%M:%S', validators=[Optional()])
    submit = SubmitField('Save Changes')

class UploadForm(VideoForm):
    video_file = FileField('Video File', 
        validators=[
            FileRequired(), 
            FileAllowed(['mp4', 'mov', 'webm', 'mkv', 'avi'], 'Only video files are allowed!')
        ],
        render_kw={'accept': 'video/*'}
    )
    submit = SubmitField('Upload Video')

class CouponForm(FlaskForm):
    code = StringField('Coupon Code', validators=[DataRequired(), Length(min=3, max=50)])
    discount_type = SelectField('Discount Type', choices=[('percentage', 'Percentage'), ('fixed', 'Fixed Amount')], validators=[DataRequired()])
    discount_value = FloatField('Discount Value', validators=[DataRequired()])
    max_uses = IntegerField('Maximum Uses', validators=[DataRequired()])
    valid_until = DateField('Valid Until (Optional)', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('Save Coupon')

class PlanForm(FlaskForm):
    price = IntegerField('Price (in Paise, e.g., 39900 for ₹399)', validators=[DataRequired()])
    slashed_price = IntegerField('Slashed Price (in Paise, optional)', validators=[Optional()])
    competitors_limit = IntegerField('Competitors Limit (-1 for unlimited)', validators=[DataRequired()])
    keyword_searches_limit = IntegerField('Daily Keyword Searches (-1 for unlimited)', validators=[DataRequired()])
    ai_generations_limit = IntegerField('Daily AI Generations (-1 for unlimited)', validators=[DataRequired()])
    has_discover_tools = BooleanField('Discover Tools Access')
    has_ai_suggestions = BooleanField('AI Video Suggestions Access')
    submit = SubmitField('Update Plan')