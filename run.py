# run.py
# No async monkey patching for now - using sync workers

from tubealgo import create_app, celery as celery_app

app = create_app()
celery = app.celery

if __name__ == '__main__':
    app.run(debug=False)