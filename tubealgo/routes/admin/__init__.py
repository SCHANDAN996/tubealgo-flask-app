# tubealgo/routes/admin/__init__.py

from flask import Blueprint

# मुख्य एडमिन Blueprint यहाँ बनाया गया है
admin_bp = Blueprint('admin', __name__, template_folder='../../templates/admin')

# बाकी की एडमिन route फाइलों को इम्पोर्ट करें ताकि उनके रूट्स रजिस्टर हो जाएं
from . import dashboard, users, monetization, system