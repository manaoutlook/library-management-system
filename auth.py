from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)

class User(UserMixin):
    def __init__(self, id: str, username: str, email: str, role: str):
        self.id = id
        self.username = username
        self.email = email
        self.role = role

    @staticmethod
    def get(user_id: str) -> Optional['User']:
        users = load_users()
        user_data = users.get(user_id)
        if user_data:
            return User(
                id=user_id,
                username=user_data['username'],
                email=user_data['email'],
                role=user_data['role']
            )
        return None

def init_user_storage():
    """Initialize the users.json file if it doesn't exist"""
    if not os.path.exists('data/users.json'):
        os.makedirs('data', exist_ok=True)
        with open('data/users.json', 'w') as f:
            json.dump({}, f)

    # Create superuser if it doesn't exist
    users = load_users()
    superuser_exists = any(
        user['email'] == 'admin@library.com' 
        for user in users.values()
    )

    if not superuser_exists:
        register_user(
            username='admin',
            email='admin@library.com',
            password='admin123',
            role='admin'
        )
        logger.info("Superuser account created")

def load_users() -> Dict:
    """Load users from the JSON file"""
    try:
        with open('data/users.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading users: {e}")
        return {}

def save_users(users: Dict) -> bool:
    """Save users to the JSON file"""
    try:
        with open('data/users.json', 'w') as f:
            json.dump(users, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving users: {e}")
        return False

def get_system_users() -> List[Dict]:
    """Get all system users (admin, librarian, staff)"""
    users = load_users()
    system_users = []
    for user_id, user_data in users.items():
        if user_data['role'] in ['admin', 'librarian', 'staff']:
            system_users.append({
                'id': user_id,
                **user_data
            })
    return system_users

def get_user_by_id(user_id: str) -> Optional[Dict]:
    """Get user by ID"""
    users = load_users()
    user_data = users.get(user_id)
    if user_data:
        return {'id': user_id, **user_data}
    return None

def update_user(user_id: str, username: str, email: str, role: str, password: Optional[str] = None) -> bool:
    """Update user details"""
    users = load_users()
    if user_id not in users:
        return False

    # Check if email is being changed and if it's already taken by another user
    if email != users[user_id]['email']:
        for uid, udata in users.items():
            if uid != user_id and udata['email'] == email:
                return False

    users[user_id].update({
        'username': username,
        'email': email,
        'role': role
    })

    if password:
        users[user_id]['password'] = generate_password_hash(password)

    return save_users(users)

def delete_user(user_id: str) -> bool:
    """Delete a user"""
    users = load_users()
    if user_id not in users or users[user_id]['email'] == 'admin@library.com':
        return False

    del users[user_id]
    return save_users(users)

def register_user(username: str, email: str, password: str, role: str = 'user') -> bool:
    """Register a new user"""
    users = load_users()

    # Check if username or email already exists
    for user in users.values():
        if user['username'] == username or user['email'] == email:
            return False

    # Create new user
    user_id = str(len(users) + 1)
    users[user_id] = {
        'username': username,
        'email': email,
        'password': generate_password_hash(password),
        'role': role
    }

    return save_users(users)

def authenticate_user(email: str, password: str) -> Optional[User]:
    """Authenticate a user"""
    users = load_users()

    for user_id, user_data in users.items():
        if user_data['email'] == email and check_password_hash(user_data['password'], password):
            return User(
                id=user_id,
                username=user_data['username'],
                email=user_data['email'],
                role=user_data['role']
            )
    return None

def requires_role(*roles):
    """Decorator to require specific roles for access"""
    def decorator(f):
        from functools import wraps
        from flask_login import current_user
        from flask import flash, redirect, url_for

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'error')
                return redirect(url_for('login'))

            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator