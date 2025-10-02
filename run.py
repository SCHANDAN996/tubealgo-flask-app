# Filepath: run.py
# This file starts the Flask application.

from tubealgo import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)

