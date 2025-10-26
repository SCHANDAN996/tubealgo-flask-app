# tubealgo/routes/admin/dashboard.py

from flask import render_template
from flask_login import login_required
from . import admin_bp
from ... import db
from ...decorators import admin_required
from ...models import User, APIKeyStatus, get_config_value
from sqlalchemy import func
from datetime import date, datetime
import pytz

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    """
    Main admin dashboard with statistics and API status.
    
    Displays:
    - Total users, subscribed users, new users today
    - Recent 5 registered users
    - YouTube API key status and quota usage
    
    Chart data endpoints are in system.py to avoid route duplication.
    """
    
    # ==================== USER STATISTICS ====================
    total_users = User.query.count()
    subscribed_users = User.query.filter(User.subscription_plan != 'free').count()
    users_today = User.query.filter(func.date(User.created_at) == date.today()).count()
    
    # Recent users (last 5 registered)
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()

    # ==================== YOUTUBE API KEY STATUS ====================
    # Get API keys from config
    api_keys_str = get_config_value('YOUTUBE_API_KEYS', '')
    api_keys_list = [key.strip() for key in api_keys_str.split(',') if key.strip()]
    
    # Reset exhausted keys if it's a new day (Pacific Time zone)
    try:
        pacific_tz = pytz.timezone('America/Los_Angeles')
        pacific_now = datetime.now(pacific_tz)
        
        # Get midnight Pacific Time
        last_reset_pacific = pacific_now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Convert to UTC for database comparison
        last_reset_utc = last_reset_pacific.astimezone(pytz.utc)

        # Reset any keys that were exhausted before today (Pacific time)
        reset_count = APIKeyStatus.query.filter(
            APIKeyStatus.status == 'exhausted',
            APIKeyStatus.last_failure_at < last_reset_utc
        ).update({
            'status': 'active', 
            'last_failure_at': None
        })
        
        if reset_count > 0:
            db.session.commit()
            print(f"Reset {reset_count} exhausted API keys for new day (Pacific Time)")
        
    except Exception as e:
        print(f"Error during API key daily reset: {e}")
        db.session.rollback()

    # Helper function to mask YouTube API keys for display
    def mask_key_yt(key):
        """
        Mask YouTube API key for secure display.
        Shows: AIzaSyAB...xyz3
        """
        if key and len(key) > 12:
            return f"{key[:8]}...{key[-4:]}"
        return "Invalid Key Format"
    
    # Get masked key identifiers
    key_identifiers = [mask_key_yt(key) for key in api_keys_list]
    
    # Get status for each key from database
    key_statuses_query = APIKeyStatus.query.filter(
        APIKeyStatus.key_identifier.in_(key_identifiers)
    ).all()
    
    # Create a dictionary for quick lookup in template
    key_status_map = {
        status.key_identifier: status 
        for status in key_statuses_query
    }
    
    # Count how many keys are exhausted today
    exhausted_today_count = sum(
        1 for status in key_status_map.values() 
        if status.status == 'exhausted'
    )

    # ==================== RENDER TEMPLATE ====================
    return render_template(
        'admin/dashboard.html', 
        # User statistics
        total_users=total_users,
        subscribed_users=subscribed_users,
        users_today=users_today,
        recent_users=recent_users,
        # API key information
        api_key_count=len(api_keys_list),
        key_identifiers=key_identifiers,
        key_status_map=key_status_map,
        exhausted_today_count=exhausted_today_count
    )


# ==================== IMPORTANT NOTE ====================
# Chart data endpoints (user_growth_data, plan_distribution_data) 
# are defined in system.py to avoid route duplication errors.
# 
# Routes in system.py:
# - /data/user_growth       -> Returns JSON for user growth chart
# - /data/plan_distribution -> Returns JSON for plan pie chart
#
# These are called via fetch() from dashboard.html
# ========================================================
```

---

## ✅ **Key Features:**

### 📊 **Statistics Calculated:**
1. **Total Users** - All registered users
2. **Subscribed Users** - Users with paid plans (creator/pro)
3. **New Users Today** - Signups from current day
4. **Recent Users** - Last 5 registered users

### 🔑 **API Key Management:**
1. **Automatic Daily Reset** - Resets exhausted keys at midnight (Pacific Time)
2. **Secure Masking** - Shows only `AIzaSyAB...xyz3` format
3. **Status Tracking** - Active/Exhausted for each key
4. **Quota Estimation** - Based on number of exhausted keys

### 🔒 **Security:**
- `@login_required` - Must be logged in
- `@admin_required` - Must be admin user
- **Key masking** - Never exposes full API keys
- **Error handling** - Graceful fallback on failures

---

## 🎯 **How Data Flows:**
```
1. Browser loads /admin
   ↓
2. dashboard() function executes
   ↓
3. Calculates stats from database
   ↓
4. Renders dashboard.html
   ↓
5. JavaScript in dashboard.html fetches chart data
   ↓
6. Calls /data/user_growth (in system.py)
   ↓
7. Calls /data/plan_distribution (in system.py)
   ↓
8. Charts render with data
```

---

## 📁 **Complete File Structure:**
```
tubealgo/routes/admin/
├── __init__.py              # Blueprint creation
├── dashboard.py             # ← THIS FILE (main dashboard)
├── system.py                # Chart APIs + settings
├── users.py                 # User management
└── monetization.py          # Plans, coupons, payments