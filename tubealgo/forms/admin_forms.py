# tubealgo/forms/admin_forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, FloatField, IntegerField, DateField, BooleanField
from wtforms.validators import DataRequired, Length, Optional

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
    playlist_suggestions_limit = IntegerField('AI Playlist Ideas Limit (-1 for unlimited)', validators=[DataRequired()])
    has_discover_tools = BooleanField('Discover Tools Access')
    has_ai_suggestions = BooleanField('AI Video Suggestions Access')
    is_popular = BooleanField('Mark as Most Popular')
    
    # === बदलाव यहाँ है: नया फील्ड जोड़ा गया ===
    has_comment_reply = BooleanField('Enable Comment Reply & AI Suggestions')
    # === बदलाव यहाँ खत्म है ===

    submit = SubmitField('Update Plan')