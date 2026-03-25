# app.py
from flask import Flask, session, render_template
from routes.main import main_bp
from routes.ops import ops_bp, format_seconds
from routes.api import api_bp
from routes.auth import auth_bp
from routes.map import map_bp
from routes.errors import errors_bp
import config

app = Flask(__name__)

app.config.from_object(config)

@app.before_request
def make_session_permanent():
    session.permanent = True

# Register standard Flask routes from main.py
app.register_blueprint(main_bp)
app.register_blueprint(ops_bp, url_prefix='/ops')
app.register_blueprint(auth_bp)
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(map_bp)
app.register_blueprint(errors_bp)

app.jinja_env.filters['format_seconds'] = format_seconds


if __name__ == '__main__':
    app.run(debug=True, port=5001)