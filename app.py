from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from datetime import datetime
from functools import wraps
import csv
import io
import re
from xhtml2pdf import pisa

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

from model import User, Category, Transaction

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash("Zaloguj się", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

@app.route('/')
@login_required
def dashboard():
    current_month = datetime.now().month
    current_year = datetime.now().year

    income = db.session.query(db.func.sum(Transaction.amount)).filter(
        Transaction.user_id == session['user_id'],
        Transaction.type == 'income',
        db.func.strftime('%m', Transaction.date) == f"{current_month:02d}",
        db.func.strftime('%Y', Transaction.date) == str(current_year)
    ).scalar() or 0

    expenses = db.session.query(db.func.sum(Transaction.amount)).filter(
        Transaction.user_id == session['user_id'],
        Transaction.type == 'expense',
        db.func.strftime('%m', Transaction.date) == f"{current_month:02d}",
        db.func.strftime('%Y', Transaction.date) == str(current_year)
    ).scalar() or 0

    balance = income - expenses

    recent_transactions = Transaction.query.filter_by(user_id=session['user_id']).order_by(Transaction.date.desc()).limit(5).all()

    expenses_by_category = db.session.query(
        Category.name, db.func.sum(Transaction.amount)
    ).join(Transaction).filter(
        Transaction.user_id == session['user_id'],
        Transaction.type == 'expense',
        db.func.strftime('%m', Transaction.date) == f"{current_month:02d}",
        db.func.strftime('%Y', Transaction.date) == str(current_year)
    ).group_by(Category.name).all()

    categories = [c[0] for c in expenses_by_category]
    amounts = [float(c[1]) for c in expenses_by_category]

    return render_template('dashboard.html', income=income, expenses=expenses, balance=balance,
                           recent_transactions=recent_transactions, categories=categories, amounts=amounts)

@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    if request.method == 'POST':
        tx = Transaction(
            type=request.form['type'],
            amount=float(request.form['amount']),
            category_id=int(request.form['category']),
            date=datetime.strptime(request.form['date'], '%Y-%m-%d'),
            description=request.form.get('description', ''),
            user_id=session['user_id']
        )
        db.session.add(tx)
        db.session.commit()
        flash('Dodano transakcję', 'success')
        return redirect(url_for('transactions'))

    filters = {
        'type': request.args.get('type', ''),
        'category': request.args.get('category', ''),
        'date_from': request.args.get('date_from', ''),
        'date_to': request.args.get('date_to', '')
    }

    query = Transaction.query.filter_by(user_id=session['user_id'])

    if filters['type']:
        query = query.filter_by(type=filters['type'])
    if filters['category']:
        query = query.filter_by(category_id=int(filters['category']))
    if filters['date_from']:
        query = query.filter(Transaction.date >= filters['date_from'])
    if filters['date_to']:
        query = query.filter(Transaction.date <= filters['date_to'])

    txs = query.order_by(Transaction.date.desc()).all()
    cats = Category.query.filter_by(user_id=session['user_id']).all()

    return render_template('transactions.html', transactions=txs, categories=cats, filters=filters, datetime=datetime)

@app.route('/transactions/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    tx = Transaction.query.get_or_404(id)
    if tx.user_id != session['user_id']:
        flash('Brak uprawnień', 'danger')
        return redirect(url_for('transactions'))

    if request.method == 'POST':
        tx.type = request.form['type']
        tx.amount = float(request.form['amount'])
        tx.category_id = int(request.form['category'])
        tx.date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        tx.description = request.form.get('description', '')
        db.session.commit()
        flash('Transakcja zaktualizowana', 'success')
        return redirect(url_for('transactions'))

    cats = Category.query.filter_by(user_id=session['user_id']).all()
    return render_template('edit_transaction.html', transaction=tx, categories=cats)

@app.route('/delete_transaction/<int:id>', methods=['POST'])
@login_required
def delete_transaction(id):
    tx = Transaction.query.get_or_404(id)
    if tx.user_id != session['user_id']:
        flash('Brak uprawnień', 'danger')
    else:
        db.session.delete(tx)
        db.session.commit()
        flash('Usunięto transakcję', 'success')
    return redirect(url_for('transactions'))

@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        cat = Category(
            name=request.form['name'],
            description=request.form.get('description', ''),
            user_id=session['user_id']
        )
        db.session.add(cat)
        db.session.commit()
        flash('Dodano kategorię', 'success')
        return redirect(url_for('categories'))

    user_cats = Category.query.filter_by(user_id=session['user_id']).all()
    return render_template('categories.html', categories=user_cats)

@app.route('/categories/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_category(id):
    category = Category.query.get_or_404(id)
    if category.user_id != session['user_id']:
        flash('Brak dostępu', 'danger')
        return redirect(url_for('categories'))

    if request.method == 'POST':
        category.name = request.form['name']
        category.description = request.form.get('description', '')
        db.session.commit()
        flash('Zaktualizowano kategorię', 'success')
        return redirect(url_for('categories'))

    return render_template('edit_category.html', category=category)

@app.route('/delete_category/<int:id>', methods=['POST'])
@login_required
def delete_category(id):
    category = Category.query.get_or_404(id)
    if category.user_id != session['user_id']:
        flash('Brak dostępu', 'danger')
        return redirect(url_for('categories'))

    if category.transactions:
        flash('Nie można usunąć kategorii z przypisanymi transakcjami', 'danger')
        return redirect(url_for('categories'))

    db.session.delete(category)
    db.session.commit()
    flash('Usunięto kategorię', 'success')
    return redirect(url_for('categories'))

@app.route('/reports')
@login_required
def reports():
    monthly = db.session.query(
        db.func.strftime('%Y-%m', Transaction.date).label('month'),
        db.func.sum(Transaction.amount).label('total')
    ).filter(
        Transaction.user_id == session['user_id'],
        Transaction.type == 'expense'
    ).group_by('month').order_by('month').all()

    months = [m.month for m in monthly]
    totals = [float(m.total) for m in monthly]

    return render_template('reports.html', months=months, monthly_totals=totals)

@app.route('/export/<format>')
@login_required
def export(format):
    txs = Transaction.query.filter_by(user_id=session['user_id']).order_by(Transaction.date.desc()).all()
    balance = sum(t.amount if t.type == 'income' else -t.amount for t in txs)

    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Data', 'Typ', 'Kwota', 'Kategoria', 'Opis'])
        for tx in txs:
            writer.writerow([
                tx.date.strftime('%Y-%m-%d'),
                tx.type,
                f"{tx.amount:.2f}",
                tx.category_ref.name,
                tx.description or ''
            ])
        output.seek(0)
        return Response(output.getvalue(), mimetype='text/csv',
                        headers={"Content-Disposition": "attachment; filename=transakcje.csv"})

    elif format == 'pdf':
        rendered = render_template('pdf_template.html', transactions=txs, balance=balance)
        pdf_io = io.BytesIO()
        pisa_status = pisa.CreatePDF(io.StringIO(rendered), dest=pdf_io)
        if pisa_status.err:
            flash('Błąd podczas generowania PDF', 'danger')
            return redirect(url_for('dashboard'))
        pdf_io.seek(0)
        return Response(pdf_io.read(), mimetype='application/pdf',
                        headers={"Content-Disposition": "attachment; filename=transakcje.pdf"})

    flash('Nieobsługiwany format eksportu', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        pwd = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(pwd):
            session['user_id'] = user.id
            session['email'] = user.email
            flash('Zalogowano', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Błędne dane', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        pwd = request.form.get('password', '').strip()
        pwd2 = request.form.get('confirm_password', '').strip()

        if not email or not pwd or not pwd2:
            flash('Wszystkie pola są wymagane.', 'danger')
            return redirect(url_for('register'))

        email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_regex, email):
            flash('Niepoprawny adres e-mail.', 'danger')
            return redirect(url_for('register'))

        if len(pwd) < 6:
            flash('Hasło musi mieć co najmniej 6 znaków.', 'danger')
            return redirect(url_for('register'))

        if pwd != pwd2:
            flash('Hasła nie są zgodne.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Ten adres e-mail jest już zarejestrowany.', 'danger')
            return redirect(url_for('register'))

        user = User(email=email)
        user.set_password(pwd)
        db.session.add(user)
        db.session.commit()
        flash('Rejestracja zakończona sukcesem.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')
@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')
@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('Wylogowano', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)