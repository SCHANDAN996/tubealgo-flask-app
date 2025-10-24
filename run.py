# run.py
import eventlet
eventlet.monkey_patch() # <-- यह लाइन सबसे ऊपर जोड़ें

from tubealgo import create_app

app = create_app()
celery = app.celery

if __name__ == '__main__':
    app.run(debug=True)