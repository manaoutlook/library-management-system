import json
import os
import fcntl
import re
from datetime import datetime
from email_validator import validate_email, EmailNotValidError
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def secure_filename(filename):
    """Ensure filename is secure and within data directory"""
    filename = os.path.basename(filename)
    if not filename.endswith('.json'):
        filename += '.json'
    return os.path.join('data', filename)

def load_data(filename):
    """Load data with improved error handling and security"""
    filepath = secure_filename(filename)
    try:
        if not os.path.exists(filepath):
            return []

        with open(filepath, 'r') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading data from {filename}: {str(e)}")
        return []

def save_data(filename, data):
    """Save data with improved error handling and security"""
    filepath = secure_filename(filename)
    try:
        with open(filepath, 'w') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(data, f, indent=4)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return True
    except IOError as e:
        logger.error(f"Error saving data to {filename}: {str(e)}")
        return False

def is_valid_isbn(isbn):
    """Validate ISBN-10 or ISBN-13"""
    isbn = re.sub(r'[^0-9X]', '', isbn.upper())

    if len(isbn) == 10:
        if not re.match(r'^[0-9]{9}[0-9X]$', isbn):
            return False
        # ISBN-10 validation
        check_sum = sum((10 - i) * (int(num) if num != 'X' else 10) 
                       for i, num in enumerate(isbn))
        return check_sum % 11 == 0

    elif len(isbn) == 13:
        if not re.match(r'^[0-9]{13}$', isbn):
            return False
        # ISBN-13 validation
        check_sum = sum((3 if i % 2 else 1) * int(num) 
                       for i, num in enumerate(isbn))
        return check_sum % 10 == 0

    return False

def validate_book(book):
    """Validate book data with improved checks"""
    required_fields = ['title', 'author', 'isbn', 'quantity']

    try:
        # Check required fields
        if not all(field in book and book[field] for field in required_fields):
            return False

        # Validate quantity
        if not isinstance(book['quantity'], int) or book['quantity'] < 0:
            return False

        # Validate ISBN
        if not is_valid_isbn(book['isbn']):
            return False

        # Validate string fields
        if not all(isinstance(book[field], str) and book[field].strip() 
                  for field in ['title', 'author', 'isbn']):
            return False

        return True
    except Exception:
        return False

def validate_member(member):
    """Validate member data with improved checks"""
    required_fields = ['name', 'email', 'phone']

    try:
        # Check required fields
        if not all(field in member and member[field] for field in required_fields):
            return False

        # Validate email
        try:
            validate_email(member['email'])
        except EmailNotValidError:
            return False

        # Validate phone (basic format check)
        phone = re.sub(r'[^0-9]', '', member['phone'])
        if len(phone) < 10:
            return False

        # Validate name
        if not member['name'].strip():
            return False

        return True
    except Exception:
        return False

def validate_transaction(transaction):
    """Validate transaction data with improved checks"""
    required_fields = ['book_isbn', 'member_email', 'type', 'date']

    try:
        # Check required fields
        if not all(field in transaction and transaction[field] for field in required_fields):
            return False

        # Validate transaction type
        if transaction['type'] not in ['borrow', 'return']:
            return False

        # Validate date format
        try:
            date = datetime.strptime(transaction['date'], '%Y-%m-%d')
            if date > datetime.now():
                return False
        except ValueError:
            return False

        # Validate ISBN and email
        if not is_valid_isbn(transaction['book_isbn']):
            return False

        try:
            validate_email(transaction['member_email'])
        except EmailNotValidError:
            return False

        return True
    except Exception:
        return False

def update_record(filename, identifier_field, identifier_value, new_data):
    data = load_data(filename)
    for item in data:
        if item.get(identifier_field) == identifier_value:
            item.update(new_data)
            break
    save_data(filename, data)
    return True

def delete_record(filename, identifier_field, identifier_value):
    data = load_data(filename)
    data = [item for item in data if item.get(identifier_field) != identifier_value]
    save_data(filename, data)
    return True

def get_record(filename, identifier_field, identifier_value):
    data = load_data(filename)
    for item in data:
        if item.get(identifier_field) == identifier_value:
            return item
    return None