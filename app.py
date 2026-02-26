# app.py
from flask import Flask, session
from routes.main import main_bp
from routes.ops import ops_bp
from routes.api import api_bp
from routes.auth import auth_bp
from routes.map import map_bp
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

if __name__ == '__main__':
    app.run(debug=True, port=5001)