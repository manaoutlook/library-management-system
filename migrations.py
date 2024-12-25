from flask import Flask
from flask_migrate import Migrate, upgrade
from extensions import db, migrate
from app import create_app
import logging

logger = logging.getLogger(__name__)

def init_migrations():
    """Initialize database migrations"""
    try:
        app = create_app()
        with app.app_context():
            # Import all models to ensure they're known to Flask-Migrate
            import models
            
            # Initialize migrations
            migrate.init_app(app, db)
            
            # Create initial migration if needed
            upgrade()
            
        return True
    except Exception as e:
        logger.error(f"Failed to initialize migrations: {str(e)}")
        return False

if __name__ == '__main__':
    init_migrations()
