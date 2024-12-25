import os
import logging
from flask import Flask
from datetime import timedelta
from extensions import db, login_manager
from flask_migrate import Migrate

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_app():
    logger.info("Starting application initialization")
    app = Flask(__name__)

    try:
        # Configure the database
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError("No DATABASE_URL environment variable set")

        logger.info("Configuring database connection")
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_recycle": 300,
            "pool_pre_ping": True,
        }
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

        logger.info("Initializing Flask extensions")
        # Initialize extensions with the app
        db.init_app(app)
        login_manager.init_app(app)
        migrate = Migrate(app, db)

        @login_manager.user_loader
        def load_user(user_id):
            from models import User
            try:
                return User.query.get(int(user_id))
            except Exception as e:
                logger.error(f"Error loading user: {str(e)}")
                return None

        # Register blueprints and initialize database
        with app.app_context():
            logger.info("Setting up application context")
            # Import routes
            from routes.auth import auth_bp
            from routes.main import main_bp
            from models import User

            # Register blueprints
            app.register_blueprint(auth_bp)
            app.register_blueprint(main_bp)

            try:
                logger.info("Creating database tables")
                db.create_all()

                # Create default admin user if it doesn't exist
                admin_user = User.query.filter_by(email='admin@library.com').first()
                if not admin_user:
                    logger.info("Creating default admin user")
                    admin_user = User(
                        username='admin',
                        email='admin@library.com',
                        role='admin',
                        is_active=True
                    )
                    admin_user.set_password('Library@123')
                    db.session.add(admin_user)
                    db.session.commit()
                    logger.info("Created default admin user")

            except Exception as e:
                logger.error(f"Database initialization error: {str(e)}")
                db.session.rollback()
                raise

    except Exception as e:
        logger.error(f"Application initialization error: {str(e)}")
        raise

    logger.info("Application initialization completed successfully")
    return app

# Create the application instance
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)