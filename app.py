from flask import Flask, request, render_template, redirect, url_for, session, flash
import sqlite3
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

# Setting up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Database setup
class Database:
    def __init__(self, db_name: str):
        self.connection = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS products (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                name TEXT NOT NULL,
                                price REAL NOT NULL,
                                category TEXT NOT NULL
                              )''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                username TEXT NOT NULL UNIQUE,
                                password TEXT NOT NULL
                              )''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
                                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id INTEGER,
                                total_amount REAL,
                                payment_method TEXT,
                                summary TEXT,
                                FOREIGN KEY(user_id) REFERENCES users(id)
                              )''')
        self.connection.commit()

    def insert_product(self, name: str, price: float, category: str):
        self.cursor.execute("INSERT INTO products (name, price, category) VALUES (?, ?, ?)",
                            (name, price, category))
        self.connection.commit()

    def fetch_products(self) -> List[Dict]:
        self.cursor.execute("SELECT name, price, category FROM products")
        rows = self.cursor.fetchall()
        products = [{"name": row[0], "price": row[1], "category": row[2]} for row in rows]
        return products

    def fetch_product_by_name(self, name: str) -> Optional[Dict]:
        self.cursor.execute("SELECT name, price, category FROM products WHERE name = ?", (name,))
        row = self.cursor.fetchone()
        if row:
            return {"name": row[0], "price": row[1], "category": row[2]}
        return None

    def insert_user(self, username: str, password: str):
        self.cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        self.connection.commit()

    def fetch_user(self, username: str) -> Optional[Dict]:
        self.cursor.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
        row = self.cursor.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "password": row[2]}
        return None

    def insert_order(self, user_id: int, total_amount: float, payment_method: str, summary: str):
        self.cursor.execute("INSERT INTO orders (user_id, total_amount, payment_method, summary) VALUES (?, ?, ?, ?)",
                            (user_id, total_amount, payment_method, summary))
        self.connection.commit()

    def fetch_orders_by_user_id(self, user_id: int) -> List[Dict]:
        self.cursor.execute("SELECT order_id, total_amount, payment_method, summary FROM orders WHERE user_id = ?", (user_id,))
        rows = self.cursor.fetchall()
        orders = [{"order_id": row[0], "total_amount": row[1], "payment_method": row[2], "summary": row[3]} for row in rows]
        return orders

# User Authentication
class User:
    def __init__(self, user_id: int, username: str, password: str):
        self.user_id = user_id
        self.username = username
        self.password = password
        self.cart = Cart.get_instance()

class AuthService:
    def __init__(self, db: Database):
        self.db = db

    def register_user(self, username: str, password: str) -> User:
        if self.db.fetch_user(username):
            raise ValueError("User already exists.")
        self.db.insert_user(username, password)
        user_data = self.db.fetch_user(username)
        user = User(user_data["id"], username, password)
        logger.info(f"User {username} registered.")
        return user

    def login(self, username: str, password: str) -> User:
        user_data = self.db.fetch_user(username)
        if user_data and user_data['password'] == password:
            logger.info(f"User {username} logged in.")
            return User(user_data["id"], username, password)
        else:
            raise ValueError("Invalid username or password.")

# Product Catalog
class Product:
    def __init__(self, name: str, price: float, category: str):
        self.name = name
        self.price = price
        self.category = category

class ProductFactory(ABC):
    @abstractmethod
    def create_product(self, name: str, price: float, category: str) -> Product:
        pass

class ConcreteProductFactory(ProductFactory):
    def create_product(self, name: str, price: float, category: str) -> Product:
        return Product(name, price, category)

class Catalog:
    def __init__(self, db: Database):
        self.db = db

    def add_product(self, product: Product):
        self.db.insert_product(product.name, product.price, product.category)
        logger.info(f"Product {product.name} added to catalog.")

    def get_product(self, name: str) -> Optional[Product]:
        product_data = self.db.fetch_product_by_name(name)
        if product_data:
            return Product(product_data["name"], product_data["price"], product_data["category"])
        return None

    def list_products(self) -> List[Product]:
        products_data = self.db.fetch_products()
        return [Product(p["name"], p["price"], p["category"]) for p in products_data]

# Singleton Cart
class Cart:
    _instance = None

    def __init__(self):
        if not Cart._instance:
            self.items = {}
            Cart._instance = self
        else:
            raise Exception("This class is a singleton!")

    @staticmethod
    def get_instance():
        if not Cart._instance:
            Cart()
        return Cart._instance

    def add_item(self, product: Product, quantity: int):
        if product.name in self.items:
            self.items[product.name]['quantity'] += quantity
        else:
            self.items[product.name] = {'product': product, 'quantity': quantity}
        logger.info(f"Added {quantity} of {product.name} to cart.")

    def remove_item(self, product: Product):
        if product.name in self.items:
            del self.items[product.name]
            logger.info(f"Removed {product.name} from cart.")

    def get_items(self) -> Dict[str, Dict[str, any]]:
        return self.items

    def clear(self):
        self.items = {}

# Order Processing
class Order:
    def __init__(self, user: User):
        self.user = user
        self.items = user.cart.get_items()

class OrderProcessor:
    @staticmethod
    def create_order(user: User) -> Order:
        if not user.cart.get_items():
            raise ValueError("Cart is empty.")
        order = Order(user)
        logger.info(f"Order created for user {user.username}.")
        return order

    @staticmethod
    def confirm_order(user: User):
        user.cart.clear()
        logger.info(f"Order confirmed for user {user.username}.")

# Payment Processing
class PaymentGateway(ABC):
    @abstractmethod
    def process_payment(self, amount: float) -> bool:
        pass

class MockPaymentGateway(PaymentGateway):
    def process_payment(self, amount: float) -> bool:
        logger.info(f"Processing payment of ${amount}.")
        return True

class PaymentProcessor:
    def __init__(self, payment_gateway: PaymentGateway):
        self.payment_gateway = payment_gateway

    def process_order_payment(self, order: Order, payment_method: str) -> bool:
        total_amount = sum(item['product'].price * item['quantity'] for item in order.items.values())
        return self.payment_gateway.process_payment(total_amount), total_amount

# Initialize components
db = Database('shopping.db')
auth_service = AuthService(db)
catalog = Catalog(db)
product_factory = ConcreteProductFactory()

# Add some products to the catalog if empty
if not db.fetch_products():  # Only add products if the database is empty
    categories = {
        "Electronics": [
            ("Laptop", 1200.0),
            ("Smartphone", 800.0),
            ("Tablet", 500.0)
        ],
        "Home Appliances": [
            ("Refrigerator", 1500.0),
            ("Microwave", 200.0),
            ("Washing Machine", 1000.0)
        ],
        "Books": [
            ("The Hobbit", 40.0),
            ("Train to Pakistan", 35.0),
            ("Harry Potter and the Deathly Hallows", 55.0)
        ],
        "Clothing": [
            ("Shirt", 30.0),
            ("Jeans", 50.0),
            ("Jacket", 100.0)
        ]
    }
    for category, products in categories.items():
        for name, price in products:
            product = product_factory.create_product(name, price, category)
            catalog.add_product(product)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            user = auth_service.register_user(username, password)
            session['user_id'] = user.user_id
            session['username'] = user.username
            flash('User registered successfully.', 'success')
            return redirect(url_for('home'))
        except ValueError as e:
            flash(str(e), 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            user = auth_service.login(username, password)
            session['user_id'] = user.user_id
            session['username'] = user.username
            flash('User logged in successfully.', 'success')
            return redirect(url_for('home'))
        except ValueError as e:
            flash(str(e), 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))

@app.route('/catalog')
def view_catalog():
    products = catalog.list_products()
    return render_template('catalog.html', products=products)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    product_name = request.form['product_name']
    quantity = int(request.form['quantity'])
    product = catalog.get_product(product_name)
    if product:
        user_id = session['user_id']
        user = auth_service.db.fetch_user(session['username'])
        user_obj = User(user['id'], user['username'], user['password'])
        user_obj.cart.add_item(product, quantity)
        flash(f"Added {quantity} of {product_name} to cart.", 'success')
    else:
        flash("Product not found.", 'danger')
    return redirect(url_for('view_catalog'))

@app.route('/cart')
def view_cart():
    if 'user_id' not in session:
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    user = auth_service.db.fetch_user(session['username'])
    user_obj = User(user['id'], user['username'], user['password'])
    cart_items = user_obj.cart.get_items()
    return render_template('cart.html', cart_items=cart_items)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    user = auth_service.db.fetch_user(session['username'])
    user_obj = User(user['id'], user['username'], user['password'])

    if request.method == 'POST':
        order = OrderProcessor.create_order(user_obj)
        payment_method = request.form['payment_method']
        payment_gateway = MockPaymentGateway()
        payment_processor = PaymentProcessor(payment_gateway)
        payment_successful, total_amount = payment_processor.process_order_payment(order, payment_method)

        if payment_successful:
            OrderProcessor.confirm_order(user_obj)
            summary = "\n".join([f"{item['quantity']}x {item['product'].name} at ${item['product'].price} each"
                                 for item in order.items.values()])
            summary += f"\nTotal Amount: ${total_amount:.2f}"
            db.insert_order(user_obj.user_id, total_amount, payment_method, summary)
            flash('Payment processed and order confirmed successfully.', 'success')
            return redirect(url_for('order_history'))
        else:
            flash('Payment failed.', 'danger')
    
    return render_template('checkout.html')

@app.route('/orders')
def order_history():
    if 'user_id' not in session:
        flash('Please log in first.', 'danger')
        return redirect(url_for('login'))

    user = auth_service.db.fetch_user(session['username'])
    orders = db.fetch_orders_by_user_id(user['id'])
    return render_template('orders.html', orders=orders)

if __name__ == "__main__":
    app.run(debug=True)
