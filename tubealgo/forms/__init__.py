# tubealgo/forms/__init__.py

from .auth_forms import SignupForm, LoginForm
from .youtube_forms import PlaylistForm, VideoForm, UploadForm
from .admin_forms import CouponForm, PlanForm

__all__ = [
    "SignupForm", "LoginForm",
    "PlaylistForm", "VideoForm", "UploadForm",
    "CouponForm", "PlanForm"
]