from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Proszę się zalogować, aby uzyskać dostęp do tej strony.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


from model import User, Category, Transaction


@app.route('/')
@login_required
def dashboard():
    # Get current month and year
    current_month = datetime.now().month
    current_year = datetime.now().year

    # Calculate total income and expenses for the current month
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

    # Get recent transactions
    recent_transactions = Transaction.query.filter_by(
        user_id=session['user_id']
    ).order_by(Transaction.date.desc()).limit(5).all()

    # Get expenses by category for the current month
    expenses_by_category = db.session.query(
        Category.name,
        db.func.sum(Transaction.amount)
    ).join(Transaction).filter(
        Transaction.user_id == session['user_id'],
        Transaction.type == 'expense',
        db.func.strftime('%m', Transaction.date) == f"{current_month:02d}",
        db.func.strftime('%Y', Transaction.date) == str(current_year)
    ).group_by(Category.name).all()

    # Prepare data for charts
    categories = [category[0] for category in expenses_by_category]
    amounts = [float(category[1]) for category in expenses_by_category]

    return render_template('dashboard.html',
                           income=income,
                           expenses=expenses,
                           balance=balance,
                           recent_transactions=recent_transactions,
                           categories=categories,
                           amounts=amounts)


@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    if request.method == 'POST':
        type = request.form.get('type')
        amount = float(request.form.get('amount'))
        category_id = int(request.form.get('category'))
        date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        description = request.form.get('description', '')

        new_transaction = Transaction(
            type=type,
            amount=amount,
            category_id=category_id,
            date=date,
            description=description,
            user_id=session['user_id']
        )

        db.session.add(new_transaction)
        db.session.commit()

        flash('Transakcja została dodana pomyślnie!', 'success')
        return redirect(url_for('transactions'))

    # Get all transactions for the user
    user_transactions = Transaction.query.filter_by(
        user_id=session['user_id']
    ).order_by(Transaction.date.desc()).all()

    # Get all categories for the dropdown
    categories = Category.query.filter_by(user_id=session['user_id']).all()

    return render_template('transactions.html',
                           transactions=user_transactions,
                           categories=categories,
                           datetime=datetime)  # <—— TO JEST KLUCZOWE


@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')

        new_category = Category(
            name=name,
            description=description,
            user_id=session['user_id']
        )

        db.session.add(new_category)
        db.session.commit()

        flash('Kategoria została dodana pomyślnie!', 'success')
        return redirect(url_for('categories'))

    user_categories = Category.query.filter_by(
        user_id=session['user_id']
    ).all()

    return render_template('categories.html', categories=user_categories)


@app.route('/reports')
@login_required
def reports():
    # Get data for monthly expenses chart
    monthly_expenses = db.session.query(
        db.func.strftime('%Y-%m', Transaction.date).label('month'),
        db.func.sum(Transaction.amount).label('total')
    ).filter(
        Transaction.user_id == session['user_id'],
        Transaction.type == 'expense'
    ).group_by('month').order_by('month').all()

    months = [expense.month for expense in monthly_expenses]
    monthly_totals = [float(expense.total) for expense in monthly_expenses]

    return render_template('reports.html',
                           months=months,
                           monthly_totals=monthly_totals)


@app.route('/export/<format>')
@login_required
def export(format):
    flash(f'Eksport do {format.upper()} nie jest jeszcze zaimplementowany.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['email'] = user.email
            flash('Zalogowano pomyślnie!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Nieprawidłowy email lub hasło.', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Hasła nie są identyczne!', 'danger')
            return redirect(url_for('register'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Użytkownik o podanym emailu już istnieje!', 'danger')
            return redirect(url_for('register'))

        new_user = User(email=email)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash('Rejestracja zakończona pomyślnie! Możesz się teraz zalogować.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('Wylogowano pomyślnie!', 'success')
    return redirect(url_for('login'))


@app.route('/delete_transaction/<int:id>', methods=['POST'])
@login_required
def delete_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    if transaction.user_id != session['user_id']:
        flash('Nie masz uprawnień do usunięcia tej transakcji', 'danger')
        return redirect(url_for('transactions'))

    db.session.delete(transaction)
    db.session.commit()
    flash('Transakcja została usunięta', 'success')
    return redirect(url_for('transactions'))


@app.route('/delete_category/<int:id>', methods=['POST'])
@login_required
def delete_category(id):
    category = Category.query.get_or_404(id)
    if category.user_id != session['user_id']:
        flash('Nie masz uprawnień do usunięcia tej kategorii', 'danger')
        return redirect(url_for('categories'))

    # Check if category is used in transactions
    if Transaction.query.filter_by(category_id=id).count() > 0:
        flash('Nie można usunąć kategorii, ponieważ jest używana w transakcjach', 'danger')
        return redirect(url_for('categories'))

    db.session.delete(category)
    db.session.commit()
    flash('Kategoria została usunięta', 'success')
    return redirect(url_for('categories'))


if __name__ == '__main__':
    from model import User, Category, Transaction  # ← TO JEST KLUCZOWE

    with app.app_context():
        print(">>> Tworzę tabele...")
        db.create_all()
        print(">>> Gotowe.")
    app.run(debug=True)