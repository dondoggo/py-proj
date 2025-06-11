from app import app, db
from model import User, Category, Transaction

with app.app_context():
    print(">>> Tworzę tabele w finance.db...")
    db.create_all()
    print(">>> Gotowe. Sprawdź plik finance.db.")