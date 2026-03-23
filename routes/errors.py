# routes/errors.py
from flask import Blueprint, render_template

errors_bp = Blueprint('errors', __name__)

@errors_bp.app_errorhandler(404)
def handle_404(e):
    return render_template('error.html', message="Page not found", code=404), 404

@errors_bp.app_errorhandler(500)
def handle_500(e):
    return render_template('error.html', message="Internal server error", code=500), 500