# tubealgo/routes/admin/__init__.py

from flask import Blueprint
# from flask_wtf.csrf import generate_csrf # <<<--- यह इम्पोर्ट हटाएं

# मुख्य एडमिन Blueprint यहाँ बनाया गया है
admin_bp = Blueprint('admin', __name__, template_folder='../../templates/admin')

# <<<--- कॉन्टेक्स्ट प्रोसेसर यहाँ से हटा दिया गया है --->>>
# @admin_bp.context_processor
# def inject_csrf_token_admin():
#    """Injects the CSRF token generation function into admin templates."""
#    return dict(csrf_token=generate_csrf)
# <<<--- यहाँ तक हटाया गया है --->>>

# बाकी की एडमिन route फाइलों को इम्पोर्ट करें ताकि उनके रूट्स रजिस्टर हो जाएं
from . import dashboard, users, monetization, system
