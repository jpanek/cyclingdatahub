# app.py
from flask import Flask
from routes.main import main_bp
from routes.ops import ops_bp
from routes.api import api_bp
import config
from dash_app.activity_dashboard import init_activity_dashboard

app = Flask(__name__)

app.config['SECRET_KEY'] = config.SECRET_KEY

# Register standard Flask routes from main.py
app.register_blueprint(main_bp)
app.register_blueprint(ops_bp)
app.register_blueprint(api_bp, url_prefix='/api')

# Initialize and attach Dash
init_activity_dashboard(app)

if __name__ == '__main__':
    app.run(debug=True, port=5001)