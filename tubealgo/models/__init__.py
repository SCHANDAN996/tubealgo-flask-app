# tubealgo/models/__init__.py

# First, import the db instance that all models will use
from .. import db

# Now, import all the model classes and related functions from their new files
from .system_models import SystemLog, ApiCache, APIKeyStatus, SiteSetting, log_system_event, is_admin_telegram_user, get_setting, get_config_value, DashboardCache
from .user_models import User, SearchHistory, ContentIdea, Goal, load_user
from .youtube_models import YouTubeChannel, ChannelSnapshot, Competitor, ThumbnailTest, VideoSnapshot
from .payment_models import Coupon, Payment, SubscriptionPlan

# __all__ defines the public API for the models package.
# This allows other parts of the application to still do `from tubealgo.models import User`
__all__ = [
    "db",
    "SystemLog", "ApiCache", "APIKeyStatus", "SiteSetting", "log_system_event", "is_admin_telegram_user", "get_setting", "get_config_value", "DashboardCache",
    "User", "SearchHistory", "ContentIdea", "Goal", "load_user",
    "YouTubeChannel", "ChannelSnapshot", "Competitor", "ThumbnailTest", "VideoSnapshot",
    "Coupon", "Payment", "SubscriptionPlan"
]