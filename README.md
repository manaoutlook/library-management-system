# Library Management System

A modern, secure library management system built using Python and Flask, providing comprehensive book collection management with advanced security and user experience features.

## Features

- User Authentication and Role-based Access Control
- Book Management (Add, Edit, Delete)
- Member Management
- Transaction Tracking
- Reservation System
- Animated Toast Notifications
- Enhanced Security Features
- Responsive Dashboard
- Export Functionality (CSV, PDF)

## Tech Stack

- Python 3.11
- Flask Web Framework
- Flask-SQLAlchemy
- Flask-Login for Authentication
- PostgreSQL Database
- Bootstrap for UI
- Feather Icons
- Toastify for Notifications

## Security Features

- CSRF Protection
- Input Sanitization
- Rate Limiting
- Secure Password Hashing
- Role-based Access Control
- Session Management

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Set up environment variables:
   - `FLASK_SECRET_KEY`
   - `DATABASE_URL`

## Usage

Run the application:
```bash
python main.py
```

The application will be available at `http://localhost:5000`

## Default Admin Credentials

- Email: admin@library.com
- Password: admin123

## License

MIT License
