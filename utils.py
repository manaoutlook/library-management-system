import json
import os
import fcntl
from datetime import datetime

def load_data(filename):
    filepath = os.path.join('data', filename)
    try:
        with open(filepath, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return data
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

def save_data(filename, data):
    filepath = os.path.join('data', filename)
    with open(filepath, 'w') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        json.dump(data, f, indent=4)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def validate_book(book):
    required_fields = ['title', 'author', 'isbn', 'quantity']
    if not all(field in book for field in required_fields):
        return False
    if not isinstance(book['quantity'], int) or book['quantity'] < 0:
        return False
    if not book['isbn'].strip():
        return False
    return True

def validate_member(member):
    required_fields = ['name', 'email', 'phone']
    if not all(field in member for field in required_fields):
        return False
    if not '@' in member['email']:
        return False
    if not member['phone'].strip():
        return False
    return True

def validate_transaction(transaction):
    required_fields = ['book_isbn', 'member_email', 'type', 'date']
    if not all(field in transaction for field in required_fields):
        return False
    if transaction['type'] not in ['borrow', 'return']:
        return False
    try:
        datetime.strptime(transaction['date'], '%Y-%m-%d')
    except ValueError:
        return False
    return True
