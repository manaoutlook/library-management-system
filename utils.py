import json
import os
import fcntl
import re
from datetime import datetime
from email_validator import validate_email, EmailNotValidError
import logging

logging.basicConfig(level=logging.ERROR) #Added for logging


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
        logging.error(f"Error loading data from {filename}: {str(e)}")
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
        logging.error(f"Error saving data to {filename}: {str(e)}")
        return False

def is_valid_isbn(isbn):
    """Validate ISBN-10 or ISBN-13 with more lenient checking"""
    if not isbn:
        return False

    # Remove any hyphens or spaces from the ISBN
    isbn = re.sub(r'[^0-9X]', '', isbn.upper())

    if len(isbn) == 10:
        if not re.match(r'^[0-9]{9}[0-9X]$', isbn):
            return False
        try:
            # ISBN-10 validation
            check_sum = sum((10 - i) * (int(num) if num != 'X' else 10) 
                           for i, num in enumerate(isbn))
            return check_sum % 11 == 0
        except Exception:
            return False

    elif len(isbn) == 13:
        if not re.match(r'^[0-9]{13}$', isbn):
            return False
        try:
            # ISBN-13 validation
            check_sum = sum((3 if i % 2 else 1) * int(num) 
                           for i, num in enumerate(isbn))
            return check_sum % 10 == 0
        except Exception:
            return False

    return False

def validate_book(book):
    """Validate book data with basic checks"""
    required_fields = ['title', 'author', 'isbn', 'quantity']
    error_messages = []

    try:
        # Check required fields
        for field in required_fields:
            if field not in book or not book[field]:
                error_messages.append(f"Missing required field: {field}")
                return False

        # Validate quantity
        try:
            quantity = int(book['quantity'])
            if quantity < 0:
                error_messages.append("Quantity must be a positive number")
                return False
        except (ValueError, TypeError):
            error_messages.append("Invalid quantity value")
            return False

        # Validate string fields
        for field in ['title', 'author']:
            if not isinstance(book[field], str) or not book[field].strip():
                error_messages.append(f"Invalid {field}")
                return False

        return True
    except Exception as e:
        logging.error(f"Book validation error: {str(e)}")
        error_messages.append("Unexpected error during validation")
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
    """Validate transaction data with improved checks and logging"""
    required_fields = ['book_isbn', 'member_email', 'type', 'date']

    try:
        # Check required fields
        for field in required_fields:
            if field not in transaction or not transaction[field]:
                logging.error(f"Missing required field in transaction: {field}")
                return False

        # Validate transaction type
        if transaction['type'] not in ['borrow', 'return']:
            logging.error(f"Invalid transaction type: {transaction['type']}")
            return False

        # Validate date format and value
        try:
            trans_date = datetime.strptime(transaction['date'], '%Y-%m-%d').date()
            current_date = datetime.now().date()

            # Only check if the date is more than today
            if trans_date > current_date:
                logging.error("Transaction date cannot be in the future")
                return False
        except ValueError as e:
            logging.error(f"Date validation error: {str(e)}")
            return False

        # Validate ISBN and email
        if not is_valid_isbn(transaction['book_isbn']):
            logging.error(f"Invalid ISBN: {transaction['book_isbn']}")
            return False

        try:
            validate_email(transaction['member_email'])
        except EmailNotValidError as e:
            logging.error(f"Invalid email: {str(e)}")
            return False

        return True
    except Exception as e:
        logging.error(f"Unexpected error in transaction validation: {str(e)}")
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

def validate_reservation(reservation):
    """Validate reservation data with basic checks"""
    required_fields = ['book_isbn', 'member_email', 'status', 'reserved_date', 'due_date']

    try:
        # Check required fields
        for field in required_fields:
            if field not in reservation or not reservation[field]:
                logging.error(f"Missing required field in reservation: {field}")
                return False

        # Validate status
        if reservation['status'] not in ['active', 'cancelled', 'completed']:
            logging.error(f"Invalid reservation status: {reservation['status']}")
            return False

        # Validate dates
        try:
            reserved_date = datetime.strptime(reservation['reserved_date'], '%Y-%m-%d')
            due_date = datetime.strptime(reservation['due_date'], '%Y-%m-%d')

            # Only validate that due date is not in the past
            if due_date < datetime.now():
                logging.error("Due date cannot be in the past")
                return False

        except ValueError as e:
            logging.error(f"Date validation error: {str(e)}")
            return False

        return True
    except Exception as e:
        logging.error(f"Unexpected error in reservation validation: {str(e)}")
        return False