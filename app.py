import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase
from datetime import timedelta

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Initialize extensions without the app
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # Configure the database
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }

    # Enhanced security configurations
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)
    app.config['REMEMBER_COOKIE_SECURE'] = True
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True

    # Setup secret key
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)

    # Initialize extensions with the app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'

    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        try:
            return User.query.get(int(user_id))
        except Exception as e:
            logger.error(f"Error loading user: {str(e)}")
            return None

    with app.app_context():
        try:
            # Import routes after app is created
            from routes.auth import auth_bp
            from routes.main import main_bp

            # Register blueprints
            app.register_blueprint(auth_bp)
            app.register_blueprint(main_bp)

            # Create database tables
            db.create_all()
        except Exception as e:
            logger.error(f"Error initializing app: {str(e)}")
            raise

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)