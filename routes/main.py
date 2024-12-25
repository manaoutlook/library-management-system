from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
import logging

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin():
            flash('Access denied. Admin privileges required.', 'error')
            return render_template('errors/403.html'), 403
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/')
@login_required
def index():
    return redirect(url_for('main.dashboard'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    try:
        return render_template('dashboard.html')
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        flash('Error loading dashboard', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/books')
@login_required
def books():
    try:
        return render_template('books.html')
    except Exception as e:
        logger.error(f"Error loading books page: {str(e)}")
        flash('Error loading books page', 'error')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/members')
@login_required
def members():
    try:
        return render_template('members.html')
    except Exception as e:
        logger.error(f"Error loading members page: {str(e)}")
        flash('Error loading members page', 'error')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/transactions')
@login_required
def transactions():
    try:
        return render_template('transactions.html')
    except Exception as e:
        logger.error(f"Error loading transactions page: {str(e)}")
        flash('Error loading transactions page', 'error')
        return redirect(url_for('main.dashboard'))

# Admin-only routes
@main_bp.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    try:
        return render_template('admin/dashboard.html')
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {str(e)}")
        flash('Error loading admin dashboard', 'error')
        return redirect(url_for('main.dashboard'))