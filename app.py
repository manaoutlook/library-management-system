import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from utils import (
    load_data,
    save_data,
    validate_book,
    validate_member,
    validate_transaction
)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "library_management_secret_key"

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

@app.route('/')
def index():
    return redirect(url_for('books'))

@app.route('/books', methods=['GET', 'POST'])
def books():
    if request.method == 'POST':
        book_data = {
            'title': request.form.get('title'),
            'author': request.form.get('author'),
            'isbn': request.form.get('isbn'),
            'quantity': int(request.form.get('quantity', 1))
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

@app.route('/members', methods=['GET', 'POST'])
def members():
    if request.method == 'POST':
        member_data = {
            'name': request.form.get('name'),
            'email': request.form.get('email'),
            'phone': request.form.get('phone')
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

@app.route('/transactions', methods=['GET', 'POST'])
def transactions():
    if request.method == 'POST':
        transaction_data = {
            'book_isbn': request.form.get('book_isbn'),
            'member_email': request.form.get('member_email'),
            'type': request.form.get('type'),  # 'borrow' or 'return'
            'date': request.form.get('date')
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
