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
    validate_transaction,
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
from auth import User, init_user_storage, register_user, authenticate_user, requires_role

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
    if data_type not in ['books', 'members', 'transactions']:
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
        else:  # transactions
            headers = ['Book ISBN', 'Member Email', 'Type', 'Date']
            writer.writerow(headers)
            for item in data:
                writer.writerow([item['book_isbn'], item['member_email'], item['type'], item['date']])

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
        else:  # transactions
            headers = ['Book ISBN', 'Member Email', 'Type', 'Date']

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

# Protected routes
@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    books = load_data('books.json')
    members = load_data('members.json')
    transactions = load_data('transactions.json')

    # Calculate statistics
    stats = {
        'total_books': sum(book['quantity'] for book in books),
        'unique_titles': len(set(book['title'] for book in books)),
        'total_members': len(members),
        'recent_transactions': sorted(transactions, key=lambda x: x['date'], reverse=True)[:5]
    }

    # Calculate books currently borrowed
    borrowed_books = defaultdict(int)
    for trans in transactions:
        if trans['type'] == 'borrow':
            borrowed_books[trans['book_isbn']] += 1
        elif trans['type'] == 'return':
            borrowed_books[trans['book_isbn']] -= 1

    # Get book details for borrowed books
    books_dict = {book['isbn']: book for book in books}
    currently_borrowed = []
    for isbn, count in borrowed_books.items():
        if count > 0 and isbn in books_dict:
            book = books_dict[isbn]
            currently_borrowed.append({
                'title': book['title'],
                'author': book['author'],
                'count': count
            })

    return render_template('dashboard.html', stats=stats, borrowed_books=currently_borrowed)

@app.route('/books', methods=['GET', 'POST'])
@login_required
@requires_role('admin', 'librarian')
def books():
    if request.method == 'POST':
        book_data = {
            'title': sanitize_input(request.form.get('title')),
            'author': sanitize_input(request.form.get('author')),
            'isbn': sanitize_input(request.form.get('isbn')),
            'quantity': int(sanitize_input(request.form.get('quantity', 1)))
        }

        if validate_book(book_data):
            books = load_data('books.json')
            books.append(book_data)
            save_data('books.json', books)
            flash('Book added successfully!', 'success')
        else:
            flash('Invalid book data!', 'error')

    books = load_data('books.json')
    return render_template('books.html', books=books)

@app.route('/books/<isbn>/edit', methods=['GET', 'POST'])
@login_required
@requires_role('admin', 'librarian')
def edit_book(isbn):
    if request.method == 'POST':
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

    book = get_record('books.json', 'isbn', isbn)
    if not book:
        flash('Book not found!', 'error')
        return redirect(url_for('books'))

    return render_template('edit_book.html', book=book)

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
    if request.method == 'POST':
        member_data = {
            'name': sanitize_input(request.form.get('name')),
            'email': sanitize_input(request.form.get('email')),
            'phone': sanitize_input(request.form.get('phone'))
        }

        if validate_member(member_data):
            members = load_data('members.json')
            members.append(member_data)
            save_data('members.json', members)
            flash('Member added successfully!', 'success')
        else:
            flash('Invalid member data!', 'error')

    members = load_data('members.json')
    return render_template('members.html', members=members)

@app.route('/members/<email>/edit', methods=['GET', 'POST'])
@login_required
@requires_role('admin', 'librarian')
def edit_member(email):
    if request.method == 'POST':
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

    member = get_record('members.json', 'email', email)
    if not member:
        flash('Member not found!', 'error')
        return redirect(url_for('members'))

    return render_template('edit_member.html', member=member)

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
    if request.method == 'POST':
        transaction_data = {
            'book_isbn': sanitize_input(request.form.get('book_isbn')),
            'member_email': sanitize_input(request.form.get('member_email')),
            'type': sanitize_input(request.form.get('type')),  # 'borrow' or 'return'
            'date': sanitize_input(request.form.get('date'))
        }

        if validate_transaction(transaction_data):
            transactions = load_data('transactions.json')
            transactions.append(transaction_data)
            save_data('transactions.json', transactions)
            flash('Transaction recorded successfully!', 'success')
        else:
            flash('Invalid transaction data!', 'error')

    transactions = load_data('transactions.json')
    books = load_data('books.json')
    members = load_data('members.json')
    return render_template('transactions.html',
                         transactions=transactions,
                         books=books,
                         members=members)

@app.route('/transactions/<int:id>/delete')
@login_required
@requires_role('admin', 'librarian')
def delete_transaction(id):
    transactions = load_data('transactions.json')
    if 0 <= id < len(transactions):
        transactions.pop(id)
        save_data('transactions.json', transactions)
        flash('Transaction deleted successfully!', 'success')
    else:
        flash('Transaction not found!', 'error')
    return redirect(url_for('transactions'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)