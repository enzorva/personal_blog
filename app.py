import sqlite3
import logging
import bcrypt
import re
from bleach import clean
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_session import Session
from datetime import datetime
from flask_wtf.csrf import CSRFProtect
from functools import wraps
import os
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

# Use environment variables for sensitive information
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')  # Fallback to a default key if not set

# Enable CSRF protection
csrf = CSRFProtect(app)

# Add a secret key for CSRF
app.config['WTF_CSRF_SECRET_KEY'] = os.getenv('WTF_CSRF_SECRET_KEY', 'default_csrf_secret_key')

# Configure Flask-Session
app.config['SESSION_TYPE'] = 'filesystem'  # Store sessions in the server's filesystem
app.config['SESSION_COOKIE_SECURE'] = True  # Ensure cookies are sent over HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to cookies
Session(app)

# Enable HTTPS and set security headers
Talisman(app, content_security_policy=None)

# Initialize Flask-Limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

@app.template_filter('long_date')
def long_date_filter(value):
    date_obj = datetime.strptime(value, '%Y-%m-%d')
    return date_obj.strftime('%B %d, %Y')

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('You must be logged in to access this page.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def entry():
    return render_template('entry.html')

@app.route('/home', defaults={'admin_id': None})
@app.route('/home/<int:admin_id>')
def home(admin_id):
    if admin_id is None:
        return redirect(url_for('choose_admin'))

    conn = get_db_connection()
    articles = conn.execute('SELECT * FROM articles WHERE user_id = ?', (admin_id,)).fetchall()
    conn.close()
    return render_template('guest_section/home.html', articles=articles)

@app.route('/choose_admin')
def choose_admin():
    conn = get_db_connection()
    admins = conn.execute('SELECT id, username FROM users').fetchall()
    conn.close()
    return render_template('guest_section/choose_admin.html', admins=admins)

@app.route('/view_article/<int:article_id>')
def view_article(article_id):
    conn = get_db_connection()
    article = conn.execute('SELECT * FROM articles WHERE id = ?', (article_id,)).fetchone()
    conn.close()

    if not article:
        flash('Article not found.', 'error')
        return redirect(url_for('home'))

    return render_template('guest_section/view_article.html', article=article)

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Validate inputs
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('login.html')

        # Sanitize inputs
        username = clean(username)

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            session['user_id'] = user['id']  # Store user_id in session
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')

@app.route('/admin/signup', methods=['GET', 'POST'])
def admin_signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Validate inputs
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('signup.html')

        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            flash('Username must be alphanumeric and can include underscores.', 'error')
            return render_template('signup.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('signup.html')

        # Sanitize inputs
        username = clean(username)

        # Hash the password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            flash('User created successfully', 'success')
            return redirect(url_for('admin_login'))
        except sqlite3.IntegrityError:
            flash('Username already exists', 'error')
        finally:
            conn.close()

    return render_template('signup.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    conn = get_db_connection()
    articles = conn.execute('SELECT id, title FROM articles WHERE user_id = ?', (session.get('user_id'),)).fetchall()
    conn.close()
    return render_template('admin_section/dashboard.html', articles=articles)

@app.route('/admin/add_article', methods=['GET', 'POST'])
@login_required
def add_article():
    if request.method == 'POST':
        title = request.form['article-title']
        date = request.form['publishing-date']
        content = request.form['content']

        user_id = session.get('user_id')
        logging.debug(f"Inserting article: title={title}, date={date}, content={content}, user_id={user_id}")

        conn = get_db_connection()
        conn.execute('INSERT INTO articles (title, date, content, user_id) VALUES (?, ?, ?, ?)', (title, date, content, user_id))
        conn.commit()
        conn.close()

        flash('Article published successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_section/add_article.html')

@app.route('/admin/delete_article/<int:article_id>', methods=['POST'])
@login_required
def delete_article(article_id):
    user_id = session.get('user_id')
    conn = get_db_connection()
    conn.execute('DELETE FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
    conn.commit()
    conn.close()

    flash('Article deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_article/<int:article_id>', methods=['GET', 'POST'])
@login_required
def edit_article(article_id):
    user_id = session.get('user_id')
    conn = get_db_connection()

    if request.method == 'POST':
        title = request.form['article-title']
        date = request.form['publishing-date']
        content = request.form['content']

        conn.execute('''
            UPDATE articles
            SET title = ?, date = ?, content = ?
            WHERE id = ? AND user_id = ?
        ''', (title, date, content, article_id, user_id))
        conn.commit()
        conn.close()

        flash('Article updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    article = conn.execute('SELECT * FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id)).fetchone()
    conn.close()

    if not article:
        flash('Article not found or you do not have permission to edit it.', 'error')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_section/edit_article.html', article=article)

# Custom error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=False)