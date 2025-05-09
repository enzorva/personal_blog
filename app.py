import sqlite3
import logging
from flask import Flask, render_template, redirect, url_for, request, flash, session

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for flashing messages

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def entry():
    return render_template('entry.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()

        if user:
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

        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
            flash('User created successfully', 'success')
            return redirect(url_for('admin_login'))
        except sqlite3.IntegrityError:
            flash('Username already exists', 'error')
        finally:
            conn.close()

    return render_template('signup.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    conn = get_db_connection()
    articles = conn.execute('SELECT id, title FROM articles WHERE user_id = ?', (session.get('user_id'),)).fetchall()
    conn.close()
    return render_template('admin_section/dashboard.html', articles=articles)

@app.route('/admin/add_article', methods=['GET', 'POST'])
def add_article():
    if request.method == 'POST':
        title = request.form['article-title']
        date = request.form['publishing-date']
        content = request.form['content']

        user_id = session.get('user_id')
        if not user_id:
            flash('You must be logged in to publish an article.', 'error')
            return redirect(url_for('admin_login'))

        logging.debug(f"Inserting article: title={title}, date={date}, content={content}, user_id={user_id}")

        conn = get_db_connection()
        conn.execute('INSERT INTO articles (title, date, content, user_id) VALUES (?, ?, ?, ?)', (title, date, content, user_id))
        conn.commit()
        conn.close()

        flash('Article published successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_section/add_article.html')

@app.route('/admin/delete_article/<int:article_id>', methods=['POST'])
def delete_article(article_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('You must be logged in to delete an article.', 'error')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    conn.execute('DELETE FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
    conn.commit()
    conn.close()

    flash('Article deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_article/<int:article_id>', methods=['GET', 'POST'])
def edit_article(article_id):
    user_id = session.get('user_id')
    if not user_id:
        flash('You must be logged in to edit an article.', 'error')
        return redirect(url_for('admin_login'))

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

if __name__ == '__main__':
    app.run(debug=True)