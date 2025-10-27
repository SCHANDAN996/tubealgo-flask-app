# create_tables.py

from tubealgo import create_app, db

print("Starting table creation process...")

# Flask ऐप इंस्टेंस बनाएं ताकि हमें ऐप का कॉन्टेक्स्ट मिल सके
app = create_app()

# ऐप कॉन्टेक्स्ट के अंदर, सभी टेबल बनाएं
with app.app_context():
    print("Inside application context, creating tables...")
    # यह आपके सभी मॉडल्स के आधार पर टेबल बनाएगा
    db.create_all()
    print("Database tables created successfully! ✨")

print("Table creation script finished.")
