# run.py
# Use eventlet instead of gevent
import eventlet
eventlet.monkey_patch()

# Now import the rest
from tubealgo import create_app, celery as celery_app

app = create_app()
celery = app.celery

if __name__ == '__main__':
    app.run(debug=False)