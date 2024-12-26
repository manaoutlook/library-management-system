import os
import logging
import csv
from io import StringIO, BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_wtf.csrf import CSRFProtect
from utils import (
    load_data,
    save_data,
    validate_book,
    validate_member,
    validate_reservation,
    update_record,
    delete_record,
    get_record
)
from collections import defaultdict
from datetime import datetime
import bleach
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, validators
from auth import User, init_user_storage, register_user, authenticate_user, requires_role, get_system_users, update_user, delete_user
from github_sync import GitHubSync # Added import


# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Use environment variable for secret key with a secure fallback
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(32))
# Enable CSRF protection
csrf = CSRFProtect(app)

# Rate limiting configuration
RATE_LIMIT = {
    'window': 60,  # 60 seconds
    'max_requests': 100  # Maximum requests per window
}
request_history = defaultdict(list)

# Ensure data directory exists with proper permissions
data_dir = "data"
os.makedirs(data_dir, mode=0o750, exist_ok=True)

def rate_limit_check():
    """Check if the request is within rate limits"""
    client_ip = request.remote_addr
    current_time = datetime.now().timestamp()

    # Clean old requests
    request_history[client_ip] = [
        t for t in request_history[client_ip]
        if current_time - t < RATE_LIMIT['window']
    ]

    # Check rate limit
    if len(request_history[client_ip]) >= RATE_LIMIT['max_requests']:
        return False

    request_history[client_ip].append(current_time)
    return True

@app.before_request
def before_request():
    if not rate_limit_check():
        return 'Too many requests', 429

def sanitize_input(data):
    """Sanitize user input"""
    if isinstance(data, str):
        return bleach.clean(data.strip())
    elif isinstance(data, dict):
        return {k: sanitize_input(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_input(v) for v in data]
    return data

def generate_pdf_report(data, headers, title):
    """Generate PDF report with improved error handling"""
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []

        styles = getSampleStyleSheet()
        elements.append(Paragraph(bleach.clean(title), styles['Heading1']))

        table_data = [headers]
        for item in data:
            row = [str(sanitize_input(item.get(header.lower().replace(' ', '_'), '')))
                  for header in headers]
            table_data.append(row)

        table = Table(table_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)

        doc.build(elements)
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        return None

@app.route('/export/<data_type>/<format>')
def export_data(data_type, format):
    if data_type not in ['books', 'members']:
        flash('Invalid data type for export', 'error')
        return redirect(url_for('dashboard'))

    data = load_data(f'{data_type}.json')

    if format == 'csv':
        si = StringIO()
        writer = csv.writer(si)

        if data_type == 'books':
            headers = ['Title', 'Author', 'ISBN', 'Quantity']
            writer.writerow(headers)
            for item in data:
                writer.writerow([item['title'], item['author'], item['isbn'], item['quantity']])
        elif data_type == 'members':
            headers = ['Name', 'Email', 'Phone']
            writer.writerow(headers)
            for item in data:
                writer.writerow([item['name'], item['email'], item['phone']])

        output = si.getvalue()
        si.close()

        return send_file(
            BytesIO(output.encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{data_type}_{datetime.now().strftime("%Y%m%d")}.csv'
        )

    elif format == 'pdf':
        if data_type == 'books':
            headers = ['Title', 'Author', 'ISBN', 'Quantity']
        elif data_type == 'members':
            headers = ['Name', 'Email', 'Phone']

        pdf_buffer = generate_pdf_report(data, headers, f'Library {data_type.title()} Report')

        if pdf_buffer:
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'{data_type}_{datetime.now().strftime("%Y%m%d")}.pdf'
            )
        else:
            flash('Error generating PDF report', 'error')
            return redirect(url_for('dashboard'))

    flash('Invalid export format', 'error')
    return redirect(url_for('dashboard'))


# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize user storage
init_user_storage()

# Forms
class LoginForm(FlaskForm):
    email = StringField('Email', [validators.Email()])
    password = PasswordField('Password', [validators.DataRequired()])

class RegisterForm(FlaskForm):
    username = StringField('Username', [validators.Length(min=4, max=25)])
    email = StringField('Email', [validators.Email()])
    password = PasswordField('Password', [validators.Length(min=6)])

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = authenticate_user(form.email.data, form.password.data)
        if user:
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if register_user(form.username.data, form.email.data, form.password.data):
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('login'))
        flash('Username or email already exists.', 'error')
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

# New routes for system users management
@app.route('/system-users', methods=['GET', 'POST'])
@login_required
@requires_role('admin')
def system_users():
    form = FlaskForm()  # For CSRF protection
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username'))
        email = sanitize_input(request.form.get('email'))
        password = request.form.get('password')
        role = sanitize_input(request.form.get('role'))

        if register_user(username, email, password, role):
            flash('User added successfully!', 'success')
        else:
            flash('Failed to add user. Username or email already exists.', 'error')

    users = get_system_users()  # Using the function from auth.py
    return render_template('system_users.html', users=users, form=form)

@app.route('/system-users/<user_id>/edit', methods=['POST'])
@login_required
@requires_role('admin')
def edit_system_user(user_id):
    username = sanitize_input(request.form.get('username'))
    email = sanitize_input(request.form.get('email'))
    role = sanitize_input(request.form.get('role'))
    password = request.form.get('password')

    if update_user(user_id, username, email, role, password): # Using the correct function from auth.py
        flash('User updated successfully!', 'success')
    else:
        flash('Failed to update user.', 'error')

    return redirect(url_for('system_users'))

@app.route('/system-users/<user_id>/delete')
@login_required
@requires_role('admin')
def delete_system_user(user_id):
    if delete_user(user_id): # Using the correct function from auth.py
        flash('User deleted successfully!', 'success')
    else:
        flash('Failed to delete user.', 'error')
    return redirect(url_for('system_users'))

# Protected routes
@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    form = FlaskForm()  # Initialize form for CSRF protection
    books = load_data('books.json')
    members = load_data('members.json')
    transactions = load_data('transactions.json')

    # Calculate currently borrowed books
    currently_borrowed = sum(1 for t in transactions if not t['return_date'])

    # Get list of currently borrowed books with details
    borrowed_books = []
    for transaction in transactions:
        if not transaction['return_date']:  # If book hasn't been returned
            book = next((b for b in books if b['isbn'] == transaction['book_isbn']), None)
            if book:
                # Check if this book is already in our list
                existing_book = next((bb for bb in borrowed_books if bb['isbn'] == book['isbn']), None)
                if existing_book:
                    existing_book['count'] += 1
                else:
                    borrowed_books.append({
                        'isbn': book['isbn'],
                        'title': book['title'],
                        'author': book.get('author', 'Unknown'),  # Safely get author
                        'count': 1
                    })

    # Calculate statistics
    stats = {
        'total_books': sum(book['quantity'] for book in books),
        'unique_titles': len(set(book['title'] for book in books)),
        'total_members': len(members),
        'currently_borrowed': currently_borrowed
    }

    return render_template('dashboard.html', stats=stats, borrowed_books=borrowed_books, form=form)

@app.route('/books', methods=['GET', 'POST'])
@login_required
@requires_role('admin', 'librarian')
def books():
    form = FlaskForm()  # Initialize form for CSRF protection
    if request.method == 'POST' and form.validate_on_submit():
        try:
            book_data = {
                'title': sanitize_input(request.form.get('title')),
                'author': sanitize_input(request.form.get('author')),
                'isbn': sanitize_input(request.form.get('isbn')),
                'quantity': int(sanitize_input(request.form.get('quantity', 1)))
            }

            if validate_book(book_data):
                books = load_data('books.json')
                # Check if ISBN already exists
                if any(book['isbn'] == book_data['isbn'] for book in books):
                    flash('A book with this ISBN already exists!', 'error')
                else:
                    books.append(book_data)
                    save_data('books.json', books)
                    flash('Book added successfully!', 'success')
            else:
                flash('Please check the book details. Ensure ISBN is valid and all fields are properly filled.', 'error')
        except ValueError as e:
            flash(f'Invalid input: {str(e)}', 'error')
        except Exception as e:
            logging.error(f"Error adding book: {str(e)}")
            flash('An error occurred while adding the book. Please try again.', 'error')

    # Load all books
    books = load_data('books.json')

    # Get search parameters
    search_query = request.args.get('search', '').lower()
    min_quantity = request.args.get('min_quantity', '')
    max_quantity = request.args.get('max_quantity', '')
    sort = request.args.get('sort', '')

    # Apply filters
    if search_query:
        books = [
            book for book in books
            if search_query in book['title'].lower()
            or search_query in book['author'].lower()
            or search_query in book['isbn'].lower()
        ]

    # Apply quantity filters
    if min_quantity.isdigit():
        books = [book for book in books if book['quantity'] >= int(min_quantity)]
    if max_quantity.isdigit():
        books = [book for book in books if book['quantity'] <= int(max_quantity)]

    # Apply sorting
    if sort:
        if sort == 'title_asc':
            books.sort(key=lambda x: x['title'])
        elif sort == 'title_desc':
            books.sort(key=lambda x: x['title'], reverse=True)
        elif sort == 'quantity_asc':
            books.sort(key=lambda x: x['quantity'])
        elif sort == 'quantity_desc':
            books.sort(key=lambda x: x['quantity'], reverse=True)

    return render_template('books.html', books=books, form=form)

@app.route('/books/<isbn>/edit', methods=['GET', 'POST'])
@login_required
@requires_role('admin', 'librarian')
def edit_book(isbn):
    form = FlaskForm()  # Initialize form for CSRF protection
    if request.method == 'POST' and form.validate_on_submit():
        try:
            book_data = {
                'title': sanitize_input(request.form.get('title')),
                'author': sanitize_input(request.form.get('author')),
                'isbn': sanitize_input(request.form.get('isbn')),
                'quantity': int(sanitize_input(request.form.get('quantity', 1)))
            }

            if validate_book(book_data):
                update_record('books.json', 'isbn', isbn, book_data)
                flash('Book updated successfully!', 'success')
                return redirect(url_for('books'))
            else:
                flash('Invalid book data!', 'error')
        except ValueError as e:
            flash(f'Invalid input: {str(e)}', 'error')
            return redirect(url_for('edit_book', isbn=isbn))

    book = get_record('books.json', 'isbn', isbn)
    if not book:
        flash('Book not found!', 'error')
        return redirect(url_for('books'))

    return render_template('edit_book.html', book=book, form=form)

@app.route('/books/<isbn>/delete')
@login_required
@requires_role('admin', 'librarian')
def delete_book(isbn):
    delete_record('books.json', 'isbn', isbn)
    flash('Book deleted successfully!', 'success')
    return redirect(url_for('books'))

@app.route('/members', methods=['GET', 'POST'])
@login_required
@requires_role('admin', 'librarian')
def members():
    form = FlaskForm()  # Initialize form for CSRF protection
    if request.method == 'POST' and form.validate_on_submit():
        try:
            member_data = {
                'name': sanitize_input(request.form.get('name')),
                'email': sanitize_input(request.form.get('email')),
                'phone': sanitize_input(request.form.get('phone'))
            }

            if validate_member(member_data):
                members = load_data('members.json')
                # Check if email already exists
                if any(member['email'] == member_data['email'] for member in members):
                    flash('A member with this email already exists!', 'error')
                else:
                    members.append(member_data)
                    save_data('members.json', members)
                    flash('Member added successfully!', 'success')
            else:
                flash('Please check the member details. All fields are required.', 'error')
        except Exception as e:
            logging.error(f"Error adding member: {str(e)}")
            flash('An error occurred while adding the member. Please try again.', 'error')

    members = load_data('members.json')
    return render_template('members.html', members=members, form=form)

@app.route('/members/<email>/edit', methods=['GET', 'POST'])
@login_required
@requires_role('admin', 'librarian')
def edit_member(email):
    form = FlaskForm()  # Initialize form for CSRF protection
    if request.method == 'POST' and form.validate_on_submit():
        try:
            member_data = {
                'name': sanitize_input(request.form.get('name')),
                'email': sanitize_input(request.form.get('email')),
                'phone': sanitize_input(request.form.get('phone'))
            }

            if validate_member(member_data):
                update_record('members.json', 'email', email, member_data)
                flash('Member updated successfully!', 'success')
                return redirect(url_for('members'))
            else:
                flash('Invalid member data!', 'error')
        except Exception as e:
            logging.error(f"Error updating member: {str(e)}")
            flash('An error occurred while updating the member. Please try again.', 'error')
            return redirect(url_for('edit_member', email=email))

    member = get_record('members.json', 'email', email)
    if not member:
        flash('Member not found!', 'error')
        return redirect(url_for('members'))

    return render_template('edit_member.html', member=member, form=form)

@app.route('/members/<email>/delete')
@login_required
@requires_role('admin', 'librarian')
def delete_member(email):
    delete_record('members.json', 'email', email)
    flash('Member deleted successfully!', 'success')
    return redirect(url_for('members'))

@app.route('/transactions', methods=['GET', 'POST'])
@login_required
@requires_role('admin', 'librarian')
def transactions():
    """
    Handle book transactions with unified borrow/return records and improved validation
    """
    form = FlaskForm()
    if request.method == 'POST' and form.validate_on_submit():
        try:
            # Get and sanitize form data
            book_isbn = sanitize_input(request.form.get('book_isbn'))
            member_email = sanitize_input(request.form.get('member_email'))
            transaction_type = sanitize_input(request.form.get('type'))
            transaction_date = sanitize_input(request.form.get('date'))

            # Basic validation
            if not all([book_isbn, member_email, transaction_type, transaction_date]):
                flash('All fields are required.', 'error')
                return redirect(url_for('transactions'))

            # Validate transaction date
            try:
                trans_date = datetime.strptime(transaction_date, '%Y-%m-%d').date()
                if trans_date > datetime.now().date():
                    flash('Transaction date cannot be in the future.', 'error')
                    return redirect(url_for('transactions'))
            except ValueError:
                flash('Invalid date format.', 'error')
                return redirect(url_for('transactions'))

            # Load data
            books = load_data('books.json')
            members = load_data('members.json')
            transactions = load_data('transactions.json')

            # Verify book exists and is available
            book = next((b for b in books if b['isbn'] == book_isbn), None)
            if not book:
                flash('Book not found.', 'error')
                return redirect(url_for('transactions'))

            # Verify member exists
            member = next((m for m in members if m['email'] == member_email), None)
            if not member:
                flash('Member not found.', 'error')
                return redirect(url_for('transactions'))

            if transaction_type == 'borrow':
                # Check if book is available
                active_borrows = sum(1 for t in transactions 
                                   if t['book_isbn'] == book_isbn and not t['return_date'])
                if active_borrows >= book['quantity']:
                    flash('This book is not available for borrowing.', 'error')
                    return redirect(url_for('transactions'))

                # Check if member has any overdue books
                overdue_books = [t for t in transactions 
                               if t['member_email'] == member_email 
                               and not t['return_date']
                               and (datetime.now().date() - datetime.strptime(t['borrow_date'], '%Y-%m-%d').date()).days > 14]
                if overdue_books:
                    flash('Member has overdue books. Please return them first.', 'error')
                    return redirect(url_for('transactions'))

                # Create new borrow record with secure ID generation
                new_transaction = {
                    'id': max((t['id'] for t in transactions), default=0) + 1,
                    'book_isbn': book_isbn,
                    'book_title': book['title'],
                    'member_email': member_email,
                    'member_name': member['name'],
                    'borrow_date': transaction_date,
                    'return_date': None
                }
                transactions.append(new_transaction)
                flash('Book borrowed successfully!', 'success')

            elif transaction_type == 'return':
                # Find the active borrow record for this book and member
                borrow_record = next(
                    (t for t in transactions 
                     if t['book_isbn'] == book_isbn 
                     and t['member_email'] == member_email 
                     and not t['return_date']),
                    None
                )

                if not borrow_record:
                    flash('No active borrow record found for this book and member.', 'error')
                    return redirect(url_for('transactions'))

                # Check if return date is after borrow date
                borrow_date = datetime.strptime(borrow_record['borrow_date'], '%Y-%m-%d').date()
                if trans_date < borrow_date:
                    flash('Return date cannot be before the borrow date.', 'error')
                    return redirect(url_for('transactions'))

                # Update the borrow record with return date
                borrow_record['return_date'] = transaction_date
                flash('Book returned successfully!', 'success')

            # Save updated transactions
            save_data('transactions.json', transactions)
            return redirect(url_for('transactions'))

        except Exception as e:
            logging.error(f"Error processing transaction: {str(e)}")
            flash('An error occurred while processing the transaction.', 'error')
            return redirect(url_for('transactions'))

    # Load data for the template
    transactions = load_data('transactions.json')
    books = load_data('books.json')
    members = load_data('members.json')

    # Apply filters
    search_query = request.args.get('search', '').lower()
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    status = request.args.get('status')

    if search_query:
        transactions = [
            t for t in transactions
            if search_query in t['book_title'].lower()
            or search_query in t['book_isbn'].lower()
            or search_query in t['member_name'].lower()
            or search_query in t['member_email'].lower()
        ]

    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            transactions = [
                t for t in transactions
                if datetime.strptime(t['borrow_date'], '%Y-%m-%d').date() >= date_from
            ]
        except ValueError:
            flash('Invalid from date format.', 'error')

    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            transactions = [
                t for t in transactions
                if datetime.strptime(t['borrow_date'], '%Y-%m-%d').date() <= date_to
            ]
        except ValueError:
            flash('Invalid to date format.', 'error')

    if status:
        if status == 'borrowed':
            transactions = [t for t in transactions if not t['return_date']]
        elif status == 'returned':
            transactions = [t for t in transactions if t['return_date']]

    return render_template('transactions.html',
                         transactions=transactions,
                         books=books,
                         members=members,
                         datetime=datetime,
                         form=form)

@app.route('/transactions/<int:id>/delete')
@login_required
@requires_role('admin', 'librarian')
def delete_transaction(id):
    """Delete a transaction record with improved validation"""
    try:
        transactions = load_data('transactions.json')
        transaction = next((t for t in transactions if t['id'] == id), None)

        if not transaction:
            flash('Transaction not found!', 'error')
            return redirect(url_for('transactions'))

        # Only allow deletion if book is returned or it's a borrow transaction
        if transaction.get('return_date') or transaction.get('borrow_date'):
            # Verify there are no dependent records before deletion
            if not transaction.get('return_date'):
                flash('Cannot delete an active borrow transaction. Return the book first.', 'error')
                return redirect(url_for('transactions'))

            transactions = [t for t in transactions if t['id'] != id]
            save_data('transactions.json', transactions)
            flash('Transaction deleted successfully!', 'success')
        else:
            flash('Cannot delete this transaction record.', 'error')
    except Exception as e:
        logging.error(f"Error deleting transaction: {str(e)}")
        flash('An error occurred while deleting the transaction.', 'error')

    return redirect(url_for('transactions'))

@app.route('/reservations', methods=['GET', 'POST'])
@login_required
@requires_role('admin', 'librarian')
def reservations():
    form = FlaskForm()  # For CSRF protection
    if request.method == 'POST':
        # Load existing data
        books = load_data('books.json')
        members = load_data('members.json')

        # Get form data
        book_isbn = sanitize_input(request.form.get('book_isbn'))
        member_email = sanitize_input(request.form.get('member_email'))
        due_date = sanitize_input(request.form.get('due_date'))

        # Validate book and member exist
        book = next((b for b in books if b['isbn'] == book_isbn), None)
        member = next((m for m in members if m['email'] == member_email), None)

        if not book or not member:
            flash('Invalid book or member selected.', 'error')
            return redirect(url_for('reservations'))

        # Create reservation data
        reservation_data = {
            'book_isbn': book_isbn,
            'book_title': book['title'],
            'member_email': member_email,
            'member_name': member['name'],
            'status': 'active',
            'reserved_date': datetime.now().strftime('%Y-%m-%d'),
            'due_date': due_date
        }

        if validate_reservation(reservation_data):
            reservations = load_data('reservations.json')
            # Add ID to reservation
            reservation_data['id'] = str(len(reservations) + 1)
            reservations.append(reservation_data)
            save_data('reservations.json', reservations)
            flash('Reservation added successfully!', 'success')
        else:
            flash('Please check the due date and ensure all fields are filled correctly.', 'error')

    reservations = load_data('reservations.json')
    books = load_data('books.json')
    members = load_data('members.json')
    return render_template('reservations.html', 
                         reservations=reservations,
                         books=books,
                         members=members,
                         form=form)

@app.route('/reservations/<reservation_id>/edit', methods=['POST'])
@login_required
@requires_role('admin', 'librarian')
def edit_reservation(reservation_id):
    status = sanitize_input(request.form.get('status'))
    due_date = sanitize_input(request.form.get('due_date'))

    reservations = load_data('reservations.json')
    for reservation in reservations:
        if reservation['id'] == reservation_id:
            reservation['status'] = status
            reservation['due_date'] = due_date
            break

    save_data('reservations.json', reservations)
    flash('Reservation updated successfully!', 'success')
    return redirect(url_for('reservations'))

@app.route('/reservations/<reservation_id>/cancel')
@login_required
@requires_role('admin', 'librarian')
def cancel_reservation(reservation_id):
    reservations = load_data('reservations.json')
    for reservation in reservations:
        if reservation['id'] == reservation_id:
            reservation['status'] = 'cancelled'
            break

    save_data('reservations.json', reservations)
    flash('Reservation cancelled successfully!', 'success')
    return redirect(url_for('reservations'))

def generate_report_data(report_type, date_from=None, date_to=None):
    """Generate report data based on type and date range"""
    books = load_data('books.json')
    members = load_data('members.json')
    transactions = load_data('transactions.json')
    current_date = datetime.now()

    # Filter transactions by date range if provided
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            transactions = [t for t in transactions 
                          if datetime.strptime(t['borrow_date'], '%Y-%m-%d').date() >= date_from]
        except ValueError:
            flash('Invalid from date format.', 'error')

    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            transactions = [t for t in transactions 
                          if datetime.strptime(t['borrow_date'], '%Y-%m-%d').date() <= date_to]
        except ValueError:
            flash('Invalid to date format.', 'error')

    report_data = []
    headers = []
    report_title = ""

    if report_type == 'book_usage':
        report_title = "Book Usage Analytics"
        headers = ['Title', 'ISBN', 'Total Borrows', 'Current Borrows', 'Average Duration', 'Usage Rate']

        book_stats = defaultdict(lambda: {
            'title': '',
            'isbn': '',
            'total_borrows': 0,
            'current_borrows': 0,
            'total_days': 0,
            'completed_borrows': 0
        })

        for t in transactions:
            stats = book_stats[t['book_isbn']]
            stats['title'] = t['book_title']
            stats['isbn'] = t['book_isbn']
            stats['total_borrows'] += 1

            if not t['return_date']:
                stats['current_borrows'] += 1
            else:
                try:
                    borrow_date = datetime.strptime(t['borrow_date'], '%Y-%m-%d')
                    return_date = datetime.strptime(t['return_date'], '%Y-%m-%d')
                    duration = (return_date - borrow_date).days
                    stats['total_days'] += duration
                    stats['completed_borrows'] += 1
                except ValueError as e:
                    logging.error(f"Error processing dates for transaction: {str(e)}")
                    continue

        for isbn, stats in book_stats.items():
            avg_duration = round(stats['total_days'] / max(stats['completed_borrows'], 1), 1)
            usage_rate = round((stats['total_borrows'] / max(len(transactions), 1)) * 100, 1)

            report_data.append({
                'title': stats['title'],
                'isbn': stats['isbn'],
                'total_borrows': stats['total_borrows'],
                'current_borrows': stats['current_borrows'],
                'avg_duration': avg_duration,
                'usage_rate': usage_rate
            })

    elif report_type == 'member_activity':
        report_title = "Member Activity Report"
        headers = ['Name', 'Email', 'Total Borrowed', 'Currently Borrowed', 'Return Rate', 'Activity Level']

        member_stats = defaultdict(lambda: {
            'name': '',
            'email': '',
            'total_borrowed': 0,
            'current_borrowed': 0,
            'returned_on_time': 0,
            'total_returns': 0
        })

        for t in transactions:
            stats = member_stats[t['member_email']]
            stats['name'] = t['member_name']
            stats['email'] = t['member_email']
            stats['total_borrowed'] += 1

            if not t['return_date']:
                stats['current_borrowed'] += 1
            else:
                stats['total_returns'] += 1
                try:
                    borrow_date = datetime.strptime(t['borrow_date'], '%Y-%m-%d')
                    return_date = datetime.strptime(t['return_date'], '%Y-%m-%d')
                    if (return_date - borrow_date).days <= 14:
                        stats['returned_on_time'] += 1
                except ValueError as e:
                    logging.error(f"Error processing dates for transaction: {str(e)}")
                    continue

        max_borrows = max((stats['total_borrowed'] for stats in member_stats.values()), default=1)
        for email, stats in member_stats.items():
            return_rate = round((stats['returned_on_time'] / max(stats['total_returns'], 1) * 100), 1) if stats['total_returns'] > 0 else 100
            activity_level = round((stats['total_borrowed'] / max_borrows * 100), 1)

            report_data.append({
                'name': stats['name'],
                'email': stats['email'],
                'total_borrowed': stats['total_borrowed'],
                'current_borrowed': stats['current_borrowed'],
                'return_rate': return_rate,
                'activity_level': activity_level
            })

    elif report_type == 'transactions':
        report_title = "Transaction History Report"
        headers = ['Date', 'Type', 'Book Title', 'Member Name', 'Status', 'Duration']

        for t in transactions:
            borrow_date = datetime.strptime(t['borrow_date'], '%Y-%m-%d')
            status = "Completed" if t['return_date'] else "Active"

            if t['return_date']:
                return_date = datetime.strptime(t['return_date'], '%Y-%m-%d')
                duration = (return_date - borrow_date).days
            else:
                duration = (current_date.date() - borrow_date.date()).days

            report_data.append({
                'borrow_date': t['borrow_date'],
                'return_date': t['return_date'],
                'book_title': t['book_title'],
                'member_name': t['member_name'],
                'status': status,
                'duration': duration
            })

    elif report_type == 'overdue':
        report_title = "Overdue Books Report"
        headers = ['Book Title', 'ISBN', 'Member Name', 'Borrow Date', 'Days Overdue', 'Status']

        for t in transactions:
            if not t['return_date']:  # Only check non-returned books
                try:
                    borrow_date = datetime.strptime(t['borrow_date'], '%Y-%m-%d').date()
                    days_overdue = (current_date.date() - borrow_date).days - 14  # Consider 14 days as standard period
                    if days_overdue > 0:
                        status = "Severely Overdue" if days_overdue > 30 else "Moderately Overdue" if days_overdue > 14 else "Slightly Overdue"
                        report_data.append({
                            'book_title': t['book_title'],
                            'book_isbn': t['book_isbn'],
                            'member_name': t['member_name'],
                            'borrow_date': t['borrow_date'],
                            'days_overdue': days_overdue,
                            'status': status
                        })
                except ValueError as e:
                    logging.error(f"Error processing dates for transaction: {str(e)}")
                    continue

    return report_data, headers, report_title

@app.route('/reports')
@login_required
@requires_role('admin', 'librarian')
def reports():
    report_type = request.args.get('report_type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    current_date = datetime.now()

    if not report_type:
        return render_template('reports.html',
                             datetime=datetime,
                             current_date=current_date)

    report_data, _, report_title = generate_report_data(report_type, date_from, date_to)

    return render_template('reports.html',
                         report_data=report_data,
                         report_title=report_title,
                         report_type=report_type,
                         datetime=datetime,
                         current_date=current_date)

@app.route('/reports/download/<report_type>')
@login_required
@requires_role('admin', 'librarian')
def download_report(report_type):
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    report_format = request.args.get('format', 'pdf')

    report_data, headers, report_title = generate_report_data(report_type, date_from, date_to)

    if report_format == 'csv':
        si = StringIO()
        writer = csv.writer(si)
        writer.writerow(headers)

        for item in report_data:
            row = []
            for header in headers:
                key = header.lower().replace(' ', '_')
                row.append(str(item.get(key, '')))
            writer.writerow(row)

        output = si.getvalue()
        si.close()

        return send_file(
            BytesIO(output.encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{report_type}_{datetime.now().strftime("%Y%m%d")}.csv'
        )
    elif report_format == 'pdf':
        pdf_buffer = generate_pdf_report(report_data, headers, report_title)
        if pdf_buffer:
            return send_file(
                pdf_buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f'{report_type}_{datetime.now().strftime("%Y%m%d")}.pdf'
            )
        else:
            flash('Error generating PDF report', 'error')
            return redirect(url_for('reports'))

    flash('Invalid export format', 'error')
    return redirect(url_for('reports'))

@app.route('/github/init', methods=['POST'])
@login_required
@requires_role('admin')
def init_github_repo():
    """Initialize GitHub repository"""
    form = FlaskForm()  # For CSRF protection
    if form.validate_on_submit():
        try:
            repo_name = sanitize_input(request.form.get('repo_name', 'library-management-system'))
            github_sync = GitHubSync()
            github_sync.init_repository(repo_name)
            flash('GitHub repository initialized successfully!', 'success')
        except Exception as e:
            logging.error(f"Error initializing GitHub repository: {str(e)}")
            flash('Error initializing GitHub repository. Please check your token and try again.', 'error')
    return redirect(url_for('dashboard'))

@app.route('/github/sync', methods=['POST'])
@login_required
@requires_role('admin')
def sync_to_github():
    """Sync code to GitHub repository"""
    form = FlaskForm()  # For CSRF protection
    if form.validate_on_submit():
        try:
            repo_name = sanitize_input(request.form.get('repo_name', 'library-management-system'))
            commit_message = sanitize_input(request.form.get('commit_message', 'Update from Library Management System'))

            github_sync = GitHubSync()
            if github_sync.sync_code(repo_name, commit_message):
                flash('Code synced to GitHub successfully!', 'success')
            else:
                flash('Error syncing code to GitHub. Please try again.', 'error')
        except Exception as e:
            logging.error(f"Error syncing to GitHub: {str(e)}")
            flash('Error syncing to GitHub. Please check your token and try again.', 'error')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)