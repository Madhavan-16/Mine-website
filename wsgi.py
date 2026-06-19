"""WSGI entry point for production servers (Gunicorn, Waitress, etc.)."""
from mine import create_app

app = create_app()
