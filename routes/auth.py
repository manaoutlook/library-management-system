from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from models import User
from forms import LoginForm, RegistrationForm
import logging
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

# Rate limiting configuration
RATE_LIMIT = {
    'login': {'attempts': 5, 'window': 300},  # 5 attempts per 5 minutes
    'register': {'attempts': 3, 'window': 3600}  # 3 attempts per hour
}

# Store login attempts in memory (in production, use Redis/database)
login_attempts = defaultdict(list)
register_attempts = defaultdict(list)

def rate_limit(limit_type):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip = request.remote_addr
            now = datetime.utcnow()

            # Get the appropriate attempt tracker
            attempts = login_attempts if limit_type == 'login' else register_attempts
            window = RATE_LIMIT[limit_type]['window']
            max_attempts = RATE_LIMIT[limit_type]['attempts']

            # Clean old attempts
            attempts[ip] = [t for t in attempts[ip] 
                          if now - t < timedelta(seconds=window)]

            if len(attempts[ip]) >= max_attempts:
                flash(f'Too many {limit_type} attempts. Please try again later.', 'error')
                return render_template('auth/login.html', form=LoginForm())

            attempts[ip].append(now)
            return f(*args, **kwargs)
        return wrapped
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit('login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = User.query.filter_by(email=form.email.data).first()
            if user and user.check_password(form.password.data):
                if not user.is_active:
                    flash('Your account has been deactivated. Please contact support.', 'error')
                    logger.warning(f"Login attempt on deactivated account: {form.email.data}")
                    return redirect(url_for('auth.login'))
                login_user(user, remember=form.remember_me.data)
                logger.info(f"Successful login for user: {user.email}")
                next_page = request.args.get('next')
                if not next_page or not next_page.startswith('/'):
                    next_page = url_for('main.dashboard')
                return redirect(next_page)
            flash('Invalid email or password', 'error')
            logger.warning(f"Failed login attempt for email: {form.email.data}")
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login. Please try again.', 'error')

    return render_template('auth/login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit('register')
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            if User.query.filter_by(email=form.email.data).first():
                flash('Email already registered', 'error')
                return redirect(url_for('auth.register'))

            if User.query.filter_by(username=form.username.data).first():
                flash('Username already taken', 'error')
                return redirect(url_for('auth.register'))

            user = User(
                username=form.username.data,
                email=form.email.data,
                role='user',
                is_active=True
            )
            user.set_password(form.password.data)

            db.session.add(user)
            db.session.commit()
            logger.info(f"New user registered: {user.email}")

            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {str(e)}")
            flash('An error occurred during registration. Please try again.', 'error')

    return render_template('auth/register.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    try:
        user_email = current_user.email
        logout_user()
        logger.info(f"User logged out: {user_email}")
        flash('You have been logged out.', 'info')
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        flash('An error occurred during logout.', 'error')
    return redirect(url_for('auth.login'))