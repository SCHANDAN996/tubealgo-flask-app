# create_tables.py

from tubealgo import create_app, db, seed_plans
# Explicitly import models to ensure they are registered with SQLAlchemy's metadata
# before db.create_all() is called within this script's context.
# This imports everything defined in models/__init__.py's __all__
from tubealgo import models
import traceback # For printing detailed errors

print("--- Starting table creation script ---")

# Create Flask app instance to get app context and config
app = create_app()

# Use app context for database operations
with app.app_context():
    print("Inside application context...")
    try:
        print("Attempting to create all tables...")
        # Create all tables based on all imported models associated with 'db'
        db.create_all()
        print("db.create_all() executed.")

        # Verify tables (optional but helpful for debugging)
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"Tables found in database: {tables}")
        if "user" in tables and "subscription_plan" in tables:
             print("Verification successful: 'user' and 'subscription_plan' tables exist.")
        else:
             print("WARNING: Key tables ('user', 'subscription_plan') might be missing after create_all!")


        # Seed plans only after tables are confirmed/created
        print("Attempting to seed plans...")
        seed_plans() # Function already checks if seeding is needed

    except Exception as e:
        # Catch any error during table creation or seeding
        print(f"!!! ERROR during table creation or seeding !!!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {e}")
        print("--- Traceback ---")
        traceback.print_exc() # Print full traceback
        print("--- End Traceback ---")
        # Exit with error code to potentially fail the build
        import sys
        sys.exit(1)


print("--- Table creation script finished successfully ---")
