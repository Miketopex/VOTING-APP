"""Entry point.

Production (Docker):   gunicorn -c gunicorn.conf.py wsgi:app
Local development:     python wsgi.py        (reads .env if python-dotenv is installed)
"""
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
