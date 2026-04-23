from flask import Flask, render_template_string, request, redirect, jsonify, url_for, session as flask_session
import requests
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from flask import Response

load_dotenv()
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

print(API_KEY)
print(SECRET_KEY)
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///store2.db'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'home'

# ================= MODELS =================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(150), unique=True, nullable=True)
    password_hash = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    oauth_provider = db.Column(db.String(50), nullable=True)   # 'google' | 'facebook' | None
    oauth_id = db.Column(db.String(200), nullable=True)        # provider's user id
    avatar_url = db.Column(db.String(500), nullable=True)      # profile picture from OAuth
    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price = db.Column(db.Integer)
    orig_price = db.Column(db.Integer)
    category = db.Column(db.String(100))
    subcategory = db.Column(db.String(100), default='')
    emoji = db.Column(db.String(10), default='🛍️')
    description = db.Column(db.String(200), default='')
    rating = db.Column(db.Float, default=4.5)
    sold = db.Column(db.String(20), default='1k+')
    is_flash = db.Column(db.Boolean, default=False)
    image_url = db.Column(db.String(500), default='')

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    product_id = db.Column(db.Integer)
    quantity = db.Column(db.Integer, default=1)

class Order(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, nullable=False)
    total      = db.Column(db.Integer, nullable=False)
    status     = db.Column(db.String(50), default='Processing')
    address    = db.Column(db.String(300), default='')
    payment    = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items      = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    order_id      = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id    = db.Column(db.Integer)
    product_name  = db.Column(db.String(100))
    product_emoji = db.Column(db.String(10))
    price         = db.Column(db.Integer)

class SavedAddress(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, nullable=False)
    label      = db.Column(db.String(50), default='Home')   # Home / Work / Other
    fname      = db.Column(db.String(100), default='')
    lname      = db.Column(db.String(100), default='')
    phone      = db.Column(db.String(20),  default='')
    address    = db.Column(db.String(300), default='')
    city       = db.Column(db.String(100), default='')
    pin        = db.Column(db.String(10),  default='')
    state      = db.Column(db.String(100), default='')
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ================= EMAIL CONFIG =================#

MAIL_SENDER   = os.environ.get('MAIL_SENDER')  
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

#AI Myra

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY') 
# PAYPAL CREDENTIALS
PAYPAL_CLIENT_ID     = os.environ.get('PAYPAL_CLIENT_ID')     
PAYPAL_CLIENT_SECRET = os.environ.get('PAYPAL_CLIENT_SECRET') 
PAYPAL_BASE_URL      = 'https://api-m.sandbox.paypal.com'  

# RAZORPAY CREDENTIALS
RAZORPAY_KEY_ID     = os.environ.get('RAZORPAY_KEY_ID')     
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET') 

STORE_NAME    = 'MyStore'

# ─── GOOGLE OAUTH CREDENTIALS ───────────────────────────────────────────────
GOOGLE_CLIENT_ID     = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

class Subscriber(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(150), unique=True, nullable=False)
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)

class Advertisement(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    slot       = db.Column(db.Integer, unique=True, nullable=False)   # 1, 2, 3
    tag        = db.Column(db.String(80), default='')
    title      = db.Column(db.String(120), default='')
    subtitle   = db.Column(db.String(200), default='')
    cta_text   = db.Column(db.String(60), default='')
    cta_link   = db.Column(db.String(300), default='/')
    discount   = db.Column(db.String(40), default='')
    emoji      = db.Column(db.String(10), default='🛍️')
    theme      = db.Column(db.String(20), default='electronics')   # electronics | fashion | accessories
    is_active  = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ================= DB INIT (runs under gunicorn AND direct) =================
def init_db():
    with app.app_context():
        db.create_all()
        # ── OAuth columns (safe no-ops if already present) ──────────────────
        for col_sql in [
            "ALTER TABLE user ADD COLUMN oauth_provider VARCHAR(50)",
            "ALTER TABLE user ADD COLUMN oauth_id VARCHAR(200)",
            "ALTER TABLE user ADD COLUMN avatar_url VARCHAR(500)",
        ]:
            try:
                with db.engine.connect() as conn:
                    conn.execute(db.text(col_sql))
                    conn.commit()
            except Exception:
                pass
        for col_sql, label in [
            ("ALTER TABLE product ADD COLUMN subcategory VARCHAR(100) DEFAULT ''", "subcategory"),
            ("ALTER TABLE product ADD COLUMN image_url VARCHAR(500) DEFAULT ''", "image_url"),
            ("ALTER TABLE cart ADD COLUMN quantity INTEGER DEFAULT 1", "quantity"),
        ]:
            try:
                with db.engine.connect() as conn:
                    conn.execute(db.text(col_sql))
                    conn.commit()
                print(f"Added {label} column.")
            except Exception:
                pass
        # Seed default advertisements if none exist
        try:
            if Advertisement.query.count() == 0:
                for ad in [
                    Advertisement(slot=1, tag='⚡ Electronics Sale', title='Latest Gadgets & Tech',
                        subtitle="Smartphones, Laptops, Audio & more — deals you can't miss",
                        cta_text='Shop Electronics →', cta_link='/?category=Electronics',
                        discount='UP TO 40% OFF', emoji='📱', theme='electronics', is_active=True),
                    Advertisement(slot=2, tag='🔥 Fashion Fiesta', title='Trendy Styles Await',
                        subtitle='T-Shirts, Jackets, Jeans & more — dress to impress',
                        cta_text='Explore Fashion →', cta_link='/?category=Fashion',
                        discount='FLAT 50% OFF', emoji='👗', theme='fashion', is_active=True),
                    Advertisement(slot=3, tag='✨ Accessories Deal', title='Complete Your Look',
                        subtitle='Watches, Bags, Jewellery & more — style in every detail',
                        cta_text='Shop Accessories →', cta_link='/?category=Accessories',
                        discount='UP TO 35% OFF', emoji='💎', theme='accessories', is_active=True),
                ]:
                    db.session.add(ad)
                db.session.commit()
                print("Seeded 3 default advertisements.")
        except Exception as e:
            print(f"Advertisement seed error: {e}")
            db.session.rollback()
        # Seed products
        try:
            if Product.query.count() == 0:
                for p in PRODUCTS:
                    db.session.add(Product(
                        name=p['name'], price=p['price'], orig_price=p['orig_price'],
                        category=p['category'], subcategory=p.get('subcategory', ''),
                        emoji=p['emoji'], description=p['description'],
                        rating=p['rating'], sold=p['sold'], is_flash=p['is_flash'],
                        image_url=p.get('image_url', '')
                    ))
                db.session.commit()
                print(f"Seeded {len(PRODUCTS)} products.")
            else:
                stale = Product.query.filter_by(category='Electronics', subcategory='Electronics').first()
                needs_reseed = (stale is not None
                    or Product.query.filter(Product.subcategory == '').first() is not None
                    or Product.query.count() < 1000
                    or Product.query.filter(Product.image_url == '').first() is not None)
                if needs_reseed:
                    print("Re-seeding products…")
                    Product.query.delete()
                    for p in PRODUCTS:
                        db.session.add(Product(
                            name=p['name'], price=p['price'], orig_price=p['orig_price'],
                            category=p['category'], subcategory=p.get('subcategory', ''),
                            emoji=p['emoji'], description=p['description'],
                            rating=p['rating'], sold=p['sold'], is_flash=p['is_flash'],
                            image_url=p.get('image_url', '')
                        ))
                    db.session.commit()
                    print(f"Re-seeded {len(PRODUCTS)} products.")
                else:
                    print("Products OK — skipping seed.")
        except Exception as e:
            print(f"Product seed error: {e}")
            db.session.rollback()

init_db()  # Always runs — works with gunicorn, waitress, and direct python

# ================= SEED DATA =================
PRODUCTS = [
    # ── Electronics ──────────────────────────────────────────────────────────
    {"name": "Samsung Galaxy S24", "price": 79999, "orig_price": 89999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "6.2\" AMOLED, 50MP Camera", "rating": 4.9, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone 15", "price": 89999, "orig_price": 99999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A16 Bionic, 48MP Camera", "rating": 4.8, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1695048133142-1a20484bce71?w=400&h=400&fit=crop"},
    {"name": "Sony WH-1000XM5", "price": 29999, "orig_price": 34999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Industry-best Noise Cancelling", "rating": 4.9, "sold": "3k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=400&h=400&fit=crop"},
    {"name": "Dell Inspiron Laptop", "price": 55999, "orig_price": 65999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i5, 16GB RAM, 512GB SSD", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=400&h=400&fit=crop"},
    {"name": "iPad Air 5th Gen", "price": 59999, "orig_price": 69999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "M1 Chip, 10.9\" Liquid Retina", "rating": 4.8, "sold": "4k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=400&h=400&fit=crop"},
    {"name": "OnePlus Buds Pro 2", "price": 9999, "orig_price": 12999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎵", "description": "48dB ANC, Spatial Audio", "rating": 4.6, "sold": "8k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1608156639585-b3a032ef9689?w=400&h=400&fit=crop"},
    {"name": "LG 4K Smart TV 55\"", "price": 49999, "orig_price": 59999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "webOS, Dolby Vision IQ", "rating": 4.7, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1586495777744-4e6b0ed34083?w=400&h=400&fit=crop"},
    {"name": "Canon EOS R50", "price": 74999, "orig_price": 84999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "24.2MP, 4K Video, Mirrorless", "rating": 4.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=400&h=400&fit=crop"},
    {"name": "Logitech MX Master 3", "price": 8499, "orig_price": 9999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖱️", "description": "Ergonomic, Multi-device", "rating": 4.8, "sold": "12k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "boAt Rockerz 450", "price": 1499, "orig_price": 2999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "40Hr Battery, Super Bass", "rating": 4.5, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1484704849700-f032a568e944?w=400&h=400&fit=crop"},
    {"name": "Realme Narzo 60", "price": 17999, "orig_price": 21999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "6.67\" AMOLED, 64MP Camera", "rating": 4.4, "sold": "15k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "HP Pavilion Laptop", "price": 62999, "orig_price": 72999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 5, 8GB RAM, 512GB SSD", "rating": 4.6, "sold": "3k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=400&h=400&fit=crop"},
    {"name": "JBL Flip 6 Speaker", "price": 11999, "orig_price": 14999, "category": "Electronics", "subcategory": "Audio", "emoji": "🔊", "description": "Portable Bluetooth, IP67 Waterproof", "rating": 4.7, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=400&h=400&fit=crop"},
    {"name": "Sony PlayStation 5", "price": 54990, "orig_price": 59990, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🎮", "description": "825GB SSD, 4K Gaming Console", "rating": 4.9, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1606144042614-b2417e99c4e3?w=400&h=400&fit=crop"},
    {"name": "Samsung 27\" Monitor", "price": 18999, "orig_price": 23999, "category": "Electronics", "subcategory": "TVs", "emoji": "🖥️", "description": "FHD IPS, 75Hz, Eye Care", "rating": 4.6, "sold": "7k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1461151304267-38535e596517?w=400&h=400&fit=crop"},

    # ── T-Shirts ──────────────────────────────────────────────────────────────
    {"name": "H&M Oversized Graphic Tee", "price": 999, "orig_price": 1499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "100% Cotton, Relaxed Fit", "rating": 4.6, "sold": "30k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop"},
    {"name": "Bewakoof Acid Wash Tee", "price": 699, "orig_price": 999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Premium Cotton, Tie-Dye Effect", "rating": 4.4, "sold": "45k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=400&h=400&fit=crop"},
    {"name": "Nike Dri-FIT T-Shirt", "price": 1799, "orig_price": 2499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Moisture-Wicking, Sports Ready", "rating": 4.7, "sold": "22k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop"},
    {"name": "Roadster Printed Round Neck Tee", "price": 599, "orig_price": 899, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Casual Wear, Soft Cotton", "rating": 4.3, "sold": "60k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1586790170083-2f9ceadc732d?w=400&h=400&fit=crop"},
    {"name": "Puma Essentials Small Logo Tee", "price": 1299, "orig_price": 1799, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Regular Fit, Soft Jersey", "rating": 4.5, "sold": "18k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1503341504253-dff4815485f1?w=400&h=400&fit=crop"},
    {"name": "Adidas Linear Logo Tee", "price": 1499, "orig_price": 1999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Recycled Cotton Blend, Slim Fit", "rating": 4.6, "sold": "14k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1556821840-3a63f15732ce?w=400&h=400&fit=crop"},
    {"name": "Tommy Hilfiger Essential Tee", "price": 2499, "orig_price": 3499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Flag Embroidery, Classic Cut", "rating": 4.8, "sold": "8k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1529374255404-311a2a4f1fd9?w=400&h=400&fit=crop"},
    {"name": "Levis Batwing Logo Tee", "price": 1899, "orig_price": 2499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "100% Cotton, Regular Fit", "rating": 4.7, "sold": "12k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=400&h=400&fit=crop"},
    {"name": "UCB Striped Polo T-Shirt", "price": 1599, "orig_price": 2299, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Pique Cotton, Slim Fit Collar", "rating": 4.5, "sold": "9k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=400&h=400&fit=crop"},
    {"name": "Zara Textured Linen Tee", "price": 1990, "orig_price": 2790, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Linen Blend, Boxy Silhouette", "rating": 4.6, "sold": "7k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1523381294911-8d3cead13475?w=400&h=400&fit=crop"},
    {"name": "Dennis Lingo Solid Tee Pack of 3", "price": 1299, "orig_price": 1999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Value Pack, Soft Cotton", "rating": 4.4, "sold": "35k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1562157873-818bc0726f68?w=400&h=400&fit=crop"},

    # ── Jackets ───────────────────────────────────────────────────────────────
    {"name": "Adidas Track Jacket", "price": 4499, "orig_price": 5999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "3-Stripes, Moisture-wicking", "rating": 4.7, "sold": "6k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1551488831-00ddcb6c6bd3?w=400&h=400&fit=crop"},
    {"name": "Mango Structured Blazer", "price": 5990, "orig_price": 7990, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Tailored Fit, Office Wear", "rating": 4.8, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=400&h=400&fit=crop"},
    {"name": "The North Face Windbreaker", "price": 8999, "orig_price": 11999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Water-Resistant, Packable", "rating": 4.9, "sold": "3k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1544923246-77307dd654cb?w=400&h=400&fit=crop"},
    {"name": "Roadster Quilted Jacket", "price": 2499, "orig_price": 3499, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Padded Fill, Winter Ready", "rating": 4.5, "sold": "11k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1544923246-77307dd654cb?w=400&h=400&fit=crop"},
    {"name": "H&M Denim Jacket", "price": 2999, "orig_price": 3999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Classic Wash, Relaxed Fit", "rating": 4.6, "sold": "14k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1576871337622-98d48d1cf531?w=400&h=400&fit=crop"},
    {"name": "Puma Sherpa Fleece Jacket", "price": 3999, "orig_price": 5499, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Cosy Fleece Lining, Full Zip", "rating": 4.7, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1563720223185-11003d516935?w=400&h=400&fit=crop"},
    {"name": "Zara Faux Leather Biker Jacket", "price": 6990, "orig_price": 8990, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Edgy Silhouette, Zip Details", "rating": 4.8, "sold": "4k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1544923246-77307dd654cb?w=400&h=400&fit=crop"},
    {"name": "Being Human Bomber Jacket", "price": 3499, "orig_price": 4999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Satin Finish, Ribbed Collar", "rating": 4.5, "sold": "9k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1563720223185-11003d516935?w=400&h=400&fit=crop"},
    {"name": "Campus Sutra Varsity Jacket", "price": 2799, "orig_price": 3999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Colour Block, Snap Buttons", "rating": 4.4, "sold": "7k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1534277538-0ea2efce5fe5?w=400&h=400&fit=crop"},
    {"name": "Louis Philippe Formal Blazer", "price": 7999, "orig_price": 10499, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Wool Blend, 2-Button Single Breasted", "rating": 4.9, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=400&h=400&fit=crop"},

    # ── Shirts ────────────────────────────────────────────────────────────────
    {"name": "Van Heusen Formal Shirt", "price": 1599, "orig_price": 2199, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Regular Fit, Easy Iron", "rating": 4.6, "sold": "18k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1620799140408-edc6dcb6d633?w=400&h=400&fit=crop"},
    {"name": "Allen Solly Slim Fit Shirt", "price": 1699, "orig_price": 2399, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Dobby Weave, French Placket", "rating": 4.5, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=400&h=400&fit=crop"},
    {"name": "Peter England Check Shirt", "price": 1299, "orig_price": 1799, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Classic Tartan, Full Sleeve", "rating": 4.4, "sold": "25k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "Levis Casual Chambray Shirt", "price": 2299, "orig_price": 2999, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Light Denim Weave, Relaxed Fit", "rating": 4.7, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=400&h=400&fit=crop"},
    {"name": "Arrow Oxford Shirt", "price": 1999, "orig_price": 2799, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Button-Down Collar, Cotton", "rating": 4.6, "sold": "13k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1619603364944-ae0e79c23af7?w=400&h=400&fit=crop"},
    {"name": "Zara Linen Blend Shirt", "price": 2990, "orig_price": 3990, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Relaxed Resort Wear, Half Sleeve", "rating": 4.8, "sold": "6k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1604695573706-53170668f6a6?w=400&h=400&fit=crop"},
    {"name": "Raymond Striped Formal Shirt", "price": 1799, "orig_price": 2499, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Slim Fit, Wrinkle Resistant", "rating": 4.5, "sold": "16k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "H&M Poplin Shirt", "price": 1299, "orig_price": 1799, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "100% Cotton, Boxy Fit", "rating": 4.4, "sold": "28k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1603252109303-2751441dd157?w=400&h=400&fit=crop"},
    {"name": "Wrangler Twill Work Shirt", "price": 1899, "orig_price": 2599, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Heavy Twill, Dual Chest Pockets", "rating": 4.6, "sold": "8k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1596755389378-c31d21fd1273?w=400&h=400&fit=crop"},
    {"name": "Mufti Floral Printed Shirt", "price": 1599, "orig_price": 2199, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Cuban Collar, Short Sleeve", "rating": 4.5, "sold": "11k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1604695573706-53170668f6a6?w=400&h=400&fit=crop"},
    {"name": "BOSS Slim Fit Shirt", "price": 7499, "orig_price": 9999, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Italian Fabric, Micro-check Pattern", "rating": 4.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1619603364944-ae0e79c23af7?w=400&h=400&fit=crop"},

    # ── Jeans ─────────────────────────────────────────────────────────────────
    {"name": "Levi's 511 Slim Jeans", "price": 3499, "orig_price": 4999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Fit, Stretch Denim", "rating": 4.8, "sold": "24k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1541099649105-f69ad21f3246?w=400&h=400&fit=crop"},
    {"name": "Pepe Jeans Vapour Skinny", "price": 2799, "orig_price": 3799, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Super Stretch, Mid Rise", "rating": 4.6, "sold": "18k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=400&h=400&fit=crop"},
    {"name": "Wrangler Regular Fit Jeans", "price": 1999, "orig_price": 2799, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Classic 5-Pocket, Dark Wash", "rating": 4.5, "sold": "30k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1555689502-c4b22d76c56f?w=400&h=400&fit=crop"},
    {"name": "Flying Machine Skinny Jeans", "price": 2299, "orig_price": 2999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "High Stretch, Ankle Length", "rating": 4.4, "sold": "22k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1582418702059-97ebafb35d09?w=400&h=400&fit=crop"},
    {"name": "Killer Bootcut Jeans", "price": 1799, "orig_price": 2499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Bootcut Silhouette, Medium Wash", "rating": 4.3, "sold": "15k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1582418702059-97ebafb35d09?w=400&h=400&fit=crop"},
    {"name": "Lee Tapered Fit Jeans", "price": 3299, "orig_price": 4499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Comfort Waist, Stretch Denim", "rating": 4.7, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1604176354204-9268737828e4?w=400&h=400&fit=crop"},
    {"name": "H&M Straight Regular Jeans", "price": 1999, "orig_price": 2699, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "5-Pocket Design, Classic Blue", "rating": 4.5, "sold": "35k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1475178626620-a4d074967452?w=400&h=400&fit=crop"},
    {"name": "Zara Mom Fit High Waist Jeans", "price": 3490, "orig_price": 4490, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Vintage Wash, Relaxed Thigh", "rating": 4.8, "sold": "9k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1475178626620-a4d074967452?w=400&h=400&fit=crop"},
    {"name": "Spykar Ripped Slim Jeans", "price": 2199, "orig_price": 2999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Distressed Look, Stretch Fabric", "rating": 4.4, "sold": "17k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1601300349942-965be72a2dab?w=400&h=400&fit=crop"},
    {"name": "Diesel D-Strukt Slim Jeans", "price": 8999, "orig_price": 11999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Premium Denim, Authentic Wash", "rating": 4.9, "sold": "3k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=400&h=400&fit=crop"},
    {"name": "Urbano Fashion Jogger Jeans", "price": 1499, "orig_price": 2199, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Elastic Waist, Knit Denim", "rating": 4.3, "sold": "40k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1552902865-b72c031ac5ea?w=400&h=400&fit=crop"},

    # ── Shoes ─────────────────────────────────────────────────────────────────
    {"name": "Nike Air Force 1", "price": 7995, "orig_price": 9495, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Classic White Leather Sneakers", "rating": 4.9, "sold": "9k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop"},
    {"name": "Adidas Ultraboost 22", "price": 14999, "orig_price": 18999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Boost Midsole, Primeknit Upper", "rating": 4.8, "sold": "6k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608231387042-66d1773070a5?w=400&h=400&fit=crop"},
    {"name": "Puma Softride Running Shoes", "price": 3999, "orig_price": 5499, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "SoftFoam+ Insole, Breathable Mesh", "rating": 4.5, "sold": "25k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1495555961986-b0bfc8883e75?w=400&h=400&fit=crop"},
    {"name": "Bata Formal Leather Shoes", "price": 2799, "orig_price": 3799, "category": "Fashion", "subcategory": "Shoes", "emoji": "👞", "description": "Oxford Style, Genuine Leather", "rating": 4.6, "sold": "12k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1560343090-f0409e92791a?w=400&h=400&fit=crop"},
    {"name": "Red Tape Casual Sneakers", "price": 1999, "orig_price": 2799, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Lace-Up, EVA Sole", "rating": 4.4, "sold": "30k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?w=400&h=400&fit=crop"},
    {"name": "Skechers GOwalk Slip-Ons", "price": 4499, "orig_price": 5999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Memory Foam, Easy Slip-On", "rating": 4.7, "sold": "8k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop"},
    {"name": "Metro Chunky Platform Sandals", "price": 2199, "orig_price": 2999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👡", "description": "Block Heel, Ankle Strap", "rating": 4.5, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=400&h=400&fit=crop"},
    {"name": "New Balance 530 Retro", "price": 8999, "orig_price": 10999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Suede & Mesh Upper, Retro Styling", "rating": 4.8, "sold": "4k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1539185441755-769473a23570?w=400&h=400&fit=crop"},
    {"name": "Woodland Trekking Boots", "price": 5999, "orig_price": 7999, "category": "Fashion", "subcategory": "Shoes", "emoji": "🥾", "description": "Waterproof, High Ankle Support", "rating": 4.7, "sold": "7k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1520219306100-ec4afeeefe58?w=400&h=400&fit=crop"},
    {"name": "Converse Chuck Taylor All Star", "price": 4999, "orig_price": 5999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Canvas Upper, Vulcanised Sole", "rating": 4.8, "sold": "15k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1463100099107-aa0980c362e6?w=400&h=400&fit=crop"},
    {"name": "Reebok Nano X3 Training", "price": 9499, "orig_price": 12499, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Floatride Energy, Wide Toe Box", "rating": 4.7, "sold": "3k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1600185365483-26d7a4cc7519?w=400&h=400&fit=crop"},

    # ── Bags ──────────────────────────────────────────────────────────────────
    {"name": "Wildcraft Backpack 30L", "price": 2499, "orig_price": 3499, "category": "Accessories", "subcategory": "Bag", "emoji": "🎒", "description": "Laptop Sleeve, Waterproof", "rating": 4.6, "sold": "22k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1622560480605-d83c853bc5c3?w=400&h=400&fit=crop"},
    {"name": "Lavie Tote Bag", "price": 2199, "orig_price": 3199, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Faux Leather, Multi-pocket", "rating": 4.6, "sold": "9k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop"},
    {"name": "Caprese Sling Bag", "price": 2499, "orig_price": 3499, "category": "Accessories", "subcategory": "Bag", "emoji": "👛", "description": "Vegan Leather, Adjustable Strap", "rating": 4.6, "sold": "6k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1591561954557-26941169b49e?w=400&h=400&fit=crop"},
    {"name": "Hidesign Genuine Leather Bag", "price": 5999, "orig_price": 7999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Full Grain Leather, Laptop Slot", "rating": 4.8, "sold": "4k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop"},
    {"name": "American Tourister Backpack", "price": 3299, "orig_price": 4499, "category": "Accessories", "subcategory": "Bag", "emoji": "🎒", "description": "15.6\" Laptop Compartment, USB Port", "rating": 4.7, "sold": "18k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1548036328-c9fa89d128fa?w=400&h=400&fit=crop"},
    {"name": "Baggit Crossbody Bag", "price": 1799, "orig_price": 2499, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Vegan Leather, Zip Pockets", "rating": 4.5, "sold": "12k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1566150905458-1bf1fc113f0d?w=400&h=400&fit=crop"},
    {"name": "Fastrack Sling Bag", "price": 1299, "orig_price": 1899, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Casual Messenger, Water Resistant", "rating": 4.4, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1590874103328-eac38a683ce7?w=400&h=400&fit=crop"},
    {"name": "Samsonite Classic Duffle Bag", "price": 4999, "orig_price": 6999, "category": "Accessories", "subcategory": "Bag", "emoji": "🧳", "description": "Weekend Travel, Expandable", "rating": 4.7, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Puma Phase Backpack", "price": 1999, "orig_price": 2799, "category": "Accessories", "subcategory": "Bag", "emoji": "🎒", "description": "Graphic Print, Padded Straps", "rating": 4.5, "sold": "14k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop"},
    {"name": "Zara Quilted Chain Bag", "price": 3990, "orig_price": 4990, "category": "Accessories", "subcategory": "Bag", "emoji": "👛", "description": "Quilted Nappa, Gold Chain Strap", "rating": 4.8, "sold": "3k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1590874103328-eac38a683ce7?w=400&h=400&fit=crop"},
    {"name": "Tommy Hilfiger Monogram Bag", "price": 7999, "orig_price": 9999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Signature Logo, Structured Body", "rating": 4.9, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1590874103328-eac38a683ce7?w=400&h=400&fit=crop"},

    # ── Watches ───────────────────────────────────────────────────────────────
    {"name": "Fossil Gen 6 Smartwatch", "price": 22999, "orig_price": 27999, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Wear OS, Heart Rate, GPS", "rating": 4.7, "sold": "3k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1523475496153-3e46f5befa04?w=400&h=400&fit=crop"},
    {"name": "Titan Raga Rose Gold Watch", "price": 5995, "orig_price": 7495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Rose Gold, Women's Analog", "rating": 4.8, "sold": "8k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1534119428213-bd2626145164?w=400&h=400&fit=crop"},
    {"name": "Noise ColorFit Pro 4", "price": 3999, "orig_price": 5499, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "1.72\" AMOLED, 100+ Watch Faces", "rating": 4.5, "sold": "25k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1508685096489-7aacd43bd3b1?w=400&h=400&fit=crop"},
    {"name": "Casio G-Shock GA-2100", "price": 8495, "orig_price": 10495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Carbon Core Guard, 200m Water Resist", "rating": 4.9, "sold": "6k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1585386959984-a4155224a1ad?w=400&h=400&fit=crop"},
    {"name": "Timex Expedition Field Watch", "price": 3499, "orig_price": 4499, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Indiglo Night-Light, Leather Strap", "rating": 4.6, "sold": "11k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "boAt Xtend Smartwatch", "price": 2499, "orig_price": 3999, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "1.69\" HD Display, SpO2 Monitor", "rating": 4.4, "sold": "35k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1434494878577-86c23bcb06b9?w=400&h=400&fit=crop"},
    {"name": "Titan Edge Ultra Slim", "price": 4995, "orig_price": 6495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "World's Slimmest, Sapphire Crystal", "rating": 4.7, "sold": "7k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1587836374828-4dbafa94cf0e?w=400&h=400&fit=crop"},
    {"name": "Seiko Presage Cocktail Time", "price": 18999, "orig_price": 23999, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Automatic, Cocktail-Inspired Dial", "rating": 4.9, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1619134778706-7015533a6150?w=400&h=400&fit=crop"},
    {"name": "Apple Watch Series 9", "price": 41900, "orig_price": 44900, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "S9 Chip, Double Tap, Always-On", "rating": 4.9, "sold": "4k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy Watch 6", "price": 26999, "orig_price": 29999, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Advanced Sleep Tracking, ECG", "rating": 4.7, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Fastrack Reflex 3.0 Band", "price": 1999, "orig_price": 2999, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Activity Tracker, HR Monitor", "rating": 4.3, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1434494878577-86c23bcb06b9?w=400&h=400&fit=crop"},

    # ── Glasses ───────────────────────────────────────────────────────────────
    {"name": "Ray-Ban Aviator Classic", "price": 8990, "orig_price": 10990, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Gold Frame, G-15 Lens", "rating": 4.9, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Fastrack UV400 Wayfarers", "price": 1499, "orig_price": 1999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "100% UV Protection, Polycarbonate", "rating": 4.5, "sold": "40k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Oakley Holbrook Sunglasses", "price": 11999, "orig_price": 14999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Prizm Lens, O-Matter Frame", "rating": 4.9, "sold": "3k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Titan Eyeplus Rectangle Frames", "price": 1999, "orig_price": 2799, "category": "Accessories", "subcategory": "Glasses", "emoji": "👓", "description": "Full Rim, Anti-Glare Coating", "rating": 4.6, "sold": "15k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Lenskart John Jacobs Round Frames", "price": 2499, "orig_price": 3499, "category": "Accessories", "subcategory": "Glasses", "emoji": "👓", "description": "Acetate Frame, Blue Light Block", "rating": 4.7, "sold": "8k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Carrera Gradient Aviators", "price": 7490, "orig_price": 9490, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Gradient Tinted, Metal Frame", "rating": 4.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Polaroid Polarised Sports Shades", "price": 2999, "orig_price": 3999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Polarised, Wraparound Sport", "rating": 4.6, "sold": "9k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Vincent Chase Retro Cateye", "price": 1799, "orig_price": 2499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Acetate, Cat-Eye Silhouette", "rating": 4.5, "sold": "12k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Hugo Boss Rectangle Readers", "price": 9999, "orig_price": 12999, "category": "Accessories", "subcategory": "Glasses", "emoji": "👓", "description": "Spring Hinges, TR-90 Frame", "rating": 4.8, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Maui Jim Peahi Sport Sunglasses", "price": 14999, "orig_price": 18999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "PolarizedPlus2, Wraparound Shield", "rating": 4.9, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Peter Jones Blue Block Glasses", "price": 799, "orig_price": 1199, "category": "Accessories", "subcategory": "Glasses", "emoji": "👓", "description": "Digital Eye Strain Relief, Unisex", "rating": 4.3, "sold": "60k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy S24 Ultra", "price": 124999, "orig_price": 139999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "12GB RAM, 200MP Camera, Titanium Frame", "rating": 4.6, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1610945264803-c22b62d2a7b3?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy S24+", "price": 99999, "orig_price": 114999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "12GB RAM, 50MP Camera, S Pen", "rating": 4.1, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy S24 FE", "price": 64999, "orig_price": 74999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "8GB RAM, 50MP, Exynos 2400e", "rating": 4.6, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1610945264803-c22b62d2a7b3?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy A55 5G", "price": 38999, "orig_price": 44999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "8GB RAM, 50MP OIS, 120Hz AMOLED", "rating": 4.3, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy A35 5G", "price": 26999, "orig_price": 31999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "6GB RAM, 50MP, 120Hz Super AMOLED", "rating": 4.1, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy A25 5G", "price": 19999, "orig_price": 23999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "6GB RAM, 50MP, 5000mAh", "rating": 4.7, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy A15 5G", "price": 14999, "orig_price": 17999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "4GB RAM, 50MP, 90Hz", "rating": 4.3, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy M55 5G", "price": 29999, "orig_price": 34999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "8GB RAM, 50MP, 5000mAh", "rating": 3.8, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy M35 5G", "price": 22999, "orig_price": 26999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "6GB RAM, 50MP, 6000mAh", "rating": 4.2, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1610945264803-c22b62d2a7b3?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy F55 5G", "price": 27999, "orig_price": 32999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "8GB RAM, 64MP, 5000mAh", "rating": 4.7, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy Z Fold 6", "price": 164999, "orig_price": 189999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "12GB RAM, Foldable, Snapdragon 8 Gen 3", "rating": 3.9, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1678685888221-cebbd00e3559?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy Z Flip 6", "price": 109999, "orig_price": 124999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "12GB RAM, Compact Flip, 50MP", "rating": 4.8, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1678685843474-748ab2618beb?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone 16 Pro Max", "price": 189999, "orig_price": 209999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A18 Pro, 48MP ProRAW, Titanium", "rating": 5.0, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1726616764146-8be9ca5c4d3e?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone 16 Pro", "price": 154999, "orig_price": 174999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A18 Pro, 48MP, Action Button", "rating": 4.2, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1726616764146-8be9ca5c4d3e?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone 16 Plus", "price": 124999, "orig_price": 139999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A18, 48MP, 6.7\" OLED", "rating": 4.6, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1695048133142-1a20484bce71?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone 16", "price": 99999, "orig_price": 114999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A18 Chip, 48MP, Dynamic Island", "rating": 4.7, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1695048133142-1a20484bce71?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone 15 Pro Max", "price": 159999, "orig_price": 179999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A17 Pro, Titanium, USB-C", "rating": 4.8, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1696446702183-de4deca5b2e8?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone 15 Pro", "price": 134999, "orig_price": 154999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A17 Pro, 48MP, ProRes Video", "rating": 4.6, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1696446702183-de4deca5b2e8?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone 15 Plus", "price": 104999, "orig_price": 119999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A16, 48MP, 6.7\" Super Retina", "rating": 4.2, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1695048133142-1a20484bce71?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone 14", "price": 69999, "orig_price": 79999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A15 Bionic, 12MP, Emergency SOS", "rating": 4.6, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1663499482523-1c0c1bae4ce1?w=400&h=400&fit=crop"},
    {"name": "Apple iPhone SE 3rd Gen", "price": 49999, "orig_price": 57999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "A15 Bionic, 12MP, Compact Design", "rating": 4.0, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1632661674596-df8be070a5c5?w=400&h=400&fit=crop"},
    {"name": "OnePlus 12R", "price": 42999, "orig_price": 49999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 8 Gen 2, 50MP, 100W Charging", "rating": 4.3, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=400&h=400&fit=crop"},
    {"name": "OnePlus 12", "price": 64999, "orig_price": 74999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 8 Gen 3, Hasselblad 50MP", "rating": 4.2, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "OnePlus Nord CE4", "price": 24999, "orig_price": 28999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 7s Gen 2, 50MP, 100W", "rating": 3.8, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574944985070-8f3ebc6b79d2?w=400&h=400&fit=crop"},
    {"name": "OnePlus Nord 4", "price": 29999, "orig_price": 34999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 7+ Gen 3, 50MP, Metal Unibody", "rating": 3.9, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "OnePlus Nord CE4 Lite", "price": 19999, "orig_price": 22999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 695, 50MP, 80W Charging", "rating": 4.4, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "OnePlus Open", "price": 139999, "orig_price": 159999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Foldable, Hasselblad, Snapdragon 8 Gen 2", "rating": 4.0, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1678685888221-cebbd00e3559?w=400&h=400&fit=crop"},
    {"name": "Realme GT 6", "price": 39999, "orig_price": 45999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 8s Gen 3, 50MP, 120W", "rating": 4.7, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574944985070-8f3ebc6b79d2?w=400&h=400&fit=crop"},
    {"name": "Realme 13 Pro+", "price": 29999, "orig_price": 33999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Sony LYT-600 50MP, 80W Charging", "rating": 4.3, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574944985070-8f3ebc6b79d2?w=400&h=400&fit=crop"},
    {"name": "Realme 13 Pro", "price": 25999, "orig_price": 29999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Sony LYT-600, 67W, 5000mAh", "rating": 4.0, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "Realme Narzo 70 Pro", "price": 19999, "orig_price": 22999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Dimensity 7050, 50MP, 45W", "rating": 3.9, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "Realme Narzo 70", "price": 14999, "orig_price": 17499, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Dimensity 6100+, 50MP, 33W", "rating": 4.0, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "Realme C65", "price": 10999, "orig_price": 12999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Helio G85, 50MP, 45W Charging", "rating": 4.3, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "Realme C55", "price": 12999, "orig_price": 14999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Helio G88, 64MP, 33W", "rating": 5.0, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "Redmi Note 13 Pro+", "price": 29999, "orig_price": 33999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "200MP, 120W HyperCharge, Dimensity 7200", "rating": 3.9, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "Redmi Note 13 Pro", "price": 25999, "orig_price": 29999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "200MP ISOCELL, 67W, 5100mAh", "rating": 4.7, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "Redmi Note 13", "price": 18999, "orig_price": 21999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "108MP, 33W, 5000mAh", "rating": 4.3, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1574944985070-8f3ebc6b79d2?w=400&h=400&fit=crop"},
    {"name": "Xiaomi 14 Ultra", "price": 99999, "orig_price": 114999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Leica Quad Camera, Snapdragon 8 Gen 3", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1610945264803-c22b62d2a7b3?w=400&h=400&fit=crop"},
    {"name": "Xiaomi 14", "price": 69999, "orig_price": 79999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Leica 50MP, Snapdragon 8 Gen 3, 90W", "rating": 4.7, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574944985070-8f3ebc6b79d2?w=400&h=400&fit=crop"},
    {"name": "Redmi 13C 5G", "price": 11999, "orig_price": 13999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Dimensity 6100+, 50MP, 5000mAh", "rating": 4.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "Poco X6 Pro", "price": 26999, "orig_price": 30999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Dimensity 8300-Ultra, 64MP, 67W", "rating": 4.4, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "Poco X6", "price": 21999, "orig_price": 24999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 7s Gen 2, 64MP, 67W", "rating": 4.7, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "Poco M6 Pro", "price": 13999, "orig_price": 15999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Helio G99-Ultra, 64MP, 67W", "rating": 4.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "Vivo V30 Pro", "price": 46999, "orig_price": 52999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Sony 50MP ZEISS, 80W FlashCharge", "rating": 4.4, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "Vivo V30e", "price": 29999, "orig_price": 33999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 6 Gen 1, 64MP, 80W", "rating": 4.9, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1574944985070-8f3ebc6b79d2?w=400&h=400&fit=crop"},
    {"name": "iQOO 12", "price": 52999, "orig_price": 59999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 8 Gen 3, 200MP, 120W", "rating": 4.1, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1610945264803-c22b62d2a7b3?w=400&h=400&fit=crop"},
    {"name": "iQOO Neo 9 Pro", "price": 36999, "orig_price": 41999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 8 Gen 2, 50MP, 120W", "rating": 4.4, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "iQOO Z9 5G", "price": 23999, "orig_price": 27999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Dimensity 7200, 50MP, 44W", "rating": 4.4, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "Google Pixel 8 Pro", "price": 106999, "orig_price": 119999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Google Tensor G3, 50MP, 7yr Updates", "rating": 4.4, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1695048133142-1a20484bce71?w=400&h=400&fit=crop"},
    {"name": "Google Pixel 8a", "price": 59999, "orig_price": 67999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Tensor G3, 64MP, IP67", "rating": 4.4, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "Nothing Phone (2a)", "price": 23999, "orig_price": 26999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Dimensity 7200 Pro, 50MP, Glyph", "rating": 4.9, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574944985070-8f3ebc6b79d2?w=400&h=400&fit=crop"},
    {"name": "Nothing Phone (2)", "price": 44999, "orig_price": 49999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 8+ Gen 1, Glyph Interface", "rating": 4.3, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "Motorola Edge 50 Pro", "price": 31999, "orig_price": 36999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 7 Gen 3, 50MP, 125W", "rating": 4.4, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1574944985070-8f3ebc6b79d2?w=400&h=400&fit=crop"},
    {"name": "Motorola G84 5G", "price": 17999, "orig_price": 20999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 695, 50MP, 5000mAh", "rating": 3.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1512499617640-c74ae3a79d37?w=400&h=400&fit=crop"},
    {"name": "Nokia G42 5G", "price": 15999, "orig_price": 18999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 480+, 50MP, Repairable", "rating": 4.1, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop"},
    {"name": "Asus ROG Phone 8 Pro", "price": 99999, "orig_price": 114999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Snapdragon 8 Gen 3, 6000mAh Gaming", "rating": 4.6, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1610945264803-c22b62d2a7b3?w=400&h=400&fit=crop"},
    {"name": "OPPO Reno 12 Pro", "price": 36999, "orig_price": 41999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Dimensity 7300, 50MP AI Portrait", "rating": 4.9, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop"},
    {"name": "OPPO Find X7 Ultra", "price": 89999, "orig_price": 99999, "category": "Electronics", "subcategory": "Smartphones", "emoji": "📱", "description": "Hasselblad 1\" Camera, Dimensity 9300", "rating": 4.1, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1610945264803-c22b62d2a7b3?w=400&h=400&fit=crop"},
    {"name": "Dell XPS 15 OLED", "price": 189999, "orig_price": 214999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i9-13900H, 32GB, 1TB, 4K OLED", "rating": 4.0, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=400&h=400&fit=crop"},
    {"name": "Dell XPS 13 Plus", "price": 129999, "orig_price": 149999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-1360P, 16GB, 512GB, FHD+", "rating": 4.4, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=400&h=400&fit=crop"},
    {"name": "Dell Inspiron 15 3520", "price": 52999, "orig_price": 61999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i5-1235U, 8GB, 512GB SSD", "rating": 3.9, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=400&h=400&fit=crop"},
    {"name": "Dell Inspiron 14 5430", "price": 72999, "orig_price": 83999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i5-1340P, 16GB, 512GB, 2.5K", "rating": 4.3, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=400&h=400&fit=crop"},
    {"name": "Dell Latitude 5540", "price": 89999, "orig_price": 104999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-1355U, 16GB, 512GB, Business", "rating": 5.0, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1515378960530-7c0da6231fb1?w=400&h=400&fit=crop"},
    {"name": "Dell Vostro 3520", "price": 45999, "orig_price": 52999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i3-1215U, 8GB, 256GB, Business", "rating": 4.7, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1423666639041-f56000c27a9a?w=400&h=400&fit=crop"},
    {"name": "Dell G15 Gaming", "price": 74999, "orig_price": 86999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-12700H, RTX 3050, 16GB", "rating": 4.0, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1588872657578-7efd1f1555ed?w=400&h=400&fit=crop"},
    {"name": "HP Pavilion 15", "price": 58999, "orig_price": 67999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i5-1335U, 8GB, 512GB, FHD IPS", "rating": 4.0, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=400&h=400&fit=crop"},
    {"name": "HP Envy x360 13", "price": 94999, "orig_price": 109999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 7 7730U, 16GB, 512GB, 2-in-1", "rating": 4.9, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1548611635-7f1d748f5665?w=400&h=400&fit=crop"},
    {"name": "HP Spectre x360 14", "price": 154999, "orig_price": 174999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-1355U, 16GB, 1TB, OLED 2-in-1", "rating": 4.8, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1587614382346-4ec70e388b28?w=400&h=400&fit=crop"},
    {"name": "HP Omen 16", "price": 99999, "orig_price": 114999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-12700H, RTX 3060, 16GB", "rating": 5.0, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop"},
    {"name": "HP EliteBook 840 G9", "price": 119999, "orig_price": 134999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-1255U, 16GB, 512GB, Business", "rating": 4.9, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1515378960530-7c0da6231fb1?w=400&h=400&fit=crop"},
    {"name": "HP Victus 15", "price": 64999, "orig_price": 74999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 5 7535HS, RTX 2050, 8GB", "rating": 4.4, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1603302576837-37561b2e2302?w=400&h=400&fit=crop"},
    {"name": "Lenovo ThinkPad X1 Carbon", "price": 164999, "orig_price": 189999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-1365U, 16GB, 1TB, Ultra-light", "rating": 4.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1541807084-5c52b6b3adef?w=400&h=400&fit=crop"},
    {"name": "Lenovo IdeaPad Slim 5", "price": 58999, "orig_price": 67999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 5 7530U, 16GB, 512GB, 2.8K", "rating": 5.0, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop"},
    {"name": "Lenovo Legion 5", "price": 84999, "orig_price": 97999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 7 7745HX, RTX 4060, 16GB", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1588872657578-7efd1f1555ed?w=400&h=400&fit=crop"},
    {"name": "Lenovo Legion Pro 7", "price": 199999, "orig_price": 224999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 9 7945HX, RTX 4080, 32GB", "rating": 4.9, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop"},
    {"name": "Lenovo ThinkBook 14", "price": 74999, "orig_price": 86999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i5-1335U, 16GB, 512GB, IPS", "rating": 4.4, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop"},
    {"name": "Lenovo Yoga 9i", "price": 144999, "orig_price": 164999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-1360P, 16GB, 1TB, OLED 2-in-1", "rating": 5.0, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1548611635-7f1d748f5665?w=400&h=400&fit=crop"},
    {"name": "Lenovo IdeaPad Gaming 3", "price": 62999, "orig_price": 72999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 5 7535HS, RTX 3050, 8GB", "rating": 4.2, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1603302576837-37561b2e2302?w=400&h=400&fit=crop"},
    {"name": "Asus VivoBook 16X", "price": 72999, "orig_price": 83999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 5 7530U, 16GB, 512GB, WUXGA", "rating": 4.4, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=400&h=400&fit=crop"},
    {"name": "Asus ZenBook 14 OLED", "price": 89999, "orig_price": 104999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 7 7745U, 16GB, 512GB, 2.8K OLED", "rating": 5.0, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1611186871525-c5c5e4d1f7cf?w=400&h=400&fit=crop"},
    {"name": "Asus ROG Strix G16", "price": 139999, "orig_price": 159999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i9-13980HX, RTX 4070, 16GB", "rating": 3.9, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1588872657578-7efd1f1555ed?w=400&h=400&fit=crop"},
    {"name": "Asus TUF Gaming A15", "price": 74999, "orig_price": 86999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 7 7435HS, RTX 4060, 16GB", "rating": 4.1, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop"},
    {"name": "Asus ProArt Studiobook 16", "price": 219999, "orig_price": 249999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i9-13980HX, RTX 4070, 64GB", "rating": 4.5, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1593642634315-48f5414c3ad9?w=400&h=400&fit=crop"},
    {"name": "Acer Aspire 5", "price": 48999, "orig_price": 56999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i5-1235U, 8GB, 512GB, FHD IPS", "rating": 4.3, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1484788984921-03950022c9ef?w=400&h=400&fit=crop"},
    {"name": "Acer Predator Helios 16", "price": 144999, "orig_price": 164999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i9-13900HX, RTX 4080, 32GB", "rating": 4.1, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1603302576837-37561b2e2302?w=400&h=400&fit=crop"},
    {"name": "Acer Swift X 14", "price": 84999, "orig_price": 97999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 7 7840U, RTX 4050, 16GB", "rating": 4.3, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1553484771-371a605b060b?w=400&h=400&fit=crop"},
    {"name": "Acer Nitro V 15", "price": 64999, "orig_price": 74999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Ryzen 5 7535HS, RTX 4050, 8GB", "rating": 4.9, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1588872657578-7efd1f1555ed?w=400&h=400&fit=crop"},
    {"name": "Apple MacBook Air M3 13\"", "price": 114999, "orig_price": 129999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Apple M3, 8GB RAM, 256GB SSD", "rating": 4.5, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&h=400&fit=crop"},
    {"name": "Apple MacBook Air M3 15\"", "price": 134999, "orig_price": 154999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Apple M3, 8GB RAM, 512GB SSD", "rating": 4.1, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&h=400&fit=crop"},
    {"name": "Apple MacBook Pro M3 Pro 14\"", "price": 199999, "orig_price": 229999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Apple M3 Pro, 18GB, 512GB SSD", "rating": 4.2, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&h=400&fit=crop"},
    {"name": "Apple MacBook Pro M3 Max 16\"", "price": 349999, "orig_price": 399999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Apple M3 Max, 48GB, 1TB SSD", "rating": 4.2, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&h=400&fit=crop"},
    {"name": "Microsoft Surface Laptop 5", "price": 114999, "orig_price": 129999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i5-1235U, 8GB, 512GB, Touch", "rating": 4.5, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1614332287897-cdc485fa562d?w=400&h=400&fit=crop"},
    {"name": "MSI Stealth 16 Mercedes-AMG", "price": 254999, "orig_price": 289999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i9-13950HX, RTX 4080, 64GB", "rating": 5.0, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop"},
    {"name": "MSI Creator Z16 HX Studio", "price": 199999, "orig_price": 229999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-13700HX, RTX 4070, 32GB", "rating": 4.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1547394765-185e1e68f34e?w=400&h=400&fit=crop"},
    {"name": "Razer Blade 15", "price": 224999, "orig_price": 254999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-13800H, RTX 4070, 16GB, 240Hz", "rating": 3.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1603302576837-37561b2e2302?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy Book 4 Pro", "price": 149999, "orig_price": 169999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-155H, 16GB, 1TB, AMOLED 3K", "rating": 4.9, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1593642634443-44adaa06623a?w=400&h=400&fit=crop"},
    {"name": "Huawei MateBook X Pro", "price": 124999, "orig_price": 144999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-1360P, 16GB, 1TB, 3.1K Touch", "rating": 4.1, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1619388139339-73e57c5f7e46?w=400&h=400&fit=crop"},
    {"name": "LG Gram 16", "price": 119999, "orig_price": 134999, "category": "Electronics", "subcategory": "Laptops", "emoji": "💻", "description": "Intel i7-1360P, 16GB, 512GB, MIL-SPEC", "rating": 4.0, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620288627223-53302f4e8c74?w=400&h=400&fit=crop"},
    {"name": "Sony WH-1000XM5", "price": 29999, "orig_price": 34999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Industry-Best ANC, 30Hr Battery, LDAC", "rating": 4.1, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=400&h=400&fit=crop"},
    {"name": "Sony WH-1000XM4", "price": 24999, "orig_price": 29999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "ANC, 30Hr, Multipoint Bluetooth", "rating": 4.3, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop"},
    {"name": "Sony WF-1000XM5", "price": 19999, "orig_price": 23999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "True Wireless ANC, 8Hr + 16Hr Case", "rating": 4.2, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1606220588913-b3aacb4d2f37?w=400&h=400&fit=crop"},
    {"name": "Sony WF-C700N", "price": 8999, "orig_price": 10999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "True Wireless ANC, IPX4, 10Hr", "rating": 4.1, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1590658268037-6bf12165a8df?w=400&h=400&fit=crop"},
    {"name": "Sony LinkBuds S", "price": 9999, "orig_price": 11999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Hybrid ANC, Open-Fit, 6Hr Battery", "rating": 4.3, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1572536147248-ac59a8abfa4b?w=400&h=400&fit=crop"},
    {"name": "Bose QuietComfort 45", "price": 32999, "orig_price": 37999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Adaptive ANC, 24Hr, foldable", "rating": 4.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1546435770-a3e426bf472b?w=400&h=400&fit=crop"},
    {"name": "Bose QuietComfort Ultra", "price": 39999, "orig_price": 44999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Immersive Audio, ANC, 24Hr", "rating": 4.8, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=400&h=400&fit=crop"},
    {"name": "Bose QuietComfort Earbuds II", "price": 23999, "orig_price": 27999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "CustomTune ANC, True Wireless, 6Hr", "rating": 4.0, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=400&h=400&fit=crop"},
    {"name": "Bose SoundLink Flex", "price": 11999, "orig_price": 13999, "category": "Electronics", "subcategory": "Audio", "emoji": "🔊", "description": "IP67 Waterproof, Portable Bluetooth", "rating": 4.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1589003077984-894e133dabab?w=400&h=400&fit=crop"},
    {"name": "Sennheiser Momentum 4", "price": 29999, "orig_price": 34999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "ANC, 60Hr Battery, Foldable", "rating": 4.1, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=400&h=400&fit=crop"},
    {"name": "Sennheiser Momentum True Wireless 3", "price": 19999, "orig_price": 23999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "ANC, 7Hr + 21Hr, IPX4", "rating": 4.2, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1608156639585-b3a032ef9689?w=400&h=400&fit=crop"},
    {"name": "Sennheiser HD 560S", "price": 9999, "orig_price": 11999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Open-Back, Audiophile, Neutral Sound", "rating": 4.3, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1599669454699-248893623440?w=400&h=400&fit=crop"},
    {"name": "JBL Tour One M2", "price": 19999, "orig_price": 22999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "ANC, 50Hr, Multipoint Bluetooth", "rating": 4.1, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1613040809024-b4ef7ba99bc3?w=400&h=400&fit=crop"},
    {"name": "JBL Club Pro+", "price": 9999, "orig_price": 11999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "True Wireless ANC, IPX4, 10Hr", "rating": 4.8, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1625245488600-7f1d7b3c5d89?w=400&h=400&fit=crop"},
    {"name": "JBL Flip 6", "price": 11999, "orig_price": 13999, "category": "Electronics", "subcategory": "Audio", "emoji": "🔊", "description": "IP67, PartyBoost, 12Hr, Portable", "rating": 4.7, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=400&h=400&fit=crop"},
    {"name": "JBL Charge 5", "price": 15999, "orig_price": 17999, "category": "Electronics", "subcategory": "Audio", "emoji": "🔊", "description": "IP67 Powerbank, 20Hr, PartyBoost", "rating": 4.3, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=400&h=400&fit=crop"},
    {"name": "JBL Xtreme 3", "price": 19999, "orig_price": 22999, "category": "Electronics", "subcategory": "Audio", "emoji": "🔊", "description": "IP67, 15Hr, USB-C Charging", "rating": 4.7, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=400&h=400&fit=crop"},
    {"name": "Apple AirPods Pro 2nd Gen", "price": 24999, "orig_price": 27999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "H2 Chip, ANC, MagSafe, 30Hr Case", "rating": 3.8, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1603351154351-5e2d0600bb77?w=400&h=400&fit=crop"},
    {"name": "Apple AirPods 3rd Gen", "price": 17999, "orig_price": 19999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Spatial Audio, IPX4, 30Hr Case", "rating": 4.8, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1585241936939-be4099591252?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy Buds 2 Pro", "price": 14999, "orig_price": 17499, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "ANC, Hi-Fi 24-bit, IPX7", "rating": 4.8, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1590658268037-6bf12165a8df?w=400&h=400&fit=crop"},
    {"name": "Samsung Galaxy Buds FE", "price": 5999, "orig_price": 7499, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "ANC, Comfortable Fit, 6Hr Battery", "rating": 4.6, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1572536147248-ac59a8abfa4b?w=400&h=400&fit=crop"},
    {"name": "boAt Rockerz 550", "price": 1799, "orig_price": 2999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "40Hr Battery, Super Extra Bass", "rating": 4.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1577174881658-0f30ed549adc?w=400&h=400&fit=crop"},
    {"name": "boAt Rockerz 450", "price": 1499, "orig_price": 2499, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "15Hr Battery, Voice Assistant", "rating": 4.4, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1484704849700-f032a568e944?w=400&h=400&fit=crop"},
    {"name": "boAt Airdopes 311 Pro", "price": 999, "orig_price": 1799, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "True Wireless, ENx ANC, 35Hr", "rating": 3.8, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1608156639585-b3a032ef9689?w=400&h=400&fit=crop"},
    {"name": "boAt Airdopes 141", "price": 1299, "orig_price": 1999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "42Hr Playtime, Beast Mode, IPX4", "rating": 5.0, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1560707303-4e980ce876ad?w=400&h=400&fit=crop"},
    {"name": "boAt Stone 1200F", "price": 2999, "orig_price": 4499, "category": "Electronics", "subcategory": "Audio", "emoji": "🔊", "description": "12W Stereo, IPX5, Dual Passive Radiator", "rating": 4.5, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=400&h=400&fit=crop"},
    {"name": "Noise Buds VS104", "price": 1499, "orig_price": 2499, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "46dB ANC, 40Hr, HyperSync", "rating": 4.2, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1649170938588-8019c1ae54a7?w=400&h=400&fit=crop"},
    {"name": "Noise Shots Xpro 5", "price": 2999, "orig_price": 3999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "ANC, 32Hr, in-ear Gaming Mode", "rating": 4.9, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1590658268037-6bf12165a8df?w=400&h=400&fit=crop"},
    {"name": "Oneplus Buds 3", "price": 5499, "orig_price": 6999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "49dB ANC, LHDC 5.0, 44Hr", "rating": 4.7, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1572536147248-ac59a8abfa4b?w=400&h=400&fit=crop"},
    {"name": "OnePlus Nord Buds 2r", "price": 2499, "orig_price": 3499, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "ANC, 38Hr, IP55 Weather Resistant", "rating": 4.8, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1608156639585-b3a032ef9689?w=400&h=400&fit=crop"},
    {"name": "Skullcandy Crusher ANC 2", "price": 14999, "orig_price": 16999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Sensory Bass, 60Hr, ANC", "rating": 3.9, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=400&h=400&fit=crop"},
    {"name": "Skullcandy Indy Fuel", "price": 4999, "orig_price": 5999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "True Wireless, IP55, 32Hr", "rating": 4.6, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1590658268037-6bf12165a8df?w=400&h=400&fit=crop"},
    {"name": "Marshall Emberton III", "price": 11999, "orig_price": 13999, "category": "Electronics", "subcategory": "Audio", "emoji": "🔊", "description": "IP67 Waterproof, 32Hr, Bluetooth 5.3", "rating": 4.2, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=400&h=400&fit=crop"},
    {"name": "Marshall Stanmore III", "price": 29999, "orig_price": 34999, "category": "Electronics", "subcategory": "Audio", "emoji": "🔊", "description": "WiFi+Bluetooth, Iconic Design, Stereo", "rating": 4.2, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1545454675-3531b543be5d?w=400&h=400&fit=crop"},
    {"name": "Jabra Elite 85h", "price": 19999, "orig_price": 22999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "ANC, 36Hr, SmartSound AI, Foldable", "rating": 4.0, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1598386651573-9232f46248b8?w=400&h=400&fit=crop"},
    {"name": "Jabra Evolve2 55", "price": 24999, "orig_price": 28999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Dual Hybrid ANC, Mono/Stereo, Link 380", "rating": 4.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1593376893114-1aed528d80cf?w=400&h=400&fit=crop"},
    {"name": "Audio-Technica ATH-M50x", "price": 9999, "orig_price": 11999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Studio Monitor, 45mm Drivers, Foldable", "rating": 4.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop"},
    {"name": "Audio-Technica ATH-M40x", "price": 6999, "orig_price": 8499, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Pro Studio, 40mm, Detachable Cable", "rating": 4.3, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1484704849700-f032a568e944?w=400&h=400&fit=crop"},
    {"name": "Anker Soundcore Q45", "price": 4999, "orig_price": 5999, "category": "Electronics", "subcategory": "Audio", "emoji": "🎧", "description": "Adaptive ANC, Hi-Res Audio, 50Hr", "rating": 4.3, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1606400082777-ef05f3c5cde2?w=400&h=400&fit=crop"},
    {"name": "Anker Soundcore Motion X600", "price": 7999, "orig_price": 9499, "category": "Electronics", "subcategory": "Audio", "emoji": "🔊", "description": "50W Spatial Audio, IPX7, 12Hr", "rating": 4.8, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=400&h=400&fit=crop"},
    {"name": "Canon EOS R50", "price": 74999, "orig_price": 84999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "24.2MP Mirrorless, 4K Video, Dual Pixel AF", "rating": 4.1, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=400&h=400&fit=crop"},
    {"name": "Canon EOS R7", "price": 99999, "orig_price": 114999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "32.5MP APS-C, 4K60, IBIS Mirrorless", "rating": 4.9, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=400&h=400&fit=crop"},
    {"name": "Canon EOS R6 Mark II", "price": 214999, "orig_price": 244999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "24.2MP Full-Frame, 4K60, IBIS", "rating": 4.1, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=400&h=400&fit=crop"},
    {"name": "Canon EOS R5", "price": 319999, "orig_price": 359999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "45MP Full-Frame, 8K RAW, IBIS", "rating": 3.9, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1499720565725-fa9798c5bb2f?w=400&h=400&fit=crop"},
    {"name": "Canon EOS 250D", "price": 49999, "orig_price": 57999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "24.1MP DSLR, 4K, Flip Screen, Beginner", "rating": 4.7, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1495121553079-4c61bcce1894?w=400&h=400&fit=crop"},
    {"name": "Canon EOS 90D", "price": 114999, "orig_price": 129999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "32.5MP DSLR, 4K, Dual Pixel CMOS AF", "rating": 4.6, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1495121553079-4c61bcce1894?w=400&h=400&fit=crop"},
    {"name": "Nikon Z50", "price": 74999, "orig_price": 84999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "20.9MP DX Mirrorless, 4K, Compact", "rating": 4.3, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1617526738882-1ea945ce3068?w=400&h=400&fit=crop"},
    {"name": "Nikon Z30", "price": 57999, "orig_price": 66999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "20.9MP Vlog Mirrorless, No Viewfinder", "rating": 4.6, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1552168324-d612d77725e3?w=400&h=400&fit=crop"},
    {"name": "Nikon Z5 II", "price": 119999, "orig_price": 134999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "24.5MP Full-Frame, 4K60, IBIS", "rating": 4.8, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=400&h=400&fit=crop"},
    {"name": "Nikon Z6 III", "price": 269999, "orig_price": 304999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "24.5MP, 6K Partial-Stacked, 20fps", "rating": 4.1, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=400&h=400&fit=crop"},
    {"name": "Nikon D3500", "price": 34999, "orig_price": 39999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "24.2MP DSLR, Beginner-Friendly, 1500-shot", "rating": 4.5, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1495121553079-4c61bcce1894?w=400&h=400&fit=crop"},
    {"name": "Sony Alpha ZV-E10", "price": 54999, "orig_price": 62999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "24.2MP APS-C, 4K, Detachable Mic", "rating": 4.8, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1516724562728-afc824a36e84?w=400&h=400&fit=crop"},
    {"name": "Sony Alpha 7C II", "price": 194999, "orig_price": 219999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "33MP Full-Frame, 4K60, IBIS", "rating": 4.5, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1516724562728-afc824a36e84?w=400&h=400&fit=crop"},
    {"name": "Sony Alpha 7 IV", "price": 249999, "orig_price": 284999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "33MP, 4K60, 759-point AF", "rating": 4.7, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1516724562728-afc824a36e84?w=400&h=400&fit=crop"},
    {"name": "Sony Alpha 6700", "price": 124999, "orig_price": 139999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "26MP APS-C, 4K120, AI Subject Recog", "rating": 4.9, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1516724562728-afc824a36e84?w=400&h=400&fit=crop"},
    {"name": "Fujifilm X-T30 II", "price": 74999, "orig_price": 84999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "26.1MP X-Trans, 4K, Film Simulations", "rating": 4.7, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1512790182412-b19e6d62bc39?w=400&h=400&fit=crop"},
    {"name": "Fujifilm X-S20", "price": 104999, "orig_price": 119999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "26.1MP, 6.2K, Vlog-Friendly, IBIS", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1499720565725-fa9798c5bb2f?w=400&h=400&fit=crop"},
    {"name": "Fujifilm X-H2S", "price": 244999, "orig_price": 274999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "26.1MP Stacked, 40fps, 6K Video", "rating": 4.4, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1510127034890-ba27508e9f1c?w=400&h=400&fit=crop"},
    {"name": "Fujifilm Instax Mini 12", "price": 8499, "orig_price": 9999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "Instant Film Camera, Selfie Mirror, Auto Exp", "rating": 3.9, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1610296669228-602fa827fc1f?w=400&h=400&fit=crop"},
    {"name": "Panasonic Lumix G100D", "price": 54999, "orig_price": 62999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "20.3MP, 4K, Directional Mic, Vlog", "rating": 4.2, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1510127034890-ba27508e9f1c?w=400&h=400&fit=crop"},
    {"name": "OM System OM-5", "price": 119999, "orig_price": 134999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "20.4MP, IP53, 5-Axis IBIS, Compact", "rating": 4.0, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1532298229144-0ec0c57515c7?w=400&h=400&fit=crop"},
    {"name": "GoPro Hero 12 Black", "price": 39999, "orig_price": 44999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "5.3K60, HyperSmooth 6.0, Waterproof", "rating": 4.6, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1551698618-1dfe5d97d256?w=400&h=400&fit=crop"},
    {"name": "GoPro Hero 11 Black", "price": 32999, "orig_price": 37999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "5.3K60, TimeWarp 3.0, 10m Waterproof", "rating": 4.2, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1504891308-2f3c048b3a89?w=400&h=400&fit=crop"},
    {"name": "DJI Osmo Pocket 3", "price": 36999, "orig_price": 41999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "1\" CMOS, 4K120, ActiveTrack 6.0", "rating": 4.0, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1579829366248-204fe8413f31?w=400&h=400&fit=crop"},
    {"name": "DJI Action 4", "price": 34999, "orig_price": 39999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "1/1.3\" Sensor, 4K120, 10m Waterproof", "rating": 4.7, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1504891308-2f3c048b3a89?w=400&h=400&fit=crop"},
    {"name": "Insta360 X4", "price": 44999, "orig_price": 49999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "8K 360°, AI Editing, 135min Battery", "rating": 4.7, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1452780212940-6f5c0d14d848?w=400&h=400&fit=crop"},
    {"name": "Nikon Coolpix P950", "price": 44999, "orig_price": 49999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "16MP, 83x Optical Zoom, 4K", "rating": 4.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1617526738882-1ea945ce3068?w=400&h=400&fit=crop"},
    {"name": "Canon PowerShot V10", "price": 27999, "orig_price": 31999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "13MP, 4K, Built-in Stand, Vlog Camera", "rating": 4.8, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1559819614-81fea9efd090?w=400&h=400&fit=crop"},
    {"name": "Kodak PixPro AZ528", "price": 17999, "orig_price": 20999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "20MP, 52x Optical Zoom, FHD Video", "rating": 4.7, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=400&h=400&fit=crop"},
    {"name": "Olympus TG-7", "price": 34999, "orig_price": 39999, "category": "Electronics", "subcategory": "Cameras", "emoji": "📷", "description": "12MP, Waterproof 15m, Macro Mode", "rating": 4.1, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=400&h=400&fit=crop"},
    {"name": "Samsung 55\" Neo QLED 4K QN85C", "price": 89999, "orig_price": 104999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "Neo QLED, Dolby Atmos, Object Tracking", "rating": 4.2, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1586495777744-4e6b0ed34083?w=400&h=400&fit=crop"},
    {"name": "Samsung 65\" OLED S95C", "price": 219999, "orig_price": 249999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "QD-OLED, 144Hz, 4K, Anti-Glare", "rating": 4.8, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Samsung 43\" Crystal 4K AU8000", "price": 42999, "orig_price": 48999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "PurColor, Motion Xcelerator, Tizen OS", "rating": 4.4, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Samsung 75\" Neo QLED 4K QN90C", "price": 189999, "orig_price": 214999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K Neo QLED, 120Hz, AMD FreeSync", "rating": 4.6, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1461151304267-38535e596517?w=400&h=400&fit=crop"},
    {"name": "Samsung 32\" Full HD T4400", "price": 17999, "orig_price": 20999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "Full HD, PurColor, Tizen Smart TV", "rating": 4.0, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1586495777744-4e6b0ed34083?w=400&h=400&fit=crop"},
    {"name": "LG 55\" OLED evo C3", "price": 139999, "orig_price": 159999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "OLED evo, α9 AI Gen6, Dolby Vision IQ", "rating": 4.1, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "LG 65\" OLED C3", "price": 179999, "orig_price": 204999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "OLED, ThinQ AI, HDMI 2.1, G-Sync", "rating": 4.2, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "LG 48\" OLED evo B3", "price": 94999, "orig_price": 109999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "OLED evo, 120Hz, Game Optimizer", "rating": 4.9, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1461151304267-38535e596517?w=400&h=400&fit=crop"},
    {"name": "LG 75\" QNED 4K QNED80", "price": 124999, "orig_price": 144999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "QNED, 120Hz, Local Dimming, webOS", "rating": 3.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1586495777744-4e6b0ed34083?w=400&h=400&fit=crop"},
    {"name": "LG 43\" NanoCell 4K NANO75", "price": 42999, "orig_price": 48999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "NanoCell, Active HDR, ThinQ AI", "rating": 3.9, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Sony 55\" Bravia XR A80L OLED", "price": 169999, "orig_price": 194999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "XR OLED, Cognitive Processor XR, Atmos", "rating": 3.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Sony 65\" Bravia XR X95L", "price": 199999, "orig_price": 224999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "Mini LED, XR Backlight Master Drive", "rating": 4.9, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1461151304267-38535e596517?w=400&h=400&fit=crop"},
    {"name": "Sony 43\" Bravia X75L", "price": 49999, "orig_price": 57999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K HDR, X1 Processor, Google TV", "rating": 4.5, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1586495777744-4e6b0ed34083?w=400&h=400&fit=crop"},
    {"name": "Mi 55\" 4K Ultra HD X Series", "price": 42999, "orig_price": 48999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "Dolby Vision IQ, Dolby Atmos, MEMC", "rating": 4.6, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Mi 65\" QLED 4K", "price": 62999, "orig_price": 72999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "Quantum Dot, 120Hz, Vivid Picture Engine", "rating": 4.1, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "OnePlus 55\" Q2 Pro QLED", "price": 52999, "orig_price": 59999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "QLED, Gamma Engine, 120Hz, OnePlus Connect", "rating": 4.5, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1461151304267-38535e596517?w=400&h=400&fit=crop"},
    {"name": "TCL 55\" C835 Mini LED", "price": 64999, "orig_price": 74999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "Mini LED QLED, 144Hz, Dolby Vision", "rating": 4.0, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1586495777744-4e6b0ed34083?w=400&h=400&fit=crop"},
    {"name": "TCL 43\" P635 4K", "price": 28999, "orig_price": 32999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K HDR, Dolby Audio, Google TV", "rating": 3.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Hisense 55\" U8K Mini LED", "price": 74999, "orig_price": 86999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "Mini LED, 144Hz, Dolby Vision IQ, ULED", "rating": 4.9, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Vu 55\" GloLED", "price": 34999, "orig_price": 39999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "Quantum Luminit, 120Hz, Dolby Vision", "rating": 4.7, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1461151304267-38535e596517?w=400&h=400&fit=crop"},
    {"name": "Vu 43\" The Cinema", "price": 27999, "orig_price": 31999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K, Dolby Vision, Dolby Atmos, Google TV", "rating": 4.8, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1586495777744-4e6b0ed34083?w=400&h=400&fit=crop"},
    {"name": "Panasonic 55\" TH-55MX800DX", "price": 47999, "orig_price": 54999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K HDR, 60Hz, Hollywood Colour", "rating": 4.7, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Philips 55\" PUS8808", "price": 58999, "orig_price": 66999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K Ambilight, P5 AI, Dolby Vision", "rating": 4.5, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Toshiba 43\" C350LP", "price": 27999, "orig_price": 31999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K, REGZA Engine, Dolby Vision, Fire TV", "rating": 4.3, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1461151304267-38535e596517?w=400&h=400&fit=crop"},
    {"name": "Coocaa 32\" Full HD", "price": 11999, "orig_price": 13999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "Full HD, HDR, Dolby Audio, Smart TV", "rating": 4.6, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1586495777744-4e6b0ed34083?w=400&h=400&fit=crop"},
    {"name": "Acer 43\" AR43AR2851UDPRO", "price": 31999, "orig_price": 36999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K UHD, 60Hz, HDR 10, MEMC", "rating": 4.8, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Sharp 55\" 4T-C55EK2X", "price": 44999, "orig_price": 51999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K AQUOS, Dolby Atmos, Android TV", "rating": 4.2, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Thomson 55\" OATHPRO5500", "price": 34999, "orig_price": 39999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K, Dolby Vision, Dolby Atmos, QLED", "rating": 4.3, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1461151304267-38535e596517?w=400&h=400&fit=crop"},
    {"name": "Kodak 43\" 43UHDXSMART", "price": 26999, "orig_price": 30999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K UHD, Dolby Vision, Smart TV OS", "rating": 4.1, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1586495777744-4e6b0ed34083?w=400&h=400&fit=crop"},
    {"name": "iFFALCON 50\" K72", "price": 29999, "orig_price": 33999, "category": "Electronics", "subcategory": "TVs", "emoji": "📺", "description": "4K QLED, 144Hz, Google TV, MEMC", "rating": 4.4, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Logitech MX Master 3S", "price": 9999, "orig_price": 11499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖱️", "description": "8K DPI, Quiet Clicks, Ergonomic Wireless", "rating": 4.1, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "Logitech MX Keys Advanced", "price": 9999, "orig_price": 11499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "⌨️", "description": "Wireless, Backlit, Multi-Device", "rating": 4.3, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "Logitech G502 X Plus", "price": 12999, "orig_price": 14999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖱️", "description": "LIGHTFORCE, LIGHTSPEED, 25K DPI", "rating": 4.6, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "Logitech G Pro X TKL", "price": 9999, "orig_price": 11499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "⌨️", "description": "Tenkeyless, Swappable Switches, Pro-Grade", "rating": 4.8, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1563791877852-d636e0413ec0?w=400&h=400&fit=crop"},
    {"name": "Razer DeathAdder V3 HyperSpeed", "price": 7999, "orig_price": 9499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖱️", "description": "Focus Pro 30K Optical, Wireless", "rating": 4.2, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "Razer BlackWidow V4 Pro", "price": 17999, "orig_price": 20999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "⌨️", "description": "Yellow Switches, Chroma RGB, Wired", "rating": 4.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1587829741301-dc798b83add3?w=400&h=400&fit=crop"},
    {"name": "Razer Kraken V3 X", "price": 4999, "orig_price": 5999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🎧", "description": "7.1 Surround, HyperSense Haptics, USB", "rating": 4.4, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop"},
    {"name": "Corsair K100 RGB", "price": 19999, "orig_price": 22999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "⌨️", "description": "Optical Mech Switches, 44-Zone RGB", "rating": 4.7, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "Corsair Vengeance RGB Pro 16GB", "price": 5999, "orig_price": 6999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "💾", "description": "DDR4 3200MHz, Dynamic RGB Lighting", "rating": 4.1, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1563791877852-d636e0413ec0?w=400&h=400&fit=crop"},
    {"name": "Corsair MP600 Pro XT 1TB", "price": 9999, "orig_price": 11499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "💾", "description": "PCIe Gen4 NVMe, 7000MB/s Read", "rating": 4.4, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1563791877852-d636e0413ec0?w=400&h=400&fit=crop"},
    {"name": "HyperX Cloud Alpha", "price": 7999, "orig_price": 9499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🎧", "description": "Dual Chamber Drivers, Detachable Mic", "rating": 4.1, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop"},
    {"name": "HyperX Alloy Origins 65", "price": 8999, "orig_price": 10499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "⌨️", "description": "HyperX Linear Switches, 65% Compact", "rating": 4.5, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1563791877852-d636e0413ec0?w=400&h=400&fit=crop"},
    {"name": "SteelSeries Apex Pro TKL", "price": 14999, "orig_price": 17499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "⌨️", "description": "OmniPoint Adjustable, OLED Smart Display", "rating": 4.2, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1587829741301-dc798b83add3?w=400&h=400&fit=crop"},
    {"name": "SteelSeries Rival 600", "price": 6999, "orig_price": 8499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖱️", "description": "TrueMove3+, Dual Sensor, 12000 CPI", "rating": 4.6, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "Asus ROG Strix Impact III", "price": 3999, "orig_price": 4999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖱️", "description": "12000 DPI, Ambidextrous, Wired", "rating": 4.1, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "Asus ROG Claymore II", "price": 15999, "orig_price": 18499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "⌨️", "description": "ROG RX Red Switches, Detachable Numpad", "rating": 4.7, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "Samsung 980 Pro 1TB NVMe", "price": 8999, "orig_price": 10499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "💾", "description": "PCIe Gen4, 7000MB/s, PS5 Compatible", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1563791877852-d636e0413ec0?w=400&h=400&fit=crop"},
    {"name": "WD Black SN850X 1TB", "price": 8999, "orig_price": 10499, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "💾", "description": "PCIe Gen4, 7300MB/s, Gaming Optimized", "rating": 5.0, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1563791877852-d636e0413ec0?w=400&h=400&fit=crop"},
    {"name": "Seagate Barracuda 2TB HDD", "price": 4499, "orig_price": 5299, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "💾", "description": "7200RPM, 256MB Cache, Desktop", "rating": 5.0, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1563791877852-d636e0413ec0?w=400&h=400&fit=crop"},
    {"name": "Samsung 27\" Odyssey G5 QHD", "price": 24999, "orig_price": 28999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖥️", "description": "QHD 165Hz, 1ms, FreeSync Premium", "rating": 4.2, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=400&h=400&fit=crop"},
    {"name": "LG 27\" UltraGear QHD", "price": 22999, "orig_price": 26999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖥️", "description": "QHD 165Hz, 1ms, G-Sync Compatible", "rating": 4.4, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=400&h=400&fit=crop"},
    {"name": "Dell 27\" S2722DGM Gaming", "price": 27999, "orig_price": 31999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖥️", "description": "QHD 165Hz, 1ms, VA Panel", "rating": 3.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=400&h=400&fit=crop"},
    {"name": "BenQ PD2706Q Designer", "price": 32999, "orig_price": 37999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖥️", "description": "QHD 60Hz, sRGB 99%, USB-C 90W", "rating": 4.0, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1593784991095-a205069470b6?w=400&h=400&fit=crop"},
    {"name": "Logitech C920 HD Pro Webcam", "price": 6999, "orig_price": 7999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "📹", "description": "1080p30fps, Stereo Mic, Auto Focus", "rating": 3.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1563791877852-d636e0413ec0?w=400&h=400&fit=crop"},
    {"name": "Razer Kiyo Pro Ultra", "price": 14999, "orig_price": 16999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "📹", "description": "4K30fps, Sony STARVIS 2, Adaptive HDR", "rating": 4.3, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1587829741301-dc798b83add3?w=400&h=400&fit=crop"},
    {"name": "Sony PlayStation 5", "price": 54990, "orig_price": 59990, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🎮", "description": "825GB SSD, 4K Gaming, DualSense", "rating": 4.1, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1606144042614-b2417e99c4e3?w=400&h=400&fit=crop"},
    {"name": "Xbox Series X", "price": 51990, "orig_price": 57990, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🎮", "description": "1TB NVMe, 4K 120fps, Quick Resume", "rating": 3.9, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1605901309584-818e25960a8f?w=400&h=400&fit=crop"},
    {"name": "Nintendo Switch OLED", "price": 34999, "orig_price": 39999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🎮", "description": "7\" OLED, Tabletop, Dock included", "rating": 4.6, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1612036782180-6f0b6cd846fe?w=400&h=400&fit=crop"},
    {"name": "Ant Esports MK3400", "price": 3499, "orig_price": 3999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "⌨️", "description": "Mechanical, Blue Switches, RGB", "rating": 4.8, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1527864550417-7fd91fc51a46?w=400&h=400&fit=crop"},
    {"name": "Zebronics Zeb-Max Plus", "price": 1499, "orig_price": 1999, "category": "Electronics", "subcategory": "PC Accessories", "emoji": "🖱️", "description": "Wireless, 2400 DPI, 3yr Battery Life", "rating": 4.1, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1563791877852-d636e0413ec0?w=400&h=400&fit=crop"},
    {"name": "Nike Dri-FIT ADV TechKnit", "price": 3499, "orig_price": 3999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Moisture-Wicking, Ultralight Running", "rating": 4.5, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop"},
    {"name": "Nike Air Max Graphic Tee", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "100% Cotton, Crew Neck, Regular Fit", "rating": 4.3, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop"},
    {"name": "Nike Sportswear Club Tee", "price": 1499, "orig_price": 1799, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Heavyweight Cotton, Ribbed Collar", "rating": 4.5, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop"},
    {"name": "Nike Just Do It Swoosh Tee", "price": 999, "orig_price": 1499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Soft Cotton, Bold Graphic, Unisex", "rating": 4.5, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop"},
    {"name": "Adidas Essentials Single Jersey", "price": 1299, "orig_price": 1799, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Regular Fit, Cotton Blend, Basic", "rating": 4.0, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1556821840-3a63f15732ce?w=400&h=400&fit=crop"},
    {"name": "Adidas Trefoil T-Shirt", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "100% Cotton, Iconic Logo, Classic Fit", "rating": 3.9, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1556821840-3a63f15732ce?w=400&h=400&fit=crop"},
    {"name": "Adidas All Blacks Rugby Tee", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Replica Jersey, Recycled Polyester", "rating": 3.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1556821840-3a63f15732ce?w=400&h=400&fit=crop"},
    {"name": "Puma ESS Logo Tee", "price": 999, "orig_price": 1499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Cotton Blend, Regular Fit, Small Logo", "rating": 4.6, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1503341504253-dff4815485f1?w=400&h=400&fit=crop"},
    {"name": "Puma Active Small Logo Tee", "price": 1199, "orig_price": 1599, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Moisture-Wicking, Active Fit", "rating": 4.1, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1503341504253-dff4815485f1?w=400&h=400&fit=crop"},
    {"name": "Puma Blank Base Tee", "price": 1499, "orig_price": 1999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Lightweight, Flatlock Seams, Training", "rating": 4.3, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1503341504253-dff4815485f1?w=400&h=400&fit=crop"},
    {"name": "H&M Oversized Printed Tee", "price": 799, "orig_price": 999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Relaxed Fit, Cotton Jersey, Hip-Length", "rating": 4.7, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=400&h=400&fit=crop"},
    {"name": "H&M Slim Fit T-Shirt", "price": 599, "orig_price": 799, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Slim Fit, Stretch Cotton, V-Neck", "rating": 4.5, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop"},
    {"name": "H&M Divided Washed Tee", "price": 699, "orig_price": 899, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Washed Effect, Boxy Fit, 100% Cotton", "rating": 4.8, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=400&h=400&fit=crop"},
    {"name": "Zara Embroidered Logo Tee", "price": 1490, "orig_price": 1790, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Cotton, Embroidered Chest Logo", "rating": 4.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1523381294911-8d3cead13475?w=400&h=400&fit=crop"},
    {"name": "Zara Textured Linen Blend Tee", "price": 1990, "orig_price": 2490, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Linen Blend, Boxy, Summer-Ready", "rating": 4.4, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1523381294911-8d3cead13475?w=400&h=400&fit=crop"},
    {"name": "US Polo Assn Solid Polo", "price": 1299, "orig_price": 1799, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Cotton Pique, Classic Polo Collar", "rating": 4.9, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=400&h=400&fit=crop"},
    {"name": "US Polo Assn Striped Tee", "price": 1099, "orig_price": 1499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "100% Cotton, Breton Stripe", "rating": 4.3, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=400&h=400&fit=crop"},
    {"name": "Tommy Hilfiger Flag Logo Tee", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "100% Cotton, Chest Logo, Classic Fit", "rating": 4.7, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1529374255404-311a2a4f1fd9?w=400&h=400&fit=crop"},
    {"name": "Tommy Hilfiger Monotype Logo", "price": 2999, "orig_price": 3499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Organic Cotton, Heritage Stripe Collar", "rating": 4.1, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1529374255404-311a2a4f1fd9?w=400&h=400&fit=crop"},
    {"name": "Allen Solly Casual T-Shirt", "price": 999, "orig_price": 1499, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "100% Cotton, Slim Fit, Crew Neck", "rating": 4.6, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop"},
    {"name": "Allen Solly Printed Polo", "price": 1199, "orig_price": 1699, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Cotton Pique, Embroidered Chest", "rating": 4.7, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=400&h=400&fit=crop"},
    {"name": "Bewakoof Oversized Acid Wash", "price": 699, "orig_price": 999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Relaxed Fit, 100% Cotton, Unisex", "rating": 4.6, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=400&h=400&fit=crop"},
    {"name": "Bewakoof Typography Tee", "price": 499, "orig_price": 799, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Bold Print, Cotton, Regular Fit", "rating": 4.5, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=400&h=400&fit=crop"},
    {"name": "Bewakoof Anime Print Tee", "price": 599, "orig_price": 899, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Licensed Print, Pre-shrunk Cotton", "rating": 4.4, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=400&h=400&fit=crop"},
    {"name": "Roadster Solid Crew Neck Tee", "price": 499, "orig_price": 699, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Cotton Blend, Regular Fit, Daily Wear", "rating": 4.6, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1586790170083-2f9ceadc732d?w=400&h=400&fit=crop"},
    {"name": "Roadster Graphic Print Tee", "price": 599, "orig_price": 799, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Cotton, Relaxed Fit, Printed", "rating": 4.6, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1586790170083-2f9ceadc732d?w=400&h=400&fit=crop"},
    {"name": "Peter England Solid V-Neck Tee", "price": 799, "orig_price": 1099, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "100% Cotton, Slim Fit, V-Neck", "rating": 4.3, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop"},
    {"name": "Van Heusen Athleisure Tee", "price": 1199, "orig_price": 1699, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Moisture-Wicking, 4-Way Stretch", "rating": 3.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop"},
    {"name": "Reebok Identity Small Logo Tee", "price": 1299, "orig_price": 1699, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Cotton Blend, Classic Fit, Logo Chest", "rating": 5.0, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1556821840-3a63f15732ce?w=400&h=400&fit=crop"},
    {"name": "Reebok Training Speedwick Tee", "price": 1499, "orig_price": 1999, "category": "Fashion", "subcategory": "T-Shirt", "emoji": "👕", "description": "Speedwick Tech, 100% Polyester", "rating": 4.8, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1556821840-3a63f15732ce?w=400&h=400&fit=crop"},
    {"name": "Van Heusen Slim Fit Formal Shirt", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "100% Cotton, Non-Iron, Spread Collar", "rating": 4.5, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "Van Heusen Regular Fit Check", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Cotton Blend, Easy Care, Check Pattern", "rating": 4.4, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=400&h=400&fit=crop"},
    {"name": "Allen Solly Slim Fit Oxford", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Oxford Cotton, Button-Down Collar", "rating": 4.7, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=400&h=400&fit=crop"},
    {"name": "Allen Solly Casual Printed Shirt", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Viscose, All-Over Print, Regular Fit", "rating": 4.0, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1589310243389-96a5483213a8?w=400&h=400&fit=crop"},
    {"name": "Peter England Formal White Shirt", "price": 1499, "orig_price": 1899, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "100% Cotton, Wrinkle-Resistant", "rating": 4.6, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1607345366928-199ea26cfe3e?w=400&h=400&fit=crop"},
    {"name": "Peter England Check Casual", "price": 1299, "orig_price": 1699, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Cotton Blend, Check, Regular Fit", "rating": 4.6, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "Louis Philippe Slim Fit Dobby", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Dobby Weave, Slim Fit, Premium", "rating": 4.2, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1620799140408-edc6dcb6d633?w=400&h=400&fit=crop"},
    {"name": "Louis Philippe Bengal Stripe", "price": 2799, "orig_price": 3499, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Bengal Stripe, Slim Fit, 100% Cotton", "rating": 3.9, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "Arrow Regular Fit Formal", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "100% Cotton, Classic Collar, Non-Iron", "rating": 3.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1619603364944-ae0e79c23af7?w=400&h=400&fit=crop"},
    {"name": "Arrow Check Spread Collar", "price": 2199, "orig_price": 2699, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Yarn-Dyed Check, Regular Fit", "rating": 4.7, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "Park Avenue Smart Casual", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Cotton Linen, Regular Fit, Casual", "rating": 4.3, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1596755389378-c31d21fd1273?w=400&h=400&fit=crop"},
    {"name": "Raymond Formal Micro Stripe", "price": 2799, "orig_price": 3499, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "100% Cotton, Micro Stripe, Slim", "rating": 4.1, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "Wrangler Twill Work Shirt", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Cotton Twill, Western Yoke, Snap Button", "rating": 4.0, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1596755389378-c31d21fd1273?w=400&h=400&fit=crop"},
    {"name": "Levi's Barstow Western Shirt", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "100% Cotton, Snap Buttons, Classic", "rating": 4.0, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=400&h=400&fit=crop"},
    {"name": "Zara Linen Cuban Collar", "price": 2490, "orig_price": 2990, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Linen Blend, Cuban Collar, Relaxed", "rating": 4.7, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1604695573706-53170668f6a6?w=400&h=400&fit=crop"},
    {"name": "Zara All-Over Floral Print", "price": 1990, "orig_price": 2490, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Viscose, Regular Fit, Floral Print", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1604695573706-53170668f6a6?w=400&h=400&fit=crop"},
    {"name": "H&M Relaxed Linen Shirt", "price": 1499, "orig_price": 1799, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Linen Blend, Relaxed Fit, Classic", "rating": 4.1, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1603252109303-2751441dd157?w=400&h=400&fit=crop"},
    {"name": "H&M Patterned Regular Fit", "price": 999, "orig_price": 1299, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Cotton, Check Pattern, Regular Fit", "rating": 4.5, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=400&h=400&fit=crop"},
    {"name": "Mango Slim Fit Oxford Shirt", "price": 2490, "orig_price": 2990, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Oxford Cloth, Button-Down, Slim Fit", "rating": 4.3, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1607345366928-199ea26cfe3e?w=400&h=400&fit=crop"},
    {"name": "Mango Cuban Collar Linen", "price": 2990, "orig_price": 3490, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Linen, Cuban Collar, Loose Fit", "rating": 4.5, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1604695573706-53170668f6a6?w=400&h=400&fit=crop"},
    {"name": "Jack & Jones Casual Chambray", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Chambray Cotton, Regular Fit", "rating": 4.9, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=400&h=400&fit=crop"},
    {"name": "Jack & Jones Flannel Check", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Flannel Cotton, Relaxed Fit, Warm", "rating": 4.1, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "Celio Blue Oxford Shirt", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Oxford, Regular Fit, Button-Down", "rating": 4.7, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1620799140408-edc6dcb6d633?w=400&h=400&fit=crop"},
    {"name": "Marks & Spencer Poplin Shirt", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "100% Cotton Poplin, Regular Fit", "rating": 4.4, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1619603364944-ae0e79c23af7?w=400&h=400&fit=crop"},
    {"name": "Blackberrys Formal Slim Fit", "price": 2799, "orig_price": 3499, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Superfine Cotton, Slim, Anti-Wrinkle", "rating": 4.6, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1619603364944-ae0e79c23af7?w=400&h=400&fit=crop"},
    {"name": "ColorPlus Micro Check Formal", "price": 2599, "orig_price": 3199, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Micro Check, Regular Fit, Cotton", "rating": 3.8, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1619603364944-ae0e79c23af7?w=400&h=400&fit=crop"},
    {"name": "Monte Carlo Casual Linen", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Linen Blend, Regular Fit, Summer", "rating": 4.2, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1604695573706-53170668f6a6?w=400&h=400&fit=crop"},
    {"name": "Provogue Slim Fit Solid", "price": 1299, "orig_price": 1699, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "Cotton, Slim Fit, Spread Collar", "rating": 4.3, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "Gant Oxford Banker Stripe", "price": 4999, "orig_price": 5999, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "100% Cotton Oxford, Banker Stripe", "rating": 3.8, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1620799139507-2a76f79a2f4d?w=400&h=400&fit=crop"},
    {"name": "Tommy Hilfiger Oxford Slim", "price": 3999, "orig_price": 4799, "category": "Fashion", "subcategory": "Shirt", "emoji": "👔", "description": "100% Cotton, Classic Fit, Iconic Logo", "rating": 4.6, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=400&h=400&fit=crop"},
    {"name": "Levi's 511 Slim Fit Jeans", "price": 3999, "orig_price": 4999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Fit, Stretch Denim, Mid Rise", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1555689502-c4b22d76c56f?w=400&h=400&fit=crop"},
    {"name": "Levi's 512 Slim Taper Jeans", "price": 3999, "orig_price": 4999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Taper, Flex Denim, Versatile", "rating": 4.6, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1475178626620-a4d074967452?w=400&h=400&fit=crop"},
    {"name": "Levi's 501 Original Fit", "price": 4499, "orig_price": 5499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Straight Leg, Button Fly, Classic", "rating": 4.8, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1541099649105-f69ad21f3246?w=400&h=400&fit=crop"},
    {"name": "Levi's 519 Extreme Skinny", "price": 3499, "orig_price": 4499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Super Skinny, Stretch, Low Rise", "rating": 4.2, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1555689502-c4b22d76c56f?w=400&h=400&fit=crop"},
    {"name": "Wrangler Regular Fit Classic", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Regular Fit, Classic 5-Pocket, Durable", "rating": 3.8, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1475178626620-a4d074967452?w=400&h=400&fit=crop"},
    {"name": "Wrangler Slim Tapered Fit", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Taper, Stretch Denim, Versatile", "rating": 4.6, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1604176354204-9268737828e4?w=400&h=400&fit=crop"},
    {"name": "Pepe Jeans Vapor Skinny", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Skinny, Low Rise, Super Stretch", "rating": 4.7, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1604176354204-9268737828e4?w=400&h=400&fit=crop"},
    {"name": "Pepe Jeans Kingston Regular", "price": 2799, "orig_price": 3499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Regular Fit, Straight Leg, Classic", "rating": 4.7, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1582418702059-97ebafb35d09?w=400&h=400&fit=crop"},
    {"name": "Lee Slim Fit Bryson", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Skinny Fit, Stretch Denim, Tapered Leg", "rating": 4.6, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1542272604-787c3835535d?w=400&h=400&fit=crop"},
    {"name": "Lee Regular Fit Luke", "price": 2799, "orig_price": 3499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Regular Fit, Classic, Durable Denim", "rating": 4.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1541099649105-f69ad21f3246?w=400&h=400&fit=crop"},
    {"name": "Spykar Super Slim Low Rise", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Super Slim, Low Rise, Stretch", "rating": 4.3, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1555689502-c4b22d76c56f?w=400&h=400&fit=crop"},
    {"name": "Spykar Athletic Regular Fit", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Athletic Build, Mid Rise, Comfort", "rating": 4.5, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1475178626620-a4d074967452?w=400&h=400&fit=crop"},
    {"name": "Flying Machine Slim Fit Jeans", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Fit, Mid Rise, Stretch Denim", "rating": 3.9, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1542272604-787c3835535d?w=400&h=400&fit=crop"},
    {"name": "Flying Machine Skinny Fit", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Skinny, Low Rise, Ripped Knees", "rating": 4.1, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1604176354204-9268737828e4?w=400&h=400&fit=crop"},
    {"name": "Jack & Jones Glenn Slim Fit", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Fit, Organic Cotton, Sustainable", "rating": 4.6, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1542272604-787c3835535d?w=400&h=400&fit=crop"},
    {"name": "Jack & Jones Liam Skinny Fit", "price": 2199, "orig_price": 2699, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Skinny Jeans, Low Rise, Modern Cut", "rating": 3.8, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1541099649105-f69ad21f3246?w=400&h=400&fit=crop"},
    {"name": "H&M Slim Jeans 360° Flex", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "360° Stretch, Slim Fit, Everyday", "rating": 4.6, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1541099649105-f69ad21f3246?w=400&h=400&fit=crop"},
    {"name": "H&M Skinny Regular Jeans", "price": 1499, "orig_price": 1899, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Skinny, Mid Rise, Cotton Blend", "rating": 4.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1555689502-c4b22d76c56f?w=400&h=400&fit=crop"},
    {"name": "Zara Z1975 Slim Straight", "price": 2990, "orig_price": 3690, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Straight, High Rise, Raw Hem", "rating": 4.3, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1555689502-c4b22d76c56f?w=400&h=400&fit=crop"},
    {"name": "Zara Ripped Skinny Jeans", "price": 2490, "orig_price": 2990, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Skinny, High Rise, Ripped Details", "rating": 4.2, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1475178626620-a4d074967452?w=400&h=400&fit=crop"},
    {"name": "Urbano Fashion Super Slim", "price": 1499, "orig_price": 1999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Super Slim, Mid Rise, 4-Way Stretch", "rating": 3.9, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1475178626620-a4d074967452?w=400&h=400&fit=crop"},
    {"name": "Killer Slim Fit Dark Wash", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Fit, Dark Wash, Stretch Denim", "rating": 4.5, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1604176354204-9268737828e4?w=400&h=400&fit=crop"},
    {"name": "Numero Uno Classic Regular", "price": 1699, "orig_price": 2199, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Regular Fit, Mid Rise, Rigid Denim", "rating": 4.8, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1542272604-787c3835535d?w=400&h=400&fit=crop"},
    {"name": "Mufti Slim Jogger Jeans", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Jogger Style, Elasticated Waist, Slim", "rating": 4.5, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1604176354204-9268737828e4?w=400&h=400&fit=crop"},
    {"name": "Breakbounce Skinny Cropped", "price": 1499, "orig_price": 1899, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Skinny, Cropped Hem, Stretch", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1541099649105-f69ad21f3246?w=400&h=400&fit=crop"},
    {"name": "Lawman Pg3 Slim Fit", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Fit, Mid Rise, Tonal Stitch", "rating": 4.1, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1555689502-c4b22d76c56f?w=400&h=400&fit=crop"},
    {"name": "Calvin Klein Slim Fit Jeans", "price": 4999, "orig_price": 5999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Fit, Cotton Rich, Classic 5-Pocket", "rating": 4.0, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1582418702059-97ebafb35d09?w=400&h=400&fit=crop"},
    {"name": "Tommy Hilfiger Straight Fit", "price": 5999, "orig_price": 6999, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Straight Fit, Organic Cotton, Classic", "rating": 4.7, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1475178626620-a4d074967452?w=400&h=400&fit=crop"},
    {"name": "Armani Exchange Slim Fit", "price": 6999, "orig_price": 8499, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Fit, AX Branding, Stretch Denim", "rating": 4.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1604176354204-9268737828e4?w=400&h=400&fit=crop"},
    {"name": "Being Human Slim Fit Dark", "price": 1299, "orig_price": 1699, "category": "Fashion", "subcategory": "Jeans", "emoji": "👖", "description": "Slim Fit, Dark Wash, Salman Khan Brand", "rating": 4.3, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1542272604-787c3835535d?w=400&h=400&fit=crop"},
    {"name": "The North Face Resolve 2", "price": 10999, "orig_price": 12999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Waterproof, HyVent 2.5L, Packable", "rating": 3.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1563720223185-11003d516935?w=400&h=400&fit=crop"},
    {"name": "The North Face ThermoBall Eco", "price": 15999, "orig_price": 18999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "PrimaLoft Insulation, Packable, Warm", "rating": 4.3, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1576871337622-98d48d1cf531?w=400&h=400&fit=crop"},
    {"name": "The North Face Nuptse Puffer", "price": 18999, "orig_price": 21999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "700-fill Down, Iconic Box Quilting", "rating": 4.4, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Columbia Watertight II", "price": 7999, "orig_price": 9499, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Omni-Tech Waterproof, Packable Shell", "rating": 4.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1534277538-0ea2efce5fe5?w=400&h=400&fit=crop"},
    {"name": "Columbia Powder Lite Hybrid", "price": 9999, "orig_price": 11499, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Omni-Heat, Hybrid Insulated, Packable", "rating": 4.8, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1551028719-00167b16eac5?w=400&h=400&fit=crop"},
    {"name": "Wildcraft Rainwear Shell", "price": 3999, "orig_price": 4999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Waterproof 3000mm, Mesh Lining", "rating": 4.2, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1544923246-77307dd654cb?w=400&h=400&fit=crop"},
    {"name": "Wildcraft Alpha Puffer", "price": 5999, "orig_price": 6999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "600-fill Down Equivalent, Warm", "rating": 4.4, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1563720223185-11003d516935?w=400&h=400&fit=crop"},
    {"name": "Decathlon Quechua MH500", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Water-Repellent, DWR, Hiking", "rating": 5.0, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1576871337622-98d48d1cf531?w=400&h=400&fit=crop"},
    {"name": "Allen Solly Bomber Jacket", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Ribbed Cuffs, MA-1 Style, Polyester", "rating": 4.8, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Allen Solly Quilted Jacket", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Lightweight Quilted, Slip Pockets", "rating": 4.3, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1534277538-0ea2efce5fe5?w=400&h=400&fit=crop"},
    {"name": "Jack & Jones Puffer Jacket", "price": 3999, "orig_price": 4999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Water-Resistant, Chest Logo, Hood", "rating": 4.3, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1551028719-00167b16eac5?w=400&h=400&fit=crop"},
    {"name": "Jack & Jones Denim Trucker", "price": 3499, "orig_price": 4299, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "100% Cotton Denim, Classic Trucker", "rating": 4.8, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1544923246-77307dd654cb?w=400&h=400&fit=crop"},
    {"name": "Puma Padded Jacket", "price": 4999, "orig_price": 5999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Synthetic Fill, Wind-Resistant, DryCell", "rating": 4.1, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1563720223185-11003d516935?w=400&h=400&fit=crop"},
    {"name": "Nike Windrunner Jacket", "price": 7999, "orig_price": 9499, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Water-Repellent, Packable, Classic", "rating": 4.9, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1563720223185-11003d516935?w=400&h=400&fit=crop"},
    {"name": "Nike Therma-FIT Repel Jacket", "price": 8999, "orig_price": 10499, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Down Fill, Therma-FIT, Hooded", "rating": 4.1, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1576871337622-98d48d1cf531?w=400&h=400&fit=crop"},
    {"name": "Adidas Tiro 23 Track Jacket", "price": 3499, "orig_price": 4299, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Slim Fit, AEROREADY, Tricot Fabric", "rating": 4.4, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Adidas BSC Insulated Jacket", "price": 6999, "orig_price": 7999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Primegreen, Insulated, Weather-Ready", "rating": 3.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1534277538-0ea2efce5fe5?w=400&h=400&fit=crop"},
    {"name": "H&M Padded Jacket", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Lightweight Padding, Stand Collar", "rating": 4.2, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1551028719-00167b16eac5?w=400&h=400&fit=crop"},
    {"name": "H&M Regular Fit Denim Jacket", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "100% Cotton Denim, Chest Pockets", "rating": 4.1, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1544923246-77307dd654cb?w=400&h=400&fit=crop"},
    {"name": "Zara Faux Leather Biker", "price": 3990, "orig_price": 4790, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Faux Leather, Asymmetric Zip, Biker", "rating": 4.3, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1563720223185-11003d516935?w=400&h=400&fit=crop"},
    {"name": "Zara Water-Repellent Anorak", "price": 3490, "orig_price": 4190, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Water-Repellent, Kangaroo Pocket", "rating": 4.7, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1576871337622-98d48d1cf531?w=400&h=400&fit=crop"},
    {"name": "Mango Oversize Padded Jacket", "price": 4490, "orig_price": 5490, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Oversize Fit, Recycled Padding", "rating": 4.6, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Monte Carlo Wool Blend Jacket", "price": 3999, "orig_price": 4999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Wool Blend, Warm, Regular Fit", "rating": 4.9, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1534277538-0ea2efce5fe5?w=400&h=400&fit=crop"},
    {"name": "Pepe Jeans Sherpa Lined Jacket", "price": 3999, "orig_price": 4999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Denim with Sherpa Lining, Cozy", "rating": 4.2, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1542272604-787c3835535d?w=400&h=400&fit=crop"},
    {"name": "Roadster Hooded Puffer", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Lightweight Fill, Hooded, Zip Front", "rating": 4.1, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1551028719-00167b16eac5?w=400&h=400&fit=crop"},
    {"name": "Being Human Varsity Jacket", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Ribbed Trim, Snap Buttons, Varsity", "rating": 4.6, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1544923246-77307dd654cb?w=400&h=400&fit=crop"},
    {"name": "Campus Sutra Windbreaker", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Ripstop Nylon, Packable, Lightweight", "rating": 4.6, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1563720223185-11003d516935?w=400&h=400&fit=crop"},
    {"name": "Levi's Sherpa Trucker Jacket", "price": 6999, "orig_price": 7999, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Denim + Sherpa Lining, Warm Trucker", "rating": 4.0, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1576871337622-98d48d1cf531?w=400&h=400&fit=crop"},
    {"name": "Dennis Lingo Fleece Jacket", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Polar Fleece, Full-Zip, Anti-Pill", "rating": 4.8, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Reebok Running Jacket", "price": 3999, "orig_price": 4799, "category": "Fashion", "subcategory": "Jacket", "emoji": "🧥", "description": "Speedwick, Wind-Resistant, Running", "rating": 4.6, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1534277538-0ea2efce5fe5?w=400&h=400&fit=crop"},
    {"name": "Nike Air Max 270", "price": 12995, "orig_price": 14995, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Air Unit Heel, Mesh Upper, Lifestyle", "rating": 4.2, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1525966222134-fcfa99b8ae77?w=400&h=400&fit=crop"},
    {"name": "Nike Air Force 1 '07", "price": 7995, "orig_price": 8995, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Full-Grain Leather, Classic Cupsole", "rating": 4.0, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1539185441755-769473a23570?w=400&h=400&fit=crop"},
    {"name": "Nike Revolution 7", "price": 4495, "orig_price": 5295, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Foam Midsole, Mesh Upper, Daily Running", "rating": 4.1, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1434494878577-86c23bcb06b9?w=400&h=400&fit=crop"},
    {"name": "Nike Pegasus 41", "price": 9995, "orig_price": 11495, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "React Foam, Air Unit, Road Running", "rating": 4.0, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1560343090-f0409e92791a?w=400&h=400&fit=crop"},
    {"name": "Nike Metcon 9", "price": 11995, "orig_price": 13495, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Cross-Training, Stable Flat Heel", "rating": 5.0, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1600185365483-26d7a4cc7519?w=400&h=400&fit=crop"},
    {"name": "Nike Blazer Mid '77", "price": 7995, "orig_price": 8995, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Vintage Basketball, Leather, High-Top", "rating": 4.8, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop"},
    {"name": "Adidas Ultraboost Light", "price": 13999, "orig_price": 15999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "BOOST Midsole, Primeknit+, Running", "rating": 3.8, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1608231387042-66d1773070a5?w=400&h=400&fit=crop"},
    {"name": "Adidas NMD R1", "price": 8999, "orig_price": 9999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Boost Midsole, Sock-Like Fit, Casual", "rating": 4.7, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1608231387042-66d1773070a5?w=400&h=400&fit=crop"},
    {"name": "Adidas Forum Low", "price": 7499, "orig_price": 8499, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Leather Upper, Basketball-Inspired", "rating": 4.1, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1539185441755-769473a23570?w=400&h=400&fit=crop"},
    {"name": "Adidas Grand Court 2.0", "price": 3999, "orig_price": 4799, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Cloudfoam, Court Classic, Everyday", "rating": 4.4, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1606107557195-0e29a4b5b4aa?w=400&h=400&fit=crop"},
    {"name": "Puma Softride Premier", "price": 3999, "orig_price": 4799, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "SOFTRIDE Foam, Slip-On, Comfortable", "rating": 4.7, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1495555961986-b0bfc8883e75?w=400&h=400&fit=crop"},
    {"name": "Puma RS-X³ Puzzle", "price": 6999, "orig_price": 7999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "RS Running System, Chunky, Retro", "rating": 4.3, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop"},
    {"name": "Puma Provoke XT", "price": 4999, "orig_price": 5799, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Training, Piped Overlays, Stable", "rating": 3.9, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1600185365483-26d7a4cc7519?w=400&h=400&fit=crop"},
    {"name": "Reebok Classic Leather", "price": 5999, "orig_price": 6999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Leather Upper, Die-Cut EVA, Vintage", "rating": 4.6, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1525966222134-fcfa99b8ae77?w=400&h=400&fit=crop"},
    {"name": "Reebok Floatride Energy 5", "price": 6999, "orig_price": 7999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Floatride Energy Foam, Road Running", "rating": 4.4, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1600185365483-26d7a4cc7519?w=400&h=400&fit=crop"},
    {"name": "New Balance Fresh Foam X 1080", "price": 12999, "orig_price": 14999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Fresh Foam X, Hypoknit, Max Cushion", "rating": 3.9, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1539185441755-769473a23570?w=400&h=400&fit=crop"},
    {"name": "New Balance 574 Core", "price": 5999, "orig_price": 6999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "ENCAP, Suede/Mesh, Classic Lifestyle", "rating": 3.9, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1539185441755-769473a23570?w=400&h=400&fit=crop"},
    {"name": "Skechers Go Walk 7", "price": 4499, "orig_price": 5299, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "ULTRA GO, GOga Mat, Slip-On Walking", "rating": 4.1, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1539185441755-769473a23570?w=400&h=400&fit=crop"},
    {"name": "Skechers D'Lites 4", "price": 5999, "orig_price": 6999, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Air-Cooled Memory Foam, Chunky Dad Shoe", "rating": 4.3, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1560343090-f0409e92791a?w=400&h=400&fit=crop"},
    {"name": "Woodland Pro Trekking", "price": 4999, "orig_price": 5799, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Nubuck Leather, Rubber Sole, Waterproof", "rating": 4.4, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1520219306100-ec4afeeefe58?w=400&h=400&fit=crop"},
    {"name": "Woodland Casual Derby", "price": 3999, "orig_price": 4799, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Genuine Leather, Lace-Up, Everyday", "rating": 4.6, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1560343090-f0409e92791a?w=400&h=400&fit=crop"},
    {"name": "Red Tape Formal Oxford", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Genuine Leather, Oxford Style, Office", "rating": 4.1, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1560343090-f0409e92791a?w=400&h=400&fit=crop"},
    {"name": "Red Tape Casual Sneaker", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "PU Upper, Lightweight EVA, Casual", "rating": 4.3, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?w=400&h=400&fit=crop"},
    {"name": "Bata Power Walking Shoe", "price": 1499, "orig_price": 1799, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "EVA Midsole, Mesh Upper, Lightweight", "rating": 4.7, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1606107557195-0e29a4b5b4aa?w=400&h=400&fit=crop"},
    {"name": "Campus Santiago Running", "price": 999, "orig_price": 1299, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "EVA Sole, Mesh Upper, Breathable", "rating": 4.6, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1523275335684-37898b6baf30?w=400&h=400&fit=crop"},
    {"name": "HRX by Hrithik Roshan Trail", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Rubber Sole, Mesh Upper, Sport", "rating": 4.6, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1600185365483-26d7a4cc7519?w=400&h=400&fit=crop"},
    {"name": "FILA Disruptor II", "price": 4999, "orig_price": 5799, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Chunky Platform, Dad Shoe Aesthetic", "rating": 4.8, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop"},
    {"name": "Sparx Running Shoes", "price": 799, "orig_price": 1099, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Phylon Midsole, Mesh, Everyday Value", "rating": 4.7, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1495555961986-b0bfc8883e75?w=400&h=400&fit=crop"},
    {"name": "Liberty Force 10 Sport", "price": 1299, "orig_price": 1599, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "TPR Sole, Synthetic Upper, Sport", "rating": 4.5, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1525966222134-fcfa99b8ae77?w=400&h=400&fit=crop"},
    {"name": "Khadim's Duke Casual", "price": 899, "orig_price": 1199, "category": "Fashion", "subcategory": "Shoes", "emoji": "👟", "description": "Synthetic Upper, Cushioned Footbed", "rating": 4.6, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1560343090-f0409e92791a?w=400&h=400&fit=crop"},
    {"name": "Biba A-Line Kurta", "price": 1299, "orig_price": 1699, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Cotton, Block Print, Knee Length", "rating": 4.6, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop"},
    {"name": "Biba Anarkali Suit Set", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Cotton, Printed, Dupatta Included", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop"},
    {"name": "W Navy Solid Kurta", "price": 1299, "orig_price": 1699, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Poly Crepe, Straight, Office Wear", "rating": 4.2, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "W Printed A-Line Dress", "price": 1499, "orig_price": 1899, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Polyester, Floral Print, Knee Length", "rating": 4.6, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Fabindia Block Print Kurta", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "100% Cotton, Hand Block Print", "rating": 4.2, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Fabindia Cotton Anarkali", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Cotton Blend, Flared, Casual Wear", "rating": 4.7, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop"},
    {"name": "Global Desi Bohemian Kurta", "price": 1499, "orig_price": 1899, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Rayon, Embroidered Neck, Casual", "rating": 4.8, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop"},
    {"name": "Global Desi Palazzo Set", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Rayon, Printed Palazzo + Kurta", "rating": 4.9, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop"},
    {"name": "Aurelia Straight Kurta", "price": 1299, "orig_price": 1699, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Poly Crepe, Regular, Office Ready", "rating": 4.1, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop"},
    {"name": "Aurelia Flared Kurti", "price": 999, "orig_price": 1299, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Cotton Blend, Flared Hem, Printed", "rating": 4.2, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Libas Embroidered Sharara Set", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Rayon, Embroidery, Festive Wear", "rating": 4.5, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop"},
    {"name": "Libas Anarkali Gown", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Georgette, Anarkali, Party Ready", "rating": 4.7, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop"},
    {"name": "Sangria Wrap Maxi Dress", "price": 1799, "orig_price": 2199, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Chiffon, Wrap Style, Floral Print", "rating": 4.4, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Sangria Bodycon Mini Dress", "price": 1499, "orig_price": 1899, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Bandage Fabric, Bodycon, Club Wear", "rating": 4.2, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Anouk Straight Kurta", "price": 1199, "orig_price": 1499, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Cotton, Regular Fit, Ethnic Wear", "rating": 4.2, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Jaypore Handloom Saree", "price": 3499, "orig_price": 4199, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Handloom Cotton, Natural Dye, Festive", "rating": 4.0, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop"},
    {"name": "Craftsvilla Lehenga Choli", "price": 4999, "orig_price": 5999, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Georgette, Embroidery, Wedding Guest", "rating": 4.1, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop"},
    {"name": "Rangmanch Sharara Suit", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Rayon, Printed Sharara, Party Wear", "rating": 4.3, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Zara Floral Midi Dress", "price": 3490, "orig_price": 4190, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Satin-Effect, Floral, Midi Length", "rating": 4.4, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Zara Linen Blend Maxi", "price": 2990, "orig_price": 3690, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Linen Blend, Loose Fit, Summer", "rating": 4.1, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop"},
    {"name": "H&M Puff Sleeve Dress", "price": 1999, "orig_price": 2499, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Cotton Poplin, Puff Sleeve, Mini", "rating": 4.2, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop"},
    {"name": "H&M Wrap Dress", "price": 1499, "orig_price": 1899, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Jersey, Wrap Style, Knee Length", "rating": 4.5, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Mango Asymmetric Hem Dress", "price": 2990, "orig_price": 3690, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Crepe, Asymmetric Hem, Office Wear", "rating": 4.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Mango Floral Print Midi", "price": 3490, "orig_price": 4190, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Satin, Floral Print, Midi Length", "rating": 4.1, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop"},
    {"name": "AND Sheath Dress", "price": 2499, "orig_price": 2999, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Poly Crepe, Sheath, Corporate Wear", "rating": 4.7, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop"},
    {"name": "Label Life Flared Gown", "price": 3999, "orig_price": 4799, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Georgette, Flared, Evening Party", "rating": 4.4, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop"},
    {"name": "SCAKHI Striped Co-ord Set", "price": 2199, "orig_price": 2699, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Linen, Co-ord Set, Casual", "rating": 4.8, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Masaba Gupta Printed Kurta", "price": 3499, "orig_price": 4199, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Rayon, Signature Print, Mastani", "rating": 4.8, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515886657613-9f3515b0c78f?w=400&h=400&fit=crop"},
    {"name": "Nidhika Shekhar Embroidered Kurta", "price": 2999, "orig_price": 3699, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Georgette, Embroidered, Semi-Formal", "rating": 4.4, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Ritu Kumar Cotton Block Saree", "price": 5999, "orig_price": 7199, "category": "Fashion", "subcategory": "Dresses & Ethnic", "emoji": "👗", "description": "Cotton, Block Print, Festive", "rating": 4.5, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1610030469983-98e550d6193c?w=400&h=400&fit=crop"},
    {"name": "Titan Edge Quartz Slim", "price": 7995, "orig_price": 9495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Ultra-Slim 5.9mm, Sapphire Glass, Men", "rating": 4.3, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1587836374828-4dbafa94cf0e?w=400&h=400&fit=crop"},
    {"name": "Titan Raga Viva Women Watch", "price": 6995, "orig_price": 8295, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Rose Gold Dial, Mesh Strap, Women", "rating": 5.0, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1534119428213-bd2626145164?w=400&h=400&fit=crop"},
    {"name": "Titan Neo Smartwatch", "price": 3999, "orig_price": 4799, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "AMOLED, Heart Rate, SpO2, Calling", "rating": 4.5, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1508685096489-7aacd43bd3b1?w=400&h=400&fit=crop"},
    {"name": "Fastrack Stunner Chronograph", "price": 3495, "orig_price": 4195, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Chronograph, 3ATM, Silicon Band", "rating": 4.8, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Fastrack Reflex Ultra Smartwatch", "price": 5999, "orig_price": 7199, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "AMOLED, GPS, BT Calling, SpO2", "rating": 4.3, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Casio G-Shock GA-2100", "price": 9995, "orig_price": 11495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Carbon Core Guard, 200m WR, Multi-Function", "rating": 4.2, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1585386959984-a4155224a1ad?w=400&h=400&fit=crop"},
    {"name": "Casio G-Shock GW-M5610", "price": 14995, "orig_price": 17495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Solar, Atomic Timekeeping, 200m WR", "rating": 4.7, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1542496658-e33a6d0d028f?w=400&h=400&fit=crop"},
    {"name": "Casio Edifice EFR-556", "price": 7495, "orig_price": 8695, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Chronograph, 100m WR, Men\'s Sports", "rating": 3.9, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1542496658-e33a6d0d028f?w=400&h=400&fit=crop"},
    {"name": "Casio F-91W Classic", "price": 1295, "orig_price": 1695, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Resin Case, Digital, 7yr Battery", "rating": 4.7, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1542496658-e33a6d0d028f?w=400&h=400&fit=crop"},
    {"name": "Fossil Gen 6 Stella Smartwatch", "price": 22995, "orig_price": 26995, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Wear OS, SpO2, AMOLED, Hybrid", "rating": 4.8, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1523475496153-3e46f5befa04?w=400&h=400&fit=crop"},
    {"name": "Fossil Neutra Chronograph", "price": 12995, "orig_price": 15495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Chronograph, Leather Strap, Slim", "rating": 4.0, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1523475496153-3e46f5befa04?w=400&h=400&fit=crop"},
    {"name": "Fossil Machine Automatic", "price": 15995, "orig_price": 18995, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Automatic Movement, Exhibition Case", "rating": 4.0, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1523475496153-3e46f5befa04?w=400&h=400&fit=crop"},
    {"name": "Seiko 5 Sports Automatic", "price": 12995, "orig_price": 14995, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "24-Jewel Automatic, Day-Date, 100m WR", "rating": 4.7, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1619134778706-7015533a6150?w=400&h=400&fit=crop"},
    {"name": "Seiko Prospex SKX Sports", "price": 24995, "orig_price": 29495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Automatic, 200m Diver, Lumibrite", "rating": 4.5, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1619134778706-7015533a6150?w=400&h=400&fit=crop"},
    {"name": "Citizen Eco-Drive Classic", "price": 14995, "orig_price": 17995, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Light-Powered, Perpetual Calendar, Sapphire", "rating": 4.9, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Citizen Promaster Diver", "price": 24995, "orig_price": 29495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Eco-Drive, 200m Diver, ISO Certified", "rating": 4.6, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Timex Weekender 38mm", "price": 2995, "orig_price": 3595, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Indiglo Backlight, Leather Strap, Classic", "rating": 4.4, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Timex Expedition Scout", "price": 3995, "orig_price": 4795, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Indiglo, 50m WR, Nylon Strap, Field Watch", "rating": 4.5, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Daniel Wellington Classic 40", "price": 7995, "orig_price": 9495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Quartz, Mesh or Leather, Slim Minimalist", "rating": 4.2, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1587836374828-4dbafa94cf0e?w=400&h=400&fit=crop"},
    {"name": "Daniel Wellington Petite 32", "price": 6995, "orig_price": 8295, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Ladies\' Quartz, Rose Gold Case, Classic", "rating": 4.2, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1534119428213-bd2626145164?w=400&h=400&fit=crop"},
    {"name": "Sonata Superfibre Smart", "price": 5499, "orig_price": 6499, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "AMOLED, SpO2, BT Calling, Slim", "rating": 4.8, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1434494878577-86c23bcb06b9?w=400&h=400&fit=crop"},
    {"name": "Sonata Analog Men's Watch", "price": 1995, "orig_price": 2395, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Quartz, Day-Date, Water Resistant 30m", "rating": 4.4, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Guess Multi-Function Men's", "price": 9995, "orig_price": 11995, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Multi-Function, Stainless Steel, Men", "rating": 4.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Tommy Hilfiger TH1791836", "price": 11995, "orig_price": 13995, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Multi-Function, Mesh Strap, Men", "rating": 4.8, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1587836374828-4dbafa94cf0e?w=400&h=400&fit=crop"},
    {"name": "Michael Kors Parker MK6174", "price": 14995, "orig_price": 17995, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Chronograph, Rose Gold, Women", "rating": 4.4, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1534119428213-bd2626145164?w=400&h=400&fit=crop"},
    {"name": "Armani Exchange AX2101", "price": 9995, "orig_price": 11995, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Chronograph, Black Dial, Stainless", "rating": 4.3, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1587836374828-4dbafa94cf0e?w=400&h=400&fit=crop"},
    {"name": "MVMT Chrono Silver Black", "price": 7995, "orig_price": 9495, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "Minimalist Chronograph, Mesh Band", "rating": 3.9, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Noise ColorFit Ultra 3 Smartwatch", "price": 3499, "orig_price": 4199, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "AMOLED, BT Calling, 100+ Watch Faces", "rating": 4.6, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1523275335684-37898b6baf30?w=400&h=400&fit=crop"},
    {"name": "Fire-Boltt Phoenix Ultra", "price": 2999, "orig_price": 3699, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "AMOLED, 1.43\", BT Calling, SpO2", "rating": 4.5, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1508685096489-7aacd43bd3b1?w=400&h=400&fit=crop"},
    {"name": "boAt Lunar Connect Pro", "price": 3999, "orig_price": 4799, "category": "Accessories", "subcategory": "Watches", "emoji": "⌚", "description": "AMOLED, BT Calling, GPS, SpO2", "rating": 4.1, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1509048191080-d2984bad6ae5?w=400&h=400&fit=crop"},
    {"name": "Wildcraft Bolt 30L Backpack", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Water-Resistant, Laptop Sleeve, Padded", "rating": 4.6, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1622560480605-d83c853bc5c3?w=400&h=400&fit=crop"},
    {"name": "Wildcraft Trident 45L Trek", "price": 4999, "orig_price": 5999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Rain Cover, Contoured Back, Hiking", "rating": 4.6, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1622560480605-d83c853bc5c3?w=400&h=400&fit=crop"},
    {"name": "Skybags Footloose Colt Backpack", "price": 1999, "orig_price": 2499, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Polyester, Laptop Compartment, 30L", "rating": 4.5, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop"},
    {"name": "Skybags Hexa Plus Trolley 55cm", "price": 5999, "orig_price": 6999, "category": "Accessories", "subcategory": "Bag", "emoji": "🧳", "description": "Polycarbonate, TSA Lock, Spinner", "rating": 4.7, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591561954557-26941169b49e?w=400&h=400&fit=crop"},
    {"name": "American Tourister Starvibe 67cm", "price": 7499, "orig_price": 8999, "category": "Accessories", "subcategory": "Bag", "emoji": "🧳", "description": "Polypropylene, Spinner, Expandable", "rating": 4.5, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop"},
    {"name": "American Tourister Linex 80cm", "price": 9999, "orig_price": 11999, "category": "Accessories", "subcategory": "Bag", "emoji": "🧳", "description": "Polypropylene, 4-Spinner, TSA Lock", "rating": 4.2, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1591561954557-26941169b49e?w=400&h=400&fit=crop"},
    {"name": "Safari Thorium 65 Spinner", "price": 4999, "orig_price": 5999, "category": "Accessories", "subcategory": "Bag", "emoji": "🧳", "description": "Polycarbonate, Dual Combination Lock", "rating": 4.7, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1548036328-c9fa89d128fa?w=400&h=400&fit=crop"},
    {"name": "Samsonite Opto PC 69cm", "price": 11999, "orig_price": 13999, "category": "Accessories", "subcategory": "Bag", "emoji": "🧳", "description": "PC, 4-Spinner, TSA Lock, Lightweight", "rating": 4.3, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1566150905458-1bf1fc113f0d?w=400&h=400&fit=crop"},
    {"name": "Samsonite Base Boost 55cm", "price": 7499, "orig_price": 8999, "category": "Accessories", "subcategory": "Bag", "emoji": "🧳", "description": "Nylon, Carry-On, Expandable", "rating": 4.6, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop"},
    {"name": "Lavie Sumptuos Tote Bag", "price": 2999, "orig_price": 3699, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Faux Leather, Large Compartment, Women", "rating": 4.6, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1566150905458-1bf1fc113f0d?w=400&h=400&fit=crop"},
    {"name": "Lavie Flap Over Satchel", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Faux Leather, Structured, Work Bag", "rating": 4.2, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1590874103328-eac38a683ce7?w=400&h=400&fit=crop"},
    {"name": "Caprese Alyssa Shoulder Bag", "price": 3499, "orig_price": 4199, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Faux Leather, Multi-Compartment, Women", "rating": 4.2, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Baggit Urban Tote", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Vegan Leather, Zip Top, Everyday", "rating": 5.0, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop"},
    {"name": "Hidesign Leather Satchel", "price": 5999, "orig_price": 6999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Genuine Leather, Hand-stitched, Premium", "rating": 4.8, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1622560480605-d83c853bc5c3?w=400&h=400&fit=crop"},
    {"name": "Da Milano Croc Crossbody", "price": 6999, "orig_price": 7999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Croc Embossed, Adjustable Strap, Ladies", "rating": 4.4, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop"},
    {"name": "Fossil Gia Leather Crossbody", "price": 9999, "orig_price": 11999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Full-Grain Leather, Zip Closure, Women", "rating": 4.2, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591561954557-26941169b49e?w=400&h=400&fit=crop"},
    {"name": "Tommy Hilfiger Heritage Tote", "price": 12999, "orig_price": 14999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Pebble Leather, Signature Lining", "rating": 4.0, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1548036328-c9fa89d128fa?w=400&h=400&fit=crop"},
    {"name": "Puma Fundamentals Sports Bag", "price": 1499, "orig_price": 1799, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "25L, Durable Polyester, Gym", "rating": 4.7, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1622560480605-d83c853bc5c3?w=400&h=400&fit=crop"},
    {"name": "Adidas Linear Core Duffle", "price": 1799, "orig_price": 2199, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Polyester, Ventilated Shoe Pocket, 38L", "rating": 3.9, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1566150905458-1bf1fc113f0d?w=400&h=400&fit=crop"},
    {"name": "Nike Brasilia 9.5 Training Bag", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Durable Fabric, Shoe Compartment, 24L", "rating": 4.1, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop"},
    {"name": "Fastrack Dual Strap Backpack", "price": 1499, "orig_price": 1799, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Polyester, Padded Laptop, 20L", "rating": 4.7, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1590874103328-eac38a683ce7?w=400&h=400&fit=crop"},
    {"name": "F Gear Saviour Water-Resistant", "price": 1999, "orig_price": 2399, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "600D Polyester, Laptop Sleeve, 25L", "rating": 4.1, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591561954557-26941169b49e?w=400&h=400&fit=crop"},
    {"name": "Mokobara Aviator Duffle 50L", "price": 6999, "orig_price": 7999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Water-Resistant, Weekend Traveller", "rating": 4.0, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Uppercase Flapover Backpack", "price": 3999, "orig_price": 4799, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "15.6\" Laptop, Anti-Theft Pocket", "rating": 4.1, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop"},
    {"name": "Bellroy Transit Backpack 38L", "price": 14999, "orig_price": 16999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Recycled Fabric, Suspended Laptop", "rating": 4.3, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1622560480605-d83c853bc5c3?w=400&h=400&fit=crop"},
    {"name": "Harissons Casual Backpack 35L", "price": 1299, "orig_price": 1599, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Padded Back, Multiple Pockets", "rating": 4.8, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop"},
    {"name": "Mboss Unisex Daypack 20L", "price": 799, "orig_price": 999, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Polyester, Lightweight, College Bag", "rating": 3.9, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1566150905458-1bf1fc113f0d?w=400&h=400&fit=crop"},
    {"name": "Gear College Backpack", "price": 999, "orig_price": 1299, "category": "Accessories", "subcategory": "Bag", "emoji": "👜", "description": "Water-Resistant, Padded, 25L", "rating": 4.5, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591561954557-26941169b49e?w=400&h=400&fit=crop"},
    {"name": "VIP Skybag Trolley 78cm", "price": 7999, "orig_price": 9499, "category": "Accessories", "subcategory": "Bag", "emoji": "🧳", "description": "Polycarbonate, 4-Wheel, TSA Lock", "rating": 4.4, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1548036328-c9fa89d128fa?w=400&h=400&fit=crop"},
    {"name": "Kamiliant Harrana 68cm Spinner", "price": 4499, "orig_price": 5299, "category": "Accessories", "subcategory": "Bag", "emoji": "🧳", "description": "Polypropylene, Number Lock, Expandable", "rating": 4.7, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1566150905458-1bf1fc113f0d?w=400&h=400&fit=crop"},
    {"name": "Ray-Ban Wayfarer RB2140", "price": 7999, "orig_price": 9499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Acetate Frame, UV400, Classic Iconic", "rating": 4.4, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Ray-Ban Aviator Classic RB3025", "price": 8499, "orig_price": 9999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Metal Frame, Crystal Lens, Timeless", "rating": 4.9, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Ray-Ban Round Metal RB3447", "price": 7999, "orig_price": 9499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Metal Frame, Round Lens, Retro", "rating": 4.9, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Ray-Ban Clubmaster RB3016", "price": 9499, "orig_price": 10999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Browline, Half-Rim, UV400", "rating": 4.4, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Ray-Ban Erika RB4171", "price": 6999, "orig_price": 7999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Acetate, Matte Lens, Women\'s Favourite", "rating": 3.9, "sold": "1k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Oakley Holbrook OO9102", "price": 12999, "orig_price": 14999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "O-Matter Frame, Plutonite Lens, UV400", "rating": 4.9, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Oakley Sutro OO9406", "price": 11999, "orig_price": 13999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "High Coverage, Shield Lens, Sport", "rating": 4.0, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Oakley Split Shot OO9416", "price": 14999, "orig_price": 17499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Prizm Water Polarized, Fishing/Surf", "rating": 4.4, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Oakley Flak 2.0 XL OO9188", "price": 13999, "orig_price": 15999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Unobtanium, Prizm Lens, Sport", "rating": 4.4, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Maui Jim Peahi MJ202", "price": 16999, "orig_price": 19999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "PolarizedPlus2, Wrap Shield, Surf", "rating": 3.8, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Maui Jim Breakwall MJ422", "price": 12999, "orig_price": 14999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Polarized, Wood-Pattern Acetate", "rating": 4.5, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Carrera Hyperfit 10/S", "price": 7999, "orig_price": 9499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Rectangular, Semi-Rimless, Polarized", "rating": 4.7, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Carrera Victory C 01/S", "price": 6999, "orig_price": 7999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Injected Frame, Shield Lens, Sport", "rating": 3.9, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Hugo Boss BOSS 1500/S", "price": 9999, "orig_price": 11499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Titanium, Rectangular, Premium Men\'s", "rating": 4.5, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1474496168649-e8c7fd98e971?w=400&h=400&fit=crop"},
    {"name": "Polaroid 2089S/X Wayfarer", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Polarized, Acetate, Classic Shape", "rating": 4.9, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Polaroid PLD 6151/S Sport", "price": 3499, "orig_price": 3999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Sport Wrap, Polarized, Flexible", "rating": 4.4, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Fastrack Club Collection", "price": 1499, "orig_price": 1799, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Acetate, Rectangle, UV Protection", "rating": 4.1, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Fastrack UV400 Aviator", "price": 1299, "orig_price": 1599, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Metal Frame, Gradient Lens, UV400", "rating": 4.1, "sold": "10k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Vincent Chase VC S11388", "price": 1999, "orig_price": 2399, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Acetate, Round, Anti-Reflective", "rating": 4.6, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Vincent Chase VC S11023", "price": 1799, "orig_price": 2199, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Metal Frame, Rectangle, UV400", "rating": 3.9, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "Titan Glares Rectangle TW110", "price": 1999, "orig_price": 2499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "TR-90, Full-Rim, UV400 Protection", "rating": 4.7, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Lenskart LK E11849 Wayfarers", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Acetate, UV Protection, Classic", "rating": 4.3, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "John Jacobs JJ S13162 Round", "price": 2999, "orig_price": 3499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Acetate, Round Frame, Bold Style", "rating": 4.3, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Peter Jones Aviator Polarized", "price": 999, "orig_price": 1299, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Polarized Lens, Metal Frame, UV400", "rating": 3.8, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "Opium G-6 Geometric", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Handcrafted Acetate, Geometric Shape", "rating": 4.7, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "David Blake Browline Style", "price": 2999, "orig_price": 3499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Acetate + Metal, Browline, Timeless", "rating": 4.7, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Sunglass Hut HU 1009 Shield", "price": 7499, "orig_price": 8699, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Havana Acetate, Shield, Exclusive", "rating": 4.2, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "I DEW CARE Retro Round", "price": 1299, "orig_price": 1599, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Lightweight, Retro Round, UV400", "rating": 4.0, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1574158622682-e40e69881006?w=400&h=400&fit=crop"},
    {"name": "IDEE S2649F Cateye", "price": 2999, "orig_price": 3499, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Acetate, Cat-Eye, UV Protection", "rating": 4.4, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1511499767150-a48a237f0083?w=400&h=400&fit=crop"},
    {"name": "ENRICO COVERI ECS 111 Aviator", "price": 3499, "orig_price": 3999, "category": "Accessories", "subcategory": "Glasses", "emoji": "🕶️", "description": "Metal Frame, UV400, Classic Aviator", "rating": 3.9, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1473496169904-658ba7574b0d?w=400&h=400&fit=crop"},
    {"name": "Tanishq 18K Gold Diamond Ring", "price": 24999, "orig_price": 28999, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "18K Gold, 0.10ct Diamond, Solitaire", "rating": 4.0, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1535632066927-ab7c9ab60908?w=400&h=400&fit=crop"},
    {"name": "Tanishq 22K Gold Stud Earrings", "price": 12999, "orig_price": 14999, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "22K BIS Hallmarked Gold, Classic", "rating": 4.2, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1535632066927-ab7c9ab60908?w=400&h=400&fit=crop"},
    {"name": "CaratLane Diamond Pendant", "price": 8999, "orig_price": 10499, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "18K White Gold, 0.07ct Diamond", "rating": 5.0, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "CaratLane Stackable Ring Set", "price": 5999, "orig_price": 6999, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Sterling Silver, 3-Ring Set, CZ", "rating": 3.8, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515377905703-c4788e51af15?w=400&h=400&fit=crop"},
    {"name": "Malabar Gold Hoop Earrings", "price": 6999, "orig_price": 7999, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "22K Gold, Hoop Design, Women", "rating": 4.8, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "Giva 925 Silver Necklace", "price": 1999, "orig_price": 2499, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Sterling Silver, Chain + Pendant", "rating": 4.2, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1535632066927-ab7c9ab60908?w=400&h=400&fit=crop"},
    {"name": "Giva Sterling Silver Bracelet", "price": 1499, "orig_price": 1799, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "925 Silver, Expandable, Minimalist", "rating": 4.3, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "Shaya by CaratLane Silver Ring", "price": 999, "orig_price": 1299, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Sterling Silver, Stackable, Boho", "rating": 4.9, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "Melorra Gold-Plated Necklace", "price": 2999, "orig_price": 3499, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Gold-Plated Brass, Contemporary", "rating": 4.0, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515377905703-c4788e51af15?w=400&h=400&fit=crop"},
    {"name": "Melorra Silver-Toned Earrings", "price": 1499, "orig_price": 1799, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Rhodium-Plated, Drop Earrings", "rating": 4.8, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515377905703-c4788e51af15?w=400&h=400&fit=crop"},
    {"name": "Ornate Jewels CZ Jhumka Set", "price": 999, "orig_price": 1299, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Gold-Plated Brass, CZ, Jhumka Earrings", "rating": 4.7, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1535632066927-ab7c9ab60908?w=400&h=400&fit=crop"},
    {"name": "Ornate Jewels Kundan Choker", "price": 1799, "orig_price": 2199, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Kundan, Gold Plated, Wedding Wear", "rating": 5.0, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1535632066927-ab7c9ab60908?w=400&h=400&fit=crop"},
    {"name": "Accessorize Pearl Drop Earrings", "price": 799, "orig_price": 999, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Faux Pearl, Gold-Tone, Minimalist", "rating": 4.2, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "Accessorize Charm Bracelet", "price": 1199, "orig_price": 1499, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Enamel Charms, Gold-Tone, Stacker", "rating": 4.2, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "Johareez Jadau Necklace Set", "price": 3499, "orig_price": 4199, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Kundan-Jadau, Gold-Plated, Festive", "rating": 4.3, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "Pipa Bella Layered Necklace", "price": 1299, "orig_price": 1599, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Gold-Toned, Multi-Strand, Boho", "rating": 3.9, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515377905703-c4788e51af15?w=400&h=400&fit=crop"},
    {"name": "Silvermerc Oxidised Earrings", "price": 699, "orig_price": 899, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Oxidised Silver, Traditional Jhumka", "rating": 4.3, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1515377905703-c4788e51af15?w=400&h=400&fit=crop"},
    {"name": "Sukkhi Floral Earring Set", "price": 799, "orig_price": 999, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Gold Plated, Floral Design, Party", "rating": 4.6, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1535632066927-ab7c9ab60908?w=400&h=400&fit=crop"},
    {"name": "PC Jeweller Diamond Solitaire", "price": 18999, "orig_price": 22499, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "18K Gold, IJ SI Diamond, Certificate", "rating": 4.7, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1535632066927-ab7c9ab60908?w=400&h=400&fit=crop"},
    {"name": "Zaveri Pearls Mangalsutra", "price": 1499, "orig_price": 1799, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Gold-Plated, Black Beads, Traditional", "rating": 4.0, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "Voylla Boho Ring Set of 7", "price": 599, "orig_price": 799, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Silver-Toned, Midi Rings, Bohemian", "rating": 3.9, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1515377905703-c4788e51af15?w=400&h=400&fit=crop"},
    {"name": "Voylla Oxidised Silver Bangles", "price": 899, "orig_price": 1099, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Oxidised Silver, 2pc Bangle Set", "rating": 4.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "ORRA 14K Gold Diamond Pendant", "price": 14999, "orig_price": 17499, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "14K Gold, Diamond, Certified", "rating": 4.6, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1535632066927-ab7c9ab60908?w=400&h=400&fit=crop"},
    {"name": "Senco Gold 22K Bangle", "price": 8999, "orig_price": 10499, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "22K Gold, Traditional Bangle, BIS", "rating": 4.7, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "BlueStone Floral Diamond Ring", "price": 9999, "orig_price": 11499, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "14K White Gold, Floral Diamond Setting", "rating": 4.3, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "Craftsvilla Meenakari Earrings", "price": 399, "orig_price": 549, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Meenakari, Gold-Plated, Rajasthani", "rating": 3.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "Jaypore Silver Cuff Bracelet", "price": 1999, "orig_price": 2399, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Sterling Silver, Wide Cuff, Artisanal", "rating": 4.3, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1543294001-f7cd5d7fb516?w=400&h=400&fit=crop"},
    {"name": "SWAROVSKI Lifelong Heart Pendant", "price": 7499, "orig_price": 8749, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Rhodium-Plated, Crystal, Gift Box", "rating": 4.7, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1515377905703-c4788e51af15?w=400&h=400&fit=crop"},
    {"name": "FOSSIL Sadie Three-Hand Rose", "price": 8499, "orig_price": 9899, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Rose Gold Bracelet Watch-Style", "rating": 4.5, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1434494878577-86c23bcb06b9?w=400&h=400&fit=crop"},
    {"name": "Her Story By Smrithi Necklace", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Jewellery", "emoji": "💍", "description": "Gold-Tone, Layered, Handcrafted", "rating": 4.0, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1535632066927-ab7c9ab60908?w=400&h=400&fit=crop"},
    {"name": "Louis Philippe Genuine Leather Belt", "price": 1999, "orig_price": 2499, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Full-Grain Leather, Pin Buckle, 35mm", "rating": 4.9, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop"},
    {"name": "Van Heusen Reversible Belt", "price": 1499, "orig_price": 1799, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Black/Brown Reversible, Formal, 30mm", "rating": 4.8, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1622560480605-d83c853bc5c3?w=400&h=400&fit=crop"},
    {"name": "Allen Solly Woven Leather Belt", "price": 1299, "orig_price": 1599, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Woven Pattern, Leather, Casual", "rating": 4.7, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop"},
    {"name": "Arrow Formal Belt", "price": 1799, "orig_price": 2199, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Split Leather, Classic Buckle, Slim", "rating": 4.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591561954557-26941169b49e?w=400&h=400&fit=crop"},
    {"name": "Levis Webbing Belt", "price": 999, "orig_price": 1299, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Cotton Canvas, Ring Buckle, Casual", "rating": 4.9, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1566150905458-1bf1fc113f0d?w=400&h=400&fit=crop"},
    {"name": "Tommy Hilfiger Logo Belt", "price": 2999, "orig_price": 3499, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Leather, Logo Buckle, Classic", "rating": 4.4, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop"},
    {"name": "Calvin Klein Flat Strap Belt", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Leather, Monogram Plaque, Slim", "rating": 4.8, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1622560480605-d83c853bc5c3?w=400&h=400&fit=crop"},
    {"name": "Woodland Trek Belt", "price": 1299, "orig_price": 1599, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Genuine Leather, D-Ring Buckle, Outdoor", "rating": 3.8, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop"},
    {"name": "Hidesign Leather Braided Belt", "price": 1999, "orig_price": 2399, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Vegetable Tanned Leather, Braided", "rating": 4.4, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1591561954557-26941169b49e?w=400&h=400&fit=crop"},
    {"name": "Fossil Leather Belt", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Genuine Leather, Logo Buckle, Gift Box", "rating": 4.9, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1566150905458-1bf1fc113f0d?w=400&h=400&fit=crop"},
    {"name": "Pashmina House Pure Pashmina Shawl", "price": 8999, "orig_price": 10499, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "100% Pashmina, Hand Embroidered, Kashmir", "rating": 5.0, "sold": "20k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Shingora Wool Stole", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "70% Wool, 30% Viscose, Herringbone Weave", "rating": 4.7, "sold": "200+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Fabindia Cotton Printed Dupatta", "price": 999, "orig_price": 1299, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Block Print, Cotton, Ethnic Wear", "rating": 4.2, "sold": "200+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Fabindia Tussar Silk Scarf", "price": 1999, "orig_price": 2499, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Tussar Silk, Hand Painted, Artisan", "rating": 4.6, "sold": "5k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "H&M Jersey Infinity Scarf", "price": 699, "orig_price": 899, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Lightweight Jersey, Loop Style, Casual", "rating": 4.8, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "H&M Knit Winter Muffler", "price": 999, "orig_price": 1199, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Soft Acrylic, Ribbed Knit, Warm", "rating": 4.0, "sold": "500+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Mango Leopard Print Scarf", "price": 1490, "orig_price": 1790, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Modal Blend, Leopard Print, Accessory", "rating": 4.9, "sold": "100+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Zara Checked Wool Muffler", "price": 1990, "orig_price": 2490, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Wool Blend, Classic Check, Winter", "rating": 4.4, "sold": "2k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Weavers Villa Handloom Stole", "price": 1299, "orig_price": 1599, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Handloom Cotton, Block Print, Indie", "rating": 4.2, "sold": "1k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Vero Moda Solid Scarf", "price": 799, "orig_price": 999, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Viscose, Solid Colour, Versatile", "rating": 4.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1591047139829-d91aecb6caea?w=400&h=400&fit=crop"},
    {"name": "Da Milano Silk Pocket Square", "price": 1499, "orig_price": 1799, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Pure Silk, Pocket Square, Formal", "rating": 4.1, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1583744946564-b52ac1c389c8?w=400&h=400&fit=crop"},
    {"name": "Peter England Tie Combo", "price": 1299, "orig_price": 1699, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Polyester, 3-Tie Set, Office Wear", "rating": 4.6, "sold": "50k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=400&h=400&fit=crop"},
    {"name": "Raymond Silk Tie", "price": 1999, "orig_price": 2399, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "100% Silk, Classic Stripe, Formal", "rating": 4.6, "sold": "500+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=400&h=400&fit=crop"},
    {"name": "Louis Philippe Knitted Tie", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Knitted Wool, Slim, Textured", "rating": 4.5, "sold": "5k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=400&h=400&fit=crop"},
    {"name": "The Tie Hub Floral Bow Tie", "price": 999, "orig_price": 1299, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Self-Tie, Floral Print, Premium Poly", "rating": 4.5, "sold": "100+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=400&h=400&fit=crop"},
    {"name": "Adidas Striped Headband", "price": 499, "orig_price": 699, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Elastic, Sports, Moisture-Wicking", "rating": 4.9, "sold": "2k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=400&h=400&fit=crop"},
    {"name": "Nike Knitted Winter Beanie", "price": 799, "orig_price": 999, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Acrylic Knit, Logo, Warm", "rating": 4.7, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=400&h=400&fit=crop"},
    {"name": "Puma Sports Sweatband Set", "price": 399, "orig_price": 599, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Wrist + Head Band Set, Terry Cotton", "rating": 3.8, "sold": "50k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=400&h=400&fit=crop"},
    {"name": "Noise ANC Neck Pillow + Eye Mask", "price": 799, "orig_price": 999, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🧣", "description": "Memory Foam, Travel Set, Soft", "rating": 4.9, "sold": "20k+", "is_flash": True, "image_url": "https://images.unsplash.com/photo-photo-1523275335684-37898b6baf30?w=400&h=400&fit=crop"},
    {"name": "Bellroy Woven Leather Key Loop", "price": 2499, "orig_price": 2999, "category": "Accessories", "subcategory": "Belts & Scarves", "emoji": "🪡", "description": "Veg-Tanned Leather, Key Organiser", "rating": 4.8, "sold": "10k+", "is_flash": False, "image_url": "https://images.unsplash.com/photo-photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop"},
]

# ================= HELPERS =================
def make_card(p, show_progress=True):
    discount_tag = ""
    orig = ""
    if p.orig_price and p.orig_price > p.price:
        d = round((1 - p.price / p.orig_price) * 100)
        discount_tag = f"<div class='discount-tag'>-{d}%</div>"
        orig = f"<span class='price-orig'>&#8377;{p.orig_price:,}</span>"

    rating_int = int(p.rating)
    stars = "★" * rating_int + "☆" * (5 - rating_int)
    progress = ""
    if show_progress:
        fill = min(95, max(20, int(p.rating * 18)))
        progress = f"<div class='progress-bar'><div class='progress-fill' style='width:{fill}%'></div></div><div class='sold-info'>{fill}% sold · {p.sold} items</div>"

    return f"""
    <div class='pcard' data-category='{p.category}' data-id='{p.id}'>
      <a href='/product/{p.id}' style='text-decoration:none;color:inherit;display:block;'>
      <div class='pcard-img'>
        {discount_tag}
        {'<img class="pcard-real-img" src="' + p.image_url + '" alt="' + p.name + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\'">' if getattr(p, 'image_url', '') else ''}
        <span class='pcard-emoji' {'style="display:none"' if getattr(p, 'image_url', '') else ''}>{p.emoji}</span>
        <button class='wishlist-btn' onclick='toggleWish(this)'>&#9825;</button>
      </div>
      <div class='pcard-body'>
        <div class='pcard-cat'>{p.category}</div>
        <div class='pcard-name'>{p.name}</div>
        <div class='pcard-desc'>{p.description}</div>
        <div class='pcard-rating'>
          <span class='stars'>{stars}</span>
          <span class='rating-num'>{p.rating}</span>
          <span class='rating-sold'>· {p.sold} Sold</span>
        </div>
        <div class='pcard-price'>
          <span class='price-current'>&#8377;{p.price:,}</span>
          {orig}
        </div>
        {progress}
      </a>
        <button class='add-cart-btn' onclick='addToCart({p.id}, this)'>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>
          Add to Cart
        </button>
      </div>
    </div>"""

# ================= MAIN PAGE TEMPLATE =================
PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MyStore – Shop Beyond Boundaries</title>
<meta name="robots" content="noindex, nofollow">
<link href="https://fonts.googleapis.com/css2?family=Clash+Display:wght@400;500;600;700&family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<script>
/* Anti-flicker: apply saved theme BEFORE any CSS renders */
(function(){var t=localStorage.getItem('mystore_theme');if(t==='light')document.documentElement.classList.add('light-theme');})();
</script>
<style>
:root{
  --primary:#0a0a0f;
  --accent:#ff3b5c;
  --accent2:#ffb347;
  --accent3:#00d4aa;
  --surface:#111118;
  --surface2:#1a1a24;
  --surface3:#22222e;
  --light:#f4f4f8;
  --white:#ffffff;
  --gray:#9898b0;
  --border:rgba(255,255,255,0.07);
  --radius:16px;
  --radius-sm:10px;
  --glow:0 0 40px rgba(255,59,92,0.15);
}
/* ═══════════════════════════════════════════════════════════
   LIGHT THEME  –  applied to <html> immediately to prevent FOUC
   ═══════════════════════════════════════════════════════════ */
html.light-theme,html.light-theme body{
  --primary:#f0f0f5;
  --surface:#ffffff;
  --surface2:#f0f0f6;
  --surface3:#e4e4ef;
  --white:#111122;
  --gray:#55556e;
  --border:rgba(0,0,0,0.09);
  --glow:0 0 40px rgba(255,59,92,0.08);
  background:#f0f0f5;
  color:#111122;
}
/* Navbar */
html.light-theme .navbar{background:rgba(248,248,252,0.97)!important;border-bottom-color:rgba(0,0,0,0.08);}
/* Announcement bar keeps its gradient – no change needed */
/* Search & category buttons */
html.light-theme .search-wrap input{background:#fff;color:#111122;border-color:rgba(0,0,0,0.12);}
html.light-theme .search-wrap input::placeholder{color:#8888a0;}
html.light-theme .cat-dropdown-btn{background:#fff;color:#111122;border-color:rgba(0,0,0,0.12);}
/* Cart drawer – was hardcoded #111118 */
html.light-theme #cartDrawer{background:#fff!important;border-left-color:rgba(0,0,0,0.09)!important;}
html.light-theme #cartDrawer [style*="background:#18181f"],
html.light-theme #cartDrawer [style*="background:#1e1e28"]{background:#f4f4f8!important;}
html.light-theme #cartDrawer [style*="border-top:1px solid rgba(255,255,255"]{border-color:rgba(0,0,0,0.08)!important;}
html.light-theme #cartDrawer [style*="border-bottom:1px solid rgba(255,255,255"]{border-color:rgba(0,0,0,0.08)!important;}
html.light-theme #cartDrawer button[style*="background:#1e1e28"]{background:#e8e8f0!important;color:#111122!important;}
html.light-theme #cartDrawer [style*="color:#f0f0f8"]{color:#111122!important;}
/* Product cards */
html.light-theme .pcard{background:#fff;border-color:rgba(0,0,0,0.07);}
html.light-theme .pcard:hover{box-shadow:0 16px 40px rgba(0,0,0,0.12);}
html.light-theme .pcard-img{background:#f5f5fa;}
html.light-theme .wishlist-btn{background:rgba(0,0,0,0.06)!important;color:#55556e;}
/* Hero section – override hardcoded dark gradients */
html.light-theme .hero-main{background:linear-gradient(135deg,#e8e8f8 0%,#f0e8f8 40%,#e8f0f8 100%)!important;}
html.light-theme .hero-main h1{color:#111122!important;}
/* Flash-sale see-all card */
html.light-theme .flash-see-all-card{background:linear-gradient(135deg,#fff0f4,#fff5f0)!important;border-color:rgba(255,59,92,0.3)!important;}
html.light-theme .flash-see-all-card:hover{background:linear-gradient(135deg,#ffe0e8,#ffe8e0)!important;}
/* Category mega dropdown */
html.light-theme .cat-mega{background:#fff;box-shadow:0 24px 60px rgba(0,0,0,0.12);}
html.light-theme .cat-item:hover{background:rgba(255,59,92,0.06);color:#111122;}
/* Section / filter tabs */
html.light-theme .tab{border-color:rgba(0,0,0,0.12);color:#55556e;background:#fff;}
html.light-theme .tab.active{background:#111122;color:#fff;border-color:#111122;}
/* Countdown timer box */
html.light-theme .cdu{background:#fff;color:#111122;border:1px solid rgba(0,0,0,0.1);}
/* Feature banner – override hardcoded dark gradient */
html.light-theme .fbanner{background:linear-gradient(135deg,#f8f0ff 0%,#fff0f4 50%,#f0f8ff 100%)!important;}
html.light-theme .fbanner h2{color:#111122!important;}
html.light-theme .fbanner-cta.outline{border-color:rgba(0,0,0,0.2);color:#111122;}
/* Newsletter – override hardcoded dark gradient */
html.light-theme .newsletter{background:linear-gradient(135deg,#e8f8f0,#f0f0ff,#fff0f4)!important;}
html.light-theme .newsletter h2,html.light-theme .newsletter p,html.light-theme .nl-left h2,html.light-theme .nl-left p{color:#111122;}
html.light-theme .nl-input{background:#fff;color:#111122;border-color:rgba(0,0,0,0.12);}
html.light-theme .nl-input::placeholder{color:#8888a0;}
/* Footer */
html.light-theme footer,.light-theme .footer{background:#e4e4ef!important;}
html.light-theme .footer-bottom{border-top-color:rgba(0,0,0,0.08);}
/* Account dropdown menu (already white, stays white in both modes) */
html.light-theme .acct-menu{background:#fff;box-shadow:0 6px 28px rgba(0,0,0,0.15);}
/* Modals */
html.light-theme .modal-overlay{background:rgba(0,0,0,0.45);}
html.light-theme .mbox{background:#fff;}
html.light-theme .mhd{background:#f4f4f8;border-bottom-color:rgba(0,0,0,0.08);}
html.light-theme .minp{background:#f8f8fc;border-color:rgba(0,0,0,0.1);color:#111122;}
html.light-theme .minp::placeholder{color:#8888a0;}
/* FAQ widget */
html.light-theme .faq-window{background:#fff;box-shadow:0 16px 56px rgba(0,0,0,0.15);}
html.light-theme .faq-header-info h4{color:#111122!important;}
html.light-theme .faq-close{background:rgba(0,0,0,0.06)!important;color:#111122!important;}
html.light-theme .msg-bubble{background:#f0f0f6!important;color:#111122!important;}
html.light-theme .msg-bubble strong{color:#111122!important;}
/* Cart badge border against light bg */
html.light-theme .cbadge{border-color:var(--surface2);}
/* Scrollbar */
html.light-theme ::-webkit-scrollbar-track{background:#e8e8f0;}
html.light-theme ::-webkit-scrollbar-thumb{background:var(--accent);}
/* Overlay backdrops */
html.light-theme .cart-overlay{background:rgba(0,0,0,0.35)!important;}
/* Price text */
html.light-theme .price-current,.light-theme .price-main{color:#111122;}
/* Social icon SVGs in footer */
html.light-theme .soc{background:#e8e8f0;border-color:rgba(0,0,0,0.1);}
html.light-theme .soc svg{fill:#55556e;}
html.light-theme .soc:hover svg{fill:#fff;}
/* Feature cards */
html.light-theme .feat-card{background:#fff;border-color:rgba(0,0,0,0.08);}
html.light-theme .feat-icon{background:#f0f0f8;}
html.light-theme .feat-title{color:#111122;}
/* Contact, career, blog, press modal cards */
html.light-theme .contact-card{background:#f4f4f8;border-color:rgba(0,0,0,0.08);}
html.light-theme .contact-card .cc-val{color:#111122;}
html.light-theme .career-card{background:#f4f4f8;border-color:rgba(0,0,0,0.08);}
html.light-theme .career-card .job-title{color:#111122;}
html.light-theme .blog-card{border-bottom-color:rgba(0,0,0,0.08);}
html.light-theme .blog-em{background:#f0f0f8;}
html.light-theme .blog-title{color:#111122;}
html.light-theme .press-card{background:#f4f4f8;border-color:rgba(0,0,0,0.08);}
html.light-theme .press-headline{color:#111122;}
html.light-theme .track-result{background:#f4f4f8;border-color:rgba(0,0,0,0.08);}
html.light-theme .track-step{border-bottom-color:rgba(0,0,0,0.06);}
html.light-theme .track-info .ts-title{color:#111122;}
html.light-theme .faq-item{background:#f4f4f8;border-color:rgba(0,0,0,0.08);}
html.light-theme .faq-q{color:#111122;}
html.light-theme .faq-q:hover{background:#eaeaf2;}
html.light-theme .faq-a{color:#55556e;}
/* Info modal sections */
html.light-theme .info-section h3{color:#111122;border-bottom-color:rgba(0,0,0,0.08);}
html.light-theme .info-section p,html.light-theme .info-section ul li{color:#55556e;}
html.light-theme .info-section ul li{border-bottom-color:rgba(0,0,0,0.05);}
/* Hero heading (hardcoded #fff fallback) */
html.light-theme .hero-main h1{color:#111122!important;}
/* Hero side cards (Electronics Sale / Top Accessories) */
html.light-theme .hcard:first-child{background:linear-gradient(135deg,#fff8e8,#fff0cc)!important;border-color:rgba(200,130,0,0.25)!important;}
html.light-theme .hcard:last-child{background:linear-gradient(135deg,#e6faf5,#ccf5ea)!important;border-color:rgba(0,170,130,0.25)!important;}
html.light-theme .hcard h3{color:#111122!important;}
html.light-theme .hcard:first-child p{color:#a06000!important;}
html.light-theme .hcard:last-child p{color:#007a5a!important;}
html.light-theme .hcard:first-child .hcard-badge{background:rgba(200,130,0,0.15)!important;color:#a06000!important;}
html.light-theme .hcard:last-child .hcard-badge{background:rgba(0,170,130,0.15)!important;color:#007a5a!important;}
/* tOrderId strong in cart */
html.light-theme #tOrderId{color:#111122!important;}
/* card-preview-val (payment card preview) */
html.light-theme .card-preview-val{color:#111122;}

/* ── THEME TOGGLE BUTTON ─────────────────────────────────── */
.theme-toggle-btn{width:38px;height:38px;border-radius:50%;border:1.5px solid var(--border);background:var(--surface2);color:var(--white);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.25s;flex-shrink:0;}
.theme-toggle-btn:hover{border-color:var(--accent);color:var(--accent);background:var(--surface3);transform:scale(1.08);}
/* prevent transition flash on initial load */
html.light-theme *{transition-duration:0s!important;}
html.light-theme.theme-ready *{transition-duration:unset!important;}
*{box-sizing:border-box;margin:0;padding:0;}
html{scroll-behavior:smooth;}
body{font-family:'DM Sans',sans-serif;background:var(--primary);color:var(--white);overflow-x:hidden;}
a{text-decoration:none;color:inherit;}

/* SCROLLBAR */
::-webkit-scrollbar{width:5px;height:5px;}
::-webkit-scrollbar-track{background:var(--surface);}
::-webkit-scrollbar-thumb{background:var(--accent);border-radius:3px;}

/* ANNOUNCEMENT BAR */
.ann-bar{background:linear-gradient(90deg,var(--accent),#ff6b35,var(--accent2));padding:10px;text-align:center;font-size:13px;font-weight:600;letter-spacing:0.5px;position:relative;overflow:hidden;}
.ann-bar::before{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.1),transparent);animation:shimmer 3s infinite;}
@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}

/* NAVBAR */
.navbar{background:rgba(10,10,15,0.95);backdrop-filter:blur(20px);padding:16px 48px;display:flex;align-items:center;gap:24px;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:500;transition:all 0.3s;}
.brand{font-family:'Syne',sans-serif;font-size:26px;font-weight:800;display:flex;align-items:center;gap:2px;white-space:nowrap;}
.brand-my{color:var(--white);}
.brand-store{color:var(--accent);}
.brand-dot{width:7px;height:7px;background:var(--accent3);border-radius:50%;margin-bottom:2px;}

.search-wrap{flex:1;max-width:520px;position:relative;}
.search-wrap input{width:100%;padding:12px 20px 12px 48px;border:1.5px solid var(--border);border-radius:50px;font-size:14px;font-family:'DM Sans',sans-serif;background:var(--surface2);color:var(--white);outline:none;transition:all 0.25s;}
.search-wrap input::placeholder{color:var(--gray);}
.search-wrap input:focus{border-color:var(--accent);background:var(--surface3);box-shadow:0 0 0 4px rgba(255,59,92,0.1);}
.search-icon{position:absolute;left:18px;top:50%;transform:translateY(-50%);color:var(--gray);pointer-events:none;}
.search-btn{position:absolute;right:6px;top:50%;transform:translateY(-50%);background:var(--accent);border:none;color:#fff;width:36px;height:36px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s;}
.search-btn:hover{background:#e02040;transform:translateY(-50%) scale(1.05);}

/* CATEGORY DROPDOWN */
.cat-dropdown-wrap{position:relative;}
.cat-dropdown-btn{display:flex;align-items:center;gap:8px;padding:10px 18px;background:var(--surface2);border:1.5px solid var(--border);border-radius:50px;color:var(--white);font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;transition:all 0.2s;font-family:'DM Sans',sans-serif;}
.cat-dropdown-btn:hover,.cat-dropdown-btn.open{border-color:var(--accent);color:var(--accent);background:var(--surface3);}
.cat-dropdown-btn svg{transition:transform 0.2s;}
.cat-dropdown-btn.open svg{transform:rotate(180deg);}
.cat-mega{position:absolute;top:calc(100% + 12px);left:0;width:680px;background:var(--surface);border:1px solid var(--border);border-radius:20px;box-shadow:0 24px 60px rgba(0,0,0,0.6);z-index:600;opacity:0;pointer-events:none;transform:translateY(-8px);transition:all 0.22s cubic-bezier(0.25,0.46,0.45,0.94);overflow:hidden;}
.cat-mega.open{opacity:1;pointer-events:all;transform:translateY(0);}
.cat-mega-hd{padding:16px 20px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;}
.cat-mega-hd span{font-family:'Syne',sans-serif;font-size:13px;font-weight:700;color:var(--gray);text-transform:uppercase;letter-spacing:1px;}
.cat-mega-body{display:grid;grid-template-columns:repeat(3,1fr);gap:0;}
.cat-col{padding:16px 0;border-right:1px solid var(--border);}
.cat-col:last-child{border-right:none;}
.cat-col-title{padding:8px 20px;font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:1.2px;display:flex;align-items:center;gap:6px;}
.cat-col-title span{font-size:14px;}
.cat-item{display:flex;align-items:center;gap:10px;padding:9px 20px;font-size:13px;font-weight:500;color:var(--gray);transition:all 0.15s;cursor:pointer;text-decoration:none;}
.cat-item:hover{background:rgba(255,59,92,0.08);color:var(--white);padding-left:26px;}
.cat-item .ci-em{font-size:15px;width:20px;text-align:center;}

.cat-mega-footer{padding:12px 20px;border-top:1px solid var(--border);display:flex;justify-content:center;}
.cat-see-all{font-size:12px;font-weight:600;color:var(--accent);display:flex;align-items:center;gap:6px;transition:opacity 0.2s;}
.cat-see-all:hover{opacity:0.75;}

.nav-actions{display:flex;align-items:center;gap:10px;margin-left:auto;}
.nbtn{padding:10px 20px;border-radius:50px;font-size:13px;font-weight:600;cursor:pointer;transition:all 0.2s;border:none;font-family:'DM Sans',sans-serif;letter-spacing:0.3px;}
.nbtn.ol{background:transparent;border:1.5px solid var(--border);color:var(--white);}
.nbtn.ol:hover{border-color:var(--accent);color:var(--accent);}
.nbtn.fi{background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;box-shadow:0 4px 15px rgba(255,59,92,0.3);}
.nbtn.fi:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(255,59,92,0.4);}

.cart-btn{background:var(--surface2);border:1.5px solid var(--border);color:var(--white);width:44px;height:44px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;position:relative;transition:all 0.2s;font-size:18px;}
.cart-btn:hover{border-color:var(--accent);background:var(--surface3);}
.cbadge{position:absolute;top:-4px;right:-4px;background:var(--accent);color:#fff;font-size:10px;font-weight:700;border-radius:50%;width:18px;height:18px;display:flex;align-items:center;justify-content:center;border:2px solid var(--primary);}

/* CART DRAWER - slides from right */
.cart-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.6);backdrop-filter:blur(8px);z-index:900;opacity:0;pointer-events:none;transition:opacity 0.3s;}
.cart-overlay.open{opacity:1;pointer-events:all;}
.cart-drawer{position:fixed;top:0;right:-440px;width:420px;height:100vh;background:var(--surface);border-left:1px solid var(--border);z-index:901;display:flex;flex-direction:column;transition:right 0.35s cubic-bezier(0.25,0.46,0.45,0.94);overflow:hidden;}
.cart-drawer.open{right:0;}
.cart-drawer-hd{padding:24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;background:var(--surface2);}
.cart-drawer-hd h3{font-family:'Syne',sans-serif;font-size:20px;font-weight:700;}
.cart-drawer-hd .cc-info{font-size:13px;color:var(--gray);margin-top:2px;}
.cart-close{background:var(--surface3);border:none;color:var(--white);width:36px;height:36px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;transition:all 0.2s;}
.cart-close:hover{background:var(--accent);transform:rotate(90deg);}
.cart-body{flex:1;overflow-y:auto;padding:20px;}
.cart-item{display:flex;align-items:center;gap:14px;padding:14px;background:var(--surface2);border-radius:var(--radius-sm);margin-bottom:12px;border:1px solid var(--border);transition:all 0.2s;}
.cart-item:hover{border-color:rgba(255,59,92,0.3);}
.cart-item-em{font-size:40px;min-width:56px;height:56px;background:var(--surface3);border-radius:10px;display:flex;align-items:center;justify-content:center;}
.cart-item-info{flex:1;}
.cart-item-name{font-size:14px;font-weight:600;margin-bottom:4px;}
.cart-item-price{font-size:15px;font-weight:700;color:var(--accent);}
.cart-item-remove{background:none;border:none;color:var(--gray);cursor:pointer;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:all 0.2s;}
.cart-item-remove:hover{background:rgba(255,59,92,0.15);color:var(--accent);}
.cart-qty-ctrl{display:flex;align-items:center;gap:6px;background:var(--surface3);border-radius:20px;padding:3px 6px;border:1px solid var(--border2);}
.qty-btn{background:none;border:none;color:var(--white);font-size:16px;font-weight:700;cursor:pointer;width:22px;height:22px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:background 0.15s;line-height:1;}
.qty-btn:hover{background:var(--accent);color:#fff;}
.qty-val{font-size:13px;font-weight:700;min-width:18px;text-align:center;color:var(--white);}
.cart-footer{padding:20px;border-top:1px solid var(--border);background:var(--surface2);}
.cart-total-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;}
.cart-total-label{font-size:14px;color:var(--gray);}
.cart-total-val{font-family:'Syne',sans-serif;font-size:22px;font-weight:700;}
.cart-checkout-btn{width:100%;padding:15px;background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;border:none;border-radius:var(--radius-sm);font-size:16px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;transition:all 0.2s;letter-spacing:0.5px;}
.cart-checkout-btn:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(255,59,92,0.4);}
.cart-view-btn{width:100%;padding:12px;background:transparent;color:var(--white);border:1.5px solid var(--border2);border-radius:var(--radius-sm);font-size:14px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;transition:all 0.2s;margin-top:10px;display:flex;align-items:center;justify-content:center;gap:8px;}
.cart-view-btn:hover{background:var(--surface3);border-color:var(--accent3);color:var(--accent3);}
.cart-empty{text-align:center;padding:60px 20px;color:var(--gray);}
.cart-empty .cart-empty-icon{font-size:56px;display:block;margin-bottom:16px;}
.cart-empty p{font-size:15px;}

/* CATEGORY NAV */
.catnav{background:var(--surface);border-bottom:1px solid var(--border);padding:0 48px;display:flex;gap:4px;overflow-x:auto;}
.catnav::-webkit-scrollbar{display:none;}
.catnav a{padding:16px 22px;font-size:13px;font-weight:600;color:var(--gray);white-space:nowrap;border-bottom:2px solid transparent;transition:all 0.2s;display:flex;align-items:center;gap:6px;}
.catnav a:hover{color:var(--white);}
.catnav a.active{color:var(--accent);border-bottom-color:var(--accent);}

/* HERO */
.hero{margin:28px 48px;display:grid;grid-template-columns:1fr 340px;gap:20px;}
.hero-main{background:linear-gradient(135deg,#0d0d1a 0%,#1a0a20 40%,#0a1020 100%);border-radius:24px;padding:56px 56px;position:relative;overflow:hidden;min-height:320px;display:flex;flex-direction:column;justify-content:center;border:1px solid var(--border);}
.hero-main::before{content:'';position:absolute;right:-80px;top:-80px;width:420px;height:420px;background:radial-gradient(circle,rgba(255,59,92,0.12),transparent 65%);border-radius:50%;}
.hero-main::after{content:'🛍️';position:absolute;right:56px;top:50%;transform:translateY(-50%);font-size:130px;opacity:0.07;filter:blur(2px);}
.hero-particles{position:absolute;inset:0;overflow:hidden;pointer-events:none;}
.particle{position:absolute;width:3px;height:3px;background:var(--accent);border-radius:50%;opacity:0.4;animation:float-particle linear infinite;}
@keyframes float-particle{0%{transform:translateY(100%) translateX(0);opacity:0}10%{opacity:0.4}90%{opacity:0.4}100%{transform:translateY(-100px) translateX(20px);opacity:0}}
.htag{display:inline-flex;align-items:center;gap:6px;background:rgba(255,59,92,0.15);color:var(--accent);border:1px solid rgba(255,59,92,0.3);border-radius:50px;padding:6px 16px;font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:18px;width:fit-content;}
.hero-main h1{font-family:'DM Sans',sans-serif;font-size:46px;font-weight:800;color:#fff;line-height:1.1;margin-bottom:14px;}
.hero-main h1 em{background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-style:normal;}
.hero-main p{color:var(--gray);font-size:16px;margin-bottom:28px;max-width:400px;}
.hcta{display:inline-flex;align-items:center;gap:10px;background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;padding:14px 32px;border-radius:50px;font-weight:700;font-size:15px;width:fit-content;transition:all 0.2s;box-shadow:0 6px 24px rgba(255,59,92,0.35);}
.hcta:hover{transform:translateY(-2px) scale(1.02);box-shadow:0 10px 32px rgba(255,59,92,0.45);}
.hcta svg{transition:transform 0.2s;}
.hcta:hover svg{transform:translateX(4px);}

.hero-side{display:flex;flex-direction:column;gap:16px;}
.hcard{flex:1;border-radius:20px;padding:26px;display:flex;flex-direction:column;justify-content:flex-end;position:relative;overflow:hidden;transition:transform 0.25s;border:1px solid transparent;cursor:pointer;}
.hcard:hover{transform:translateY(-4px);}
.hcard:first-child{background:linear-gradient(135deg,#1a1000,#2d1f00);border-color:rgba(255,179,71,0.2);}
.hcard:last-child{background:linear-gradient(135deg,#001a14,#002a20);border-color:rgba(0,212,170,0.2);}
.hcard-em{font-size:60px;position:absolute;right:20px;top:16px;opacity:0.6;filter:drop-shadow(0 4px 8px rgba(0,0,0,0.3));}
.hcard h3{font-family:'Syne',sans-serif;font-size:18px;font-weight:700;color:var(--white);}
.hcard p{font-size:12px;margin-top:4px;}
.hcard:first-child p{color:var(--accent2);}
.hcard:last-child p{color:var(--accent3);}
.hcard-badge{display:inline-block;margin-top:10px;padding:4px 12px;border-radius:50px;font-size:11px;font-weight:700;}
.hcard:first-child .hcard-badge{background:rgba(255,179,71,0.2);color:var(--accent2);}
.hcard:last-child .hcard-badge{background:rgba(0,212,170,0.2);color:var(--accent3);}

/* MARQUEE STRIP */
.marquee-strip{background:var(--surface);border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:14px 0;overflow:hidden;white-space:nowrap;margin:0;}
.marquee-inner{display:inline-flex;gap:0;animation:marquee 35s linear infinite;}
.marquee-item{display:inline-flex;align-items:center;gap:10px;padding:0 32px;font-size:13px;font-weight:500;color:var(--gray);}
.marquee-item span{color:var(--accent);font-weight:700;}

/* CATEGORY ICONS */
.caticons{margin:28px 48px;display:grid;grid-template-columns:repeat(12,1fr);gap:12px;}
.ci{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px 12px;display:flex;flex-direction:column;align-items:center;gap:10px;cursor:pointer;transition:all 0.25px;text-decoration:none;}
.ci:hover{border-color:var(--accent);background:var(--surface2);transform:translateY(-4px);}
.ci-circle{width:60px;height:60px;border-radius:50%;background:var(--surface2);display:flex;align-items:center;justify-content:center;font-size:28px;transition:all 0.25s;}
.ci:hover .ci-circle{background:rgba(255,59,92,0.1);}
.ci-label{font-size:12px;font-weight:500;color:var(--gray);text-align:center;}
.ci:hover .ci-label{color:var(--white);}

/* SECTIONS */
.sec{margin:0 48px 40px;}
.sec-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px;}
.sec-title{display:flex;align-items:center;gap:12px;}
.sec-title h2{font-family:'Syne',sans-serif;font-size:26px;font-weight:700;}
.sec-badge{background:var(--accent);color:#fff;padding:5px 12px;border-radius:50px;font-size:12px;font-weight:700;animation:pulse-badge 2s infinite;}
@keyframes pulse-badge{0%,100%{box-shadow:0 0 0 0 rgba(255,59,92,0.4)}50%{box-shadow:0 0 0 8px rgba(255,59,92,0)}}
.cd{display:flex;align-items:center;gap:6px;}
.cdu{background:var(--surface2);border:1px solid var(--border);color:#fff;padding:5px 10px;border-radius:8px;font-size:14px;font-weight:700;min-width:36px;text-align:center;font-variant-numeric:tabular-nums;}
.cds{color:var(--accent);font-weight:700;font-size:18px;}
.see-all{font-size:13px;color:var(--accent);font-weight:600;display:flex;align-items:center;gap:6px;padding:9px 20px;border:1.5px solid rgba(255,59,92,0.4);border-radius:50px;transition:all 0.2s;}
.see-all:hover{background:var(--accent);color:#fff;border-color:var(--accent);}
.see-all-sm{font-size:12px;color:var(--accent);font-weight:600;display:inline-flex;align-items:center;gap:5px;padding:6px 16px;border:1.5px solid rgba(255,59,92,0.4);border-radius:50px;transition:all 0.2s;text-decoration:none;margin-top:18px;}
.see-all-sm:hover{background:var(--accent);color:#fff;border-color:var(--accent);}
.see-all-wrap{display:flex;justify-content:center;}

/* Flash Sale — "See All" as last scroll card */
.flash-see-all-card{flex:0 0 100px;border-radius:16px;background:linear-gradient(135deg,#1a0008,#2d0010);border:1.5px dashed rgba(255,59,92,0.45);display:flex;align-items:center;justify-content:center;text-decoration:none;transition:all 0.3s;cursor:pointer;}
.flash-see-all-card:hover{background:linear-gradient(135deg,#2a0012,#3d0018);border-color:var(--accent);transform:translateY(-4px);box-shadow:0 12px 32px rgba(255,59,92,0.2);}
.fsac-inner{display:flex;flex-direction:column;align-items:center;gap:8px;padding:16px 10px;text-align:center;}
.fsac-icon{font-size:24px;animation:fsac-bob 2.5s ease-in-out infinite;}
@keyframes fsac-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
.fsac-label{font-family:'Syne',sans-serif;font-size:11px;font-weight:700;color:var(--white);line-height:1.4;}
.fsac-arrow{width:26px;height:26px;border-radius:50%;background:rgba(255,59,92,0.15);border:1.5px solid rgba(255,59,92,0.4);display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--accent);transition:all 0.25s;}
.flash-see-all-card:hover .fsac-arrow{background:var(--accent);color:#fff;border-color:var(--accent);transform:translateX(3px);}

/* PRODUCT ROWS/GRIDS */
.prow{display:flex;gap:20px;overflow-x:auto;padding-bottom:8px;scroll-behavior:smooth;}
.prow::-webkit-scrollbar{height:4px;}
.prow::-webkit-scrollbar-thumb{background:var(--accent);border-radius:2px;}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:20px;}
#tgrid{grid-template-columns:repeat(3,1fr);}

/* PRODUCT CARDS */
.pcard{background:var(--surface);border-radius:20px;overflow:hidden;border:1px solid var(--border);transition:all 0.3s;position:relative;flex:0 0 250px;}
.pcard:hover{transform:translateY(-6px);box-shadow:0 16px 40px rgba(0,0,0,0.4);border-color:rgba(255,59,92,0.25);}
.pcard-img{height:140px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--surface2),var(--surface3));position:relative;overflow:hidden;}
.pcard-img::after{content:'';position:absolute;inset:0;background:radial-gradient(circle at center,transparent 40%,rgba(0,0,0,0.2));pointer-events:none;}
.pcard-emoji{font-size:60px;transition:transform 0.35s;display:block;line-height:1;filter:drop-shadow(0 8px 16px rgba(0,0,0,0.3));}
.pcard-real-img{width:100%;height:100%;object-fit:cover;display:block;}
.pcard:hover .pcard-emoji{transform:scale(1.12) rotate(-3deg);}
.wishlist-btn{position:absolute;top:12px;right:12px;width:34px;height:34px;background:rgba(0,0,0,0.5);backdrop-filter:blur(8px);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:15px;cursor:pointer;transition:all 0.2s;border:none;color:var(--gray);z-index:2;}
.wishlist-btn:hover,.wishlist-btn.active{background:rgba(255,59,92,0.3);color:var(--accent);}
.discount-tag{position:absolute;top:12px;left:12px;background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;font-size:11px;font-weight:700;padding:4px 10px;border-radius:50px;z-index:2;box-shadow:0 2px 8px rgba(255,59,92,0.4);}

.pcard-body{padding:16px;}
.pcard-cat{font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--accent);margin-bottom:5px;}
.pcard-name{font-size:14px;font-weight:600;color:var(--white);margin-bottom:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;line-height:1.4;}
.pcard-desc{font-size:12px;color:var(--gray);margin-bottom:8px;}
.pcard-rating{display:flex;align-items:center;gap:6px;margin-bottom:10px;}
.stars{color:var(--accent2);font-size:12px;letter-spacing:1px;}
.rating-num{font-size:12px;font-weight:700;color:var(--white);}
.rating-sold{font-size:11px;color:var(--gray);}
.pcard-price{display:flex;align-items:baseline;gap:8px;margin-bottom:12px;}
.price-current{font-family:'Syne',sans-serif;font-size:18px;font-weight:700;color:var(--white);}
.price-orig{font-size:13px;color:var(--gray);text-decoration:line-through;}
.progress-bar{height:3px;background:var(--surface3);border-radius:2px;margin-bottom:7px;overflow:hidden;}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--accent3),var(--accent));border-radius:2px;}
.sold-info{font-size:11px;color:var(--gray);margin-bottom:12px;}

.add-cart-btn{width:100%;padding:11px;background:var(--surface2);color:var(--white);border:1.5px solid var(--border);border-radius:var(--radius-sm);font-size:13px;font-weight:600;cursor:pointer;transition:all 0.2s;font-family:'DM Sans',sans-serif;display:flex;align-items:center;justify-content:center;gap:8px;}
.add-cart-btn:hover{background:var(--accent);border-color:var(--accent);transform:translateY(-1px);box-shadow:0 4px 14px rgba(255,59,92,0.3);}
.add-cart-btn.adding{background:var(--accent3);border-color:var(--accent3);color:#000;}

/* BRAND/STORE PANEL */
.two-col{margin:0 48px 40px;display:grid;grid-template-columns:1fr 340px;gap:24px;align-items:start;}


/* TABS */
.tabs{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap;}
.tab{padding:8px 18px;border-radius:50px;font-size:12px;font-weight:600;cursor:pointer;border:1.5px solid var(--border);background:transparent;color:var(--gray);transition:all 0.2s;}
.tab.active{background:var(--white);color:var(--primary);border-color:var(--white);}
.tab:hover:not(.active){border-color:var(--accent);color:var(--accent);}

/* FEATURES BAR */
.features-bar{margin:0 48px 40px;display:grid;grid-template-columns:repeat(4,1fr);gap:16px;}
.feat-card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:28px 24px;display:flex;align-items:center;gap:16px;transition:all 0.25s;cursor:default;}
.feat-card:hover{border-color:var(--accent);transform:translateY(-3px);}
.feat-icon{font-size:36px;width:56px;height:56px;background:var(--surface2);border-radius:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.feat-title{font-size:14px;font-weight:700;margin-bottom:3px;}
.feat-desc{font-size:12px;color:var(--gray);}

/* BANNER */
/* ADVERTISEMENT BANNER SWIPER */
.ad-swiper-wrap{margin:0 48px 40px;position:relative;}
.ad-swiper{overflow:hidden;border-radius:22px;}
.ad-swiper-track{display:flex;transition:transform 0.55s cubic-bezier(0.4,0,0.2,1);will-change:transform;}
.ad-banner{flex:0 0 100%;width:100%;border-radius:22px;padding:52px 56px;position:relative;overflow:hidden;display:flex;flex-direction:row;align-items:center;justify-content:space-between;min-height:220px;border:1px solid transparent;text-decoration:none;cursor:pointer;}
.ad-banner-electronics{background:linear-gradient(135deg,#050d1f 0%,#0a1a3a 50%,#0d1030 100%);border-color:rgba(99,179,255,0.25);}
.ad-banner-fashion{background:linear-gradient(135deg,#1a001a 0%,#2d0038 50%,#1a0010 100%);border-color:rgba(220,80,255,0.25);}
.ad-banner-accessories{background:linear-gradient(135deg,#1a0e00 0%,#2d1a00 50%,#1a0a00 100%);border-color:rgba(255,179,71,0.25);}
.ad-banner::before{content:'';position:absolute;inset:0;opacity:0.04;background:repeating-linear-gradient(45deg,#fff 0px,#fff 1px,transparent 1px,transparent 12px);}
.ad-banner-glow-blue{position:absolute;top:-60px;right:80px;width:320px;height:320px;background:radial-gradient(circle,rgba(99,179,255,0.14),transparent 70%);border-radius:50%;pointer-events:none;}
.ad-banner-glow-pink{position:absolute;top:-60px;right:80px;width:320px;height:320px;background:radial-gradient(circle,rgba(220,80,255,0.14),transparent 70%);border-radius:50%;pointer-events:none;}
.ad-banner-glow-gold{position:absolute;top:-60px;right:80px;width:320px;height:320px;background:radial-gradient(circle,rgba(255,179,71,0.14),transparent 70%);border-radius:50%;pointer-events:none;}
.ad-banner-left{position:relative;z-index:1;max-width:520px;}
.ad-banner-right{position:relative;z-index:1;font-size:130px;opacity:0.75;filter:drop-shadow(0 8px 24px rgba(0,0,0,0.5));line-height:1;transition:transform 0.4s,opacity 0.4s;flex-shrink:0;}
.ad-banner:hover .ad-banner-right{transform:scale(1.08) rotate(-6deg);opacity:0.9;}
.ad-banner-tag{display:inline-flex;align-items:center;gap:6px;padding:5px 14px;border-radius:50px;font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:14px;width:fit-content;}
.ad-banner-electronics .ad-banner-tag{background:rgba(99,179,255,0.15);color:#63b3ff;border:1px solid rgba(99,179,255,0.3);}
.ad-banner-fashion .ad-banner-tag{background:rgba(220,80,255,0.15);color:#dc50ff;border:1px solid rgba(220,80,255,0.3);}
.ad-banner-accessories .ad-banner-tag{background:rgba(255,179,71,0.15);color:var(--accent2);border:1px solid rgba(255,179,71,0.3);}
.ad-banner-title{font-family:'DM Sans',sans-serif;font-size:42px;font-weight:800;color:#fff;line-height:1.1;margin-bottom:10px;}
.ad-banner-subtitle{font-size:15px;color:rgba(255,255,255,0.5);margin-bottom:22px;}
.ad-banner-cta-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;}
.ad-banner-cta{display:inline-flex;align-items:center;gap:8px;padding:12px 26px;border-radius:50px;font-size:13px;font-weight:700;width:fit-content;transition:all 0.2s;}
.ad-banner-electronics .ad-banner-cta{background:rgba(99,179,255,0.18);color:#63b3ff;border:1px solid rgba(99,179,255,0.35);}
.ad-banner-fashion .ad-banner-cta{background:rgba(220,80,255,0.18);color:#dc50ff;border:1px solid rgba(220,80,255,0.35);}
.ad-banner-accessories .ad-banner-cta{background:rgba(255,179,71,0.18);color:var(--accent2);border:1px solid rgba(255,179,71,0.35);}
.ad-banner:hover .ad-banner-cta{filter:brightness(1.3);}
.ad-banner-discount{background:var(--accent);color:#fff;font-size:12px;font-weight:800;padding:8px 16px;border-radius:12px;letter-spacing:0.5px;box-shadow:0 4px 14px rgba(255,59,92,0.45);white-space:nowrap;}
/* Swiper controls */
.ad-swiper-btn{position:absolute;top:50%;transform:translateY(-50%);width:44px;height:44px;border-radius:50%;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);color:#fff;font-size:18px;display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:10;transition:all 0.2s;backdrop-filter:blur(8px);}
.ad-swiper-btn:hover{background:rgba(255,59,92,0.25);border-color:var(--accent);}
.ad-swiper-prev{left:-20px;}
.ad-swiper-next{right:-20px;}
.ad-swiper-dots{display:flex;justify-content:center;gap:8px;margin-top:16px;}
.ad-dot{width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,0.2);border:none;cursor:pointer;transition:all 0.3s;padding:0;}
.ad-dot.active{width:24px;border-radius:4px;background:var(--accent);}
@media(max-width:900px){.ad-swiper-wrap{margin-left:24px;margin-right:24px;}.ad-banner{padding:36px 32px;min-height:190px;}.ad-banner-title{font-size:30px;font-stretch:normal;}.ad-banner-right{font-size:90px;}}
@media(max-width:640px){.ad-swiper-wrap{margin-left:16px;margin-right:16px;}.ad-swiper-btn{display:none;}.ad-banner{padding:28px 22px;min-height:170px;flex-direction:column;align-items:flex-start;}.ad-banner-right{font-size:70px;position:absolute;right:16px;bottom:16px;opacity:0.4;}.ad-banner-title{font-size:24px;font-stretch:normal;}}
.fbanner{margin:0 48px 40px;background:linear-gradient(135deg,var(--surface) 0%,#160010 50%,var(--surface) 100%);border-radius:24px;padding:60px;text-align:center;position:relative;overflow:hidden;border:1px solid var(--border);}
.fbanner::before{content:'';position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:500px;height:500px;background:radial-gradient(circle,rgba(255,59,92,0.08),transparent 70%);}
.fbanner-tag{display:inline-block;background:rgba(255,59,92,0.15);color:var(--accent);border:1px solid rgba(255,59,92,0.3);border-radius:50px;padding:6px 18px;font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:18px;}
.fbanner h2{font-family:'DM Sans',sans-serif;font-size:36px;color:#fff;margin-bottom:10px;font-weight:800;}
.fbanner h2 em{background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-style:normal;}
.fbanner p{color:var(--gray);font-size:15px;margin-bottom:28px;}
.fbanner-actions{display:flex;gap:14px;justify-content:center;}
.fbanner-cta{padding:13px 32px;border-radius:50px;font-size:14px;font-weight:700;cursor:pointer;transition:all 0.2s;font-family:'DM Sans',sans-serif;}
.fbanner-cta.primary{background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;border:none;box-shadow:0 6px 20px rgba(255,59,92,0.3);}
.fbanner-cta.primary:hover{transform:translateY(-2px);box-shadow:0 10px 28px rgba(255,59,92,0.4);}
.fbanner-cta.outline{background:transparent;border:1.5px solid var(--border);color:var(--white);}
.fbanner-cta.outline:hover{border-color:var(--accent);color:var(--accent);}

/* NEWSLETTER */
.newsletter{margin:0 48px 40px;background:linear-gradient(135deg,#001a10,#0a0a1a,#1a0008);border-radius:24px;padding:56px;display:grid;grid-template-columns:1fr 1fr;gap:40px;align-items:center;border:1px solid var(--border);}
.nl-left h2{font-family:'Syne',sans-serif;font-size:30px;font-weight:800;margin-bottom:10px;}
.nl-left h2 em{color:var(--accent3);font-style:normal;}
.nl-left p{color:var(--gray);font-size:14px;}
.nl-form{display:flex;gap:10px;}
.nl-input{flex:1;padding:14px 20px;background:var(--surface2);border:1.5px solid var(--border);border-radius:50px;font-size:14px;font-family:'DM Sans',sans-serif;color:var(--white);outline:none;transition:all 0.2s;}
.nl-input::placeholder{color:var(--gray);}
.nl-input:focus{border-color:var(--accent3);}
.nl-btn{padding:14px 28px;background:linear-gradient(135deg,var(--accent3),#00a884);color:#000;border:none;border-radius:50px;font-size:14px;font-weight:700;cursor:pointer;font-family:'DM Sans',sans-serif;transition:all 0.2s;white-space:nowrap;}
.nl-btn:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,212,170,0.35);}

/* FOOTER */
footer{background:var(--surface);border-top:1px solid var(--border);padding:48px;}
.fg{display:grid;grid-template-columns:1.5fr repeat(3,1fr);gap:40px;margin-bottom:40px;}
.fc-brand{display:flex;flex-direction:column;gap:14px;}
.fc-brand-logo{font-family:'Syne',sans-serif;font-size:24px;font-weight:800;}
.fc-brand-logo span{color:var(--accent);}
.fc-brand p{color:var(--gray);font-size:13px;line-height:1.6;max-width:240px;}
.fc h4{color:var(--white);font-size:13px;font-weight:700;margin-bottom:16px;letter-spacing:1px;text-transform:uppercase;}
.fc a{display:block;font-size:13px;margin-bottom:10px;color:var(--gray);transition:color 0.2s;}
.fc a:hover{color:var(--white);}
.social-links{display:flex;gap:10px;margin-top:4px;}
.soc{width:38px;height:38px;background:var(--surface2);border:1px solid var(--border);border-radius:50%;display:flex;align-items:center;justify-content:center;transition:all 0.2s;cursor:pointer;text-decoration:none;}
.soc:hover{background:var(--accent);border-color:var(--accent);transform:translateY(-3px);}
.soc svg{width:16px;height:16px;fill:var(--gray);}
.soc:hover svg{fill:#fff;}
/* Per-brand hover colours */
.soc.fb:hover{background:#1877f2;border-color:#1877f2;}
.soc.pin:hover{background:#e60023;border-color:#e60023;}
.soc.wa:hover{background:#25d366;border-color:#25d366;}
/* Info modal content styles */
.info-section{margin-bottom:22px;}
.info-section h3{font-family:'Syne',sans-serif;font-size:15px;font-weight:700;color:var(--white);margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--border);}
.info-section p{font-size:13px;color:var(--gray);line-height:1.7;margin-bottom:8px;}
.info-section ul{list-style:none;padding:0;}
.info-section ul li{font-size:13px;color:var(--gray);padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);display:flex;align-items:flex-start;gap:8px;}
.info-section ul li::before{content:'→';color:var(--accent);font-weight:700;flex-shrink:0;}
.info-highlight{background:rgba(255,59,92,0.08);border:1px solid rgba(255,59,92,0.2);border-radius:10px;padding:14px 16px;margin-bottom:14px;}
.info-highlight p{color:var(--white);margin:0;}
.contact-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;}
.contact-card{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center;}
.contact-card .cc-icon{font-size:28px;margin-bottom:8px;}
.contact-card .cc-label{font-size:11px;color:var(--gray);margin-bottom:4px;}
.contact-card .cc-val{font-size:13px;font-weight:600;color:var(--white);}
.contact-card a{color:var(--accent);text-decoration:none;}
.faq-item{background:var(--surface2);border:1px solid var(--border);border-radius:10px;margin-bottom:10px;overflow:hidden;}
.faq-q{padding:14px 16px;cursor:pointer;font-size:13px;font-weight:600;display:flex;justify-content:space-between;align-items:center;transition:background 0.2s;}
.faq-q:hover{background:var(--surface3);}
.faq-q .faq-chevron{transition:transform 0.25s;color:var(--accent);}
.faq-a{display:none;padding:0 16px 14px;font-size:13px;color:var(--gray);line-height:1.6;}
.faq-item.open .faq-a{display:block;}
.faq-item.open .faq-chevron{transform:rotate(180deg);}
.track-form{display:flex;flex-direction:column;gap:12px;}
.track-result{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:18px;margin-top:14px;display:none;}
.track-step{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.05);}
.track-step:last-child{border-bottom:none;}
.track-dot{width:10px;height:10px;border-radius:50%;background:var(--surface3);border:2px solid var(--gray);flex-shrink:0;margin-top:4px;}
.track-dot.done{background:var(--accent3);border-color:var(--accent3);}
.track-dot.active{background:var(--accent);border-color:var(--accent);box-shadow:0 0 0 3px rgba(255,59,92,0.2);}
.track-info .ts-title{font-size:13px;font-weight:600;}
.track-info .ts-date{font-size:11px;color:var(--gray);margin-top:2px;}
.career-card{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;}
.career-card .job-title{font-size:14px;font-weight:600;}
.career-card .job-meta{font-size:11px;color:var(--gray);margin-top:3px;}
.career-badge{padding:4px 12px;border-radius:50px;font-size:11px;font-weight:700;background:rgba(0,212,170,0.15);color:var(--accent3);}
.blog-card{display:flex;gap:14px;padding:12px 0;border-bottom:1px solid var(--border);}
.blog-card:last-child{border-bottom:none;}
.blog-em{font-size:32px;width:52px;height:52px;background:var(--surface2);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.blog-title{font-size:13px;font-weight:600;margin-bottom:4px;}
.blog-meta{font-size:11px;color:var(--gray);}
.press-card{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:10px;}
.press-source{font-size:12px;color:var(--accent);font-weight:700;margin-bottom:6px;}
.press-headline{font-size:13px;font-weight:600;margin-bottom:4px;}
.press-date{font-size:11px;color:var(--gray);}
.footer-bottom{border-top:1px solid var(--border);padding-top:24px;display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--gray);}

/* MODALS */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:1000;backdrop-filter:blur(8px);align-items:center;justify-content:center;}
.modal-overlay.open{display:flex;}
.mbox{background:var(--surface);width:460px;border-radius:24px;overflow:hidden;box-shadow:0 32px 80px rgba(0,0,0,0.5);animation:mIn .3s ease;border:1px solid var(--border);}
@keyframes mIn{from{opacity:0;transform:scale(.94) translateY(16px)}to{opacity:1;transform:scale(1) translateY(0)}}
.mhd{padding:32px 36px 0;display:flex;justify-content:space-between;align-items:flex-start;}
.mhd-info h2{font-family:'Syne',sans-serif;font-size:24px;font-weight:700;}
.mhd-info p{color:var(--gray);font-size:13px;margin-top:5px;}
.mclose{background:var(--surface2);border:1px solid var(--border);color:var(--white);width:34px;height:34px;border-radius:50%;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s;}
.mclose:hover{background:var(--accent);border-color:var(--accent);transform:rotate(90deg);}
.mbody{padding:28px 36px 36px;}
.minput{width:100%;padding:14px 18px;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-size:14px;font-family:'DM Sans',sans-serif;margin-bottom:14px;outline:none;transition:all 0.2s;background:var(--surface2);color:var(--white);}
.minput::placeholder{color:var(--gray);}
.minput:focus{border-color:var(--accent);background:var(--surface3);}

/* PASSWORD WRAP — used in BOTH login and register */
.pass-wrap{position:relative;margin-bottom:14px;}
.pass-wrap .minput.pass-input{margin-bottom:0;padding-right:48px;}
.eye-btn{position:absolute;top:50%;right:14px;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:var(--gray);display:flex;align-items:center;justify-content:center;padding:4px;border-radius:6px;transition:color 0.2s;}
.eye-btn:hover{color:var(--white);}

.msub{width:100%;padding:14px;background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;border:none;border-radius:var(--radius-sm);font-size:15px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;transition:all 0.2s;margin-top:4px;}
.msub:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(255,59,92,0.4);}
.mswitch{text-align:center;margin-top:16px;font-size:13px;color:var(--gray);}
.mswitch a{color:var(--accent);font-weight:600;cursor:pointer;}
.mdivider{display:flex;align-items:center;gap:14px;margin:14px 0;}
.mdivider::before,.mdivider::after{content:'';flex:1;height:1px;background:var(--border);}
.mdivider span{font-size:12px;color:var(--gray);}
/* ── SOCIAL LOGIN BUTTONS ── */
.social-btn{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;padding:13px 18px;border-radius:var(--radius-sm);font-size:14px;font-weight:600;font-family:'DM Sans',sans-serif;cursor:pointer;text-decoration:none;transition:all 0.2s;margin-bottom:10px;border:1.5px solid var(--border);}
.google-btn{background:var(--surface2);color:var(--white);}
.google-btn:hover{background:var(--surface3);border-color:#4285F4;box-shadow:0 4px 14px rgba(66,133,244,0.18);transform:translateY(-1px);}
/* ── OR DIVIDER ── */
.or-divider{display:flex;align-items:center;gap:12px;margin:6px 0 16px;}
.or-divider::before,.or-divider::after{content:'';flex:1;height:1px;background:var(--border);}
.or-divider span{font-size:12px;color:var(--gray);white-space:nowrap;}

/* TOAST */
.toast-stack{position:fixed;bottom:28px;right:28px;display:flex;flex-direction:column;gap:10px;z-index:9999;}
.toast{padding:14px 20px;border-radius:12px;font-size:14px;font-weight:500;color:#fff;animation:tin .35s ease;box-shadow:0 8px 28px rgba(0,0,0,0.3);display:flex;align-items:center;gap:10px;border:1px solid rgba(255,255,255,0.1);min-width:240px;}
@keyframes tin{from{opacity:0;transform:translateX(24px)}to{opacity:1;transform:translateX(0)}}
.toast.success{background:linear-gradient(135deg,#065f46,#047857);}
.toast.error{background:linear-gradient(135deg,#7f1d1d,#991b1b);}
.toast.info{background:linear-gradient(135deg,#1e3a5f,#1d4ed8);}

/* FAQ WIDGET */
.faq-bubble{position:fixed;bottom:28px;right:28px;z-index:800;}
.faq-toggle{width:58px;height:58px;border-radius:50%;background:linear-gradient(135deg,var(--accent),#c73333);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 24px rgba(255,59,92,0.5);transition:all 0.25s;}
.faq-toggle:hover{transform:scale(1.08);}
.faq-toggle svg{width:26px;height:26px;}
.faq-ping{position:absolute;top:-3px;right:-3px;width:14px;height:14px;background:var(--accent3);border-radius:50%;border:2px solid var(--primary);}
.faq-ping::after{content:'';position:absolute;inset:0;border-radius:50%;background:var(--accent3);animation:ping 1.8s ease-out infinite;}
@keyframes ping{0%{transform:scale(1);opacity:1}100%{transform:scale(2.4);opacity:0}}
.faq-window{position:absolute;bottom:72px;right:0;width:370px;background:var(--surface);border-radius:20px;box-shadow:0 16px 56px rgba(0,0,0,0.5);display:none;flex-direction:column;overflow:hidden;animation:faqIn .25s ease;border:1px solid var(--border);}
.faq-window.open{display:flex;}
@keyframes faqIn{from{opacity:0;transform:translateY(14px) scale(.96)}to{opacity:1;transform:translateY(0) scale(1)}}
.faq-header{background:linear-gradient(135deg,var(--surface2),var(--surface3));padding:18px 20px;display:flex;align-items:center;gap:12px;border-bottom:1px solid var(--border);}
.faq-avatar{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,var(--accent),#c73333);display:flex;align-items:center;justify-content:center;font-size:20px;}
.faq-header-info h4{color:#fff;font-size:14px;font-weight:700;}
.faq-header-info p{color:var(--gray);font-size:11px;display:flex;align-items:center;gap:5px;}
.faq-header-info p::before{content:'';width:7px;height:7px;border-radius:50%;background:var(--accent3);display:inline-block;}
.faq-close{background:rgba(255,255,255,0.06);border:none;color:#fff;width:30px;height:30px;border-radius:50%;cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;transition:all 0.2s;}
.faq-close:hover{background:rgba(255,59,92,0.25);}
.chat-clear-btn{background:rgba(255,255,255,0.06);border:none;color:var(--gray);width:30px;height:30px;border-radius:50%;cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;transition:all 0.2s;margin-left:auto;}
.chat-clear-btn:hover{background:rgba(255,179,71,0.2);color:var(--accent2);}
.faq-send:disabled{opacity:0.5;cursor:not-allowed;}
.msg-bubble strong{color:#fff;}
.faq-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;max-height:300px;min-height:200px;}
.msg{display:flex;gap:8px;align-items:flex-end;}
.msg.user{flex-direction:row-reverse;}
.msg-bubble{padding:10px 14px;border-radius:14px;font-size:13px;line-height:1.55;max-width:80%;}
.msg.bot .msg-bubble{background:var(--surface2);color:var(--white);border-bottom-left-radius:4px;}
.msg.user .msg-bubble{background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;border-bottom-right-radius:4px;}
.msg-avatar{width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,var(--accent),#c73333);display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0;}
.faq-suggestions{padding:0 12px 10px;display:flex;flex-wrap:wrap;gap:6px;}
.faq-chip{padding:5px 12px;background:var(--surface2);border:1px solid var(--border);border-radius:50px;font-size:11px;color:var(--white);cursor:pointer;transition:all 0.2s;white-space:nowrap;}
.faq-chip:hover{background:var(--accent);border-color:var(--accent);}
.faq-input-row{display:flex;align-items:center;gap:8px;padding:12px;border-top:1px solid var(--border);}
.faq-input{flex:1;padding:10px 14px;border:1.5px solid var(--border);border-radius:50px;font-size:13px;font-family:'DM Sans',sans-serif;outline:none;transition:all 0.2s;background:var(--surface2);color:var(--white);}
.faq-input::placeholder{color:var(--gray);}
.faq-input:focus{border-color:var(--accent);}
.faq-send{width:38px;height:38px;border-radius:50%;background:var(--accent);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.2s;}
.faq-send:hover{background:#c73333;}
.faq-send svg{width:16px;height:16px;}
.typing-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--gray);animation:td .9s infinite;margin:0 2px;}
.typing-dot:nth-child(2){animation-delay:.2s;}
.typing-dot:nth-child(3){animation-delay:.4s;}
@keyframes td{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}

.ptitle{margin:28px 48px 20px;display:flex;align-items:center;gap:14px;}
.ptitle h1{font-family:'Syne',sans-serif;font-size:28px;font-weight:800;}
.ptitle span{color:var(--gray);font-size:14px;font-family:'DM Sans',sans-serif;font-weight:400;}
.empty{text-align:center;padding:80px;color:var(--gray);}
.empty .em{font-size:64px;margin-bottom:16px;}
.empty p{font-size:16px;}

@keyframes marquee{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}

/* Responsive */

/* ── ACCOUNT DROPDOWN ─────────────────────────────────────── */
.acct-wrap{position:relative;display:inline-block;}
.acct-trigger{display:flex;align-items:center;gap:8px;background:none;border:none;cursor:pointer;padding:0;font-family:'DM Sans',sans-serif;}
.acct-trigger:hover .acct-label{color:var(--accent);}
.acct-avatar{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,var(--accent),#ff6b35);display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;color:#fff;flex-shrink:0;}
.acct-label{font-size:13px;font-weight:600;color:var(--white);transition:color .2s;}
.acct-caret{font-size:10px;color:var(--gray);transition:transform .25s;margin-left:2px;}
.acct-wrap.open .acct-caret{transform:rotate(180deg);}
.acct-menu{position:absolute;top:calc(100% + 14px);right:0;width:230px;background:#fff;border-radius:6px;box-shadow:0 6px 28px rgba(0,0,0,0.2);z-index:700;opacity:0;pointer-events:none;transform:translateY(-6px);transition:opacity .18s,transform .18s;}
.acct-wrap.open .acct-menu{opacity:1;pointer-events:all;transform:translateY(0);}
.acct-menu-hd{padding:14px 18px 10px;border-bottom:1px solid #f0f0f0;}
.acct-menu-hd .am-title{font-size:13px;font-weight:700;color:#212121;}
.acct-menu-item{display:flex;align-items:center;gap:13px;padding:12px 18px;font-size:13px;color:#212121;cursor:pointer;transition:background .15s;text-decoration:none;border:none;background:none;width:100%;text-align:left;font-family:'DM Sans',sans-serif;}
.acct-menu-item:hover{background:#f5f5f5;}
.acct-menu-item .ami-icon{font-size:17px;width:20px;text-align:center;flex-shrink:0;}
.acct-menu-divider{height:1px;background:#f0f0f0;margin:4px 0;}
.acct-menu-item.am-logout:hover{background:#fff3f3;}

/* ── PROFILE MODAL TABS ───────────────────────────────────── */
.pm-tabs{display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:22px;}
.pm-tab{flex:1;padding:11px;font-size:13px;font-weight:600;color:var(--gray);border:none;background:none;cursor:pointer;font-family:'DM Sans',sans-serif;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .2s;}
.pm-tab.active{color:var(--accent);border-bottom-color:var(--accent);}
.pm-tab:hover:not(.active){color:var(--white);}
.pm-pane{display:none;}
.pm-pane.active{display:block;}
.pm-avatar-lg{width:68px;height:68px;border-radius:50%;background:linear-gradient(135deg,var(--accent),#ff6b35);display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:800;color:#fff;margin:0 auto 10px;border:3px solid rgba(255,59,92,.25);}
.pm-field{margin-bottom:14px;}
.pm-field label{display:block;font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--gray);margin-bottom:6px;}
.pm-field input{width:100%;padding:13px 16px;border:1.5px solid var(--border);border-radius:10px;font-size:14px;font-family:'DM Sans',sans-serif;outline:none;transition:all .2s;background:var(--surface2);color:var(--white);}
.pm-field input:focus{border-color:var(--accent);background:var(--surface3);}
.pm-field input:read-only{opacity:.6;cursor:default;}
.pm-save-btn{width:100%;padding:13px;background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;transition:all .2s;margin-top:4px;}
.pm-save-btn:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(255,59,92,.4);}
.pm-save-btn:disabled{opacity:.5;cursor:not-allowed;transform:none;}
.pm-msg{font-size:12px;padding:9px 12px;border-radius:8px;margin-bottom:12px;display:none;}
.pm-msg.ok{background:rgba(0,212,170,.12);color:#00d4aa;border:1px solid rgba(0,212,170,.3);}
.pm-msg.err{background:rgba(255,59,92,.12);color:var(--accent);border:1px solid rgba(255,59,92,.3);}
.pw-strength{height:4px;border-radius:2px;margin-top:6px;transition:all .3s;background:var(--surface3);}
.pw-strength-label{font-size:11px;color:var(--gray);margin-top:4px;}

/* ── HAMBURGER MENU (hidden on desktop) ─────────────────── */
.ham-btn{display:none;background:var(--surface2);border:1.5px solid var(--border);color:var(--white);width:40px;height:40px;border-radius:10px;cursor:pointer;align-items:center;justify-content:center;flex-shrink:0;transition:all .2s;}
.ham-btn:hover{border-color:var(--accent);color:var(--accent);}
.mob-menu{display:none;position:fixed;inset:0;z-index:900;background:rgba(0,0,0,.6);backdrop-filter:blur(6px);}
.mob-menu.open{display:block;}
.mob-menu-panel{position:absolute;left:0;top:0;bottom:0;width:280px;background:var(--surface);border-right:1px solid var(--border);padding:0;overflow-y:auto;transform:translateX(-100%);transition:transform .3s;}
.mob-menu.open .mob-menu-panel{transform:translateX(0);}
.mob-menu-hd{display:flex;align-items:center;justify-content:space-between;padding:18px 16px;border-bottom:1px solid var(--border);}
.mob-menu-hd .brand{font-size:20px;}
.mob-close{background:none;border:none;color:var(--gray);font-size:22px;cursor:pointer;padding:4px;}
.mob-menu-links{padding:8px 0;}
.mob-menu-links a,.mob-menu-links button{display:flex;align-items:center;gap:12px;padding:14px 20px;font-size:14px;font-weight:600;color:var(--white);text-decoration:none;background:none;border:none;width:100%;text-align:left;cursor:pointer;font-family:'DM Sans',sans-serif;transition:background .15s;}
.mob-menu-links a:hover,.mob-menu-links button:hover{background:var(--surface2);color:var(--accent);}
.mob-menu-divider{height:1px;background:var(--border);margin:8px 0;}
.mob-menu-section{padding:10px 20px 4px;font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--gray);}
.mob-auth-btns{display:flex;gap:8px;padding:12px 16px;}
.mob-auth-btns .nbtn{flex:1;text-align:center;padding:11px 10px;}

/* ── 1024px ─────────────────────────────────────────────── */
@media(max-width:1024px){
  .navbar{padding:14px 24px;gap:14px;}
  .sec,.two-col,.features-bar,.fbanner,.newsletter{margin-left:24px;margin-right:24px;}
  .hero{margin-left:24px;margin-right:24px;}
  footer{padding:40px 24px;}
  .caticons{grid-template-columns:repeat(5,1fr);}
  .features-bar{grid-template-columns:repeat(2,1fr);}
  .newsletter{grid-template-columns:1fr;padding:40px 32px;}
  .fg{grid-template-columns:repeat(2,1fr);}
  .two-col{grid-template-columns:1fr;}
  .hero{grid-template-columns:1fr;}
  .hero-side{display:none;}
  .cat-mega{width:580px;}
  .cat-mega-body{grid-template-columns:repeat(2,1fr);}
}

/* ── 768px ──────────────────────────────────────────────── */
@media(max-width:768px){
  /* Navbar — show hamburger, collapse middle items */
  .navbar{padding:12px 16px;gap:10px;}
  .cat-dropdown-wrap{display:none;}
  .search-wrap{flex:1;max-width:none;}
  .nbtn.ol{display:none;}
  .nbtn.fi{display:none;}
  .acct-label,.acct-caret{display:none;}
  .ham-btn{display:flex;}

  /* Category nav */
  .catnav{padding:0 8px;}
  .catnav a{padding:13px 14px;font-size:12px;}

  /* Sections */
  .sec,.two-col,.features-bar,.fbanner,.newsletter{margin-left:16px;margin-right:16px;}
  .hero{margin:16px 16px 24px;grid-template-columns:1fr;}
  .hero-side{display:none;}
  footer{padding:32px 16px;}

  /* Product grid */
  .pgrid{grid-template-columns:repeat(2,1fr);gap:14px;}
  .pcard{flex:0 0 200px;}

  /* Category icons */
  .caticons{grid-template-columns:repeat(4,1fr);gap:10px;}
  .ci{padding:14px 6px;}
  .ci-circle{width:50px;height:50px;font-size:22px;}

  /* Section header */
  .sec-hd{flex-direction:column;align-items:flex-start;gap:10px;}
  .sec-title h2{font-size:22px;}

  /* Features */
  .features-bar{grid-template-columns:repeat(2,1fr);gap:12px;}
  .feat-card{padding:20px 14px;}

  /* Hero */
  .hero-main{padding:36px 24px;}
  .hero-main h1{font-size:34px;font-stretch:normal;}
  .hero-main p{font-size:14px;}

  /* Banner */
  .fbanner{padding:36px 24px;}
  .fbanner h2{font-size:26px;}
  .fbanner-actions{flex-direction:column;gap:10px;}
  .fbanner-cta{width:100%;text-align:center;}

  /* Newsletter */
  .newsletter{padding:32px 24px;}
  .nl-left h2{font-size:24px;}
  .nl-form{flex-direction:column;}
  .nl-btn{border-radius:12px;}

  /* Footer */
  .fg{grid-template-columns:1fr 1fr;gap:24px;}
  .footer-bottom{flex-direction:column;gap:10px;text-align:center;}

  /* Cart drawer full width */
  #cartDrawer{width:100vw!important;}

  /* Modals */
  .mbox{width:calc(100vw - 24px);}
  .contact-grid{grid-template-columns:1fr;}
  .pm-tab{font-size:11px;padding:9px 6px;}
}

/* ── 480px ──────────────────────────────────────────────── */
@media(max-width:480px){
  /* Navbar */
  .navbar{padding:10px 12px;gap:8px;}
  .brand{font-size:20px;}
  .theme-toggle-btn{width:34px;height:34px;}
  .cart-btn{width:38px;height:38px;font-size:16px;}

  /* Announcement */
  .ann-bar{font-size:11px;padding:8px 10px;}

  /* Margins */
  .sec,.two-col,.features-bar,.fbanner,.newsletter{margin-left:12px;margin-right:12px;}
  .hero{margin:12px 12px 20px;}
  footer{padding:24px 12px;}

  /* Hero */
  .hero-main{padding:28px 18px;}
  .hero-main h1{font-size:26px;}
  .hero-main p{font-size:13px;margin-bottom:20px;}
  .hero-main::after{font-size:80px;right:18px;}

  /* Product cards */
  .pgrid{grid-template-columns:repeat(2,1fr);gap:10px;}
  .pcard{flex:0 0 155px;}
  .pcard-img{height:120px;}
  .pcard-emoji{font-size:60px;}
  .pcard-body{padding:10px;}
  .pcard-name{font-size:12px;}
  .price-current{font-size:15px;}
  .add-cart-btn{font-size:12px;padding:9px;gap:5px;}

  /* Category icons */
  .caticons{grid-template-columns:repeat(3,1fr);gap:8px;}
  .ci{padding:12px 4px;}
  .ci-circle{width:44px;height:44px;font-size:20px;}
  .ci-label{font-size:10px;}

  /* Section title */
  .sec-title h2{font-size:19px;}

  /* Features */
  .features-bar{grid-template-columns:1fr;}
  .feat-card{padding:16px;}

  /* Banner */
  .fbanner{padding:28px 16px;}
  .fbanner h2{font-size:22px;}

  /* Newsletter */
  .newsletter{padding:24px 16px;}
  .nl-left h2{font-size:21px;}

  /* Footer single col */
  .fg{grid-template-columns:1fr;}

  /* Tabs */
  .tabs{gap:6px;}
  .tab{padding:7px 12px;font-size:11px;}

  /* Countdown */
  .cdu{padding:4px 7px;font-size:12px;min-width:28px;}

  /* Modals */
  .mbox{width:calc(100vw - 16px);padding:20px 14px;}
  .mhd{padding:14px 16px;}
}
</style>
</head>
<body>

<!-- ANNOUNCEMENT BAR -->
<div class="ann-bar">🔥 Flash Sale LIVE! Up to 50% OFF · Free shipping on orders ₹999+ · Use code <strong>FIRST10</strong> for extra 10% off</div>

<!-- NAVBAR -->
<nav class="navbar" id="mainNav">
  <a href="/" class="brand">
    <span class="brand-my">My</span><span class="brand-store">Store</span>
    <div class="brand-dot"></div>
  </a>

  <!-- CATEGORY DROPDOWN -->
  <div class="cat-dropdown-wrap" id="catDropWrap">
    <button class="cat-dropdown-btn" id="catDropBtn" onclick="toggleCatDrop(event)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      Categories
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
    </button>
    <div class="cat-mega" id="catMega">
      <div class="cat-mega-hd"><span>🛍️ Shop by Category</span></div>
      <div class="cat-mega-body">
        <!-- Electronics -->
        <div class="cat-col">
          <div class="cat-col-title"><span>⚡</span> Electronics</div>
          <a href="/?sub=Smartphones" class="cat-item"><span class="ci-em">📱</span> Smartphones</a>
          <a href="/?sub=Laptops" class="cat-item"><span class="ci-em">💻</span> Laptops & Computers</a>
          <a href="/?sub=Audio" class="cat-item"><span class="ci-em">🎧</span> Audio & Headphones</a>
          <a href="/?sub=Cameras" class="cat-item"><span class="ci-em">📸</span> Cameras</a>
          <a href="/?sub=TVs" class="cat-item"><span class="ci-em">📺</span> TVs & Displays</a>
          <a href="/?sub=PC Accessories" class="cat-item"><span class="ci-em">⌨️</span> PC Accessories</a>
        </div>
        <!-- Fashion -->
        <div class="cat-col">
          <div class="cat-col-title"><span>👗</span> Fashion</div>
          <a href="/?sub=T-Shirt" class="cat-item"><span class="ci-em">👕</span> T-Shirts</a>
          <a href="/?sub=Shirt" class="cat-item"><span class="ci-em">👔</span> Shirts</a>
          <a href="/?sub=Jeans" class="cat-item"><span class="ci-em">👖</span> Jeans & Trousers</a>
          <a href="/?sub=Jacket" class="cat-item"><span class="ci-em">🧥</span> Jackets & Coats</a>
          <a href="/?sub=Shoes" class="cat-item"><span class="ci-em">👟</span> Shoes & Footwear</a>
          <a href="/?category=Fashion" class="cat-item"><span class="ci-em">👗</span> Dresses & Ethnic</a>
        </div>
        <!-- Accessories -->
        <div class="cat-col">
          <div class="cat-col-title"><span>💼</span> Accessories</div>
          <a href="/?sub=Watches" class="cat-item"><span class="ci-em">⌚</span> Watches</a>
          <a href="/?sub=Bag" class="cat-item"><span class="ci-em">👜</span> Bags & Wallets</a>
          <a href="/?sub=Glasses" class="cat-item"><span class="ci-em">🕶️</span> Sunglasses</a>
          <a href="/?sub=Jewellery" class="cat-item"><span class="ci-em">💍</span> Jewellery</a>
          <a href="/?category=Accessories" class="cat-item"><span class="ci-em">🧣</span> Belts & Scarves</a>
          <a href="/?flash=1" class="cat-item"><span class="ci-em">🔥</span> Flash Sale Deals</a>
        </div>
      </div>
      <div class="cat-mega-footer">
        <a href="/?category=all" class="cat-see-all">Browse All Products →</a>
      </div>
    </div>
  </div>
  <div class="search-wrap">
    <span class="search-icon">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    </span>
    <input type="text" id="searchInput" placeholder="Search products, brands, categories..." value="{{ sv }}" onkeydown="if(event.key==='Enter')doSearch()">
    <button class="search-btn" onclick="doSearch()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    </button>
  </div>
  <!-- MOBILE HAMBURGER -->
  <button class="ham-btn" onclick="openMobMenu()" aria-label="Open menu">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
  </button>
  <div class="nav-actions">
    <button class="theme-toggle-btn" id="themeToggleBtn" onclick="toggleTheme()" title="Toggle dark/light theme" aria-label="Toggle theme">
      <svg id="theme-icon-dark" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:none"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      <svg id="theme-icon-light" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
    </button>
    {% if current_user.is_authenticated %}
      <div class="acct-wrap" id="acctWrap">
        <button class="acct-trigger" onclick="toggleAcct(event)">
          <div class="acct-avatar">{{ current_user.username[0]|upper }}</div>
          <span class="acct-label">{{ current_user.username }}</span>
          <span class="acct-caret">▾</span>
        </button>
        <div class="acct-menu" id="acctMenu">
          <div class="acct-menu-hd"><div class="am-title">Your Account</div></div>
          <button class="acct-menu-item" onclick="openProfileModal('info')">
            <span class="ami-icon">👤</span> My Profile
          </button>
          <a class="acct-menu-item" href="/orders">
            <span class="ami-icon">📦</span> Orders
          </a>
          <button class="acct-menu-item" onclick="openProfileModal('edit')">
            <span class="ami-icon">✏️</span> Edit Profile
          </button>
          <button class="acct-menu-item" onclick="openProfileModal('password')">
            <span class="ami-icon">🔑</span> Change Password
          </button>
          <button class="acct-menu-item" onclick="window.location='/track-order';closeAcct()">
            <span class="ami-icon">🚚</span> Track Order
          </button>
          <button class="acct-menu-item" onclick="showToast('Wishlist coming soon! ❤️','info');closeAcct()">
            <span class="ami-icon">❤️</span> Wishlist
          </button>
          <button class="acct-menu-item" onclick="window.location='/faq';closeAcct()">
            <span class="ami-icon">❓</span> Help & FAQ
          </button>
          {% if current_user.is_admin %}
          <a class="acct-menu-item" href="/admin" style="color:var(--accent3);font-weight:700;">
            <span class="ami-icon">⚙️</span> Admin Panel
          </a>
          {% endif %}
          <div class="acct-menu-divider"></div>
          <a class="acct-menu-item am-logout" href="/logout">
            <span class="ami-icon">🚪</span> Logout
          </a>
        </div>
      </div>
    {% else %}
      <button class="nbtn ol" onclick="openModal('registerModal')">Sign Up</button>
      <button class="nbtn fi" onclick="openModal('loginModal')">Login</button>
    {% endif %}
    <button class="cart-btn" onclick="openCart()" id="cartBtn">
      🛒
      {% if cc > 0 %}<span class="cbadge" id="cartBadge">{{ cc }}</span>{% endif %}
    </button>
  </div>
</nav>

<!-- MOBILE MENU -->
<div class="mob-menu" id="mobMenu" onclick="closeMobMenu(event)">
  <div class="mob-menu-panel">
    <div class="mob-menu-hd">
      <span class="brand"><span class="brand-my">My</span><span class="brand-store">Store</span></span>
      <button class="mob-close" onclick="closeMobMenuDirect()">✕</button>
    </div>
    <div class="mob-menu-links">
      <div class="mob-menu-section">Browse</div>
      <a href="/">🏠 All Products</a>
      <a href="/?category=Electronics">⚡ Electronics</a>
      <a href="/?category=Fashion">👗 Fashion</a>
      <a href="/?category=Accessories">💼 Accessories</a>
      <a href="/?flash=1">🔥 Flash Sale</a>
      <div class="mob-menu-divider"></div>
      <div class="mob-menu-section">Categories</div>
      <a href="/?sub=Smartphones">📱 Smartphones</a>
      <a href="/?sub=Laptops">💻 Laptops</a>
      <a href="/?sub=Audio">🎧 Audio</a>
      <a href="/?sub=T-Shirt">👕 T-Shirts</a>
      <a href="/?sub=Shoes">👟 Shoes</a>
      <a href="/?sub=Watches">⌚ Watches</a>
      <div class="mob-menu-divider"></div>
      <div class="mob-menu-section">Account</div>
      <a href="/orders">📦 My Orders</a>
      <a href="/track-order">🚚 Track Order</a>
      <a href="/faq">❓ Help & FAQ</a>
    </div>
    <div class="mob-auth-btns">
      <button class="nbtn ol" onclick="openModal('registerModal');closeMobMenuDirect()">Sign Up</button>
      <button class="nbtn fi" onclick="openModal('loginModal');closeMobMenuDirect()">Login</button>
    </div>
  </div>
</div>

<!-- CART DRAWER -->
<div class="cart-overlay" id="cartOverlay" onclick="closeCart()"></div>
<div class="cart-drawer" id="cartDrawer">
  <div class="cart-drawer-hd">
    <div>
      <h3>Your Cart 🛒</h3>
      <div class="cc-info" id="cartCount">{{ cc }} item(s)</div>
    </div>
    <button class="cart-close" onclick="closeCart()">✕</button>
  </div>
  <div class="cart-body" id="cartBody">
    {{ ch | safe }}
  </div>
  <div class="cart-footer" id="cartFooter" style="{{ 'display:none' if cc == 0 else '' }}">
    <div class="cart-total-row">
      <span class="cart-total-label">Total Amount</span>
      <span class="cart-total-val" id="cartTotal">₹{{ cart_total | default(0) | int | format_num }}</span>
    </div>
    <a href="/checkout"><button class="cart-checkout-btn">Proceed to Checkout →</button></a>
    <a href="/cart" onclick="closeCart()"><button class="cart-view-btn">🛒 View Full Cart</button></a>
  </div>
</div>

<!-- CATEGORY NAV -->
<nav class="catnav">
  <a href="/" class="{{ 'active' if not ac and not sv and not fo else '' }}">🏠 All</a>
  <a href="/?category=Electronics" class="{{ 'active' if ac == 'Electronics' else '' }}">⚡ Electronics</a>
  <a href="/?category=Fashion" class="{{ 'active' if ac == 'Fashion' else '' }}">👗 Fashion</a>
  <a href="/?category=Accessories" class="{{ 'active' if ac == 'Accessories' else '' }}">💼 Accessories</a>
  <a href="/?flash=1" class="{{ 'active' if fo else '' }}">🔥 Flash Sale</a>
  <a href="/orders" class="">📋 My Orders</a>
</nav>

{{ pc | safe }}

<!-- FEATURES BAR -->
<div class="features-bar">
  <div class="feat-card">
    <div class="feat-icon">🚀</div>
    <div><div class="feat-title">Express Delivery</div><div class="feat-desc">1-2 day delivery available</div></div>
  </div>
  <div class="feat-card">
    <div class="feat-icon">↩️</div>
    <div><div class="feat-title">7-Day Returns</div><div class="feat-desc">Hassle-free return policy</div></div>
  </div>
  <div class="feat-card">
    <div class="feat-icon">🔒</div>
    <div><div class="feat-title">Secure Payments</div><div class="feat-desc">256-bit SSL encryption</div></div>
  </div>
  <div class="feat-card">
    <div class="feat-icon">💬</div>
    <div><div class="feat-title">24/7 AI Support</div><div class="feat-desc">Instant help anytime</div></div>
  </div>
</div>

<!-- NEWSLETTER -->
<div class="newsletter">
  <div class="nl-left">
    <h2>Stay in the <em>loop</em> 📬</h2>
    <p>Get exclusive deals, early access to flash sales, and new arrivals straight to your inbox.</p>
  </div>
  <div>
    <div class="nl-form">
      <input class="nl-input" id="nlEmailInput" type="email" placeholder="Enter your email address">
      <button class="nl-btn" onclick="handleSubscribe()">Subscribe</button>
    </div>
  </div>
</div>

<!-- FOOTER -->
<footer>
  <div class="fg">
    <div class="fc-brand">
      <div class="fc-brand-logo">My<span>Store</span></div>
      <p>Your one-stop destination for Electronics, Fashion & Accessories. Shop beyond boundaries.</p>
      <div class="social-links">
        <!-- Facebook — opens MyStore Facebook page -->
        <a href="https://www.facebook.com/sharer/sharer.php?u=https://mystore.in&quote=Shop+at+MyStore+%E2%80%94+Up+to+50%25+OFF+on+Electronics%2C+Fashion+%26+Accessories!+%F0%9F%9B%8D%EF%B8%8F"
           target="_blank" rel="noopener noreferrer"
           class="soc fb" title="Share MyStore on Facebook"
           onclick="showToast('Opening Facebook… 👍','info')">
          <svg viewBox="0 0 24 24"><path d="M13.397 20.997v-8.196h2.765l.411-3.209h-3.176V7.548c0-.926.258-1.56 1.587-1.56h1.684V3.127A22.336 22.336 0 0 0 14.201 3c-2.444 0-4.122 1.492-4.122 4.231v2.355H7.332v3.209h2.753v8.202h3.312z"/></svg>
        </a>
        <!-- Pinterest — pins MyStore to Pinterest -->
        <a href="https://pinterest.com/pin/create/button/?url=https://mystore.in&description=Shop+Electronics%2C+Fashion+%26+Accessories+at+MyStore+%E2%80%94+Up+to+50%25+OFF!+%F0%9F%9B%8D%EF%B8%8F"
           target="_blank" rel="noopener noreferrer"
           class="soc pin" title="Pin MyStore on Pinterest"
           onclick="showToast('Opening Pinterest… 📌','info')">
          <svg viewBox="0 0 24 24"><path d="M12 2C6.477 2 2 6.477 2 12c0 4.236 2.636 7.855 6.356 9.312-.088-.791-.167-2.005.035-2.868.181-.78 1.172-4.97 1.172-4.97s-.299-.598-.299-1.482c0-1.388.806-2.428 1.808-2.428.853 0 1.267.641 1.267 1.408 0 .858-.546 2.14-.828 3.33-.236.995.499 1.806 1.476 1.806 1.772 0 2.963-2.29 2.963-5.008 0-2.063-1.375-3.575-3.845-3.575-2.8 0-4.532 2.095-4.532 4.41 0 .8.235 1.368.602 1.798.168.197.192.276.13.503-.043.166-.143.566-.185.724-.06.232-.246.315-.452.229-1.266-.52-1.854-1.918-1.854-3.487 0-2.583 2.184-5.703 6.517-5.703 3.496 0 5.808 2.544 5.808 5.276 0 3.613-1.998 6.322-4.928 6.322-.987 0-1.915-.531-2.232-1.124l-.617 2.378c-.221.823-.807 1.84-1.219 2.484.935.286 1.924.44 2.948.44 5.523 0 10-4.477 10-10S17.523 2 12 2z"/></svg>
        </a>
        <!-- WhatsApp — opens WhatsApp with pre-filled store message -->
        <a href="https://wa.me/?text=Hey!+Check+out+MyStore+%F0%9F%9B%8D%EF%B8%8F+%E2%80%94+Up+to+50%25+OFF+on+Electronics%2C+Fashion+%26+Accessories%21+Shop+now+at+https%3A%2F%2Fmystore.in"
           target="_blank" rel="noopener noreferrer"
           class="soc wa" title="Share MyStore on WhatsApp"
           onclick="showToast('Opening WhatsApp… 💬','info')">
          <svg viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z"/></svg>
        </a>
      </div>
    </div>

    <!-- COMPANY links -->
    <div class="fc">
      <h4>Company</h4>
      <a href="/about">About Us</a>
      <a href="/careers">Careers</a>
      <a href="/press">Press</a>
      <a href="/contact">Contact</a>
      <a href="/blog">Blog</a>
    </div>

    <!-- SHOPPING links -->
    <div class="fc">
      <h4>Shopping</h4>
      <a href="#" onclick="openModal('registerModal');return false;">Registration</a>
      <a href="/orders">Orders &amp; Returns</a>
      <a href="/help">Help Center</a>
      <a href="/track-order">Track Order</a>
    </div>

    <!-- SUPPORT links -->
    <div class="fc">
      <h4>Support</h4>
      <a href="/faq">FAQ</a>
      <a href="/shipping-policy">Shipping Policy</a>
      <a href="/privacy-policy">Privacy Policy</a>
      <a href="/terms">Terms of Service</a>
    </div>
  </div>
  <div class="footer-bottom">
    <span>© 2026 MyStore. All rights reserved. Made with ❤️ in India</span>
    <span>🔒 Secured by SSL · PCI DSS Compliant</span>
  </div>
</footer>

<!-- ===== INFO MODAL (reusable for all footer links) ===== -->
<div id="infoModal" class="modal-overlay">
  <div class="mbox" style="width:520px;max-height:80vh;overflow-y:auto;">
    <div class="mhd" style="position:sticky;top:0;background:var(--surface);z-index:2;padding-bottom:16px;">
      <div class="mhd-info">
        <h2 id="infoModalTitle">Info</h2>
        <p id="infoModalSub" style="color:var(--gray);font-size:13px;margin-top:4px;"></p>
      </div>
      <button class="mclose" onclick="closeModal('infoModal')">✕</button>
    </div>
    <div class="mbody" style="padding-top:8px;" id="infoModalBody"></div>
  </div>
</div>

<!-- ============================================================
     LOGIN MODAL  — now has eye-toggle on password field
     ============================================================ -->
<div id="loginModal" class="modal-overlay">
  <div class="mbox">
    <div class="mhd">
      <div class="mhd-info"><h2>Welcome Back 👋</h2><p>Sign in to continue shopping</p></div>
      <button class="mclose" onclick="closeModal('loginModal')">✕</button>
    </div>
    <div class="mbody">
      <!-- ── SOCIAL LOGIN ── -->
      <a href="/auth/google" class="social-btn google-btn">
        <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.11 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-3.59-13.46-8.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>
        Continue with Google
      </a>
      <!-- ── DIVIDER ── -->
      <div class="or-divider"><span>or sign in with email</span></div>
      <form method="post" action="/login">
        <input class="minput" name="username" placeholder="Username or Email" required autocomplete="username">
        <!-- PASSWORD with eye toggle -->
        <div class="pass-wrap">
          <input class="minput pass-input" name="password" type="password" id="login_password"
                 placeholder="Your password" required autocomplete="current-password">
          <button type="button" class="eye-btn" onclick="toggleEye('login_password', this)" tabindex="-1"
                  title="Show / hide password">
            <!-- Eye-open icon (shown by default — password is hidden) -->
            <svg class="eye-open" width="18" height="18" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
            <!-- Eye-slash icon (hidden by default) -->
            <svg class="eye-shut" width="18" height="18" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                 style="display:none">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94
                       M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19
                       m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
              <line x1="1" y1="1" x2="23" y2="23"/>
            </svg>
          </button>
        </div>
        <button class="msub" type="submit">Sign In →</button>
      </form>
      <div class="mswitch">No account? <a onclick="closeModal('loginModal');openModal('registerModal')">Create one</a></div>
    </div>
  </div>
</div>

<!-- REGISTER MODAL (unchanged — already had eye toggles) -->
<div id="registerModal" class="modal-overlay">
  <div class="mbox">
    <div class="mhd">
      <div class="mhd-info"><h2>Create Account ✨</h2><p>Join thousands of happy shoppers</p></div>
      <button class="mclose" onclick="closeModal('registerModal')">✕</button>
    </div>
    <div class="mbody">
      <!-- ── SOCIAL SIGN-UP ── -->
      <a href="/auth/google" class="social-btn google-btn">
        <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.11 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-3.59-13.46-8.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>
        Sign up with Google
      </a>
      <!-- ── DIVIDER ── -->
      <div class="or-divider"><span>or create account with email</span></div>
      <form method="post" action="/register" id="regForm" onsubmit="return validateReg()">
        <input class="minput" name="username" id="reg_username" placeholder="Choose a username" required autocomplete="username">
        <input class="minput" name="email" id="reg_email" type="email" placeholder="Your email address" required autocomplete="email">
        <div class="pass-wrap">
          <input class="minput pass-input" name="password" type="password" id="reg_password"
                 placeholder="Create a strong password (min 6 chars)" required autocomplete="new-password">
          <button type="button" class="eye-btn" onclick="toggleEye('reg_password',this)" tabindex="-1">
            <svg class="eye-open" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <svg class="eye-shut" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:none"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
          </button>
        </div>
        <div class="pass-wrap">
          <input class="minput pass-input" id="reg_confirm" type="password"
                 placeholder="Confirm your password" required autocomplete="new-password">
          <button type="button" class="eye-btn" onclick="toggleEye('reg_confirm',this)" tabindex="-1">
            <svg class="eye-open" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <svg class="eye-shut" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:none"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
          </button>
        </div>
        <div id="regError" style="display:none;color:var(--accent);font-size:13px;margin-bottom:10px;padding:10px 14px;background:rgba(255,59,92,0.1);border-radius:8px;border:1px solid rgba(255,59,92,0.25);"></div>
        <button class="msub" type="submit">Create Account →</button>
      </form>
      <div class="mswitch">Already have an account? <a onclick="closeModal('registerModal');openModal('loginModal')">Sign In</a></div>
    </div>
  </div>
</div>


<!-- ══ PROFILE MODAL ══ -->
<div id="profileModal" class="modal-overlay">
  <div class="mbox" style="width:440px;max-height:90vh;overflow-y:auto;">
    <div class="mhd" style="position:sticky;top:0;background:var(--surface);z-index:2;padding-bottom:16px;">
      <div class="mhd-info"><h2>My Account</h2><p id="pmSubtitle">Profile &amp; Settings</p></div>
      <button class="mclose" onclick="closeModal('profileModal')">✕</button>
    </div>
    <div class="mbody" style="padding-top:0;">

      <!-- Avatar row -->
      <div style="text-align:center;margin-bottom:18px;">
        <div class="pm-avatar-lg" id="pmAvatar">?</div>
        <div id="pmDisplayName" style="font-family:'Syne',sans-serif;font-size:17px;font-weight:700;"></div>
        <div id="pmDisplayEmail" style="font-size:12px;color:var(--gray);margin-top:3px;"></div>
      </div>

      <!-- Tabs -->
      <div class="pm-tabs">
        <button class="pm-tab active" onclick="switchPmTab('info',this)">👤 Info</button>
        <button class="pm-tab" onclick="switchPmTab('edit',this)">✏️ Edit Profile</button>
        <button class="pm-tab" onclick="switchPmTab('password',this)">🔑 Password</button>
      </div>

      <!-- ── TAB: INFO ── -->
      <div class="pm-pane active" id="pmPane-info">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:18px;">
          <div style="background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center;">
            <div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;" id="pmOrderCount">0</div>
            <div style="font-size:11px;color:var(--gray);margin-top:3px;">Total Orders</div>
          </div>
          <div style="background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center;">
            <div style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;" id="pmCartCount">0</div>
            <div style="font-size:11px;color:var(--gray);margin-top:3px;">Cart Items</div>
          </div>
        </div>
        <div class="pm-field"><label>Username</label><input id="pmInfoU" readonly></div>
        <div class="pm-field"><label>Email</label><input id="pmInfoE" readonly></div>
        <div class="pm-field"><label>Member Since</label><input id="pmInfoSince" readonly></div>
        <button class="pm-save-btn" style="background:var(--surface2);border:1.5px solid var(--border);color:var(--white);" onclick="switchPmTab('edit',document.querySelectorAll('.pm-tab')[1])">✏️ Edit My Profile</button>
      </div>

      <!-- ── TAB: EDIT PROFILE ── -->
      <div class="pm-pane" id="pmPane-edit">
        <div class="pm-msg" id="editMsg"></div>
        <div class="pm-field">
          <label>New Username</label>
          <input id="editUsername" placeholder="Enter new username">
        </div>
        <div class="pm-field">
          <label>New Email</label>
          <input id="editEmail" type="email" placeholder="Enter new email">
        </div>
        <div class="pm-field">
          <label>Current Password (required to save)</label>
          <input id="editCurrentPw" type="password" placeholder="Confirm with current password">
        </div>
        <button class="pm-save-btn" onclick="saveProfile()">💾 Save Changes</button>
      </div>

      <!-- ── TAB: PASSWORD ── -->
      <div class="pm-pane" id="pmPane-password">
        <div class="pm-msg" id="pwMsg"></div>
        <div class="pm-field">
          <label>Current Password</label>
          <input id="pwCurrent" type="password" placeholder="Your current password">
        </div>
        <div class="pm-field">
          <label>New Password</label>
          <input id="pwNew" type="password" placeholder="Min 6 characters" oninput="checkPwStrength(this.value)">
          <div class="pw-strength" id="pwStrengthBar"></div>
          <div class="pw-strength-label" id="pwStrengthLabel"></div>
        </div>
        <div class="pm-field">
          <label>Confirm New Password</label>
          <input id="pwConfirm" type="password" placeholder="Repeat new password">
        </div>
        <button class="pm-save-btn" onclick="savePassword()">🔑 Update Password</button>
      </div>

    </div>
  </div>
</div>

<!-- TOAST STACK -->
<div class="toast-stack" id="toastStack"></div>

<!-- AI CHAT WIDGET -->
<div class="faq-bubble" id="faqBubble">
  <div class="faq-window" id="faqWindow">
    <div class="faq-header">
      <div class="faq-avatar">🤖</div>
      <div class="faq-header-info">
        <h4>Myra — AI Assistant</h4>
        <p>Online · Powered by Claude AI</p>
      </div>
      <button class="chat-clear-btn" onclick="clearChat()" title="Clear conversation">🗑️</button>
      <button class="faq-close" onclick="toggleFAQ()">✕</button>
    </div>
    <div class="faq-msgs" id="faqMsgs">
      <div class="msg bot">
        <div class="msg-avatar">🤖</div>
        <div class="msg-bubble">Hi! 👋 I'm <strong>Myra</strong>, your MyStore AI assistant.<br>Ask me about products, deals, shipping, returns — anything! 🛍️</div>
      </div>
    </div>
    <div class="faq-suggestions" id="faqChips">
      <span class="faq-chip" onclick="askChip(this)">🔥 Flash Sale deals?</span>
      <span class="faq-chip" onclick="askChip(this)">📦 Shipping info</span>
      <span class="faq-chip" onclick="askChip(this)">↩️ Return policy</span>
      <span class="faq-chip" onclick="askChip(this)">💳 Payment methods</span>
      <span class="faq-chip" onclick="askChip(this)">📱 Best phone under ₹30k?</span>
    </div>
    <div class="faq-input-row">
      <input class="faq-input" id="faqInput" placeholder="Ask Myra anything..." onkeydown="if(event.key==='Enter')sendFAQ()">
      <button class="faq-send" id="faqSendBtn" onclick="sendFAQ()">
        <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </div>
  </div>
  <button class="faq-toggle" onclick="toggleFAQ()" title="Chat with Myra — AI Assistant">
    <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    <span class="faq-ping"></span>
  </button>
</div>

<script>
// ===== MOBILE MENU =====
function openMobMenu(){document.getElementById('mobMenu').classList.add('open');document.body.style.overflow='hidden';}
function closeMobMenuDirect(){document.getElementById('mobMenu').classList.remove('open');document.body.style.overflow='';}
function closeMobMenu(e){if(e.target===document.getElementById('mobMenu'))closeMobMenuDirect();}

// ===== SEARCH =====
function doSearch(){
  var q = document.getElementById('searchInput').value.trim();
  if(q) window.location.href = '/?search=' + encodeURIComponent(q);
}

// ===== CATEGORY DROPDOWN =====
function toggleCatDrop(e){
  e.stopPropagation();
  var btn = document.getElementById('catDropBtn');
  var mega = document.getElementById('catMega');
  var isOpen = mega.classList.contains('open');
  closeCatDrop();
  if(!isOpen){ btn.classList.add('open'); mega.classList.add('open'); }
}
function closeCatDrop(){
  var btn = document.getElementById('catDropBtn');
  var mega = document.getElementById('catMega');
  if(btn) btn.classList.remove('open');
  if(mega) mega.classList.remove('open');
}
document.addEventListener('click', function(e){
  var wrap = document.getElementById('catDropWrap');
  if(wrap && !wrap.contains(e.target)) closeCatDrop();
});

// ===== MODALS =====
function openModal(id){document.getElementById(id).classList.add('open');}
function closeModal(id){document.getElementById(id).classList.remove('open');}
window.addEventListener('click',function(e){
  ['loginModal','registerModal','infoModal','profileModal'].forEach(function(id){
    if(e.target===document.getElementById(id))closeModal(id);
  });
});

// ===== CART DRAWER =====
function openCart(){
  document.getElementById('cartDrawer').classList.add('open');
  document.getElementById('cartOverlay').classList.add('open');
  document.body.style.overflow='hidden';
}
function closeCart(){
  document.getElementById('cartDrawer').classList.remove('open');
  document.getElementById('cartOverlay').classList.remove('open');
  document.body.style.overflow='';
}

// ===== ADD TO CART (AJAX) =====
function addToCart(productId, btn){
  btn.classList.add('adding');
  btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Added!';
  btn.disabled = true;
  fetch('/add-ajax/' + productId, {method:'POST', headers:{'Content-Type':'application/json'}})
    .then(function(r){return r.json();})
    .then(function(data){
      if(data.success){
        updateCartUI(data);
        showToast(data.product_name + ' added to cart!','success');
      } else {
        showToast(data.message || 'Error adding to cart','error');
      }
      setTimeout(function(){
        btn.classList.remove('adding');
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg> Add to Cart';
        btn.disabled = false;
      }, 1800);
    })
    .catch(function(){
      showToast('Something went wrong. Try again!','error');
      btn.classList.remove('adding');
      btn.disabled = false;
    });
}

function updateCartUI(data){
  var badge = document.getElementById('cartBadge');
  if(data.count > 0){
    if(!badge){
      badge = document.createElement('span');
      badge.id = 'cartBadge';
      badge.className = 'cbadge';
      document.getElementById('cartBtn').appendChild(badge);
    }
    badge.textContent = data.count;
  } else {
    if(badge) badge.textContent = '';
  }
  var cc = document.getElementById('cartCount');
  if(cc) cc.textContent = data.count + ' item(s)';
  if(data.cart_html) document.getElementById('cartBody').innerHTML = data.cart_html;
  if(data.total !== undefined){
    var tv = document.getElementById('cartTotal');
    if(tv) tv.textContent = '₹' + data.total.toLocaleString('en-IN');
  }
  var footer = document.getElementById('cartFooter');
  if(footer) footer.style.display = data.count > 0 ? '' : 'none';
}

function removeFromCart(cartId){
  fetch('/remove-cart/' + cartId, {method:'POST'})
    .then(function(r){return r.json();})
    .then(function(data){updateCartUI(data);showToast('Item removed from cart','info');});
}

function updateQty(cartId, delta){
  fetch('/update-cart-qty/' + cartId, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({delta:delta})})
    .then(function(r){return r.json();})
    .then(function(data){updateCartUI(data);});
}

// ===== WISHLIST =====
function toggleWish(btn){
  btn.classList.toggle('active');
  btn.innerHTML = btn.classList.contains('active') ? '&#10084;' : '&#9825;';
  showToast(btn.classList.contains('active') ? 'Added to wishlist ❤️' : 'Removed from wishlist','info');
}

// ===== TOAST =====
function showToast(msg, type){
  var stack = document.getElementById('toastStack');
  var t = document.createElement('div');
  t.className = 'toast ' + (type||'success');
  var icon = type==='success'?'✓':type==='error'?'✕':'ℹ';
  t.innerHTML = '<span style="font-size:18px">' + icon + '</span><span>' + msg + '</span>';
  stack.appendChild(t);
  setTimeout(function(){
    t.style.opacity='0';t.style.transform='translateX(24px)';t.style.transition='all 0.3s';
    setTimeout(function(){if(t.parentNode)t.parentNode.removeChild(t);},300);
  }, 3000);
}

// ===== COUNTDOWN =====
function updateCD(){
  var end=new Date();end.setHours(23,59,59,0);
  var d=Math.max(0,Math.floor((end-new Date())/1000));
  var pad=function(n){return String(n).padStart(2,'0');};
  var h=document.getElementById('cdh'),m=document.getElementById('cdm'),s=document.getElementById('cds');
  if(h)h.textContent=pad(Math.floor(d/3600));
  if(m)m.textContent=pad(Math.floor((d%3600)/60));
  if(s)s.textContent=pad(d%60);
}
setInterval(updateCD,1000);updateCD();

// ===== TAB FILTER =====
function filterTab(el,cat){
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
  el.classList.add('active');
  var all = Array.from(document.querySelectorAll('#tgrid .pcard'));
  var visible = all.filter(function(c){return cat==='all'||c.dataset.category===cat;});
  var shown = 0;
  all.forEach(function(c){
    if((cat==='all'||c.dataset.category===cat) && shown<9){
      c.style.display=''; shown++;
    } else {
      c.style.display='none';
    }
  });
}

// ===== REGISTRATION VALIDATION =====
function validateReg(){
  var errEl = document.getElementById('regError');
  var u = document.getElementById('reg_username').value.trim();
  var e = document.getElementById('reg_email').value.trim();
  var p = document.getElementById('reg_password').value;
  var c = document.getElementById('reg_confirm').value;
  if(!u){errEl.textContent='Please enter a username.';errEl.style.display='block';return false;}
  if(!e||!e.includes('@')){errEl.textContent='Please enter a valid email address.';errEl.style.display='block';return false;}
  if(p.length<6){errEl.textContent='Password must be at least 6 characters.';errEl.style.display='block';return false;}
  if(p!==c){errEl.textContent='Passwords do not match.';errEl.style.display='block';return false;}
  errEl.style.display='none';
  return true;
}

// ===== EYE TOGGLE — shared by login & register =====
function toggleEye(inputId, btn){
  var inp = document.getElementById(inputId);
  var isHidden = inp.type === 'password';
  inp.type = isHidden ? 'text' : 'password';
  btn.querySelector('.eye-open').style.display = isHidden ? 'none' : '';
  btn.querySelector('.eye-shut').style.display = isHidden ? '' : 'none';
  // accent colour when visible, gray when hidden
  btn.style.color = isHidden ? 'var(--accent)' : 'var(--gray)';
}

// ===== FAQ ASSISTANT =====
function toggleFAQ(){
  var w=document.getElementById('faqWindow');
  w.classList.toggle('open');
  if(w.classList.contains('open')){document.getElementById('faqInput').focus();scrollMsgs();}
}
function scrollMsgs(){var m=document.getElementById('faqMsgs');setTimeout(function(){m.scrollTop=m.scrollHeight;},60);}
function addMsg(text,role){
  var msgs=document.getElementById('faqMsgs');
  var d=document.createElement('div');d.className='msg '+role;
  d.innerHTML=role==='bot'
    ?'<div class="msg-avatar">🤖</div><div class="msg-bubble">'+text+'</div>'
    :'<div class="msg-bubble">'+text+'</div>';
  msgs.appendChild(d);scrollMsgs();
}
function showTyping(){
  var msgs=document.getElementById('faqMsgs');
  var d=document.createElement('div');d.className='msg bot';d.id='typingIndicator';
  d.innerHTML='<div class="msg-avatar">🤖</div><div class="msg-bubble"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>';
  msgs.appendChild(d);scrollMsgs();
}
function hideTyping(){var t=document.getElementById('typingIndicator');if(t)t.remove();}
function askChip(el){
  document.getElementById('faqChips').style.display='none';
  var q = el.textContent.replace(/^[^a-zA-Z0-9₹]*/,'').trim();
  addMsg(el.textContent,'user');
  var inp=document.getElementById('faqInput');
  var btn=document.getElementById('faqSendBtn');
  if(inp) inp.disabled=true; if(btn) btn.disabled=true;
  getBotReply(q, function(){
    if(inp) inp.disabled=false; if(btn) btn.disabled=false;
    if(inp) inp.focus();
  });
}
function sendFAQ(){
  var inp=document.getElementById('faqInput');
  var btn=document.getElementById('faqSendBtn');
  var q=inp.value.trim();if(!q)return;
  addMsg(q,'user');inp.value='';
  document.getElementById('faqChips').style.display='none';
  // Disable input while waiting
  inp.disabled=true; if(btn) btn.disabled=true;
  getBotReply(q, function(){
    inp.disabled=false; if(btn) btn.disabled=false; inp.focus();
  });
}
// Conversation history for multi-turn memory
var chatHistory = [];

function getBotReply(question, done){
  showTyping();
  // Add user msg to history before sending
  chatHistory.push({role:'user', content:question});

  fetch('/chat',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({question:question, history:chatHistory.slice(0,-1)})
  })
  .then(function(r){return r.json();})
  .then(function(data){
    hideTyping();
    var reply = data.reply || 'Sorry, I could not respond. Try again!';
    // Add assistant reply to history
    chatHistory.push({role:'assistant', content:reply});
    // Keep history manageable
    if(chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    addMsgAnimated(reply,'bot');
    if(done) done();
  })
  .catch(function(){
    hideTyping();
    addMsg('Oops! Something went wrong. Try again! 🙏','bot');
    if(done) done();
  });
}

function addMsgAnimated(text, type){
  var msgs = document.getElementById('faqMsgs');
  var d = document.createElement('div');
  d.className = 'msg ' + type;
  var avatarHtml = type === 'bot'
    ? '<div class="msg-avatar">🤖</div>'
    : '<div class="msg-avatar" style="background:linear-gradient(135deg,#3b82f6,#1d4ed8);">👤</div>';
  d.innerHTML = avatarHtml + '<div class="msg-bubble" id="animMsg_' + Date.now() + '"></div>';
  msgs.appendChild(d);
  scrollMsgs();

  // Word-by-word reveal
  var bubble = d.querySelector('.msg-bubble');
  var words = text.split(' ');
  var i = 0;
  function revealWord(){
    if(i < words.length){
      bubble.textContent += (i === 0 ? '' : ' ') + words[i];
      i++;
      scrollMsgs();
      setTimeout(revealWord, 35 + Math.random() * 25);
    }
  }
  revealWord();
}

// ===== STARTUP TOASTS =====
{% if added %}
document.addEventListener('DOMContentLoaded',function(){showToast('Item added to cart! 🛒','success');});
{% endif %}

{% if oauth_error %}
document.addEventListener('DOMContentLoaded',function(){
  showToast('Google sign-in failed: {{ oauth_error }}','error');
  openModal('loginModal');
});
{% endif %}


// ===== FOOTER INFO MODAL =====
function openInfoModal(key) {
  var el = document.getElementById('ic-' + key);
  if (!el) return;
  document.getElementById('infoModalTitle').textContent = el.getAttribute('data-title');
  document.getElementById('infoModalSub').textContent   = el.getAttribute('data-sub');
  document.getElementById('infoModalBody').innerHTML    = el.innerHTML;
  openModal('infoModal');
}
function toggleFaqItem(el) { el.classList.toggle('open'); }
function simulateTracking() {
  var val = document.getElementById('trackOrderInput') ? document.getElementById('trackOrderInput').value.trim() : '';
  if (!val) { showToast('Please enter an Order ID', 'error'); return; }
  var result = document.getElementById('trackResult');
  result.style.display = 'block';
  document.getElementById('trackOrderId').textContent = '#' + val;
  var today = new Date();
  var fmt = function(d) { return d.toLocaleDateString('en-IN', {day:'numeric', month:'short', year:'numeric'}); };
  document.getElementById('ts1').textContent = fmt(new Date(today - 2*86400000)) + ', 10:32 AM';
  document.getElementById('ts2').textContent = fmt(new Date(today - 1*86400000)) + ', 3:15 PM';
  document.getElementById('trackETA').textContent = 'Today by 7:00 PM';
  showToast('Order #' + val + ' found! Tracking loaded', 'success');
}





// ── ACCOUNT DROPDOWN ──────────────────────────────────────────
function toggleAcct(e){
  e.stopPropagation();
  var w=document.getElementById('acctWrap');
  if(w) w.classList.toggle('open');
}
function closeAcct(){
  var w=document.getElementById('acctWrap');
  if(w) w.classList.remove('open');
}
document.addEventListener('click',function(e){
  var w=document.getElementById('acctWrap');
  if(w&&!w.contains(e.target)) w.classList.remove('open');
});

// ── THEME TOGGLE ─────────────────────────────────────────────
// On DOMContentLoaded: enable smooth transitions now that initial paint is done
document.addEventListener('DOMContentLoaded', function(){
  document.documentElement.classList.add('theme-ready');
  syncThemeIcon();
});
function syncThemeIcon(){
  var isLight=document.documentElement.classList.contains('light-theme');
  var iconDark=document.getElementById('theme-icon-dark');
  var iconLight=document.getElementById('theme-icon-light');
  if(iconDark) iconDark.style.display=isLight?'block':'none';
  if(iconLight) iconLight.style.display=isLight?'none':'block';
}
function toggleTheme(){
  var html=document.documentElement;
  var isLight=html.classList.contains('light-theme');
  if(isLight){
    html.classList.remove('light-theme');
    localStorage.setItem('mystore_theme','dark');
  }else{
    html.classList.add('light-theme');
    localStorage.setItem('mystore_theme','light');
  }
  syncThemeIcon();
}

// ── PROFILE MODAL ─────────────────────────────────────────────
function openProfileModal(tab){
  closeAcct();
  {% if current_user.is_authenticated %}
  var u='{{ current_user.username }}';
  var em='{{ current_user.email or "" }}';
  // populate avatar & display
  document.getElementById('pmAvatar').textContent=u[0].toUpperCase();
  document.getElementById('pmDisplayName').textContent=u;
  document.getElementById('pmDisplayEmail').textContent=em||'No email set';
  // info tab
  document.getElementById('pmInfoU').value=u;
  document.getElementById('pmInfoE').value=em||'Not set';
  document.getElementById('pmInfoSince').value='Member since April 2026';
  var badge=document.getElementById('cartBadge');
  document.getElementById('pmCartCount').textContent=badge?badge.textContent:'0';
  // edit tab prefill
  document.getElementById('editUsername').value=u;
  document.getElementById('editEmail').value=em||'';
  document.getElementById('editCurrentPw').value='';
  document.getElementById('editMsg').style.display='none';
  // password tab reset
  ['pwCurrent','pwNew','pwConfirm'].forEach(function(id){document.getElementById(id).value='';});
  document.getElementById('pwMsg').style.display='none';
  document.getElementById('pwStrengthBar').style.width='0';
  document.getElementById('pwStrengthLabel').textContent='';
  {% endif %}
  // switch to requested tab
  var tabs=document.querySelectorAll('.pm-tab');
  var idx=tab==='edit'?1:tab==='password'?2:0;
  switchPmTab(tab||'info', tabs[idx]);
  openModal('profileModal');
}

function switchPmTab(name, btn){
  document.querySelectorAll('.pm-tab').forEach(function(t){t.classList.remove('active');});
  document.querySelectorAll('.pm-pane').forEach(function(p){p.classList.remove('active');});
  if(btn) btn.classList.add('active');
  var pane=document.getElementById('pmPane-'+name);
  if(pane) pane.classList.add('active');
}

function showPmMsg(elId, text, type){
  var el=document.getElementById(elId);
  el.textContent=text;
  el.className='pm-msg '+(type||'ok');
  el.style.display='block';
}

// ── SAVE PROFILE (username + email) ──────────────────────────
function saveProfile(){
  var newU=document.getElementById('editUsername').value.trim();
  var newE=document.getElementById('editEmail').value.trim();
  var curPw=document.getElementById('editCurrentPw').value;
  if(!newU){showPmMsg('editMsg','Username cannot be empty.','err');return;}
  if(!curPw){showPmMsg('editMsg','Enter your current password to confirm changes.','err');return;}
  var btn=event.target;
  btn.disabled=true; btn.textContent='Saving…';
  fetch('/update-profile',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username:newU,email:newE,current_password:curPw})
  }).then(function(r){return r.json();})
  .then(function(d){
    if(d.success){
      showPmMsg('editMsg',d.message,'ok');
      // update navbar avatar + label live
      var lbl=document.getElementById('acctWrap');
      if(lbl){
        var avatarEl=lbl.querySelector('.acct-avatar');
        var labelEl=lbl.querySelector('.acct-label');
        if(avatarEl) avatarEl.textContent=newU[0].toUpperCase();
        if(labelEl) labelEl.textContent=newU;
      }
      document.getElementById('pmDisplayName').textContent=newU;
      document.getElementById('pmDisplayEmail').textContent=newE||'No email set';
      document.getElementById('pmAvatar').textContent=newU[0].toUpperCase();
      document.getElementById('pmInfoU').value=newU;
      document.getElementById('pmInfoE').value=newE||'Not set';
      showToast('Profile updated successfully! ✅','success');
    } else {
      showPmMsg('editMsg',d.message,'err');
    }
  }).catch(function(){showPmMsg('editMsg','Something went wrong. Try again.','err');})
  .finally(function(){btn.disabled=false;btn.textContent='💾 Save Changes';});
}

// ── SAVE PASSWORD ─────────────────────────────────────────────
function savePassword(){
  var cur=document.getElementById('pwCurrent').value;
  var nw=document.getElementById('pwNew').value;
  var cf=document.getElementById('pwConfirm').value;
  if(!cur){showPmMsg('pwMsg','Enter your current password.','err');return;}
  if(nw.length<6){showPmMsg('pwMsg','New password must be at least 6 characters.','err');return;}
  if(nw!==cf){showPmMsg('pwMsg','New passwords do not match.','err');return;}
  var btn=event.target;
  btn.disabled=true; btn.textContent='Updating…';
  fetch('/update-password',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({current_password:cur,new_password:nw})
  }).then(function(r){return r.json();})
  .then(function(d){
    if(d.success){
      showPmMsg('pwMsg',d.message,'ok');
      ['pwCurrent','pwNew','pwConfirm'].forEach(function(id){document.getElementById(id).value='';});
      document.getElementById('pwStrengthBar').style.cssText='';
      document.getElementById('pwStrengthLabel').textContent='';
      showToast('Password updated! 🔑','success');
    } else {
      showPmMsg('pwMsg',d.message,'err');
    }
  }).catch(function(){showPmMsg('pwMsg','Something went wrong. Try again.','err');})
  .finally(function(){btn.disabled=false;btn.textContent='🔑 Update Password';});
}

// ── PASSWORD STRENGTH METER ───────────────────────────────────
function checkPwStrength(pw){
  var bar=document.getElementById('pwStrengthBar');
  var lbl=document.getElementById('pwStrengthLabel');
  if(!pw){bar.style.cssText='';lbl.textContent='';return;}
  var score=0;
  if(pw.length>=6) score++;
  if(pw.length>=10) score++;
  if(/[A-Z]/.test(pw)&&/[a-z]/.test(pw)) score++;
  if(/[0-9]/.test(pw)) score++;
  if(/[^A-Za-z0-9]/.test(pw)) score++;
  var levels=[
    {w:'20%',color:'#ef4444',label:'Very Weak'},
    {w:'40%',color:'#f97316',label:'Weak'},
    {w:'60%',color:'#eab308',label:'Fair'},
    {w:'80%',color:'#22c55e',label:'Strong'},
    {w:'100%',color:'#00d4aa',label:'Very Strong'}
  ];
  var lv=levels[Math.min(score-1,4)]||levels[0];
  bar.style.cssText='height:4px;border-radius:2px;margin-top:6px;background:'+lv.color+';width:'+lv.w+';transition:all .3s;';
  lbl.textContent=lv.label;
  lbl.style.color=lv.color;
}

function openChatFromBanner(){
  // Open chat and scroll to bottom smoothly
  var bubble = document.getElementById('faqBubble');
  var win = document.getElementById('faqWindow');
  if(win && !win.classList.contains('open')){
    win.classList.add('open');
  }
  // Scroll the chat into view on mobile
  setTimeout(function(){
    var inp = document.getElementById('faqInput');
    if(inp) inp.focus();
    scrollMsgs();
  }, 300);
}

function clearChat(){
  chatHistory = [];
  var msgs = document.getElementById('faqMsgs');
  msgs.innerHTML = '<div class="msg bot"><div class="msg-avatar">🤖</div><div class="msg-bubble">Chat cleared! 🧹 How can I help you? 😊</div></div>';
  document.getElementById('faqChips').style.display = 'flex';
}

function handleSubscribe(){
  var emailInput = document.getElementById('nlEmailInput');
  var email = emailInput ? emailInput.value.trim() : '';
  if(!email || !email.includes('@')){
    showToast('Please enter a valid email address.','error');
    return;
  }
  var btn = document.querySelector('.nl-btn');
  if(btn){ btn.textContent='Sending…'; btn.disabled=true; }
  fetch('/subscribe',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({email:email})
  })
  .then(function(r){return r.json();})
  .then(function(data){
    showToast(data.message, data.success ? 'success' : 'error');
    if(data.success && emailInput){ emailInput.value=''; }
  })
  .catch(function(){showToast('Something went wrong. Try again!','error');})
  .finally(function(){
    if(btn){ btn.textContent='Subscribe'; btn.disabled=false; }
  });
}

</script>

<!-- ===== HIDDEN INFO CONTENT DIVS (read by openInfoModal JS) ===== -->
<div style="display:none">

  <div id="ic-about" data-title="About MyStore" data-sub="Our story and mission">
    <div class="info-highlight"><p>MyStore is India&#39;s fastest-growing e-commerce platform, connecting millions of shoppers with top brands across Electronics, Fashion and Accessories.</p></div>
    <div class="info-section"><h3>Our Mission</h3><p>To make quality products accessible to every Indian household with unbeatable prices, fast delivery, and a shopping experience that truly delights.</p></div>
    <div class="info-section"><h3>By the Numbers</h3><ul><li>2M+ happy customers across India</li><li>10,000+ products from 500+ trusted brands</li><li>Deliveries in 500+ cities and towns</li><li>4.8 star average customer rating</li><li>Founded in 2022, headquartered in Bengaluru</li></ul></div>
    <div class="info-section"><h3>Our Values</h3><ul><li>Customer-first in every decision we make</li><li>Transparency in pricing - no hidden fees</li><li>Sustainability - eco-friendly packaging by 2026</li><li>Empowering local sellers and small businesses</li></ul></div>
  </div>

  <div id="ic-careers" data-title="Careers at MyStore" data-sub="Join our growing team">
    <div class="info-highlight"><p>We are hiring! Join a passionate team building the future of Indian e-commerce.</p></div>
    <div class="info-section"><h3>Open Positions</h3></div>
    <div class="career-card"><div><div class="job-title">Frontend Engineer</div><div class="job-meta">Bengaluru - Full-time - Rs 12-20 LPA</div></div><span class="career-badge">Hiring</span></div>
    <div class="career-card"><div><div class="job-title">Product Manager</div><div class="job-meta">Mumbai - Full-time - Rs 18-28 LPA</div></div><span class="career-badge">Hiring</span></div>
    <div class="career-card"><div><div class="job-title">Growth Marketing Lead</div><div class="job-meta">Remote - Full-time - Rs 10-16 LPA</div></div><span class="career-badge">Hiring</span></div>
    <div class="career-card"><div><div class="job-title">Customer Success Associate</div><div class="job-meta">Pune - Full-time - Rs 4-6 LPA</div></div><span class="career-badge">Hiring</span></div>
    <div class="career-card"><div><div class="job-title">Supply Chain Analyst</div><div class="job-meta">Delhi - Full-time - Rs 8-12 LPA</div></div><span class="career-badge">Hiring</span></div>
    <div class="info-section" style="margin-top:18px;"><h3>Perks and Benefits</h3><ul><li>Competitive salary + ESOPs</li><li>Health insurance for you and family</li><li>Rs 20,000/year learning budget</li><li>Flexible work-from-home policy</li><li>Employee discount on all MyStore products</li></ul></div>
    <button class="msub" style="margin-top:8px;" onclick="showToast('Resume submitted! We will reach out soon.','success');closeModal('infoModal')">Apply Now - Send Resume</button>
  </div>

  <div id="ic-press" data-title="Press and Media" data-sub="MyStore in the news">
    <div class="info-section"><h3>Latest Coverage</h3></div>
    <div class="press-card"><div class="press-source">Economic Times</div><div class="press-headline">MyStore crosses Rs 500 Cr GMV milestone in just 2 years</div><div class="press-date">March 2026</div></div>
    <div class="press-card"><div class="press-source">YourStory</div><div class="press-headline">How MyStore is disrupting D2C with AI-powered shopping assistant</div><div class="press-date">February 2026</div></div>
    <div class="press-card"><div class="press-source">Inc42</div><div class="press-headline">MyStore raises Rs 150 Cr Series B to expand to Tier-2 cities</div><div class="press-date">January 2026</div></div>
    <div class="press-card"><div class="press-source">Business Standard</div><div class="press-headline">Best E-commerce Startup of the Year - MyStore wins Startup India Award</div><div class="press-date">December 2025</div></div>
    <div class="info-section" style="margin-top:18px;"><h3>Press Inquiries</h3><p>For media queries, interviews, or press kit requests:</p><p>Email: <a href="mailto:press@mystore.in" style="color:var(--accent)">press@mystore.in</a> &nbsp; Phone: +91 80 4567 8900</p></div>
  </div>

  <div id="ic-contact" data-title="Contact Us" data-sub="We are here to help 24/7">
    <div class="contact-grid">
      <div class="contact-card"><div class="cc-icon">&#128222;</div><div class="cc-label">Customer Care</div><div class="cc-val"><a href="tel:+918045678900">+91 80 4567 8900</a></div></div>
      <div class="contact-card"><div class="cc-icon">&#128140;</div><div class="cc-label">Email Support</div><div class="cc-val"><a href="mailto:support@mystore.in">support@mystore.in</a></div></div>
      <div class="contact-card"><div class="cc-icon">&#128172;</div><div class="cc-label">Live Chat</div><div class="cc-val" style="cursor:pointer;color:var(--accent);" onclick="closeModal('infoModal');toggleFAQ()">Chat Now</div></div>
      <div class="contact-card"><div class="cc-icon">&#128336;</div><div class="cc-label">Support Hours</div><div class="cc-val">24 x 7 x 365</div></div>
    </div>
    <div class="info-section">
      <h3>Write to Us</h3>
      <input class="minput" placeholder="Your name" style="margin-bottom:10px;">
      <input class="minput" placeholder="Your email" type="email" style="margin-bottom:10px;">
      <textarea class="minput" rows="3" placeholder="Describe your issue or question" style="resize:vertical;margin-bottom:10px;"></textarea>
      <button class="msub" onclick="showToast('Message sent! We will reply within 24hrs.','success');closeModal('infoModal')">Send Message</button>
    </div>
    <div class="info-section"><h3>Head Office</h3><p>MyStore HQ, 4th Floor, Brigade Gateway, Malleswaram, Bengaluru - 560055, Karnataka, India</p></div>
  </div>

  <div id="ic-blog" data-title="MyStore Blog" data-sub="Tips, trends and deals">
    <div class="info-section"><h3>Latest Posts</h3></div>
    <div class="blog-card"><div class="blog-em">&#128241;</div><div><div class="blog-title">Top 10 Smartphones Under Rs 20,000 in 2026</div><div class="blog-meta">March 28, 2026 - 5 min read</div></div></div>
    <div class="blog-card"><div class="blog-em">&#128263;</div><div><div class="blog-title">Summer Fashion Guide: What is Trending This Season</div><div class="blog-meta">March 22, 2026 - 4 min read</div></div></div>
    <div class="blog-card"><div class="blog-em">&#128161;</div><div><div class="blog-title">How to Spot Fake Products Online - Expert Tips</div><div class="blog-meta">March 15, 2026 - 6 min read</div></div></div>
    <div class="blog-card"><div class="blog-em">&#127873;</div><div><div class="blog-title">Ultimate Gift Guide for Every Budget</div><div class="blog-meta">March 10, 2026 - 7 min read</div></div></div>
    <div class="blog-card"><div class="blog-em">&#8987;</div><div><div class="blog-title">Smartwatch vs Traditional Watch: Which One Suits You?</div><div class="blog-meta">March 5, 2026 - 5 min read</div></div></div>
    <button class="msub" style="margin-top:16px;" onclick="showToast('Subscribe to our newsletter for blog updates!','info');closeModal('infoModal')">Subscribe to Blog</button>
  </div>

  <div id="ic-help" data-title="Help Center" data-sub="Quick answers to common questions">
    <div class="info-highlight"><p>Can not find your answer? <span style="color:var(--accent);cursor:pointer;" onclick="closeModal('infoModal');toggleFAQ()">Chat with our AI assistant</span></p></div>
    <div class="info-section"><h3>Popular Topics</h3></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">How do I track my order? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">Go to My Orders from the navbar or footer. Each order has a Track Order button that shows real-time delivery status.</div></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">Can I cancel my order? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">Yes! Orders can be cancelled within 24 hours of placing them. Go to My Orders, select the order, then Cancel Order. After 24 hrs contact our support team.</div></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">How do I change my delivery address? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">Address changes are allowed only before the order is shipped. Contact us at support@mystore.in or call +91 80 4567 8900 within 2 hours of placing the order.</div></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">Is Cash on Delivery available everywhere? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">COD is available in 400+ cities across India. Availability is shown at checkout based on your PIN code. Orders above Rs 50,000 require prepaid payment.</div></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">How do I apply a coupon code? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">Add items to your cart, proceed to Checkout, enter your coupon code e.g. FIRST10 in the coupon field and click Apply. The discount appears in your order summary.</div></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">What if I receive a damaged product? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">Take a photo of the damaged item and contact us within 48 hours. We will arrange a free replacement or full refund, no questions asked.</div></div>
  </div>

  <div id="ic-track" data-title="Track Your Order" data-sub="Real-time delivery status">
    <div class="track-form">
      <input class="minput" id="trackOrderInput" placeholder="Enter Order ID e.g. 1042" type="number">
      <button class="msub" onclick="simulateTracking()">Track Order</button>
    </div>
    <div class="track-result" id="trackResult" style="display:none;">
      <div style="margin-bottom:14px;">
        <div style="font-size:13px;color:var(--gray);">Order <strong id="trackOrderId" style="color:var(--white);">#-</strong></div>
        <div style="font-size:12px;color:var(--accent3);margin-top:4px;">Estimated delivery: <strong id="trackETA">-</strong></div>
      </div>
      <div class="track-step"><div class="track-dot done"></div><div class="track-info"><div class="ts-title">Order Confirmed</div><div class="ts-date" id="ts1">-</div></div></div>
      <div class="track-step"><div class="track-dot done"></div><div class="track-info"><div class="ts-title">Packed and Ready</div><div class="ts-date" id="ts2">-</div></div></div>
      <div class="track-step"><div class="track-dot active"></div><div class="track-info"><div class="ts-title">Out for Delivery</div><div class="ts-date" id="ts3">Today, estimated by 7 PM</div></div></div>
      <div class="track-step"><div class="track-dot"></div><div class="track-info"><div class="ts-title">Delivered</div><div class="ts-date">Pending</div></div></div>
    </div>
  </div>

  <div id="ic-faq" data-title="Frequently Asked Questions" data-sub="Everything you need to know">
    <div class="info-section"><h3>Orders and Payments</h3></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">What payment methods are accepted? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">We accept UPI (GPay, PhonePe, Paytm), Credit/Debit Cards (Visa, Mastercard, RuPay), Net Banking (all major Indian banks), and Cash on Delivery.</div></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">Is it safe to pay on MyStore? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">All transactions are secured with 256-bit SSL encryption and we are PCI DSS compliant. We never store your card details.</div></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">How long does delivery take? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">Standard delivery is 3-5 business days. Express delivery is 1-2 business days available in select cities. Metro cities usually get next-day delivery.</div></div>
    <div class="info-section" style="margin-top:18px;"><h3>Returns and Refunds</h3></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">What is the return policy? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">We offer a hassle-free 7-day return policy from the date of delivery. Items must be unused, in original packaging with all tags intact.</div></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">When will I get my refund? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">Refunds are processed within 5-7 business days after we receive the returned item. UPI and Card refunds are instant once processed.</div></div>
    <div class="info-section" style="margin-top:18px;"><h3>Account and Security</h3></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">How do I reset my password? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">Contact our support at support@mystore.in with your registered email. Password reset via email will be available in the next app update.</div></div>
    <div class="faq-item" onclick="toggleFaqItem(this)"><div class="faq-q">Is my personal data safe? <span class="faq-chevron">&#9660;</span></div><div class="faq-a">We never sell your personal data to third parties. All data is encrypted and stored securely per Indian IT Act and DPDP Act 2023 guidelines.</div></div>
  </div>

  <div id="ic-shipping" data-title="Shipping Policy" data-sub="Delivery terms and timelines">
    <div class="info-highlight"><p>FREE shipping on all orders above Rs 999! Orders below Rs 999 attract a flat Rs 99 delivery fee.</p></div>
    <div class="info-section"><h3>Delivery Timelines</h3><ul><li>Metro cities (Delhi, Mumbai, Bengaluru, Chennai, Hyderabad, Kolkata) - 1-2 business days</li><li>Tier-1 cities - 2-3 business days</li><li>Tier-2 and Tier-3 cities - 3-5 business days</li><li>Remote areas - 5-7 business days</li></ul></div>
    <div class="info-section"><h3>Express Delivery</h3><p>Same-day and next-day delivery available in 50+ cities. Express option shown at checkout if available for your PIN code. Additional charge of Rs 149 applies.</p></div>
    <div class="info-section"><h3>Order Tracking</h3><p>Once your order is shipped, you will receive an SMS and email with the tracking link. You can also track via My Orders on the website.</p></div>
    <div class="info-section"><h3>Shipping Partners</h3><ul><li>Delhivery - pan-India coverage</li><li>Blue Dart - express and high-value orders</li><li>DTDC - Tier-2 and rural areas</li><li>Ekart - select regions</li></ul></div>
  </div>

  <div id="ic-privacy" data-title="Privacy Policy" data-sub="How we protect your data">
    <div class="info-highlight"><p>Last updated: 1 January 2026. We are committed to protecting your privacy per the DPDP Act 2023.</p></div>
    <div class="info-section"><h3>Data We Collect</h3><ul><li>Account info - name, email, phone number</li><li>Order and transaction history</li><li>Delivery addresses you provide</li><li>Browsing behaviour on our platform (anonymous)</li><li>Device and IP information for security</li></ul></div>
    <div class="info-section"><h3>How We Use Your Data</h3><ul><li>Processing and fulfilling your orders</li><li>Sending order confirmations and shipping updates</li><li>Personalising product recommendations</li><li>Fraud detection and account security</li><li>Improving our platform and services</li></ul></div>
    <div class="info-section"><h3>Data Sharing</h3><p>We never sell your personal data. We share data only with logistics partners (for delivery), payment processors (for transactions), and when required by law.</p></div>
    <div class="info-section"><h3>Your Rights</h3><ul><li>Access your personal data at any time</li><li>Request correction or deletion of your data</li><li>Opt out of marketing communications</li><li>Data portability - export your data</li></ul><p style="margin-top:10px;">Email: <a href="mailto:privacy@mystore.in" style="color:var(--accent)">privacy@mystore.in</a></p></div>
  </div>

  <div id="ic-terms" data-title="Terms of Service" data-sub="Rules for using MyStore">
    <div class="info-highlight"><p>By using MyStore, you agree to these terms. Last updated: 1 January 2026.</p></div>
    <div class="info-section"><h3>1. Eligibility</h3><p>You must be 18 years or older to create an account and make purchases. By registering, you confirm you meet this requirement.</p></div>
    <div class="info-section"><h3>2. Account Responsibility</h3><ul><li>You are responsible for maintaining account security</li><li>Do not share your password with anyone</li><li>Notify us immediately of any unauthorised access</li><li>One account per person - duplicate accounts will be suspended</li></ul></div>
    <div class="info-section"><h3>3. Purchases and Pricing</h3><ul><li>All prices are in Indian Rupees and include GST</li><li>We reserve the right to change prices without prior notice</li><li>Orders are confirmed only after payment is successful</li><li>We may cancel orders if products are out of stock</li></ul></div>
    <div class="info-section"><h3>4. Prohibited Activities</h3><ul><li>Reselling purchased items without authorisation</li><li>Fraudulent chargebacks or return abuse</li><li>Scraping product data or automated purchases</li><li>Posting fake reviews or ratings</li></ul></div>
    <div class="info-section"><h3>5. Governing Law</h3><p>These terms are governed by the laws of India. Disputes shall be resolved in the courts of Bengaluru, Karnataka.</p><p style="margin-top:8px;">Questions? Email <a href="mailto:legal@mystore.in" style="color:var(--accent)">legal@mystore.in</a></p></div>
  </div>

</div>
</body>
</html>"""

# ================= HOME PAGE BUILDER =================
def render_home(flash_cards, today_cards, ads=None):
    marquee_items = "".join([
        f"<div class='marquee-item'><span>{item}</span></div>"
        for item in ["⚡ Free Shipping on ₹999+", "🔥 Flash Sale Now Live!", "↩️ 7-Day Easy Returns", "🔒 Secure Payments", "💳 UPI · Cards · COD", "🎁 New Arrivals Daily", "⭐ Top Rated Products", "🚀 Express Delivery Available"]
    ] * 3)

    glow_map = {"electronics":"ad-banner-glow-blue","fashion":"ad-banner-glow-pink","accessories":"ad-banner-glow-gold"}

    ad_slides_html = ""
    active_ads = sorted([a for a in (ads or []) if a.is_active], key=lambda x: x.slot)

    for ad in active_ads:
        glow_cls = glow_map.get(ad.theme, "ad-banner-glow-blue")
        ad_slides_html += f"""
      <a href="{ad.cta_link}" class="ad-banner ad-banner-{ad.theme}">
        <div class="{glow_cls}"></div>
        <div class="ad-banner-left">
          <div class="ad-banner-tag">{ad.tag}</div>
          <div class="ad-banner-title">{ad.title}</div>
          <div class="ad-banner-subtitle">{ad.subtitle}</div>
          <div class="ad-banner-cta-row">
            <div class="ad-banner-cta">{ad.cta_text}</div>
            <div class="ad-banner-discount">{ad.discount}</div>
          </div>
        </div>
        <div class="ad-banner-right">{ad.emoji}</div>
      </a>"""

    num_slides = max(len(active_ads), 1)
    dots_html = "".join([f'<button class="ad-dot {"active" if i==0 else ""}" onclick="adGoTo({i})"></button>' for i in range(num_slides)])

    return f"""
<div class="hero">
  <div class="hero-main">
    <div class="hero-particles" id="heroParticles"></div>
    <div class="htag">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
      Big Fashion Sale — Limited Time
    </div>
    <h1>Shop Smarter,<br>Save <em>Up to 50% OFF!</em></h1>
    <p>Discover thousands of products across Electronics, Fashion & Accessories — all at unbeatable prices.</p>
    <a href="/?category=Fashion" class="hcta">
      Shop Now
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
    </a>
  </div>
  <div class="hero-side">
    <a href="/?category=Electronics" class="hcard">
      <span class="hcard-em">⚡</span>
      <h3>Electronics Sale</h3>
      <p>Up to 40% off on gadgets</p>
      <span class="hcard-badge">Shop Now →</span>
    </a>
    <a href="/?category=Accessories" class="hcard">
      <span class="hcard-em">💎</span>
      <h3>Top Accessories</h3>
      <p>Trending styles this season</p>
      <span class="hcard-badge">Explore →</span>
    </a>
  </div>
</div>

<div class="marquee-strip">
  <div class="marquee-inner">{marquee_items}</div>
</div>

<div class="caticons">
  <a href="/?sub=T-Shirt" class="ci"><div class="ci-circle">👕</div><div class="ci-label">T-Shirts</div></a>
  <a href="/?sub=Jacket" class="ci"><div class="ci-circle">🧥</div><div class="ci-label">Jackets</div></a>
  <a href="/?sub=Shirt" class="ci"><div class="ci-circle">👔</div><div class="ci-label">Shirts</div></a>
  <a href="/?sub=Jeans" class="ci"><div class="ci-circle">👖</div><div class="ci-label">Jeans</div></a>
  <a href="/?sub=Bag" class="ci"><div class="ci-circle">👜</div><div class="ci-label">Bags</div></a>
  <a href="/?sub=Shoes" class="ci"><div class="ci-circle">👟</div><div class="ci-label">Shoes</div></a>
  <a href="/?sub=Watches" class="ci"><div class="ci-circle">⌚</div><div class="ci-label">Watches</div></a>
  <a href="/?sub=Glasses" class="ci"><div class="ci-circle">🕶️</div><div class="ci-label">Glasses</div></a>
  <a href="/?category=Electronics" class="ci"><div class="ci-circle">📱</div><div class="ci-label">Electronics</div></a>
  <a href="/?category=Fashion" class="ci"><div class="ci-circle">🛍️</div><div class="ci-label">Fashion</div></a>
  <a href="/?category=Accessories" class="ci"><div class="ci-circle">💎</div><div class="ci-label">Accessories</div></a>
  <a href="/" class="ci"><div class="ci-circle">✨</div><div class="ci-label">All Items</div></a>
</div>

<div class="ad-swiper-wrap">
  <div class="ad-swiper" id="adSwiper">
    <div class="ad-swiper-track" id="adTrack">
      {ad_slides_html}
    </div>
  </div>
  <button class="ad-swiper-btn ad-swiper-prev" id="adPrev" onclick="adSlide(-1)">&#8249;</button>
  <button class="ad-swiper-btn ad-swiper-next" id="adNext" onclick="adSlide(1)">&#8250;</button>
  <div class="ad-swiper-dots" id="adDots">
    {dots_html}
  </div>
</div>
<script>
(function(){{
  var cur=0, total={num_slides}, autoT;
  function goTo(n){{
    cur=(n+total)%total;
    document.getElementById('adTrack').style.transform='translateX(-'+cur*100+'%)';
    var dots=document.querySelectorAll('.ad-dot');
    dots.forEach(function(d,i){{d.classList.toggle('active',i===cur);}});
  }}
  window.adSlide=function(d){{clearInterval(autoT);goTo(cur+d);startAuto();}};
  window.adGoTo=function(n){{clearInterval(autoT);goTo(n);startAuto();}};
  function startAuto(){{autoT=setInterval(function(){{goTo(cur+1);}},4500);}}
  var sx=0,dragging=false;
  var el=document.getElementById('adSwiper');
  el.addEventListener('touchstart',function(e){{sx=e.touches[0].clientX;dragging=true;}},{{passive:true}});
  el.addEventListener('touchend',function(e){{
    if(!dragging)return;
    var dx=e.changedTouches[0].clientX-sx;
    if(Math.abs(dx)>40){{clearInterval(autoT);goTo(cur+(dx<0?1:-1));startAuto();}}
    dragging=false;
  }});
  startAuto();
}})();
</script>

<div class="sec">
  <div class="sec-hd">
    <div class="sec-title">
      <span class="sec-badge">⚡ FLASH</span>
      <h2>Flash Sale</h2>
      <div class="cd">
        <div class="cdu" id="cdh">08</div><span class="cds">:</span>
        <div class="cdu" id="cdm">17</div><span class="cds">:</span>
        <div class="cdu" id="cds">56</div>
      </div>
    </div>
  </div>
  <div class="prow">{flash_cards}<a href="/?flash=1" class="flash-see-all-card">
    <div class="fsac-inner">
      <div class="fsac-icon">🛍️</div>
      <div class="fsac-label">See All<br>Flash Deals</div>
      <div class="fsac-arrow">→</div>
    </div>
  </a></div>
</div>

<div class="sec">
  <div>
    <div class="sec-hd">
      <div class="sec-title"><h2>Today's For You!</h2></div>
    </div>
    <div class="tabs">
      <div class="tab active" onclick="filterTab(this,'all')">Best Seller</div>
      <div class="tab" onclick="filterTab(this,'Electronics')">Electronics</div>
      <div class="tab" onclick="filterTab(this,'Fashion')">Fashion</div>
      <div class="tab" onclick="filterTab(this,'Accessories')">Accessories</div>
    </div>
    <div class="pgrid" id="tgrid">{today_cards}</div>
    <div class="see-all-wrap"><a href="/?category=all" class="see-all-sm">See All →</a></div>
  </div>
</div>
<script>
(function(){{
  var cards = document.querySelectorAll('#tgrid .pcard');
  for(var i=9;i<cards.length;i++) cards[i].style.display='none';
}})();
</script>

<div class="sec">
  <div class="sec-hd">
    <div class="sec-title"><h2>✨ New Arrivals</h2></div>
  </div>
  <div class="prow" id="newArrivalsRow"></div>
  <div class="see-all-wrap"><a href="/?new_arrivals=1" class="see-all-sm">View All →</a></div>
</div>

<div class="fbanner">
  <div class="fbanner-tag">🎉 LIMITED OFFER</div>
  <h2><em>"Let's Shop Beyond Boundaries"</em></h2>
  <p>MyStore — Your one-stop destination for Electronics, Fashion & Accessories</p>
  <div class="fbanner-actions">
    <a href="/"><button class="fbanner-cta primary">Start Shopping →</button></a>
    <button class="fbanner-cta outline" onclick="openChatFromBanner()">💬 Chat with AI</button>
  </div>
</div>

<script>
(function(){{
  var c = document.getElementById('heroParticles');
  if(!c) return;
  for(var i=0;i<12;i++){{
    var p=document.createElement('div');
    p.className='particle';
    p.style.left=Math.random()*100+'%';
    p.style.animationDuration=(6+Math.random()*8)+'s';
    p.style.animationDelay=(Math.random()*6)+'s';
    c.appendChild(p);
  }}
}})();

document.addEventListener('DOMContentLoaded', function(){{
  var pgrid = document.getElementById('tgrid');
  if(!pgrid) return;
  var cards = pgrid.querySelectorAll('.pcard');
  var naRow = document.getElementById('newArrivalsRow');
  if(!naRow) return;
  var shown = [];
  cards.forEach(function(c,i){{if(i<8)shown.push(c.cloneNode(true));}});
  shown.reverse().forEach(function(c){{naRow.appendChild(c);}});
}});
</script>"""




# ================= PRODUCT DETAIL PAGE TEMPLATE =================
PRODUCT_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ p.name }} – MyStore</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0a0f;--surface:#111118;--surface2:#18181f;--surface3:#1e1e28;
  --border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.14);
  --white:#f0f0f8;--gray:#7b7b95;--gray2:#404055;
  --accent:#ff3b5c;--accent2:#ff6b35;--accent3:#00d4aa;--accent4:#7c5cff;--accent5:#ffcc44;
  --radius:18px;--radius-sm:12px;--radius-xs:8px;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--white);min-height:100vh;}
body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;
  background:radial-gradient(ellipse 80% 60% at 10% 20%,rgba(124,92,255,0.08) 0%,transparent 60%),
             radial-gradient(ellipse 60% 50% at 90% 80%,rgba(0,212,170,0.05) 0%,transparent 60%);
  pointer-events:none;z-index:0;}
a{text-decoration:none;color:inherit;}
/* NAVBAR */
.navbar{position:sticky;top:0;z-index:100;background:rgba(10,10,15,0.9);backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);padding:0 32px;height:62px;display:flex;align-items:center;gap:16px;}
.brand{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;letter-spacing:-0.5px;}
.brand span{color:var(--accent);}
.nav-back{margin-left:auto;font-size:13px;color:var(--accent3);font-weight:600;
  padding:7px 16px;border:1px solid rgba(0,212,170,0.3);border-radius:20px;transition:all 0.2s;}
.nav-back:hover{background:rgba(0,212,170,0.1);}
/* BREADCRUMB */
.breadcrumb{position:relative;z-index:1;max-width:1100px;margin:0 auto;padding:20px 24px 0;
  display:flex;align-items:center;gap:8px;font-size:12px;color:var(--gray);}
.breadcrumb a{color:var(--gray);transition:color 0.2s;}
.breadcrumb a:hover{color:var(--accent3);}
.breadcrumb span{color:var(--white);font-weight:500;}
/* MAIN LAYOUT */
.wrap{position:relative;z-index:1;max-width:1100px;margin:0 auto;padding:24px 24px 80px;}
.product-grid{display:grid;grid-template-columns:1fr 420px;gap:36px;align-items:start;}
@media(max-width:860px){.product-grid{grid-template-columns:1fr;}}
/* LEFT: Image */
.img-panel{position:sticky;top:80px;}
.img-box{background:linear-gradient(135deg,var(--surface2),var(--surface3));border-radius:var(--radius);
  border:1px solid var(--border);height:420px;display:flex;align-items:center;justify-content:center;
  overflow:hidden;position:relative;}
.img-box img{width:100%;height:100%;object-fit:cover;}
.img-emoji{font-size:140px;filter:drop-shadow(0 12px 32px rgba(0,0,0,0.4));}
.discount-badge{position:absolute;top:16px;left:16px;background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#fff;font-size:13px;font-weight:800;padding:6px 14px;border-radius:50px;
  box-shadow:0 4px 12px rgba(255,59,92,0.4);}
.flash-badge{position:absolute;top:16px;right:16px;background:linear-gradient(135deg,#ff6b35,#ffcc44);
  color:#000;font-size:12px;font-weight:800;padding:5px 12px;border-radius:50px;}
/* RIGHT: Info */
.info-panel{}
.prod-cat{font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  color:var(--accent);margin-bottom:8px;}
.prod-name{font-family:'Syne',sans-serif;font-size:28px;font-weight:800;line-height:1.2;
  margin-bottom:12px;color:var(--white);}
.prod-rating-row{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap;}
.stars{color:var(--accent5);font-size:16px;letter-spacing:1px;}
.rating-num{font-size:14px;font-weight:700;color:var(--white);}
.rating-sold{font-size:13px;color:var(--gray);}
.price-row{display:flex;align-items:baseline;gap:12px;margin-bottom:8px;}
.price-main{font-family:'DM Sans',sans-serif;font-size:36px;font-weight:700;color:var(--white);}
.price-orig{font-size:18px;color:var(--gray);text-decoration:line-through;}
.price-save{font-size:13px;font-weight:700;color:var(--accent3);
  background:rgba(0,212,170,0.1);padding:3px 10px;border-radius:20px;}
.delivery-info{font-size:13px;color:var(--gray);margin-bottom:20px;
  display:flex;align-items:center;gap:6px;}
.delivery-info .free{color:var(--accent3);font-weight:600;}
/* Action buttons */
.action-row{display:flex;gap:12px;margin-bottom:24px;}
.btn-add{flex:1;padding:15px 20px;background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#fff;border:none;border-radius:var(--radius-sm);font-size:15px;font-weight:700;
  cursor:pointer;font-family:'Syne',sans-serif;transition:all 0.2s;display:flex;align-items:center;justify-content:center;gap:8px;}
.btn-add:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(255,59,92,0.4);}
.btn-add.added{background:linear-gradient(135deg,var(--accent3),#00a884);color:#000;}
.btn-buy{flex:1;padding:15px 20px;background:var(--surface2);color:var(--white);
  border:1.5px solid var(--border2);border-radius:var(--radius-sm);font-size:15px;font-weight:700;
  cursor:pointer;font-family:'Syne',sans-serif;transition:all 0.2s;}
.btn-buy:hover{background:var(--surface3);border-color:var(--accent3);color:var(--accent3);}
/* Highlights strip */
.highlights{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:24px;}
.hl-item{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-xs);
  padding:12px 14px;display:flex;align-items:flex-start;gap:10px;}
.hl-icon{font-size:20px;flex-shrink:0;}
.hl-label{font-size:11px;color:var(--gray);margin-bottom:2px;}
.hl-val{font-size:13px;font-weight:600;color:var(--white);}
/* DESCRIPTION SECTION */
.desc-section{margin-top:40px;}
.sec-hd{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;margin-bottom:20px;
  padding-bottom:12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;}
.sec-hd-icon{width:32px;height:32px;border-radius:9px;background:var(--surface2);
  display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;}
/* AI description content styles */
.ai-content{font-size:14px;line-height:1.8;color:#c8c8e0;}
.ai-content h2{font-family:'Syne',sans-serif;font-size:18px;font-weight:700;color:var(--white);margin:28px 0 12px;}
.ai-content h3{font-family:'Syne',sans-serif;font-size:15px;font-weight:700;color:var(--white);margin:20px 0 10px;}
.ai-content p{margin-bottom:14px;}
.ai-content ul,.ai-content ol{margin:10px 0 14px 20px;}
.ai-content li{margin-bottom:6px;}
.ai-content strong{color:var(--white);font-weight:600;}
.ai-content .spec-table{width:100%;border-collapse:collapse;margin:16px 0;}
.ai-content .spec-table tr{border-bottom:1px solid var(--border);}
.ai-content .spec-table tr:last-child{border-bottom:none;}
.ai-content .spec-table td{padding:10px 14px;font-size:13px;}
.ai-content .spec-table td:first-child{color:var(--gray);width:40%;font-weight:500;}
.ai-content .spec-table td:last-child{color:var(--white);font-weight:500;}
.ai-content .spec-table tr:hover td{background:var(--surface3);}
/* Spec card */
.spec-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden;margin-bottom:24px;}
/* Loading skeleton */
.skeleton{background:linear-gradient(90deg,var(--surface2) 25%,var(--surface3) 50%,var(--surface2) 75%);
  background-size:200% 100%;animation:shimmer 1.5s infinite;border-radius:6px;}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.skel-line{height:14px;margin-bottom:10px;}
.skel-line.wide{width:90%;}
.skel-line.mid{width:70%;}
.skel-line.short{width:45%;}
.skel-line.title{height:20px;width:55%;margin-bottom:18px;}
/* Related products */
.related-grid{display:flex;gap:16px;overflow-x:auto;padding-bottom:8px;}
.related-grid::-webkit-scrollbar{height:4px;}
.related-grid::-webkit-scrollbar-track{background:var(--surface2);}
.related-grid::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px;}
.rcard{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:14px;flex:0 0 180px;transition:all 0.2s;cursor:pointer;}
.rcard:hover{border-color:rgba(255,59,92,0.3);transform:translateY(-3px);}
.rcard-em{font-size:40px;text-align:center;margin-bottom:10px;}
.rcard-name{font-size:12px;font-weight:600;color:var(--white);margin-bottom:4px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.rcard-price{font-size:13px;font-weight:700;color:var(--white);}
/* Toast */
.toast-wrap{position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:10px;}
.toast{background:var(--surface2);border:1px solid var(--border2);border-radius:12px;
  padding:14px 18px;display:flex;align-items:center;gap:10px;font-size:14px;font-weight:500;
  box-shadow:0 8px 32px rgba(0,0,0,0.4);animation:slideIn 0.3s ease;}
.toast.success{border-color:var(--accent3);}
@keyframes slideIn{from{opacity:0;transform:translateX(40px)}to{opacity:1;transform:translateX(0)}}
.cart-item{display:flex;align-items:center;gap:14px;padding:14px;background:var(--surface2);border-radius:var(--radius-sm);margin-bottom:12px;border:1px solid var(--border);transition:all 0.2s;}
.cart-item:hover{border-color:rgba(255,59,92,0.3);}
.cart-item-em{font-size:40px;min-width:56px;height:56px;background:var(--surface3);border-radius:10px;display:flex;align-items:center;justify-content:center;overflow:hidden;}
.cart-item-info{flex:1;}
.cart-item-name{font-size:14px;font-weight:600;margin-bottom:4px;}
.cart-item-price{font-size:15px;font-weight:700;color:var(--accent);}
.cart-item-remove{background:none;border:none;color:var(--gray);cursor:pointer;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:all 0.2s;}
.cart-item-remove:hover{background:rgba(255,59,92,0.15);color:var(--accent);}
.cart-qty-ctrl{display:flex;align-items:center;gap:6px;background:var(--surface3);border-radius:20px;padding:3px 6px;border:1px solid var(--border2);}
.qty-btn{background:none;border:none;color:var(--white);font-size:16px;font-weight:700;cursor:pointer;width:22px;height:22px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:background 0.15s;line-height:1;}
.qty-btn:hover{background:var(--accent);color:#fff;}
.cart-empty{text-align:center;padding:40px 20px;color:var(--gray);}
.cart-empty-icon{font-size:48px;display:block;margin-bottom:12px;}
</style>
</head>
<body>
<nav class="navbar">
  <a href="/" class="brand">My<span>Store</span></a>
  <a href="/" class="nav-back">← Back to Shop</a>
  <button class="cart-btn" onclick="openCart()" id="cartBtn" style="margin-left:12px;background:rgba(255,255,255,0.07);border:1.5px solid rgba(255,255,255,0.14);color:#f0f0f8;width:44px;height:44px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;position:relative;font-size:18px;transition:all 0.2s;">
    🛒
    {% if cc > 0 %}<span class="cbadge" id="cartBadge" style="position:absolute;top:-4px;right:-4px;background:#ff3b5c;color:#fff;font-size:11px;font-weight:700;width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;border:2px solid #0a0a0f;">{{ cc }}</span>{% endif %}
  </button>
</nav>
<!-- Cart Overlay & Drawer -->
<div class="cart-overlay" id="cartOverlay" onclick="closeCart()" style="position:fixed;inset:0;background:rgba(0,0,0,0.6);backdrop-filter:blur(8px);z-index:900;opacity:0;pointer-events:none;transition:opacity 0.3s;"></div>
<div class="cart-drawer" id="cartDrawer" style="position:fixed;top:0;right:-440px;width:420px;height:100vh;background:#111118;border-left:1px solid rgba(255,255,255,0.07);z-index:901;display:flex;flex-direction:column;transition:right 0.35s cubic-bezier(0.25,0.46,0.45,0.94);overflow:hidden;">
  <div style="padding:24px;border-bottom:1px solid rgba(255,255,255,0.07);display:flex;align-items:center;justify-content:space-between;background:#18181f;">
    <div><h3 style="font-family:'Syne',sans-serif;font-size:20px;font-weight:700;">Your Cart 🛒</h3>
    <div id="cartCount" style="font-size:13px;color:#7b7b95;margin-top:2px;">{{ cc }} item(s)</div></div>
    <button onclick="closeCart()" style="background:#1e1e28;border:none;color:#f0f0f8;width:36px;height:36px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;">✕</button>
  </div>
  <div class="cart-body" id="cartBody" style="flex:1;overflow-y:auto;padding:20px;">{{ ch|safe }}</div>
  <div id="cartFooter" style="padding:20px;border-top:1px solid rgba(255,255,255,0.07);background:#18181f;{{ 'display:none' if cc == 0 else '' }}">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <span style="font-size:14px;color:#7b7b95;">Total</span>
      <span id="cartTotal" style="font-family:'Syne',sans-serif;font-size:22px;font-weight:700;">₹{{ cart_total }}</span>
    </div>
    <a href="/checkout"><button style="width:100%;padding:15px;background:linear-gradient(135deg,#ff3b5c,#ff6b35);color:#fff;border:none;border-radius:12px;font-size:16px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;">Checkout →</button></a>
    <a href="/cart" onclick="closeCart()"><button style="width:100%;padding:12px;background:transparent;color:#f0f0f8;border:1.5px solid rgba(255,255,255,0.14);border-radius:12px;font-size:14px;font-weight:600;cursor:pointer;margin-top:10px;">🛒 View Full Cart</button></a>
  </div>
</div>

<!-- Breadcrumb -->
<div class="breadcrumb">
  <a href="/">Home</a> › <a href="/?category={{ p.category }}">{{ p.category }}</a> › <span>{{ p.name }}</span>
</div>

<div class="wrap">
  <div class="product-grid">
    <!-- IMAGE PANEL -->
    <div class="img-panel">
      <div class="img-box">
        {% if discount_pct %}<div class="discount-badge">-{{ discount_pct }}% OFF</div>{% endif %}
        {% if p.is_flash %}<div class="flash-badge">⚡ Flash Sale</div>{% endif %}
        {% if p.image_url %}
          <img src="{{ p.image_url }}" alt="{{ p.name }}" onerror="this.style.display='none';document.getElementById('fallback-em').style.display='block'">
          <div class="img-emoji" id="fallback-em" style="display:none">{{ p.emoji }}</div>
        {% else %}
          <div class="img-emoji">{{ p.emoji }}</div>
        {% endif %}
      </div>
    </div>

    <!-- INFO PANEL -->
    <div class="info-panel">
      <div class="prod-cat">{{ p.subcategory or p.category }}</div>
      <h1 class="prod-name">{{ p.name }}</h1>

      <div class="prod-rating-row">
        <span class="stars">{{ stars }}</span>
        <span class="rating-num">{{ p.rating }}/5</span>
        <span class="rating-sold">· {{ p.sold }} sold</span>
      </div>

      <div class="price-row">
        <span class="price-main">₹{{ '{:,}'.format(p.price) }}</span>
        {% if p.orig_price and p.orig_price > p.price %}
        <span class="price-orig">₹{{ '{:,}'.format(p.orig_price) }}</span>
        <span class="price-save">Save ₹{{ '{:,}'.format(p.orig_price - p.price) }}</span>
        {% endif %}
      </div>

      <div class="delivery-info">
        🚚&nbsp;
        {% if p.price >= 999 %}
          <span class="free">FREE Delivery</span>
        {% else %}
          ₹99 delivery · <span class="free">FREE above ₹999</span>
        {% endif %}
        &nbsp;· Usually ships in 2–4 days
      </div>

      <div class="action-row">
        <button class="btn-add" id="addBtn" onclick="addToCart()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>
          Add to Cart
        </button>
        <button class="btn-buy" onclick="window.location='/checkout'">Buy Now</button>
      </div>

      <!-- Highlights -->
      <div class="highlights">
        <div class="hl-item"><span class="hl-icon">🔒</span><div><div class="hl-label">Secure Payment</div><div class="hl-val">UPI / Card / COD</div></div></div>
        <div class="hl-item"><span class="hl-icon">↩️</span><div><div class="hl-label">Easy Returns</div><div class="hl-val">7-day policy</div></div></div>
        <div class="hl-item"><span class="hl-icon">✅</span><div><div class="hl-label">Authenticity</div><div class="hl-val">100% Genuine</div></div></div>
        <div class="hl-item"><span class="hl-icon">🏆</span><div><div class="hl-label">Top Rated</div><div class="hl-val">{{ p.rating }}★ · {{ p.sold }} sold</div></div></div>
      </div>

      <!-- Short description -->
      <div style="font-size:14px;color:var(--gray);line-height:1.7;padding:14px;background:var(--surface2);border-radius:var(--radius-xs);border:1px solid var(--border);">
        {{ p.description }}
      </div>
    </div>
  </div>

  <!-- ===== FULL DESCRIPTION + SPECS (AI-generated) ===== -->
  <div class="desc-section">
    <div class="sec-hd"><div class="sec-hd-icon">📋</div> Full Description &amp; Specifications</div>
    <div class="spec-card">
      <div id="aiContent" style="padding:28px;">
        <!-- Skeleton loader -->
        <div id="skeleton">
          <div class="skeleton skel-line title"></div>
          <div class="skeleton skel-line wide"></div>
          <div class="skeleton skel-line mid"></div>
          <div class="skeleton skel-line wide"></div>
          <div class="skeleton skel-line short"></div>
          <br>
          <div class="skeleton skel-line title" style="width:40%;margin-top:10px;"></div>
          <div class="skeleton skel-line wide"></div>
          <div class="skeleton skel-line mid"></div>
          <div class="skeleton skel-line wide"></div>
          <div class="skeleton skel-line mid"></div>
          <div class="skeleton skel-line short"></div>
        </div>
        <div class="ai-content" id="aiText" style="display:none;"></div>
      </div>
    </div>

    <!-- Related Products -->
    {% if related %}
    <div class="sec-hd" style="margin-top:36px;"><div class="sec-hd-icon">🛍️</div> You May Also Like</div>
    <div class="related-grid">
      {% for r in related %}
      <a href="/product/{{ r.id }}" style="text-decoration:none;">
        <div class="rcard">
          <div class="rcard-em">{{ r.emoji }}</div>
          <div class="rcard-name">{{ r.name }}</div>
          <div class="rcard-price">₹{{ '{:,}'.format(r.price) }}</div>
        </div>
      </a>
      {% endfor %}
    </div>
    {% endif %}
  </div>
</div>

<!-- Toast -->
<div class="toast-wrap" id="toastWrap"></div>

<script>
var productId = {{ p.id }};
var productName = {{ p.name | tojson }};

function showToast(msg, type) {
  var wrap = document.getElementById('toastWrap');
  var t = document.createElement('div');
  t.className = 'toast ' + (type || 'success');
  t.innerHTML = '<span>' + (type==='success'?'✓':'ℹ') + '</span><span>' + msg + '</span>';
  wrap.appendChild(t);
  setTimeout(function(){ t.style.opacity='0'; t.style.transition='opacity 0.3s'; setTimeout(function(){t.remove();},300); }, 3000);
}

function addToCart() {
  var btn = document.getElementById('addBtn');
  btn.disabled = true;
  btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Adding...';
  fetch('/add-ajax/' + productId, {method:'POST', headers:{'Content-Type':'application/json'}})
    .then(function(r){ return r.json(); })
    .then(function(data) {
      if (data.success) {
        btn.classList.add('added');
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Added to Cart!';
        showToast(productName + ' added to cart 🛒', 'success');
        setTimeout(function(){ btn.disabled=false; btn.classList.remove('added'); btn.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>Add to Cart'; }, 2500);
      } else {
        btn.disabled = false;
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>Add to Cart';
        showToast('Could not add to cart', 'error');
      }
    })
    .catch(function() {
      btn.disabled = false;
      btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>Add to Cart';
      showToast('Something went wrong. Please try again.', 'error');
    });
}

// ===== Load AI description =====
function renderHTML(md) {
  // Simple markdown-to-HTML converter
  return md
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^\| (.+) \|$/gm, function(line) {
      var cells = line.split('|').map(function(c){return c.trim();}).filter(Boolean);
      return '<tr>' + cells.map(function(c){ return '<td>'+c+'</td>'; }).join('') + '</tr>';
    })
    .replace(/(<tr>[\s\S]+?<\/tr>)+/g, function(tbl) {
      return '<table class="spec-table">' + tbl + '</table>';
    })
    .replace(/^---+$/gm, '<hr style="border:none;border-top:1px solid var(--border);margin:20px 0;">')
    .replace(/^\* (.+)$/gm, '<li>$1</li>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]+?<\/li>)/g, function(list){ return '<ul>'+list+'</ul>'; })
    .replace(/<\/ul>\s*<ul>/g, '')
    .replace(/\n\n/g, '</p><p>');
}

(function loadDescription() {
  fetch('/product/{{ p.id }}/description')
    .then(function(r){ return r.json(); })
    .then(function(data) {
      document.getElementById('skeleton').style.display = 'none';
      var el = document.getElementById('aiText');
      el.innerHTML = '<p>' + renderHTML(data.description) + '</p>';
      el.style.display = 'block';
    })
    .catch(function() {
      document.getElementById('skeleton').style.display = 'none';
      var el = document.getElementById('aiText');
      el.innerHTML = '<p style="color:var(--gray);font-size:14px;">Description could not be loaded. Please try refreshing.</p>';
      el.style.display = 'block';
    });
})();

function openCart(){
  document.getElementById('cartOverlay').style.opacity='1';
  document.getElementById('cartOverlay').style.pointerEvents='all';
  document.getElementById('cartDrawer').style.right='0';
}
function closeCart(){
  document.getElementById('cartOverlay').style.opacity='0';
  document.getElementById('cartOverlay').style.pointerEvents='none';
  document.getElementById('cartDrawer').style.right='-440px';
}
function removeFromCart(cartId){
  fetch('/remove-cart/'+cartId, {method:'POST'})
    .then(function(r){ return r.json(); })
    .then(function(data){ refreshCart(data); });
}
function updateQty(cartId, delta){
  fetch('/update-cart-qty/'+cartId, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({delta:delta})})
    .then(function(r){ return r.json(); })
    .then(function(data){ refreshCart(data); });
}
function refreshCart(data){
  if(data.cart_html) document.getElementById('cartBody').innerHTML = data.cart_html;
  var itemCount = data.cc !== undefined ? data.cc : (data.count !== undefined ? data.count : 0);
  var cartTotal = data.cart_total !== undefined ? data.cart_total : (data.total !== undefined ? data.total : 0);
  var badge = document.getElementById('cartBadge');
  if(itemCount > 0){
    if(!badge){
      badge = document.createElement('span');
      badge.id = 'cartBadge';
      badge.style.cssText='position:absolute;top:-4px;right:-4px;background:#ff3b5c;color:#fff;font-size:11px;font-weight:700;width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;border:2px solid #0a0a0f;';
      document.getElementById('cartBtn').appendChild(badge);
    }
    badge.textContent = itemCount;
  } else if(badge){ badge.remove(); }
  var cc = document.getElementById('cartCount');
  if(cc) cc.textContent = itemCount + ' item(s)';
  var ct = document.getElementById('cartTotal');
  if(ct) ct.textContent = '\u20b9' + cartTotal.toLocaleString('en-IN');
  var cf = document.getElementById('cartFooter');
  if(cf) cf.style.display = itemCount > 0 ? '' : 'none';
}
function addToCartById(id, btn){
  if(btn){ btn.classList.add('adding'); btn.textContent='Adding\u2026'; }
  fetch('/add-ajax/'+id, {method:'POST'})
    .then(function(r){ return r.json(); })
    .then(function(data){
      if(btn){ btn.classList.remove('adding'); btn.innerHTML='🛒 Add to Cart'; }
      refreshCart(data);
      openCart();
    });
}
</script>
</body>
</html>"""


# ================= CART PAGE TEMPLATE =================
CART_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your Cart – MyStore</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0a0f;--surface:#111118;--surface2:#18181f;--surface3:#1e1e28;
  --border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.14);
  --white:#f0f0f8;--gray:#7b7b95;
  --accent:#ff3b5c;--accent2:#ff6b35;--accent3:#00d4aa;--accent4:#7c5cff;
  --radius:18px;--radius-sm:12px;--radius-xs:8px;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--white);min-height:100vh;}
body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;
  background:radial-gradient(ellipse 80% 60% at 10% 20%,rgba(124,92,255,0.07) 0%,transparent 60%),
             radial-gradient(ellipse 60% 50% at 90% 80%,rgba(0,212,170,0.05) 0%,transparent 60%);
  pointer-events:none;z-index:0;}
a{text-decoration:none;color:inherit;}
.navbar{position:sticky;top:0;z-index:100;background:rgba(10,10,15,0.88);backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);padding:0 32px;height:62px;display:flex;align-items:center;gap:16px;}
.brand{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;letter-spacing:-0.5px;}
.brand span{color:var(--accent);}
.nav-back{margin-left:auto;font-size:13px;color:var(--accent3);font-weight:600;
  padding:7px 16px;border:1px solid rgba(0,212,170,0.3);border-radius:20px;transition:all 0.2s;}
.nav-back:hover{background:rgba(0,212,170,0.1);}
.wrap{position:relative;z-index:1;max-width:1000px;margin:0 auto;padding:36px 20px 80px;}
.page-title{font-family:'Syne',sans-serif;font-size:28px;font-weight:800;margin-bottom:8px;}
.page-sub{font-size:14px;color:var(--gray);margin-bottom:32px;}
.grid{display:grid;grid-template-columns:1fr 340px;gap:24px;align-items:start;}
@media(max-width:760px){.grid{grid-template-columns:1fr;}}
/* Cart Items */
.cart-list{display:flex;flex-direction:column;gap:14px;}
.ci{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:18px;display:flex;align-items:center;gap:16px;transition:border-color 0.2s;animation:fadeUp 0.3s ease both;}
.ci:hover{border-color:var(--border2);}
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.ci-em{width:64px;height:64px;border-radius:10px;background:var(--surface2);
  display:flex;align-items:center;justify-content:center;font-size:36px;flex-shrink:0;overflow:hidden;}
.ci-em img{width:100%;height:100%;object-fit:cover;border-radius:10px;}
.ci-info{flex:1;min-width:0;}
.ci-name{font-size:15px;font-weight:600;color:var(--white);margin-bottom:4px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.ci-cat{font-size:12px;color:var(--gray);}
.ci-price{font-family:'DM Sans',sans-serif;font-size:17px;font-weight:600;color:var(--white);flex-shrink:0;}
.ci-remove{background:none;border:none;color:var(--gray);font-size:18px;cursor:pointer;
  width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;
  transition:all 0.2s;flex-shrink:0;}
.ci-remove:hover{background:rgba(255,59,92,0.15);color:var(--accent);}
.ci-qty-ctrl{display:flex;align-items:center;gap:6px;background:var(--surface2);border-radius:20px;padding:4px 8px;border:1px solid var(--border2);flex-shrink:0;}
.ci-qty-btn{background:none;border:none;color:var(--white);font-size:18px;font-weight:700;cursor:pointer;width:24px;height:24px;display:flex;align-items:center;justify-content:center;border-radius:50%;transition:background 0.15s;line-height:1;}
.ci-qty-btn:hover{background:var(--accent);color:#fff;}
.ci-qty-val{font-size:14px;font-weight:700;min-width:20px;text-align:center;}
/* Empty state */
.empty-cart{text-align:center;padding:60px 20px;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--radius);}
.empty-cart .em{font-size:64px;margin-bottom:16px;}
.empty-cart h3{font-family:'Syne',sans-serif;font-size:20px;font-weight:700;margin-bottom:8px;}
.empty-cart p{color:var(--gray);font-size:14px;margin-bottom:24px;}
.btn-shop{display:inline-flex;align-items:center;gap:8px;padding:12px 28px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;
  border-radius:50px;font-size:14px;font-weight:700;transition:all 0.2s;}
.btn-shop:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(255,59,92,0.35);}
/* Summary */
.summary{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;position:sticky;top:80px;}
.s-title{font-family:'Syne',sans-serif;font-size:17px;font-weight:700;margin-bottom:20px;
  padding-bottom:14px;border-bottom:1px solid var(--border);}
.s-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-size:14px;}
.s-row .label{color:var(--gray);}
.s-row .val{font-weight:600;}
.s-divider{height:1px;background:var(--border);margin:16px 0;}
.s-total{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;}
.s-total .label{font-size:15px;font-weight:600;}
.s-total .val{font-family:'DM Sans',sans-serif;font-size:22px;font-weight:700;color:var(--white);}
.s-note{font-size:11px;color:var(--accent3);margin-bottom:18px;
  background:rgba(0,212,170,0.07);border-radius:8px;padding:8px 12px;}
.btn-checkout{width:100%;padding:15px;background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#fff;border:none;border-radius:var(--radius-sm);font-size:16px;font-weight:700;
  cursor:pointer;font-family:'Syne',sans-serif;transition:all 0.2s;letter-spacing:0.3px;}
.btn-checkout:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(255,59,92,0.4);}
.btn-continue{width:100%;padding:12px;background:transparent;color:var(--white);
  border:1.5px solid var(--border2);border-radius:var(--radius-sm);font-size:14px;
  font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;transition:all 0.2s;margin-top:10px;}
.btn-continue:hover{background:var(--surface2);border-color:var(--accent3);color:var(--accent3);}
.free-del-bar{height:6px;background:var(--surface3);border-radius:3px;overflow:hidden;margin-bottom:6px;}
.free-del-fill{height:100%;background:linear-gradient(90deg,var(--accent3),#00a884);border-radius:3px;transition:width 0.5s ease;}
.free-del-txt{font-size:12px;color:var(--gray);margin-bottom:16px;}
</style>
</head>
<body>
<nav class="navbar">
  <a href="/" class="brand">My<span>Store</span></a>
  <a href="/" class="nav-back">← Continue Shopping</a>
</nav>
<div class="wrap">
  <div class="page-title">Your Cart 🛒</div>
  <div class="page-sub" id="cartSubtitle">{{ items|sum(attribute='quantity') }} item(s) in your cart</div>

  {% if items %}
  <div class="grid">
    <div>
      <div class="cart-list" id="cartList">
        {% for item in items %}
        <div class="ci" id="ci-{{ item.cart_key }}">
          <div class="ci-em">
            {% if item.image_url %}<img src="{{ item.image_url }}" onerror="this.style.display='none'">{% else %}{{ item.emoji }}{% endif %}
          </div>
          <div class="ci-info">
            <div class="ci-name">{{ item.name }}</div>
            <div class="ci-cat">{{ item.category }}</div>
          </div>
          <div class="ci-qty-ctrl">
            <button class="ci-qty-btn" onclick="changeQty('{{ item.cart_key }}', {{ item.price }}, -1)">−</button>
            <span class="ci-qty-val" id="qty-{{ item.cart_key }}">{{ item.quantity }}</span>
            <button class="ci-qty-btn" onclick="changeQty('{{ item.cart_key }}', {{ item.price }}, 1)">+</button>
          </div>
          <div class="ci-price" id="price-{{ item.cart_key }}">₹{{ '{:,}'.format(item.price * item.quantity) }}</div>
          <button class="ci-remove" onclick="removeItem('{{ item.cart_key }}', {{ item.price }}, {{ item.quantity }})">✕</button>
        </div>
        {% endfor %}
      </div>
    </div>
    <div>
      <div class="summary">
        <div class="s-title">Order Summary</div>
        <div class="s-row"><span class="label">Subtotal ({{ items|sum(attribute='quantity') }} items)</span><span class="val" id="s-subtotal">₹{{ '{:,}'.format(subtotal) }}</span></div>
        <div class="s-row"><span class="label">Delivery</span><span class="val" id="s-delivery" style="color:{{ 'var(--accent3)' if delivery == 0 else 'var(--white)' }}">{{ 'FREE' if delivery == 0 else '₹' + delivery|string }}</span></div>
        {% if subtotal < 999 %}
        <div style="margin-top:8px;">
          <div class="free-del-bar"><div class="free-del-fill" id="delBar" style="width:{{ [(subtotal/999*100)|int, 100]|min }}%"></div></div>
          <div class="free-del-txt" id="delTxt">Add ₹{{ '{:,}'.format(999 - subtotal) }} more for <strong style="color:var(--accent3)">FREE delivery</strong></div>
        </div>
        {% endif %}
        <div class="s-divider"></div>
        <div class="s-total"><span class="label">Total</span><span class="val" id="s-total">₹{{ '{:,}'.format(total) }}</span></div>
        {% if delivery == 0 %}
        <div class="s-note">🎉 You've unlocked FREE delivery!</div>
        {% endif %}
        <a href="/checkout"><button class="btn-checkout">Proceed to Checkout →</button></a>
        <a href="/"><button class="btn-continue">← Continue Shopping</button></a>
      </div>
    </div>
  </div>
  {% else %}
  <div class="empty-cart">
    <div class="em">🛒</div>
    <h3>Your cart is empty</h3>
    <p>Looks like you haven't added anything yet. Start shopping!</p>
    <a href="/" class="btn-shop">🛍️ Shop Now</a>
  </div>
  {% endif %}
</div>
<script>
var subtotal = {{ subtotal }};
var delivery = {{ delivery }};

function fmt(n){ return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g,','); }

function updateSummary(){
  delivery = subtotal >= 999 ? 0 : (subtotal > 0 ? 99 : 0);
  var total = subtotal + delivery;
  document.getElementById('s-subtotal').textContent = '₹' + fmt(subtotal);
  document.getElementById('s-delivery').textContent = delivery === 0 ? 'FREE' : '₹' + delivery;
  document.getElementById('s-delivery').style.color = delivery === 0 ? 'var(--accent3)' : 'var(--white)';
  document.getElementById('s-total').textContent = '₹' + fmt(total);
  var bar = document.getElementById('delBar');
  var txt = document.getElementById('delTxt');
  if(bar){ bar.style.width = Math.min(subtotal/999*100,100)+'%'; }
  if(txt){ txt.innerHTML = subtotal >= 999 ? '' : 'Add ₹'+fmt(999-subtotal)+' more for <strong style="color:var(--accent3)">FREE delivery</strong>'; }
}

function getTotalQty(){
  var vals = document.querySelectorAll('.ci-qty-val');
  var t = 0; vals.forEach(function(v){ t += parseInt(v.textContent)||0; }); return t;
}

function changeQty(cartKey, unitPrice, delta){
  fetch('/update-cart-qty/' + cartKey, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({delta:delta})})
    .then(function(r){return r.json();})
    .then(function(){
      var qtyEl = document.getElementById('qty-' + cartKey);
      var priceEl = document.getElementById('price-' + cartKey);
      if(qtyEl){
        var newQty = parseInt(qtyEl.textContent) + delta;
        if(newQty <= 0){
          var el = document.getElementById('ci-' + cartKey);
          if(el){ el.style.opacity='0'; el.style.transform='translateX(40px)'; el.style.transition='all 0.3s'; setTimeout(function(){el.remove(); checkEmpty();},300); }
          subtotal -= unitPrice * (parseInt(qtyEl.textContent)||1);
        } else {
          qtyEl.textContent = newQty;
          if(priceEl) priceEl.textContent = '₹' + fmt(unitPrice * newQty);
          subtotal += unitPrice * delta;
        }
        document.getElementById('cartSubtitle').textContent = getTotalQty() + ' item(s) in your cart';
        updateSummary();
      }
    })
    .catch(function(){ window.location.reload(); });
}

function removeItem(cartKey, unitPrice, qty) {
  fetch('/remove-cart/' + cartKey, {method:'POST'})
    .then(function(r){return r.json();})
    .then(function(){
      var el = document.getElementById('ci-' + cartKey);
      if(el){ el.style.opacity='0'; el.style.transform='translateX(40px)'; el.style.transition='all 0.3s'; setTimeout(function(){el.remove(); checkEmpty();},300); }
      subtotal -= unitPrice * (qty||1);
      updateSummary();
      setTimeout(function(){ document.getElementById('cartSubtitle').textContent = getTotalQty() + ' item(s) in your cart'; }, 350);
    })
    .catch(function(){ window.location.reload(); });
}

function checkEmpty() {
  if (document.querySelectorAll('.ci').length === 0) {
    document.querySelector('.grid').innerHTML = '<div class="empty-cart" style="grid-column:1/-1"><div class="em">🛒</div><h3>Your cart is empty</h3><p>Looks like you haven\'t added anything yet.</p><a href="/" class="btn-shop">🛍️ Shop Now</a></div>';
  }
}
</script>
</body>
</html>"""


# ================= CHECKOUT / SUCCESS / ORDERS TEMPLATES =================
CHECKOUT_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Checkout – MyStore</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0a0f;--surface:#111118;--surface2:#18181f;--surface3:#1e1e28;
  --border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.14);
  --white:#f0f0f8;--gray:#7b7b95;--gray2:#404055;
  --accent:#ff3b5c;--accent2:#ff6b35;--accent3:#00d4aa;--accent4:#7c5cff;--accent5:#ffcc44;
  --radius:18px;--radius-sm:12px;--radius-xs:8px;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--white);min-height:100vh;overflow-x:hidden;}
body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;
  background:radial-gradient(ellipse 80% 60% at 10% 20%,rgba(124,92,255,0.07) 0%,transparent 60%),
             radial-gradient(ellipse 60% 50% at 90% 80%,rgba(0,212,170,0.05) 0%,transparent 60%);
  pointer-events:none;z-index:0;}
a{text-decoration:none;color:inherit;}
.navbar{position:sticky;top:0;z-index:100;background:rgba(10,10,15,0.88);backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);padding:0 32px;height:62px;display:flex;align-items:center;gap:16px;}
.brand{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;letter-spacing:-0.5px;}
.brand span{color:var(--accent);}
.nav-back{margin-left:auto;font-size:13px;color:var(--accent3);font-weight:600;
  padding:7px 16px;border:1px solid rgba(0,212,170,0.3);border-radius:20px;transition:all 0.2s;}
.nav-back:hover{background:rgba(0,212,170,0.1);}
.stepper-wrap{position:relative;z-index:1;max-width:1080px;margin:0 auto;padding:32px 20px 80px;}
.stepper{display:flex;align-items:center;justify-content:center;margin-bottom:36px;}
.step{display:flex;align-items:center;gap:10px;}
.step-circle{width:38px;height:38px;border-radius:50%;background:var(--surface2);
  border:2px solid var(--border2);display:flex;align-items:center;justify-content:center;
  font-family:'Syne',sans-serif;font-size:14px;font-weight:700;color:var(--gray);transition:all 0.35s;}
.step-label{font-size:12px;font-weight:600;color:var(--gray);transition:color 0.35s;white-space:nowrap;letter-spacing:0.3px;}
.step-line{width:60px;height:2px;background:var(--border2);margin:0 10px;transition:background 0.35s;flex-shrink:0;border-radius:2px;}
.step.active .step-circle{background:linear-gradient(135deg,var(--accent),var(--accent2));border-color:transparent;color:#fff;box-shadow:0 0 20px rgba(255,59,92,0.35);}
.step.active .step-label{color:var(--white);}
.step.done .step-circle{background:var(--accent3);border-color:transparent;color:#0a0a0f;}
.step.done .step-label{color:var(--accent3);}
.step-line.done{background:var(--accent3);}
.checkout-grid{display:grid;grid-template-columns:1fr 360px;gap:24px;align-items:start;}
@media(max-width:860px){.checkout-grid{grid-template-columns:1fr;}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  padding:28px;margin-bottom:20px;position:relative;overflow:hidden;animation:fadeUp 0.3s ease;}
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--accent),var(--accent2),var(--accent3));opacity:0;transition:opacity 0.3s;}
.card:hover::before{opacity:0.6;}
.card-title{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;color:var(--white);
  margin-bottom:20px;display:flex;align-items:center;gap:10px;letter-spacing:-0.3px;
  padding-bottom:16px;border-bottom:1px solid var(--border);}
.card-title-icon{width:30px;height:30px;border-radius:8px;background:var(--surface2);
  display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.field{display:flex;flex-direction:column;gap:7px;margin-bottom:14px;}
.field label{font-size:11px;font-weight:700;color:var(--gray);text-transform:uppercase;letter-spacing:0.9px;}
.field input,.field select{background:var(--surface2);border:1.5px solid var(--border);
  border-radius:var(--radius-xs);padding:12px 15px;font-size:14px;font-family:'DM Sans',sans-serif;
  color:var(--white);outline:none;transition:border-color 0.2s,box-shadow 0.2s;width:100%;}
.field input::placeholder{color:var(--gray2);}
.field input:focus,.field select:focus{border-color:var(--accent3);box-shadow:0 0 0 3px rgba(0,212,170,0.1);}
.field select option{background:var(--surface2);}
.field-error{font-size:12px;color:var(--accent);min-height:16px;margin-top:2px;}
.pin-loader{width:17px;height:17px;border:2px solid var(--border2);border-top-color:var(--accent3);border-radius:50%;animation:spin 0.7s linear infinite;}
@keyframes spin{to{transform:rotate(360deg)}}
.saved-addr-item{position:relative;padding:14px 16px;border:1.5px solid var(--border);
  border-radius:var(--radius-sm);margin-bottom:10px;cursor:pointer;background:var(--surface2);transition:all 0.2s;}
.saved-addr-item:hover{border-color:var(--accent3);background:rgba(0,212,170,0.04);}
.saved-addr-item.selected{border-color:var(--accent3);background:rgba(0,212,170,0.07);}
.saved-addr-item.default{border-color:rgba(0,212,170,0.3);}
.sa-badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;
  background:rgba(124,92,255,0.18);color:var(--accent4);margin-bottom:5px;letter-spacing:0.3px;}
.sa-name{font-size:14px;font-weight:600;color:var(--white);}
.sa-phone{font-size:12px;color:var(--gray);font-weight:400;}
.sa-addr{font-size:12px;color:var(--gray);line-height:1.5;margin-top:3px;}
.sa-default-tag{font-size:11px;color:var(--accent3);margin-top:4px;}
.sa-del-btn{position:absolute;top:12px;right:12px;background:none;border:none;font-size:14px;cursor:pointer;opacity:0.4;transition:opacity 0.2s;color:var(--white);}
.sa-del-btn:hover{opacity:1;color:var(--accent);}
/* areaField hidden by JS */
#area{border-color:var(--accent3);}
.save-row{display:flex;align-items:center;gap:10px;padding:12px 14px;
  background:var(--surface2);border-radius:var(--radius-xs);border:1px solid var(--border);margin-bottom:8px;}
.save-row label{font-size:13px;color:var(--white);font-weight:500;cursor:pointer;}
.order-item{display:flex;align-items:center;gap:14px;padding:13px 0;border-bottom:1px solid rgba(255,255,255,0.05);}
.order-item:last-child{border-bottom:none;}
.oi-em{font-size:26px;width:50px;height:50px;background:var(--surface2);border-radius:10px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.oi-info{flex:1;min-width:0;}
.oi-name{font-size:14px;font-weight:600;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.oi-cat{font-size:11px;color:var(--gray);margin-top:2px;}
.oi-price{font-size:15px;font-weight:700;color:var(--accent3);font-family:'Syne',sans-serif;flex-shrink:0;}
.summary-sticky{position:sticky;top:80px;}
.summary-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;}
.s-title{font-family:'Syne',sans-serif;font-size:15px;font-weight:700;color:var(--white);margin-bottom:16px;letter-spacing:-0.3px;}
.s-row{display:flex;justify-content:space-between;align-items:center;font-size:14px;
  padding:9px 0;border-bottom:1px solid rgba(255,255,255,0.04);}
.s-row:last-of-type{border-bottom:none;}
.s-label{color:var(--gray);}
.s-val{color:var(--white);font-weight:500;}
.s-divider{height:1px;background:var(--border);margin:12px 0;}
.s-total-row{display:flex;justify-content:space-between;align-items:center;}
.s-total-label{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;color:var(--white);}
.s-total-val{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;
  background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.free-tag{color:var(--accent3);font-weight:700;}
.disc-tag{color:var(--accent3);}
.coupon-row{display:flex;gap:8px;margin-top:14px;}
.coupon-inp{flex:1;background:var(--surface2);border:1.5px solid var(--border);border-radius:var(--radius-xs);
  padding:10px 12px;font-size:13px;color:var(--white);outline:none;font-family:'DM Sans',sans-serif;transition:border-color 0.2s;}
.coupon-inp:focus{border-color:var(--accent3);}
.coupon-inp::placeholder{color:var(--gray2);}
.coupon-btn{padding:10px 16px;background:var(--surface3);border:1.5px solid var(--border2);border-radius:var(--radius-xs);
  color:var(--white);font-size:13px;font-family:'DM Sans',sans-serif;cursor:pointer;font-weight:600;white-space:nowrap;transition:all 0.2s;}
.coupon-btn:hover{border-color:var(--accent3);color:var(--accent3);}
.coupon-msg{font-size:12px;margin-top:6px;display:none;align-items:center;gap:5px;}
.coupon-msg.ok{display:flex;color:var(--accent3);}
.coupon-msg.err{display:flex;color:var(--accent);}
.secure{display:flex;align-items:center;justify-content:center;gap:6px;font-size:11px;color:var(--gray);margin-top:14px;}
.btn-next{width:100%;padding:15px;background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#fff;border:none;border-radius:var(--radius-sm);font-size:15px;font-weight:700;
  font-family:'Syne',sans-serif;cursor:pointer;transition:all 0.2s;margin-top:8px;
  display:flex;align-items:center;justify-content:center;gap:8px;letter-spacing:0.3px;}
.btn-next:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(255,59,92,0.4);}
.btn-next:active{transform:translateY(0);}
.btn-back{width:100%;padding:13px;background:transparent;color:var(--gray);border:1.5px solid var(--border2);
  border-radius:var(--radius-sm);font-size:14px;font-weight:500;font-family:'DM Sans',sans-serif;
  cursor:pointer;transition:all 0.2s;margin-top:10px;}
.btn-back:hover{border-color:var(--white);color:var(--white);}
.btn-new-addr{background:transparent;border:1.5px dashed var(--border2);border-radius:var(--radius-sm);
  padding:12px 18px;color:var(--gray);font-size:13px;font-family:'DM Sans',sans-serif;cursor:pointer;
  transition:all 0.2s;margin-top:8px;display:block;width:100%;text-align:center;}
.btn-new-addr:hover{border-color:var(--accent3);color:var(--accent3);}
.mini-summary{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:13px 17px;margin-bottom:18px;display:flex;justify-content:space-between;align-items:center;
  font-size:13px;color:var(--gray);}
.mini-summary strong{color:var(--white);font-family:'Syne',sans-serif;font-size:15px;}
.mini-edit{font-size:12px;color:var(--accent3);font-weight:600;cursor:pointer;}
.mini-edit:hover{text-decoration:underline;}
.pay-tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:10px;}
.pay-tabs-r2{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px;}
.pay-tab{background:var(--surface2);border:1.5px solid var(--border);border-radius:var(--radius-sm);
  padding:14px 8px;cursor:pointer;text-align:center;transition:all 0.2s;position:relative;}
.pay-tab:hover{border-color:var(--border2);}
.pay-tab.active{border-color:var(--accent4);background:rgba(124,92,255,0.1);}
.pay-tab.active::after{content:'\\2713';position:absolute;top:6px;right:8px;font-size:11px;color:var(--accent3);font-weight:700;}
.pay-tab-icon{font-size:20px;margin-bottom:5px;}
.pay-tab-name{font-size:10px;font-weight:700;color:var(--gray);letter-spacing:0.4px;text-transform:uppercase;}
.pay-tab.active .pay-tab-name{color:var(--white);}
.pay-panel{display:none;animation:fadeUp 0.28s ease;}
.pay-panel.visible{display:block;}
.panel-title{font-size:13px;font-weight:700;color:var(--gray);text-transform:uppercase;letter-spacing:0.9px;margin-bottom:14px;}
.pay-now-btn{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;
  margin-top:16px;padding:16px 20px;
  background:linear-gradient(135deg,#f5c518,#f0a500);
  color:#111;border:none;border-radius:var(--radius-sm);
  font-family:'Syne',sans-serif;font-size:16px;font-weight:800;letter-spacing:0.3px;cursor:pointer;
  box-shadow:0 4px 20px rgba(245,197,24,0.3);transition:transform 0.18s,box-shadow 0.18s;position:relative;overflow:hidden;}
.pay-now-btn::after{content:'';position:absolute;inset:0;
  background:linear-gradient(135deg,rgba(255,255,255,0.16),transparent);pointer-events:none;}
.pay-now-btn:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(245,197,24,0.45);}
.pay-now-btn:active{transform:translateY(0);}
.pay-now-btn--cod{background:linear-gradient(135deg,#00c9a7,#00a98f);color:#fff;box-shadow:0 4px 20px rgba(0,201,167,0.28);}
.pay-now-btn--cod:hover{box-shadow:0 8px 28px rgba(0,201,167,0.42);}
.pay-lock{font-size:15px;}
.pay-now-amt{font-size:18px;font-weight:900;}
.pay-notice{font-size:12px;color:var(--gray);line-height:1.6;padding:10px 14px;
  background:rgba(255,255,255,0.03);border-left:3px solid var(--accent3);border-radius:0 8px 8px 0;margin-bottom:14px;}
.upi-apps{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;}
.upi-app-btn{display:flex;flex-direction:column;align-items:center;gap:5px;padding:10px 16px;
  border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--surface3);
  cursor:pointer;transition:all 0.15s;color:var(--white);font-size:11px;font-weight:700;
  font-family:'DM Sans',sans-serif;min-width:68px;}
.upi-app-btn img{width:30px;height:30px;object-fit:contain;border-radius:6px;}
.upi-app-btn:hover{border-color:var(--accent3);}
.upi-app-btn.selected{border-color:var(--accent3);background:rgba(0,212,170,0.09);color:var(--accent3);}
.card-preview{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);border-radius:14px;
  padding:20px 24px;margin-bottom:18px;position:relative;overflow:hidden;min-height:130px;
  border:1px solid rgba(255,255,255,0.1);}
.card-preview::before{content:'';position:absolute;width:200px;height:200px;border-radius:50%;
  background:rgba(255,255,255,0.04);top:-60px;right:-60px;}
.card-preview-chip{font-size:20px;margin-bottom:16px;color:gold;letter-spacing:2px;}
.card-preview-num{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;
  letter-spacing:3px;margin-bottom:16px;color:rgba(255,255,255,0.9);}
.card-preview-row{display:flex;align-items:flex-end;gap:24px;}
.card-preview-lbl{font-size:9px;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:3px;}
.card-preview-val{font-size:13px;font-weight:600;color:#fff;}
.card-preview-network{margin-left:auto;font-size:14px;font-weight:800;color:rgba(255,255,255,0.85);font-family:'Syne',sans-serif;}
.bank-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px;}
.bank-btn{padding:10px 6px;border:1.5px solid var(--border);border-radius:var(--radius-xs);
  background:var(--surface2);color:var(--white);font-size:12px;font-weight:600;cursor:pointer;
  transition:all 0.15s;font-family:'DM Sans',sans-serif;text-align:center;}
.bank-btn:hover{border-color:var(--accent3);}
.bank-btn.selected{border-color:var(--accent3);background:rgba(0,212,170,0.1);color:var(--accent3);}
.cod-box{text-align:center;padding:24px 16px;background:var(--surface2);border-radius:var(--radius-sm);
  border:1px solid var(--border);margin-bottom:16px;}
.cod-note{margin-top:12px;padding:9px 14px;background:rgba(255,204,68,0.08);
  border:1px solid rgba(255,204,68,0.25);border-radius:8px;font-size:12px;color:var(--accent5);}
#paypal-button-container{min-height:50px;}
.paypal-processing{display:none;align-items:center;justify-content:center;gap:10px;padding:14px;
  background:rgba(0,180,255,0.07);border:1px solid rgba(0,180,255,0.22);border-radius:var(--radius-sm);
  font-size:14px;color:#00b4ff;margin-top:12px;}
.pin-fetched-badge{display:inline-flex;align-items:center;gap:5px;background:rgba(0,212,170,0.1);
  border:1px solid rgba(0,212,170,0.3);color:var(--accent3);padding:3px 10px;border-radius:50px;
  font-size:11px;font-weight:600;margin-top:5px;}
@media(max-width:600px){
  .row2{grid-template-columns:1fr;}
  .bank-grid{grid-template-columns:repeat(3,1fr);}
  .pay-tabs,.pay-tabs-r2{grid-template-columns:repeat(3,1fr);}
  .card{padding:18px;}
  .stepper-wrap{padding:20px 12px 60px;}
  .navbar{padding:0 16px;}
}
</style>
</head>
<body>
<nav class="navbar">
  <a href="/" class="brand">My<span>Store</span></a>
  <span style="color:var(--gray);font-size:13px;">› Checkout</span>
  <a href="/" class="nav-back">← Back to store</a>
</nav>
<div class="stepper-wrap">
  <div class="stepper">
    <div class="step active" id="st1">
      <div class="step-circle" id="sc1">1</div>
      <div class="step-label">Address</div>
    </div>
    <div class="step-line" id="sl1"></div>
    <div class="step" id="st2">
      <div class="step-circle" id="sc2">2</div>
      <div class="step-label">Order Review</div>
    </div>
    <div class="step-line" id="sl2"></div>
    <div class="step" id="st3">
      <div class="step-circle" id="sc3">3</div>
      <div class="step-label">Payment</div>
    </div>
  </div>
  <form method="post" action="/checkout" id="mainForm">
    <input type="hidden" name="fname" id="hfname">
    <input type="hidden" name="lname" id="hlname">
    <input type="hidden" name="phone" id="hphone">
    <input type="hidden" name="address" id="haddress">
    <input type="hidden" name="city" id="hcity">
    <input type="hidden" name="pin" id="hpin">
    <input type="hidden" name="state" id="hstate">
    <input type="hidden" name="payment" id="hpayment" value="UPI">
  </form>

  {% if is_guest %}
  <div style="max-width:1080px;margin:0 auto 0;padding:0 20px;">
    <div style="background:rgba(124,92,255,0.1);border:1.5px solid rgba(124,92,255,0.3);border-radius:12px;padding:14px 20px;display:flex;align-items:center;gap:14px;margin-bottom:20px;">
      <span style="font-size:22px;">👤</span>
      <div>
        <div style="font-size:13px;font-weight:700;color:#c4b5fd;margin-bottom:2px;">Checking out as Guest</div>
        <div style="font-size:12px;color:var(--gray);">You're placing this order without an account. <a href="/" onclick="closeCart();openModal('loginModal');return false;" style="color:var(--accent3);font-weight:600;">Sign in</a> to save your address and track orders easily.</div>
      </div>
    </div>
  </div>
  {% endif %}
  <!-- STEP 1: ADDRESS -->
  <div id="step1">
  <div class="checkout-grid">
  <div>
    {% if saved_addresses %}
    <div class="card" id="savedAddrCard">
      <div class="card-title"><div class="card-title-icon">&#127968;</div> Saved Addresses</div>
      <div id="savedAddrList">
        {% for sa in saved_addresses %}
        <div class="saved-addr-item {% if sa.is_default %}default{% endif %}" id="sa-{{ sa.id }}"
             onclick="fillSavedAddress({{ sa.id }},'{{ sa.fname|e }}','{{ sa.lname|e }}','{{ sa.phone|e }}','{{ sa.address|e }}','{{ sa.pin|e }}','{{ sa.city|e }}','{{ sa.state|e }}')">
          <div class="sa-badge">{{ sa.label }}</div>
          <div class="sa-name">{{ sa.fname }} {{ sa.lname }} <span class="sa-phone">· {{ sa.phone }}</span></div>
          <div class="sa-addr">{{ sa.address }}, {{ sa.city }} – {{ sa.pin }}, {{ sa.state }}</div>
          {% if sa.is_default %}<div class="sa-default-tag">✓ Default</div>{% endif %}
          <button class="sa-del-btn" type="button" onclick="event.stopPropagation();deleteSavedAddr({{ sa.id }})">✕</button>
        </div>
        {% endfor %}
      </div>
      <button type="button" class="btn-new-addr" onclick="document.getElementById('newAddrSection').style.display='block';document.getElementById('savedAddrCard').style.display='none';">+ Add New Address</button>
    </div>
    <div id="newAddrSection" style="display:none;">
    {% else %}
    <div id="newAddrSection">
    {% endif %}
    <div class="card">
      <div class="card-title"><div class="card-title-icon">&#128230;</div> Delivery Address</div>
      <div class="row2">
        <div class="field"><label>First Name</label><input id="fname" placeholder="Rahul" autocomplete="given-name"></div>
        <div class="field"><label>Last Name</label><input id="lname" placeholder="Sharma" autocomplete="family-name"></div>
      </div>
      <div class="field"><label>Phone Number</label><input id="phone" placeholder="+91 98765 43210" type="tel" maxlength="13" autocomplete="tel"></div>
      <div class="field"><label>Address Line</label><input id="address" placeholder="Flat no., Society name, Street" autocomplete="street-address"></div>
      <div class="row2">
        <div class="field" style="position:relative;">
          <label>PIN Code</label>
          <div style="position:relative;">
            <input id="pin" placeholder="e.g. 400001" maxlength="6" inputmode="numeric"
              oninput="this.value=this.value.replace(/[^0-9]/g,'');onPinInput(this.value)"
              autocomplete="postal-code" style="padding-right:44px;">
            <div id="pinSpinner" style="display:none;position:absolute;right:13px;top:50%;transform:translateY(-50%);">
              <div class="pin-loader"></div>
            </div>
            <div id="pinTick" style="display:none;position:absolute;right:11px;top:50%;transform:translateY(-50%);color:var(--accent3);font-size:18px;font-weight:700;">✓</div>
          </div>
          <div id="pinError" class="field-error"></div>
        </div>
        <div class="field">
          <label>District / City</label>
          <input id="city" placeholder="Auto-filled from PIN">
        </div>
      </div>
      <div class="field" id="areaField">
        <label>Area / Locality <span style="color:var(--accent);font-size:10px;">← Select your area</span></label>
        <select id="area" onchange="onAreaChange(this.value)">
          <option value="">-- Select your Area / Locality --</option>
        </select>
      </div>
      <div class="field">
        <label>State / UT</label>
        <select id="state">
          <option value="">-- Select State --</option>
          <option>Andaman and Nicobar Islands</option><option>Andhra Pradesh</option>
          <option>Arunachal Pradesh</option><option>Assam</option><option>Bihar</option>
          <option>Chandigarh</option><option>Chhattisgarh</option>
          <option>Dadra and Nagar Haveli and Daman and Diu</option><option>Delhi</option>
          <option>Goa</option><option>Gujarat</option><option>Haryana</option>
          <option>Himachal Pradesh</option><option>Jammu and Kashmir</option>
          <option>Jharkhand</option><option>Karnataka</option><option>Kerala</option>
          <option>Ladakh</option><option>Lakshadweep</option><option>Madhya Pradesh</option>
          <option>Maharashtra</option><option>Manipur</option><option>Meghalaya</option>
          <option>Mizoram</option><option>Nagaland</option><option>Odisha</option>
          <option>Puducherry</option><option>Punjab</option><option>Rajasthan</option>
          <option>Sikkim</option><option>Tamil Nadu</option><option>Telangana</option>
          <option>Tripura</option><option>Uttar Pradesh</option><option>Uttarakhand</option>
          <option>West Bengal</option>
        </select>
      </div>
      {% if not is_guest %}
      <div class="save-row">
        <input type="checkbox" id="saveAddrCheck" style="width:16px;height:16px;accent-color:var(--accent3);flex-shrink:0;">
        <label for="saveAddrCheck">Save this address for future orders</label>
        <select id="saveAddrLabel" style="margin-left:auto;background:var(--surface3);border:1px solid var(--border2);color:var(--white);padding:4px 8px;border-radius:6px;font-size:12px;font-family:'DM Sans',sans-serif;outline:none;">
          <option>Home</option><option>Work</option><option>Other</option>
        </select>
      </div>
      {% endif %}
      <button type="button" class="btn-next" onclick="goStep2()">Continue to Order Review →</button>
      {% if saved_addresses %}
      <button type="button" class="btn-back" onclick="document.getElementById('savedAddrCard').style.display='block';document.getElementById('newAddrSection').style.display='none';">← Back to Saved Addresses</button>
      {% endif %}
    </div>
    </div>
  </div>
  <div class="summary-sticky">
    <div class="summary-card">
      <div class="s-title">Order Summary</div>
      {% for item in items %}
      <div class="order-item">
        <div class="oi-em">{{ item.emoji }}</div>
        <div class="oi-info">
          <div class="oi-name">{{ item.name }}</div>
          <div class="oi-cat">{{ item.category }}</div>
        </div>
        <div class="oi-price">₹{{ "{:,}".format(item.price) }}</div>
      </div>
      {% endfor %}
      <div class="s-divider"></div>
      <div class="s-row"><span class="s-label">Subtotal</span><span class="s-val">₹{{ "{:,}".format(subtotal) }}</span></div>
      <div class="s-row"><span class="s-label">Delivery</span>
        <span class="s-val">{% if subtotal >= 999 %}<span class="free-tag">FREE</span>{% else %}₹99{% endif %}</span>
      </div>
      <div class="s-row" id="discRow" style="display:none;">
        <span class="s-label" id="discLabel">Discount</span>
        <span class="s-val disc-tag" id="discAmt"></span>
      </div>
      <div class="s-divider"></div>
      <div class="s-total-row">
        <span class="s-total-label">Total</span>
        <span class="s-total-val" id="totalDisplay">₹{{ "{:,}".format(total) }}</span>
      </div>
      <div class="coupon-row">
        <input class="coupon-inp" id="couponInp" placeholder="Coupon code" oninput="this.value=this.value.toUpperCase()">
        <button class="coupon-btn" onclick="applyCoupon()">Apply</button>
      </div>
      <div class="coupon-msg" id="couponOk">✓ Coupon applied!</div>
      <div class="coupon-msg err" id="couponErr">Invalid coupon code.</div>
      <div class="secure">&#128274; SSL Encrypted · PCI DSS Compliant</div>
    </div>
  </div>
  </div>
  </div>

  <!-- STEP 2: ORDER REVIEW -->
  <div id="step2" style="display:none;">
  <div class="checkout-grid">
  <div>
    <div class="mini-summary">
      <div>
        <div style="font-size:11px;color:var(--gray);margin-bottom:3px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;">Delivering to</div>
        <strong id="addrPreview" style="font-size:13px;font-weight:500;font-family:'DM Sans',sans-serif;"></strong>
      </div>
      <span class="mini-edit" onclick="goStep(1)">Change</span>
    </div>
    <div class="card">
      <div class="card-title"><div class="card-title-icon">&#128717;</div> Your Items ({{ items|length }})</div>
      {% for item in items %}
      <div class="order-item">
        <div class="oi-em">{{ item.emoji }}</div>
        <div class="oi-info">
          <div class="oi-name">{{ item.name }}</div>
          <div class="oi-cat">{{ item.category }}</div>
        </div>
        <div class="oi-price">₹{{ "{:,}".format(item.price) }}</div>
      </div>
      {% endfor %}
    </div>
    <div class="card">
      <div class="card-title"><div class="card-title-icon">&#128176;</div> Price Breakdown</div>
      <div class="s-row"><span class="s-label">Items ({{ items|length }})</span><span class="s-val">₹{{ "{:,}".format(subtotal) }}</span></div>
      <div class="s-row"><span class="s-label">Delivery</span>
        <span class="s-val">{% if subtotal >= 999 %}<span class="free-tag">FREE</span>{% else %}₹99{% endif %}</span>
      </div>
      <div class="s-row" id="discRow2" style="display:none;">
        <span class="s-label" id="discLabel2">Discount</span>
        <span class="s-val disc-tag" id="discAmt2"></span>
      </div>
      <div class="s-divider"></div>
      <div class="s-total-row">
        <span class="s-total-label">Amount Payable</span>
        <span class="s-total-val" id="totalDisplay2">₹{{ "{:,}".format(total) }}</span>
      </div>
    </div>
    <button type="button" class="btn-next" onclick="goStep3()">Proceed to Payment →</button>
    <button type="button" class="btn-back" onclick="goStep(1)">← Back to Address</button>
  </div>
  <div class="summary-sticky">
    <div class="summary-card">
      <div class="s-title">Order Summary</div>
      {% for item in items %}
      <div class="order-item">
        <div class="oi-em">{{ item.emoji }}</div>
        <div class="oi-info"><div class="oi-name">{{ item.name }}</div></div>
        <div class="oi-price">₹{{ "{:,}".format(item.price) }}</div>
      </div>
      {% endfor %}
      <div class="s-divider"></div>
      <div class="s-total-row"><span class="s-total-label">Total</span><span class="s-total-val" id="totalDisplay3">₹{{ "{:,}".format(total) }}</span></div>
      <div class="secure">&#128274; SSL Encrypted · PCI DSS Compliant</div>
    </div>
  </div>
  </div>
  </div>

  <!-- STEP 3: PAYMENT -->
  <div id="step3" style="display:none;">
  <div class="checkout-grid">
  <div>
    <div class="mini-summary">
      <div>
        <div style="font-size:11px;color:var(--gray);margin-bottom:3px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;">Delivering to</div>
        <strong id="addrPreview2" style="font-size:13px;font-weight:500;font-family:'DM Sans',sans-serif;"></strong>
      </div>
      <span class="mini-edit" onclick="goStep(1)">Change</span>
    </div>
    <div class="card">
      <div class="card-title"><div class="card-title-icon">&#128179;</div> Choose Payment Method</div>
      <div class="pay-tabs" style="grid-template-columns:repeat(3,1fr);">
        <div class="pay-tab active" id="tab-RAZORPAY" onclick="selPay(this,'RAZORPAY','Razorpay')">
          <div class="pay-tab-icon">&#128274;</div><div class="pay-tab-name">Razorpay</div>
        </div>
        <div class="pay-tab" id="tab-PAYPAL" onclick="selPay(this,'PAYPAL','PayPal')">
          <div class="pay-tab-icon">&#127837;</div><div class="pay-tab-name">PayPal</div>
        </div>
        <div class="pay-tab" id="tab-COD" onclick="selPay(this,'COD','Cash on Delivery')">
          <div class="pay-tab-icon">&#128181;</div><div class="pay-tab-name">Cash on Delivery</div>
        </div>
      </div>

      <!-- RAZORPAY PANEL -->
      <div id="panel-RAZORPAY" class="pay-panel visible">
        <div class="panel-title">Pay via Razorpay</div>
        <div style="display:flex;align-items:center;gap:14px;background:var(--surface2);border:1.5px solid var(--border2);border-radius:12px;padding:18px 20px;margin-bottom:16px;">
          <img src="https://razorpay.com/favicon.ico" alt="Razorpay" style="width:36px;height:36px;border-radius:8px;">
          <div>
            <div style="font-size:14px;font-weight:700;color:var(--white);margin-bottom:3px;">Razorpay Secure Checkout</div>
            <div style="font-size:12px;color:var(--gray);line-height:1.5;">Pay using UPI, Cards, Net Banking, Wallets &amp; more — all in one secure gateway.</div>
          </div>
        </div>
        <div class="pay-notice">&#128274; You will be redirected to Razorpay secure checkout to complete payment. Your data is encrypted and never stored.</div>
        <button class="pay-now-btn" id="payBtn-RAZORPAY" onclick="submitOrder()">
          <span class="pay-lock">&#128274;</span> Pay <span class="pay-now-amt" id="payAmt-RAZORPAY">₹{{ "{:,}".format(total) }}</span>
        </button>
      </div>

      <!-- COD PANEL -->
      <div id="panel-COD" class="pay-panel" style="display:none;">
        <div class="cod-box">
          <div style="font-size:42px;margin-bottom:10px;">&#128181;</div>
          <div style="font-size:16px;font-weight:700;margin-bottom:6px;font-family:'Syne',sans-serif;">Cash on Delivery</div>
          <div style="font-size:13px;color:var(--gray);line-height:1.6;">Pay in cash when your order arrives.<br>Keep exact change ready — our partner will provide a receipt.</div>
          <div class="cod-note">⚠️ COD orders above ₹50,000 are not accepted. Available in 400+ cities.</div>
        </div>
        <button class="pay-now-btn pay-now-btn--cod" id="payBtn-COD" onclick="submitOrder()">
          Confirm Order · <span class="pay-now-amt" id="payAmt-COD">₹{{ "{:,}".format(total) }}</span> on Delivery
        </button>
      </div>

      <!-- PAYPAL PANEL -->
      <div id="panel-PAYPAL" class="pay-panel" style="display:none;">
        <div class="pay-notice" style="margin-bottom:14px;">&#127837; You'll be redirected to PayPal to securely complete your payment.</div>
        <div id="paypal-button-container"></div>
        <div class="paypal-processing" id="paypalProcessing">⏳ Processing PayPal payment…</div>
      </div>

      <button type="button" class="btn-back" id="backBtn" onclick="goStep(2)">← Back to Order Review</button>
      <div class="secure" style="margin-top:14px;">&#128274; 100% Secure · SSL Encrypted · PCI DSS Compliant</div>
    </div>
  </div>
  <div class="summary-sticky">
    <div class="summary-card">
      <div class="s-title">Order Summary</div>
      {% for item in items %}
      <div class="order-item">
        <div class="oi-em">{{ item.emoji }}</div>
        <div class="oi-info"><div class="oi-name">{{ item.name }}</div></div>
        <div class="oi-price">₹{{ "{:,}".format(item.price) }}</div>
      </div>
      {% endfor %}
      <div class="s-divider"></div>
      <div class="s-total-row"><span class="s-total-label">Total</span><span class="s-total-val" id="finalTotal">₹{{ "{:,}".format(total) }}</span></div>
      <div class="secure">&#128274; SSL Encrypted · PCI DSS Compliant</div>
    </div>
  </div>
  </div>
  </div>

</div>

<script src="https://www.paypal.com/sdk/js?client-id={{ paypal_client_id }}&currency=USD"></script>
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
<script>
var currentStep=1,selectedPayment='RAZORPAY',selectedPaymentLabel='Razorpay',selectedBank='',selectedUpiApp='gpay';
var subtotal={{ subtotal }},deliveryFee={{ 0 if subtotal >= 999 else 99 }},couponDiscount=0;
var paypalRendered=false,pinFetched=false,pinTimer=null,_cachedAddr={};

// ── STEP NAV ─────────────────────────────────────────────────
function goStep(n){
  document.getElementById('step'+currentStep).style.display='none';
  document.getElementById('step'+n).style.display='block';
  for(var i=1;i<=3;i++){
    var st=document.getElementById('st'+i),sc=document.getElementById('sc'+i);
    st.className='step'; sc.textContent=i;
    if(i<n){st.classList.add('done');sc.innerHTML='&#10003;';}
    else if(i===n){st.classList.add('active');}
    if(i<3){var sl=document.getElementById('sl'+i);sl.className='step-line'+(i<n?' done':'');}
  }
  currentStep=n;
  window.scrollTo({top:0,behavior:'smooth'});
}

// ── PIN LOOKUP ────────────────────────────────────────────────
function onPinInput(val){
  pinFetched=false;
  clearTimeout(pinTimer);
  document.getElementById('city').value='';
  document.getElementById('city').removeAttribute('readonly');
  document.getElementById('state').value='';
  document.getElementById('areaField').style.display='none';
  document.getElementById('area').innerHTML='<option value="">-- Select Area / Locality --</option>';
  document.getElementById('pinTick').style.display='none';
  document.getElementById('pinError').textContent='';
  if(val.length===6){ pinTimer=setTimeout(function(){fetchPinData(val);},400); }
}

function fetchPinData(pin){
  document.getElementById('pinSpinner').style.display='block';
  document.getElementById('pinTick').style.display='none';
  document.getElementById('pinError').textContent='';

  function applyResult(district,stateName,areas){
    document.getElementById('pinSpinner').style.display='none';
    document.getElementById('city').value=district;
    var stEl=document.getElementById('state');
    for(var i=0;i<stEl.options.length;i++){
      if(stEl.options[i].text.toLowerCase()===stateName.toLowerCase()){stEl.selectedIndex=i;break;}
    }
    var aEl=document.getElementById('area');
    aEl.innerHTML='<option value="">-- Select Area / Locality --</option>';
    if(areas&&areas.length){
      areas.forEach(function(a){
        var o=document.createElement('option');
        o.value=a.name;
        o.textContent=a.name+(a.type?' ('+a.type+')':'');
        aEl.appendChild(o);
      });
      document.getElementById('areaField').style.display='block';
    }
    document.getElementById('pinTick').style.display='block';
    pinFetched=true;
  }

  function tryServerProxy(){
    fetch('/api/pincode/'+pin)
      .then(function(r){return r.json();})
      .then(function(d){
        if(d&&d.ok&&d.district){applyResult(d.district,d.state||'',d.areas||[]);}
        else{showPinError('PIN not found. Please enter city and state manually.');}
      })
      .catch(function(){showPinError('Could not auto-fill. Please enter city and state manually.');});
  }

  function showPinError(msg){
    document.getElementById('pinSpinner').style.display='none';
    document.getElementById('pinError').textContent='⚠ '+msg;
    document.getElementById('city').placeholder='Enter your district / city';
    pinFetched=true;
  }

  // Try direct API call from browser first
  fetch('https://api.postalpincode.in/pincode/'+pin)
    .then(function(r){return r.json();})
    .then(function(data){
      if(!data||!data[0]||data[0].Status!=='Success'||!data[0].PostOffice||!data[0].PostOffice.length){
        tryServerProxy(); return;
      }
      var posts=data[0].PostOffice;
      var seen={},areas=[];
      posts.forEach(function(p){
        var n=(p.Name||'').trim();
        if(n&&!seen[n]){seen[n]=1;areas.push({name:n,type:p.BranchType||''});}
      });
      applyResult(posts[0].District||'',posts[0].State||'',areas);
    })
    .catch(function(){tryServerProxy();});
}

function onAreaChange(val){
  if(val&&!document.getElementById('address').value.trim())
    document.getElementById('address').placeholder=val+', '+document.getElementById('city').value;
}

// ── SAVED ADDRESSES ───────────────────────────────────────────
function fillSavedAddress(id,fname,lname,phone,address,pin,city,state){
  document.querySelectorAll('.saved-addr-item').forEach(function(e){e.classList.remove('selected');});
  var el=document.getElementById('sa-'+id);
  if(el)el.classList.add('selected');
  document.getElementById('fname').value=fname;
  document.getElementById('lname').value=lname;
  document.getElementById('phone').value=phone;
  document.getElementById('address').value=address;
  document.getElementById('pin').value=pin;
  document.getElementById('city').value=city;
  document.getElementById('pinTick').style.display='block';
  document.getElementById('pinSpinner').style.display='none';
  document.getElementById('pinError').textContent='';
  pinFetched=true;
  var stEl=document.getElementById('state');
  for(var i=0;i<stEl.options.length;i++){
    if(stEl.options[i].text===state||stEl.options[i].text.toLowerCase()===state.toLowerCase()){stEl.selectedIndex=i;break;}
  }
  var savedCard=document.getElementById('savedAddrCard');
  if(savedCard)savedCard.style.display='none';
  document.getElementById('newAddrSection').style.display='block';
  window.scrollTo({top:0,behavior:'smooth'});
}

function deleteSavedAddr(id){
  if(!confirm('Remove this saved address?'))return;
  fetch('/saved-address/'+id+'/delete',{method:'POST'})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){
        var el=document.getElementById('sa-'+id);
        if(el)el.remove();
        if(!document.querySelectorAll('.saved-addr-item').length){
          var c=document.getElementById('savedAddrCard');
          if(c)c.style.display='none';
          var ns=document.getElementById('newAddrSection');
          if(ns)ns.style.display='block';
        }
      }
    });
}

// ── STEP 1 → 2 ────────────────────────────────────────────────
function goStep2(){
  clearTimeout(pinTimer);
  document.getElementById('pinSpinner').style.display='none';
  var fname=document.getElementById('fname').value.trim();
  var lname=document.getElementById('lname').value.trim();
  var phone=document.getElementById('phone').value.trim();
  var address=document.getElementById('address').value.trim();
  var city=document.getElementById('city').value.trim();
  var pin=document.getElementById('pin').value.trim();
  var state=document.getElementById('state').value.trim();
  var areaEl=document.getElementById('area');
  var area=areaEl?areaEl.value.trim():'';

  if(!fname){alert('Please enter your First Name.');return;}
  if(!lname){alert('Please enter your Last Name.');return;}
  var digits=phone.replace(/[^0-9]/g,'');
  if(digits.length<10){alert('Please enter a valid phone number (at least 10 digits).');return;}
  if(!address){alert('Please enter your Address Line.');return;}
  if(!/^[0-9]{6}$/.test(pin)){alert('Please enter a valid 6-digit PIN code.');return;}
  if(!city){alert('Please enter your District / City.');document.getElementById('city').focus();return;}
  if(!state){alert('Please select your State.');return;}

  var fullAddr=address+(area?', '+area:'')+', '+city+' - '+pin+', '+state;
  var preview=fname+' '+lname+', '+fullAddr;
  document.getElementById('addrPreview').textContent=preview;
  document.getElementById('addrPreview2').textContent=preview;
  if(area)document.getElementById('address').value=address+', '+area;

  var saveCheck=document.getElementById('saveAddrCheck');
  if(saveCheck&&saveCheck.checked){
    var label=document.getElementById('saveAddrLabel').value||'Home';
    fetch('/saved-address/add',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({fname:fname,lname:lname,phone:phone,
        address:document.getElementById('address').value,city:city,pin:pin,state:state,label:label})
    }).catch(function(){});
    saveCheck.checked=false;
  }
  _cachedAddr={fname:fname,lname:lname,phone:phone,
    address:document.getElementById('address').value,city:city,pin:pin,state:state};
  goStep(2);
}

function goStep3(){goStep(3);updateFinalTotal();}

// ── PAYMENT TABS ─────────────────────────────────────────────
function selPay(el,key,label){
  document.querySelectorAll('.pay-tab').forEach(function(t){t.classList.remove('active');});
  document.querySelectorAll('.pay-panel').forEach(function(p){p.style.display='none';p.classList.remove('visible');});
  el.classList.add('active');
  selectedPayment=key; selectedPaymentLabel=label||key;
  var panel=document.getElementById('panel-'+key);
  if(panel){panel.style.display='block';panel.classList.add('visible');}
  if(key==='PAYPAL'&&!paypalRendered){renderPayPalButton();paypalRendered=true;}
}

// ── UPI ──────────────────────────────────────────────────────
function selUpiApp(btn,app){
  document.querySelectorAll('.upi-app-btn').forEach(function(b){b.classList.remove('selected');});
  btn.classList.add('selected');
  selectedUpiApp=app;
  var hints={gpay:'yourname@okaxis',phonepe:'yourname@ybl',paytm:'yourname@paytm',other:'yourname@upi'};
  document.getElementById('upiId').placeholder=hints[app]||'yourname@upi';
  var appNames={gpay:'Google Pay',phonepe:'PhonePe',paytm:'Paytm',other:'your UPI app'};

}

function validateUpi(val){
  var tick=document.getElementById('upiTick'),err=document.getElementById('upiErr');
  if(/^[a-zA-Z0-9._-]+@[a-zA-Z0-9]+$/.test(val)){tick.style.display='block';err.textContent='';}
  else{tick.style.display='none';if(val.length>3)err.textContent='Invalid UPI ID (e.g. name@upi)';}
}

// ── CARD ────────────────────────────────────────────────────
function fmtCard(inp){
  var v=inp.value.replace(/[^0-9]/g,'').substring(0,16);
  inp.value=v.replace(/(.{4})/g,'$1 ').trim();
  document.getElementById('cpNum').textContent=v?v.replace(/(.{4})/g,'$1 ').trim():'**** **** **** ****';
  var net='CARD';
  if(/^4/.test(v))net='VISA';
  else if(/^5[1-5]/.test(v)||/^2[2-7]/.test(v))net='MC';
  else if(/^6/.test(v))net='RuPay';
  else if(/^3[47]/.test(v))net='AMEX';
  document.getElementById('cpNet').textContent=net;
}

function fmtExp(inp){
  var v=inp.value.replace(/[^0-9]/g,'').substring(0,4);
  if(v.length>2)v=v.substring(0,2)+'/'+v.substring(2);
  inp.value=v;
  document.getElementById('cpExp').textContent=v||'MM/YY';
}

function validateCard(){
  var num=document.getElementById('cardNum').value.replace(/[^0-9]/g,'');
  var name=document.getElementById('cardName').value.trim();
  var exp=document.getElementById('cardExp').value.trim();
  var cvv=document.getElementById('cardCvv').value.trim();
  var err=document.getElementById('cardErr');
  if(num.length<15){err.textContent='Enter a valid card number.';return false;}
  if(!name){err.textContent='Enter the name on card.';return false;}
  var expParts=exp.split('/');
  if(expParts.length!==2||expParts[0].length!==2||expParts[1].length!==2){err.textContent='Enter expiry as MM/YY.';return false;}
  if(cvv.length<3){err.textContent='Enter a valid CVV.';return false;}
  err.textContent='';return true;
}

// ── NET BANKING ──────────────────────────────────────────────
function selBank(btn,bank){
  document.querySelectorAll('.bank-btn').forEach(function(b){b.classList.remove('selected');});
  btn.classList.add('selected');
  selectedBank=bank;
  document.getElementById('bankOther').value='';
  document.getElementById('bankErr').textContent='';
}

function selBankText(val){
  document.querySelectorAll('.bank-btn').forEach(function(b){b.classList.remove('selected');});
  selectedBank=val.trim();
}

function validateNetBanking(){
  if(!selectedBank){document.getElementById('bankErr').textContent='Please select a bank.';return false;}
  document.getElementById('bankErr').textContent='';return true;
}

// ── COUPON ───────────────────────────────────────────────────
function applyCoupon(){
  var v=document.getElementById('couponInp').value.trim().toUpperCase();
  var ok=document.getElementById('couponOk'),err=document.getElementById('couponErr');
  ok.className='coupon-msg'; err.className='coupon-msg err';
  if(v==='FIRST10'||v==='LOOP10'||v==='SAVE10'){
    couponDiscount=Math.round(subtotal*0.1);
    ok.className='coupon-msg ok';
    document.getElementById('discRow').style.display='flex';
    document.getElementById('discLabel').textContent='Discount ('+v+')';
    document.getElementById('discAmt').textContent='-Rs '+couponDiscount.toLocaleString('en-IN');
    document.getElementById('discRow2').style.display='flex';
    document.getElementById('discLabel2').textContent='Discount ('+v+')';
    document.getElementById('discAmt2').textContent='-Rs '+couponDiscount.toLocaleString('en-IN');
    updateAllPayBtns('Rs '+(subtotal+deliveryFee-couponDiscount).toLocaleString('en-IN'));
  } else {
    couponDiscount=0; err.className='coupon-msg err';
    document.getElementById('discRow').style.display='none';
    document.getElementById('discRow2').style.display='none';
    updateAllPayBtns('Rs '+(subtotal+deliveryFee).toLocaleString('en-IN'));
  }
}

function updateAllPayBtns(amtStr){
  ['payAmt-RAZORPAY','payAmt-COD'].forEach(function(id){
    var el=document.getElementById(id); if(el)el.textContent=amtStr;
  });
  ['totalDisplay','totalDisplay2','totalDisplay3','finalTotal'].forEach(function(id){
    var el=document.getElementById(id); if(el)el.textContent=amtStr;
  });
}

function updateFinalTotal(){
  updateAllPayBtns('Rs '+(subtotal+deliveryFee-couponDiscount).toLocaleString('en-IN'));
}

// ── SUBMIT ORDER ─────────────────────────────────────────────
function submitOrder(){
  var fname=_cachedAddr.fname||document.getElementById('fname').value.trim();
  var phone=_cachedAddr.phone||document.getElementById('phone').value.trim();
  var address=_cachedAddr.address||document.getElementById('address').value.trim();
  var city=_cachedAddr.city||document.getElementById('city').value.trim();
  var pin=_cachedAddr.pin||document.getElementById('pin').value.trim();
  var state=_cachedAddr.state||document.getElementById('state').value.trim();
  var lname=_cachedAddr.lname||document.getElementById('lname').value.trim();
  if(!fname||!phone||!address||!city||!pin||!state){
    alert('Please complete your delivery address first.');goStep(1);return;
  }

  var activeBtn=document.getElementById('payBtn-'+selectedPayment);
  if(activeBtn){
    activeBtn.disabled=true;
    activeBtn.innerHTML='<span style="display:inline-block;width:16px;height:16px;border:3px solid rgba(0,0,0,.3);border-top-color:#111;border-radius:50%;animation:spin .7s linear infinite;margin-right:8px;vertical-align:middle;"></span>Opening Gateway...';
  }

  if(selectedPayment==='COD'){
    document.getElementById('hfname').value=fname;
    document.getElementById('hlname').value=lname;
    document.getElementById('hphone').value=phone;
    document.getElementById('haddress').value=address;
    document.getElementById('hcity').value=city;
    document.getElementById('hpin').value=pin;
    document.getElementById('hstate').value=state;
    document.getElementById('hpayment').value='Cash on Delivery';
    document.getElementById('mainForm').submit();
    return;
  }

  var payLabel=selectedPaymentLabel;
  var payload={fname:fname,lname:lname,phone:phone,address:address,city:city,pin:pin,state:state,
    payment_method:selectedPayment,payment_label:payLabel,
    upi_id:'',bank:'',coupon_discount:couponDiscount};

  fetch('/razorpay/create-order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.error){
      alert('Payment error: '+d.error);
      if(activeBtn){activeBtn.disabled=false;activeBtn.innerHTML='Pay';}
      return;
    }
    var options={
      key:d.key_id,amount:d.amount,currency:'INR',name:'MyStore',
      description:'Order Payment',order_id:d.razorpay_order_id,
      prefill:{name:fname+' '+lname,contact:phone,email:d.email||''},
      theme:{color:'#ff3b5c'},
      modal:{ondismiss:function(){
        if(activeBtn){activeBtn.disabled=false;activeBtn.innerHTML='Pay Rs '+d.amount_display;}
      }},
      handler:function(response){
        if(activeBtn)activeBtn.innerHTML='Confirming...';
        fetch('/razorpay/verify-payment',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            razorpay_order_id:response.razorpay_order_id,
            razorpay_payment_id:response.razorpay_payment_id,
            razorpay_signature:response.razorpay_signature,
            fname:fname,lname:lname,phone:phone,address:address,city:city,pin:pin,state:state,
            payment_label:payLabel,coupon_discount:couponDiscount
          })
        }).then(function(r){return r.json();}).then(function(res){
          if(res.success){window.location.href='/order-success/'+res.order_id;}
          else{alert('Verification failed. Contact support. Ref: '+(response.razorpay_payment_id||''));if(activeBtn)activeBtn.disabled=false;}
        });
      }
    };
    var rzp=new Razorpay(options);
    rzp.on('payment.failed',function(resp){
      alert('Payment failed: '+resp.error.description);
      if(activeBtn){activeBtn.disabled=false;activeBtn.innerHTML='Pay Rs '+d.amount_display;}
    });
    rzp.open();
  })
  .catch(function(){
    alert('Network error. Please try again.');
    if(activeBtn){activeBtn.disabled=false;activeBtn.innerHTML='Pay';}
  });
}

// ── PAYPAL ───────────────────────────────────────────────────
function renderPayPalButton(){
  paypal.Buttons({
    style:{layout:'vertical',color:'gold',shape:'rect',label:'pay',height:48},
    createOrder:function(){
      return fetch('/paypal/create-order',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({coupon_discount:couponDiscount})
      }).then(function(r){return r.json();}).then(function(d){
        if(d.error){alert('PayPal error: '+d.error);throw new Error(d.error);}
        return d.id;
      });
    },
    onApprove:function(data){
      document.getElementById('paypalProcessing').style.display='flex';
      document.getElementById('paypal-button-container').style.display='none';
      return fetch('/paypal/capture-order',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          paypal_order_id:data.orderID,
          fname:_cachedAddr.fname||'',lname:_cachedAddr.lname||'',phone:_cachedAddr.phone||'',
          address:_cachedAddr.address||'',city:_cachedAddr.city||'',pin:_cachedAddr.pin||'',
          state:_cachedAddr.state||'',coupon_discount:couponDiscount
        })
      }).then(function(r){return r.json();}).then(function(d){
        if(d.success){window.location.href='/order-success/'+d.order_id;}
        else{alert('Capture failed: '+(d.error||'Unknown'));
          document.getElementById('paypalProcessing').style.display='none';
          document.getElementById('paypal-button-container').style.display='block';}
      });
    },
    onError:function(err){console.error('PayPal error',err);alert('PayPal error. Please try another method.');},
    onCancel:function(){console.log('PayPal cancelled.');}
  }).render('#paypal-button-container');
}
</script>
</body>
</html>"""



SUCCESS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Order Confirmed – MyStore</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{--primary:#0a0a0f;--accent:#ff3b5c;--surface:#111118;--surface2:#1a1a24;--white:#fff;--gray:#9898b0;--border:rgba(255,255,255,0.07);--radius:16px;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--primary);color:var(--white);}
a{text-decoration:none;color:inherit;}
.navbar{background:rgba(10,10,15,0.95);padding:16px 48px;display:flex;align-items:center;border-bottom:1px solid var(--border);}
.brand{font-family:'Syne',sans-serif;font-size:24px;font-weight:800;}
.brand span{color:var(--accent);}
.center{max-width:580px;margin:60px auto;padding:0 24px;text-align:center;}
.tick{font-size:80px;margin-bottom:24px;animation:pop .6s cubic-bezier(0.175,0.885,0.32,1.275);}
@keyframes pop{from{transform:scale(0) rotate(-15deg)}to{transform:scale(1) rotate(0)}}
h1{font-family:'Syne',sans-serif;font-size:32px;font-weight:800;margin-bottom:12px;}
.sub{color:var(--gray);font-size:15px;margin-bottom:36px;line-height:1.6;}
.card{background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);padding:26px;text-align:left;margin-bottom:22px;}
.card h3{font-family:'Syne',sans-serif;font-size:15px;font-weight:700;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border);}
.info-row{display:flex;justify-content:space-between;font-size:14px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04);}
.info-row:last-child{border-bottom:none;}
.info-row span:first-child{color:var(--gray);}
.info-row span:last-child{font-weight:600;}
.status-badge{display:inline-block;padding:4px 12px;border-radius:50px;font-size:12px;font-weight:700;background:rgba(255,179,71,0.15);color:#ffb347;}
.order-item{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.04);}
.order-item:last-child{border-bottom:none;}
.oi-em{font-size:30px;width:44px;height:44px;background:var(--surface2);border-radius:10px;display:flex;align-items:center;justify-content:center;}
.oi-name{font-size:13px;font-weight:600;flex:1;}
.oi-price{font-size:14px;font-weight:700;color:var(--accent);}
.btns{display:flex;gap:12px;justify-content:center;}
.btn{padding:13px 28px;border-radius:50px;font-size:14px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;transition:all 0.2s;}
.btn.primary{background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;border:none;box-shadow:0 6px 20px rgba(255,59,92,0.3);}
.btn.primary:hover{transform:translateY(-2px);}
.btn.outline{background:transparent;color:var(--white);border:1.5px solid var(--border);}
.btn.outline:hover{border-color:var(--accent);color:var(--accent);}
</style>
</head>
<body>
<nav class="navbar">
  <a href="/" class="brand">My<span>Store</span></a>
</nav>
<div class="center">
  <div class="tick">✅</div>
  <h1>Order Confirmed!</h1>
  <p class="sub">Thank you for shopping with MyStore 🎉<br>Your order is being processed and will be delivered soon.</p>
  <div class="card">
    <h3>Order Details</h3>
    <div class="info-row"><span>Order ID</span><span>#{{ order.id }}</span></div>
    <div class="info-row"><span>Date</span><span>{{ order.created_at.strftime('%d %b %Y, %I:%M %p') }}</span></div>
    <div class="info-row"><span>Payment</span><span>{{ order.payment }}</span></div>
    <div class="info-row"><span>Delivery to</span><span>{{ order.address }}</span></div>
    <div class="info-row"><span>Total Paid</span><span>₹{{ "{:,}".format(order.total) }}</span></div>
    <div class="info-row"><span>Status</span><span><span class="status-badge">{{ order.status }}</span></span></div>
  </div>
  <div class="card">
    <h3>Items Ordered</h3>
    {% for item in order.items %}
    <div class="order-item">
      <div class="oi-em">{{ item.product_emoji }}</div>
      <div class="oi-name">{{ item.product_name }}</div>
      <div class="oi-price">₹{{ "{:,}".format(item.price) }}</div>
    </div>
    {% endfor %}
  </div>
  <div class="btns">
    <a href="/orders"><button class="btn outline">📋 My Orders</button></a>
    <a href="/"><button class="btn primary">Continue Shopping →</button></a>
  </div>
</div>
</body>
</html>"""

ORDERS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>My Orders – MyStore</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{--primary:#0a0a0f;--accent:#ff3b5c;--surface:#111118;--surface2:#1a1a24;--white:#fff;--gray:#9898b0;--border:rgba(255,255,255,0.07);--radius:16px;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--primary);color:var(--white);}
a{text-decoration:none;color:inherit;}
.navbar{background:rgba(10,10,15,0.95);padding:16px 48px;display:flex;align-items:center;gap:16px;border-bottom:1px solid var(--border);}
.brand{font-family:'Syne',sans-serif;font-size:24px;font-weight:800;}
.brand span{color:var(--accent);}
.wrap{max-width:860px;margin:40px auto;padding:0 24px;}
.page-title{font-family:'Syne',sans-serif;font-size:30px;font-weight:800;margin-bottom:8px;}
.page-sub{color:var(--gray);font-size:14px;margin-bottom:30px;}
.order-card{background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);margin-bottom:22px;overflow:hidden;transition:all 0.2s;}
.order-card:hover{border-color:rgba(255,59,92,0.2);box-shadow:0 8px 28px rgba(0,0,0,0.3);}
.order-head{display:flex;align-items:center;gap:16px;padding:20px 24px;border-bottom:1px solid var(--border);background:var(--surface2);}
.order-id{font-family:'Syne',sans-serif;font-weight:700;font-size:16px;}
.order-date{font-size:12px;color:var(--gray);}
.order-total{font-family:'Syne',sans-serif;font-weight:700;font-size:16px;color:var(--accent);margin-left:auto;}
.status-badge{display:inline-block;padding:5px 14px;border-radius:50px;font-size:11px;font-weight:700;}
.status-badge.processing{background:rgba(255,179,71,0.15);color:#ffb347;}
.status-badge.shipped{background:rgba(59,130,246,0.15);color:#60a5fa;}
.status-badge.delivered{background:rgba(0,212,170,0.15);color:#00d4aa;}
.status-badge.cancelled{background:rgba(255,59,92,0.15);color:var(--accent);}
.order-items{padding:16px 24px;}
.oi-row{display:flex;align-items:center;gap:14px;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.04);}
.oi-row:last-child{border-bottom:none;}
.oi-em{font-size:32px;width:48px;height:48px;background:var(--surface2);border-radius:10px;display:flex;align-items:center;justify-content:center;}
.oi-info{flex:1;}
.oi-name{font-size:14px;font-weight:600;}
.oi-price{font-size:14px;font-weight:700;color:var(--gray);}
.order-foot{display:flex;align-items:center;gap:12px;padding:16px 24px;border-top:1px solid var(--border);background:var(--surface2);}
.pay-tag{font-size:12px;color:var(--gray);}
.track-btn{margin-left:auto;padding:9px 20px;background:var(--surface);color:var(--white);border:1.5px solid var(--border);border-radius:50px;font-size:12px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;transition:all 0.2s;}
.track-btn:hover{border-color:var(--accent);color:var(--accent);}
.empty{text-align:center;padding:90px 20px;color:var(--gray);}
.empty .em{font-size:72px;margin-bottom:20px;display:block;}
.empty h2{font-family:'Syne',sans-serif;font-size:24px;color:var(--white);margin-bottom:10px;}
.shop-btn{display:inline-block;margin-top:22px;padding:14px 32px;background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;border-radius:50px;font-weight:700;font-size:14px;font-family:'Syne',sans-serif;}
</style>
</head>
<body>
<nav class="navbar">
  <a href="/" class="brand">My<span>Store</span></a>
  <span style="color:var(--gray);font-size:13px;">› My Orders</span>
  <a href="/" style="margin-left:auto;font-size:13px;color:var(--accent);font-weight:600;">← Continue Shopping</a>
</nav>
<div class="wrap">
  <div class="page-title">My Orders</div>
  <div class="page-sub">{{ orders|length }} order{{ 's' if orders|length != 1 else '' }} placed</div>
  {% if orders %}
    {% for o in orders %}
    <div class="order-card">
      <div class="order-head">
        <div>
          <div class="order-id">Order #{{ o.id }}</div>
          <div class="order-date">{{ o.created_at.strftime('%d %b %Y · %I:%M %p') }}</div>
        </div>
        <span class="status-badge {{ o.status.lower() }}">{{ o.status }}</span>
        <div class="order-total">₹{{ "{:,}".format(o.total) }}</div>
      </div>
      <div class="order-items">
        {% for item in o.items %}
        <div class="oi-row">
          <div class="oi-em">{{ item.product_emoji }}</div>
          <div class="oi-info"><div class="oi-name">{{ item.product_name }}</div></div>
          <div class="oi-price">₹{{ "{:,}".format(item.price) }}</div>
        </div>
        {% endfor %}
      </div>
      <div class="order-foot">
        <span class="pay-tag">💳 {{ o.payment }} · 📍 {{ o.address[:60] }}...</span>
        <button class="track-btn">Track Order →</button>
      </div>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">
      <span class="em">📦</span>
      <h2>No orders yet!</h2>
      <p>Looks like you haven't placed any orders. Let's fix that!</p>
      <a href="/" class="shop-btn">Start Shopping →</a>
    </div>
  {% endif %}
</div>
</body>
</html>"""


# ================= ROUTES =================
def build_cart_html(user_id=None):
    """Build cart HTML. user_id=None means guest (session-based cart)."""
    import uuid as _uuid
    if user_id:
        items = Cart.query.filter_by(user_id=user_id).all()
        if not items:
            return '<div class="cart-empty"><span class="cart-empty-icon">🛒</span><p>Your cart is empty</p></div>', 0, 0
        total = 0
        count = 0
        html = ""
        for i in items:
            p = db.session.get(Product, i.product_id)
            if p:
                qty = i.quantity or 1
                item_total = p.price * qty
                total += item_total
                count += qty
                html += f"""<div class="cart-item" id="citem-{i.id}">
              <div class="cart-item-em">{'<img src="' + p.image_url + '" style="width:100%;height:100%;object-fit:cover;border-radius:10px;" onerror="this.style.display=\'none\'">' if getattr(p, 'image_url', '') else p.emoji}</div>
              <div class="cart-item-info">
                <div class="cart-item-name">{p.name}</div>
                <div class="cart-item-price">₹{item_total:,}</div>
              </div>
              <div class="cart-qty-ctrl">
                <button class="qty-btn" onclick="updateQty({i.id}, -1)">−</button>
                <span class="qty-val">{qty}</span>
                <button class="qty-btn" onclick="updateQty({i.id}, 1)">+</button>
              </div>
              <button class="cart-item-remove" onclick="removeFromCart({i.id})">✕</button>
            </div>"""
        return html, total, count
    else:
        # Guest cart stored in flask_session as list of {cart_key, product_id, quantity}
        guest_cart = flask_session.get('guest_cart', [])
        if not guest_cart:
            return '<div class="cart-empty"><span class="cart-empty-icon">🛒</span><p>Your cart is empty</p></div>', 0, 0
        total = 0
        count = 0
        html = ""
        for entry in guest_cart:
            p = db.session.get(Product, entry['product_id'])
            if p:
                qty = entry.get('quantity', 1)
                item_total = p.price * qty
                total += item_total
                count += qty
                ck = entry['cart_key']
                html += f"""<div class="cart-item" id="citem-{ck}">
              <div class="cart-item-em">{'<img src="' + p.image_url + '" style="width:100%;height:100%;object-fit:cover;border-radius:10px;" onerror="this.style.display=\'none\'">' if getattr(p, 'image_url', '') else p.emoji}</div>
              <div class="cart-item-info">
                <div class="cart-item-name">{p.name}</div>
                <div class="cart-item-price">₹{item_total:,}</div>
              </div>
              <div class="cart-qty-ctrl">
                <button class="qty-btn" onclick="updateQty('{ck}', -1)">−</button>
                <span class="qty-val">{qty}</span>
                <button class="qty-btn" onclick="updateQty('{ck}', 1)">+</button>
              </div>
              <button class="cart-item-remove" onclick="removeFromCart('{ck}')">✕</button>
            </div>"""
        return html, total, count


@app.template_filter('format_num')
def format_num_filter(val):
    try:
        return f"{int(val):,}"
    except:
        return val


@app.route('/')
def home():
    sv = request.args.get('search', '')
    ac = request.args.get('category', '')
    sub = request.args.get('sub', '')
    fo = request.args.get('flash', '')
    na = request.args.get('new_arrivals', '')
    added = request.args.get('added', '')
    nl = request.args.get('need_login', '')
    oauth_error = request.args.get('oauth_error', '')

    cc = 0
    cart_total = 0
    if current_user.is_authenticated:
        ch, cart_total, cc = build_cart_html(current_user.id)
    else:
        ch, cart_total, cc = build_cart_html()

    if sv or (ac and ac != 'all') or sub or fo or na:
        q = Product.query
        if sv: q = q.filter(Product.name.ilike(f'%{sv}%'))
        if ac and ac != 'all': q = q.filter_by(category=ac)
        if sub: q = q.filter_by(subcategory=sub)
        if fo: q = q.filter_by(is_flash=True)
        prods = q.all()
        if prods:
            cards = "<div class='pgrid'>" + "".join(make_card(p, False) for p in prods) + "</div>"
        else:
            cards = "<div class='empty'><div class='em'>😕</div><p>No products found. Try a different search!</p></div>"
        if fo:
            label = "🔥 Flash Sale"
        elif na:
            label = "✨ New Arrivals"
        elif ac == 'all' or (not sv and not sub):
            label = "🛍️ All Products"
        else:
            label = sub or ac or f'Results for "{sv}"'
        pc = f"<div class='ptitle'><h1>{label}</h1> <span>{len(prods) if prods else 0} products</span></div><div class='sec'>{cards}</div>"
    elif ac == 'all':
        prods = Product.query.all()
        cards = "<div class='pgrid'>" + "".join(make_card(p, False) for p in prods) + "</div>"
        pc = f"<div class='ptitle'><h1>🛍️ All Products</h1> <span>{len(prods)} products</span></div><div class='sec'>{cards}</div>"
    else:
        flash_prods = Product.query.filter_by(is_flash=True).limit(10).all()
        fc = "".join(make_card(p) for p in flash_prods)
        today_prods = Product.query.all()
        tc = "".join(make_card(p, False) for p in today_prods)
        ads = Advertisement.query.order_by(Advertisement.slot).all()
        pc = render_home(fc, tc, ads=ads)

    return render_template_string(PAGE, pc=pc, ac=ac, sv=sv, fo=fo,
        added=added, need_login=nl, cc=cc, ch=ch, cart_total=cart_total,
        oauth_error=oauth_error, current_user=current_user)


@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    if username and not User.query.filter_by(username=username).first():
        u = User(username=username, email=email if email else None)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        login_user(u)
    return redirect('/')


@app.route('/login', methods=['POST'])
def login():
    u = User.query.filter_by(username=request.form['username']).first()
    if u and u.check_password(request.form['password']):
        login_user(u)
    return redirect('/')


@app.route('/logout')
def logout():
    logout_user()
    return redirect('/')


# ══════════════════════════════════════════════════════════════════════════════
#  GOOGLE  OAUTH  2.0
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/auth/google')
def auth_google():
    """Redirect the browser to Google's consent screen."""
    import urllib.parse
    if not GOOGLE_CLIENT_ID:
        return redirect('/?oauth_error=Google+OAuth+is+not+configured')
    params = {
        'client_id':     GOOGLE_CLIENT_ID,
        'redirect_uri':  url_for('auth_google_callback', _external=True),
        'response_type': 'code',
        'scope':         'openid email profile',
        'access_type':   'online',
        'prompt':        'select_account',
    }
    auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)
    return redirect(auth_url)


@app.route('/auth/google/callback')
def auth_google_callback():
    """Exchange code for token, fetch profile, log in or register the user."""
    import urllib.parse
    code = request.args.get('code')
    error = request.args.get('error')
    if error or not code:
        return redirect('/?oauth_error=' + urllib.parse.quote(error or 'Google+login+cancelled'))

    # ── 1. Exchange code for access token ───────────────────────────────────
    token_resp = requests.post('https://oauth2.googleapis.com/token', data={
        'code':          code,
        'client_id':     GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri':  url_for('auth_google_callback', _external=True),
        'grant_type':    'authorization_code',
    })
    if not token_resp.ok:
        print(f"[Google OAuth] Token exchange failed: {token_resp.status_code} {token_resp.text}")
        return redirect('/?oauth_error=Google+token+exchange+failed')
    access_token = token_resp.json().get('access_token')

    # ── 2. Fetch the user's Google profile ──────────────────────────────────
    profile_resp = requests.get(
        'https://www.googleapis.com/oauth2/v2/userinfo',
        headers={'Authorization': f'Bearer {access_token}'}
    )
    if not profile_resp.ok:
        print(f"[Google OAuth] Profile fetch failed: {profile_resp.status_code} {profile_resp.text}")
        return redirect('/?oauth_error=Could+not+fetch+Google+profile')
    profile = profile_resp.json()

    google_id  = str(profile.get('id', ''))
    email      = profile.get('email', '')
    name       = profile.get('name', '') or profile.get('given_name', '') or email.split('@')[0]
    avatar_url = profile.get('picture', '')

    # ── 3. Find or create the user ──────────────────────────────────────────
    user = User.query.filter_by(oauth_provider='google', oauth_id=google_id).first()

    if not user and email:
        # Maybe they already registered with the same email → link accounts
        user = User.query.filter_by(email=email).first()
        if user:
            user.oauth_provider = 'google'
            user.oauth_id = google_id
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            db.session.commit()

    if not user:
        # Brand new user — auto-create account
        base_username = name.replace(' ', '').lower()[:30] or 'user'
        username = base_username
        suffix = 1
        while User.query.filter_by(username=username).first():
            username = f'{base_username}{suffix}'
            suffix += 1

        user = User(
            username=username,
            email=email or None,
            oauth_provider='google',
            oauth_id=google_id,
            avatar_url=avatar_url or None,
        )
        db.session.add(user)
        db.session.commit()

    login_user(user)
    return redirect('/')


# ══════════════════════════════════════════════════════════════════════════════
#  FACEBOOK  OAUTH  2.0
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/add-ajax/<int:id>', methods=['POST'])
def add_ajax(id):
    import uuid as _uuid
    p = db.session.get(Product, id)
    if not p:
        return jsonify({'success': False, 'message': 'Product not found'})
    if current_user.is_authenticated:
        existing = Cart.query.filter_by(user_id=current_user.id, product_id=id).first()
        if existing:
            existing.quantity = (existing.quantity or 1) + 1
        else:
            db.session.add(Cart(user_id=current_user.id, product_id=id, quantity=1))
        db.session.commit()
        ch, total, count = build_cart_html(current_user.id)
    else:
        guest_cart = flask_session.get('guest_cart', [])
        found = next((e for e in guest_cart if e['product_id'] == id), None)
        if found:
            found['quantity'] = found.get('quantity', 1) + 1
        else:
            guest_cart.append({'cart_key': str(_uuid.uuid4()), 'product_id': id, 'quantity': 1})
        flask_session['guest_cart'] = guest_cart
        flask_session.modified = True
        ch, total, count = build_cart_html()
    return jsonify({
        'success': True,
        'product_name': p.name,
        'cart_html': ch,
        'total': total,
        'count': count
    })


@app.route('/add/<int:id>')
def add(id):
    import uuid as _uuid
    if current_user.is_authenticated:
        existing = Cart.query.filter_by(user_id=current_user.id, product_id=id).first()
        if existing:
            existing.quantity = (existing.quantity or 1) + 1
        else:
            db.session.add(Cart(user_id=current_user.id, product_id=id, quantity=1))
        db.session.commit()
    else:
        guest_cart = flask_session.get('guest_cart', [])
        found = next((e for e in guest_cart if e['product_id'] == id), None)
        if found:
            found['quantity'] = found.get('quantity', 1) + 1
        else:
            guest_cart.append({'cart_key': str(_uuid.uuid4()), 'product_id': id, 'quantity': 1})
        flask_session['guest_cart'] = guest_cart
        flask_session.modified = True
    return redirect('/?added=1')


@app.route('/remove-cart/<cart_id>', methods=['POST'])
def remove_cart(cart_id):
    if current_user.is_authenticated:
        try:
            cid = int(cart_id)
        except ValueError:
            return jsonify({'cart_html': '', 'total': 0, 'count': 0})
        item = Cart.query.filter_by(id=cid, user_id=current_user.id).first()
        if item:
            db.session.delete(item)
            db.session.commit()
        ch, total, count = build_cart_html(current_user.id)
    else:
        guest_cart = flask_session.get('guest_cart', [])
        guest_cart = [e for e in guest_cart if e.get('cart_key') != cart_id]
        flask_session['guest_cart'] = guest_cart
        flask_session.modified = True
        ch, total, count = build_cart_html()
    return jsonify({'cart_html': ch, 'total': total, 'count': count})


@app.route('/update-cart-qty/<cart_id>', methods=['POST'])
def update_cart_qty(cart_id):
    """Increment or decrement quantity. Removes item if qty reaches 0."""
    data = request.get_json() or {}
    delta = int(data.get('delta', 0))  # +1 or -1
    if current_user.is_authenticated:
        try:
            cid = int(cart_id)
        except ValueError:
            return jsonify({'cart_html': '', 'total': 0, 'count': 0})
        item = Cart.query.filter_by(id=cid, user_id=current_user.id).first()
        if item:
            new_qty = (item.quantity or 1) + delta
            if new_qty <= 0:
                db.session.delete(item)
            else:
                item.quantity = new_qty
            db.session.commit()
        ch, total, count = build_cart_html(current_user.id)
    else:
        guest_cart = flask_session.get('guest_cart', [])
        for entry in guest_cart:
            if entry.get('cart_key') == cart_id:
                entry['quantity'] = entry.get('quantity', 1) + delta
                break
        guest_cart = [e for e in guest_cart if e.get('quantity', 1) > 0]
        flask_session['guest_cart'] = guest_cart
        flask_session.modified = True
        ch, total, count = build_cart_html()
    return jsonify({'cart_html': ch, 'total': total, 'count': count})


# ================= CHAT ROUTE =================
STORE_CONTEXT = (
    "You are Myra, the friendly AI shopping assistant for MyStore — India's fastest-growing e-commerce platform. "
    "Your personality: warm, helpful, knowledgeable, concise. Always reply in 1-3 short sentences with 1-2 relevant emojis. Never write long paragraphs. "
    "\n\nPRODUCTS & PRICES (in Indian Rupees):\n"
    "Electronics: Samsung Galaxy S24 ₹79,999 | iPhone 15 ₹89,999 | Sony WH-1000XM5 headphones ₹29,999 | Dell Inspiron Laptop ₹55,999 | iPad Air ₹59,999 | OnePlus Buds Pro 2 ₹9,999 | LG 4K TV ₹49,999 | PS5 ₹54,990 | boAt Rockerz 450 ₹1,499 | JBL Flip 6 ₹11,999\n"
    "Fashion: H&M Oversized Tee ₹999 | Nike Dri-FIT ₹1,799 | Adidas Track Jacket ₹4,499 | Zara Faux Leather Jacket ₹6,990 | Levis 511 Jeans ₹3,499 | Nike Air Force 1 ₹7,995 | Puma Running Shoes ₹4,299 | Fossil Chronograph Watch ₹22,999\n"
    "Accessories: Ray-Ban Aviators ₹8,990 | Wildcraft Backpack ₹2,499 | Titan Edge Watch ₹5,995 | Hidesign Leather Wallet ₹1,799\n"
    "\nSTORE POLICIES:\n"
    "- Shipping: FREE on orders above ₹999, else ₹99 flat. Standard 3-5 days, Express 1-2 days (₹149 extra).\n"
    "- Returns: Hassle-free 7-day return policy. Damaged items replaced free within 48 hours.\n"
    "- Payment: UPI (GPay/PhonePe/Paytm), Credit/Debit Cards, Net Banking, Cash on Delivery (COD available in 400+ cities).\n"
    "- Discount: Use code FIRST10 for 10% off first order. Newsletter subscribers get code LOOP10.\n"
    "- Flash Sales: Daily deals up to 50% off — visible on the homepage with countdown timer.\n"
    "- Support: support@mystore.in | +91 80 4567 8900 | 24x7\n"
    "\nIMPORTANT: If asked about anything unrelated to shopping, products, or MyStore, politely say you can only help with shopping-related questions. "
    "Never make up prices or products not listed above. If unsure, direct them to browse the store or contact support."
)

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data     = request.get_json()
        question = (data.get("question") or "").strip()
        history  = data.get("history") or []   # list of {role, content} dicts

        if not question:
            return jsonify({"reply": "Please ask me something! 😊"})

        # Build message list: history + new user message
        messages = []
        for msg in history[-10:]:   # keep last 10 turns to stay within token limits
            role = msg.get("role")
            text = (msg.get("content") or "").strip()
            if role in ("user", "assistant") and text:
                messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": question})

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://mystore.in",
                "X-Title": "MyStore AI Assistant",
            },
            json={
                "model": "openai/gpt-4o-mini",
                "max_tokens": 350,
                "messages": [{"role": "system", "content": STORE_CONTEXT}] + messages,
            },
            timeout=15
        )
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        print("Chat error:", e)
        return jsonify({"reply": "Sorry, I am having trouble right now. Please try again! 🙏"})



# ================= PAYPAL PAYMENT ROUTES =================

def get_paypal_access_token():
    """Get PayPal OAuth2 access token."""
    resp = requests.post(
        f"{PAYPAL_BASE_URL}/v1/oauth2/token",
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        data={"grant_type": "client_credentials"}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@app.route("/paypal/create-order", methods=["POST"])
def paypal_create_order():
    """Create a PayPal order and return the PayPal order ID."""
    try:
        if current_user.is_authenticated:
            cart_items = Cart.query.filter_by(user_id=current_user.id).all()
        else:
            class _GI:
                def __init__(self, pid): self.product_id = pid
            cart_items = [_GI(e['product_id']) for e in flask_session.get('guest_cart', [])]
        if not cart_items:
            return jsonify({"error": "Cart is empty"}), 400

        subtotal = sum(
            db.session.get(Product, i.product_id).price
            for i in cart_items if db.session.get(Product, i.product_id)
        )
        data = request.get_json() or {}
        coupon_discount = int(data.get("coupon_discount", 0))
        delivery = 0 if subtotal >= 999 else 99
        total = subtotal + delivery - coupon_discount
        # Convert INR paise to rupees, format as string with 2 decimals
        total_str = "{:.2f}".format(total)

        access_token = get_paypal_access_token()
        resp = requests.post(
            f"{PAYPAL_BASE_URL}/v2/checkout/orders",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            },
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {
                        "currency_code": "USD",   # PayPal Sandbox works best with USD
                        "value": total_str
                    },
                    "description": f"MyStore Order - {len(cart_items)} item(s)"
                }],
                "application_context": {
                    "brand_name": "MyStore",
                    "user_action": "PAY_NOW"
                }
            }
        )
        resp.raise_for_status()
        paypal_order = resp.json()
        return jsonify({"id": paypal_order["id"]})
    except Exception as e:
        print("PayPal create-order error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/paypal/capture-order", methods=["POST"])
def paypal_capture_order():
    """Capture payment and create the store order."""
    try:
        data            = request.get_json()
        paypal_order_id = data.get("paypal_order_id")
        fname           = data.get("fname", "")
        lname           = data.get("lname", "")
        phone           = data.get("phone", "")
        address         = data.get("address", "")
        city            = data.get("city", "")
        pin             = data.get("pin", "")
        state           = data.get("state", "")
        coupon_discount = int(data.get("coupon_discount", 0))

        # Capture from PayPal
        access_token = get_paypal_access_token()
        resp = requests.post(
            f"{PAYPAL_BASE_URL}/v2/checkout/orders/{paypal_order_id}/capture",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            }
        )
        resp.raise_for_status()
        capture_data = resp.json()

        if capture_data.get("status") != "COMPLETED":
            return jsonify({"error": "Payment not completed"}), 400

        # Create store order
        if current_user.is_authenticated:
            uid = current_user.id
            cart_items = Cart.query.filter_by(user_id=uid).all()
        else:
            uid = 0
            class _GI:
                def __init__(self, pid): self.product_id = pid
            cart_items = [_GI(e['product_id']) for e in flask_session.get('guest_cart', [])]
        subtotal = sum(
            db.session.get(Product, i.product_id).price
            for i in cart_items if db.session.get(Product, i.product_id)
        )
        delivery = 0 if subtotal >= 999 else 99
        total    = subtotal + delivery - coupon_discount
        full_address = f"{fname} {lname}, {address}, {city} - {pin}, {state} | 📞 {phone}"

        order = Order(
            user_id=uid, total=total,
            status="Paid via PayPal",
            address=full_address, payment="PayPal"
        )
        db.session.add(order)
        db.session.flush()
        for ci in cart_items:
            p = db.session.get(Product, ci.product_id)
            if p:
                db.session.add(OrderItem(
                    order_id=order.id, product_id=p.id,
                    product_name=p.name, product_emoji=p.emoji, price=p.price
                ))
        if current_user.is_authenticated:
            Cart.query.filter_by(user_id=uid).delete()
        else:
            flask_session.pop('guest_cart', None)
        db.session.commit()
        flask_session['last_order_id'] = order.id
        return jsonify({"success": True, "order_id": order.id})
    except Exception as e:
        print("PayPal capture error:", e)
        return jsonify({"error": str(e)}), 500



# ── PINCODE PROXY (server-side, avoids browser CORS issues) ───
@app.route('/api/pincode/<pin>')
def api_pincode(pin):
    """Robust pincode lookup: tries multiple sources."""
    if not pin.isdigit() or len(pin) != 6:
        return jsonify({'ok': False, 'error': 'Invalid PIN'})

    # ── Source 1: api.postalpincode.in ──────────────────────────
    try:
        resp = requests.get(
            f'https://api.postalpincode.in/pincode/{pin}',
            timeout=5, headers={'User-Agent': 'Mozilla/5.0'}
        )
        resp.raise_for_status()
        data = resp.json()
        if data and data[0].get('Status') == 'Success':
            posts = data[0].get('PostOffice') or []
            if posts:
                seen = set()
                areas = []
                for p in posts:
                    name = p.get('Name', '').strip()
                    if name and name not in seen:
                        seen.add(name)
                        areas.append({'name': name, 'type': p.get('BranchType', '')})
                return jsonify({
                    'ok': True,
                    'district': posts[0].get('District', ''),
                    'state':    posts[0].get('State', ''),
                    'areas':    areas
                })
    except Exception:
        pass

    # ── Source 2: api.zippopotam.us (returns place names) ───────
    try:
        resp2 = requests.get(
            f'https://api.zippopotam.us/in/{pin}',
            timeout=5, headers={'User-Agent': 'Mozilla/5.0'}
        )
        if resp2.status_code == 200:
            d2 = resp2.json()
            places = d2.get('places', [])
            if places:
                district = places[0].get('place name', '')
                state    = places[0].get('state', '')
                areas    = [{'name': p.get('place name', ''), 'type': ''} for p in places if p.get('place name')]
                return jsonify({'ok': True, 'district': district, 'state': state, 'areas': areas})
    except Exception:
        pass

    return jsonify({'ok': False, 'error': 'PIN not found in any source'})

@app.route('/saved-address/add', methods=['POST'])
@login_required
def saved_address_add():
    data = request.get_json() or {}
    # Limit to 5 saved addresses per user
    count = SavedAddress.query.filter_by(user_id=current_user.id).count()
    if count >= 5:
        return jsonify({'ok': False, 'error': 'Max 5 saved addresses'})
    is_default = (count == 0)   # first address is default
    addr = SavedAddress(
        user_id    = current_user.id,
        label      = data.get('label', 'Home')[:50],
        fname      = data.get('fname', '')[:100],
        lname      = data.get('lname', '')[:100],
        phone      = data.get('phone', '')[:20],
        address    = data.get('address', '')[:300],
        city       = data.get('city', '')[:100],
        pin        = data.get('pin', '')[:10],
        state      = data.get('state', '')[:100],
        is_default = is_default,
    )
    db.session.add(addr)
    db.session.commit()
    return jsonify({'ok': True, 'id': addr.id})


@app.route('/saved-address/<int:addr_id>/delete', methods=['POST'])
@login_required
def saved_address_delete(addr_id):
    addr = SavedAddress.query.filter_by(id=addr_id, user_id=current_user.id).first()
    if not addr:
        return jsonify({'ok': False})
    was_default = addr.is_default
    db.session.delete(addr)
    db.session.commit()
    # If deleted address was default, make the first remaining one default
    if was_default:
        first = SavedAddress.query.filter_by(user_id=current_user.id).order_by(SavedAddress.created_at).first()
        if first:
            first.is_default = True
            db.session.commit()
    return jsonify({'ok': True})


# ================= RAZORPAY PAYMENT ROUTES =================
import hmac
import hashlib
import json as _json

@app.route('/razorpay/create-order', methods=['POST'])
def razorpay_create_order():
    """Create a Razorpay order and return credentials for the frontend checkout."""
    try:
        import razorpay as rzp_sdk
    except ImportError:
        rzp_sdk = None

    try:
        data = request.get_json() or {}
        if current_user.is_authenticated:
            uid = current_user.id
            cart_items = Cart.query.filter_by(user_id=uid).all()
            user_email = current_user.email or ''
        else:
            uid = 0
            class _GI:
                def __init__(self, pid): self.product_id = pid
            cart_items = [_GI(e['product_id']) for e in flask_session.get('guest_cart', [])]
            user_email = ''
        if not cart_items:
            return jsonify({'error': 'Cart is empty'}), 400

        subtotal = sum(
            db.session.get(Product, i.product_id).price
            for i in cart_items if db.session.get(Product, i.product_id)
        )
        coupon_discount = int(data.get('coupon_discount', 0))
        delivery = 0 if subtotal >= 999 else 99
        total = subtotal + delivery - coupon_discount
        amount_paise = total * 100

        receipt = f"order_{uid}_{int(__import__('time').time())}"
        order_payload = {
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': receipt,
            'notes': {'store': 'MyStore', 'user_id': str(uid)}
        }

        resp = requests.post(
            'https://api.razorpay.com/v1/orders',
            auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
            json=order_payload
        )
        resp.raise_for_status()
        rz_order = resp.json()

        return jsonify({
            'key_id': RAZORPAY_KEY_ID,
            'razorpay_order_id': rz_order['id'],
            'amount': amount_paise,
            'amount_display': '{:,}'.format(total),
            'email': user_email
        })
    except Exception as e:
        print('Razorpay create-order error:', e)
        return jsonify({'error': str(e)}), 500


@app.route('/razorpay/verify-payment', methods=['POST'])
def razorpay_verify_payment():
    """Verify Razorpay payment signature and create the store order."""
    try:
        data = request.get_json() or {}
        rz_order_id   = data.get('razorpay_order_id', '')
        rz_payment_id = data.get('razorpay_payment_id', '')
        rz_signature  = data.get('razorpay_signature', '')

        # Verify HMAC-SHA256 signature
        expected = hmac.new(
            RAZORPAY_KEY_SECRET.encode(),
            f"{rz_order_id}|{rz_payment_id}".encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, rz_signature):
            return jsonify({'success': False, 'error': 'Signature mismatch'}), 400

        # Build the store order
        fname    = data.get('fname', '')
        lname    = data.get('lname', '')
        phone    = data.get('phone', '')
        address  = data.get('address', '')
        city     = data.get('city', '')
        pin      = data.get('pin', '')
        state    = data.get('state', '')
        pay_lbl  = data.get('payment_label', 'Razorpay')
        coupon_discount = int(data.get('coupon_discount', 0))
        full_address = f"{fname} {lname}, {address}, {city} - {pin}, {state} | 📞 {phone}"

        if current_user.is_authenticated:
            uid = current_user.id
            cart_items = Cart.query.filter_by(user_id=uid).all()
        else:
            uid = 0
            class _GI:
                def __init__(self, pid): self.product_id = pid
            cart_items = [_GI(e['product_id']) for e in flask_session.get('guest_cart', [])]

        subtotal = sum(
            db.session.get(Product, i.product_id).price
            for i in cart_items if db.session.get(Product, i.product_id)
        )
        delivery = 0 if subtotal >= 999 else 99
        total = subtotal + delivery - coupon_discount

        order = Order(
            user_id=uid, total=total, status='Confirmed',
            address=full_address,
            payment=f"{pay_lbl} (Paid · {rz_payment_id})"
        )
        db.session.add(order)
        db.session.flush()

        for ci in cart_items:
            p = db.session.get(Product, ci.product_id)
            if p:
                db.session.add(OrderItem(
                    order_id=order.id, product_id=p.id,
                    product_name=p.name, product_emoji=p.emoji, price=p.price
                ))
        if current_user.is_authenticated:
            Cart.query.filter_by(user_id=uid).delete()
        else:
            flask_session.pop('guest_cart', None)
        db.session.commit()
        flask_session['last_order_id'] = order.id

        return jsonify({'success': True, 'order_id': order.id})
    except Exception as e:
        print('Razorpay verify error:', e)
        return jsonify({'success': False, 'error': str(e)}), 500




# Description cache (in-memory, keyed by product id)
_desc_cache = {}

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    p = db.session.get(Product, product_id)
    if not p:
        return redirect('/')
    rating_int = int(p.rating)
    stars = "★" * rating_int + "☆" * (5 - rating_int)
    discount_pct = 0
    if p.orig_price and p.orig_price > p.price:
        discount_pct = round((1 - p.price / p.orig_price) * 100)
    # Related products: same subcategory, exclude self
    related = Product.query.filter(
        Product.subcategory == p.subcategory,
        Product.id != p.id
    ).limit(8).all()
    if len(related) < 4:
        related = Product.query.filter(
            Product.category == p.category,
            Product.id != p.id
        ).limit(8).all()
    cc = 0
    cart_total = 0
    ch = ''
    if current_user.is_authenticated:
        ch, cart_total, cc = build_cart_html(current_user.id)
    else:
        ch, cart_total, cc = build_cart_html()
    return render_template_string(
        PRODUCT_PAGE, p=p, stars=stars, discount_pct=discount_pct, related=related,
        cc=cc, ch=ch, cart_total=cart_total, current_user=current_user
    )


@app.route('/product/<int:product_id>/description')
def product_description(product_id):
    """Return AI-generated full description + specs as JSON (cached in memory)."""
    if product_id in _desc_cache:
        return jsonify({'description': _desc_cache[product_id]})

    p = db.session.get(Product, product_id)
    if not p:
        return jsonify({'description': 'Product not found.'}), 404

    discount_pct = 0
    if p.orig_price and p.orig_price > p.price:
        discount_pct = round((1 - p.price / p.orig_price) * 100)

    prompt = f"""You are a product copywriter for an Indian e-commerce store. Write a detailed, engaging product description page for the following product. Use markdown formatting (##, ###, **, bullet lists, and a spec table with | Col1 | Col2 | format). Be specific, realistic and accurate about specs based on the product name.

Product: {p.name}
Category: {p.category} > {p.subcategory or p.category}
Short description: {p.description}
Price: ₹{p.price:,} (was ₹{p.orig_price:,}, saving {discount_pct}%)
Rating: {p.rating}/5 · {p.sold} units sold

Write the following sections IN ORDER:
1. ## Overview — 2–3 engaging paragraphs about what makes this product great, who it's for, and why it stands out.
2. ## Key Features — A bullet list of 6–8 specific, realistic features with brief explanations.
3. ## Technical Specifications — A markdown table with at least 10 realistic spec rows (e.g. dimensions, weight, materials, battery, connectivity, etc. as relevant to this product type).
4. ## What's in the Box — A bullet list of everything included.
5. ## Why Buy from MyStore — 2–3 sentences about authenticity, warranty, and fast delivery.

Be thorough. Each section should be meaty and informative. Total response should be around 600–900 words."""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1200,
            },
            timeout=30
        )
        result = resp.json()
        description = result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("AI description error:", e)
        description = f"""## {p.name}

{p.description}

## Key Features
* Category: {p.category}
* Rating: {p.rating}/5
* Sold: {p.sold} units
* Price: ₹{p.price:,}

## Technical Specifications
| Specification | Details |
| Product Name | {p.name} |
| Category | {p.category} |
| Subcategory | {p.subcategory or 'N/A'} |
| Price | ₹{p.price:,} |
| Rating | {p.rating}/5 |
| Units Sold | {p.sold} |

## What's in the Box
* {p.name}
* User Manual
* Warranty Card

## Why Buy from MyStore
MyStore guarantees 100% authentic products with fast 2–4 day delivery across India. Easy 7-day returns and 24/7 customer support."""

    _desc_cache[product_id] = description
    return jsonify({'description': description})


@app.route('/cart')
def cart_page():
    """Full-page cart view."""
    if current_user.is_authenticated:
        db_items = Cart.query.filter_by(user_id=current_user.id).all()
        items = []
        for i in db_items:
            p = db.session.get(Product, i.product_id)
            if p:
                qty = i.quantity or 1
                items.append({
                    'cart_key': str(i.id),
                    'name': p.name,
                    'emoji': p.emoji,
                    'category': p.category,
                    'price': p.price,
                    'quantity': qty,
                    'image_url': getattr(p, 'image_url', '') or '',
                })
    else:
        guest_cart = flask_session.get('guest_cart', [])
        items = []
        for entry in guest_cart:
            p = db.session.get(Product, entry['product_id'])
            if p:
                qty = entry.get('quantity', 1)
                items.append({
                    'cart_key': entry['cart_key'],
                    'name': p.name,
                    'emoji': p.emoji,
                    'category': p.category,
                    'price': p.price,
                    'quantity': qty,
                    'image_url': getattr(p, 'image_url', '') or '',
                })

    subtotal = sum(i['price'] * i['quantity'] for i in items)
    delivery = 0 if subtotal >= 999 else (99 if items else 0)
    total = subtotal + delivery
    return render_template_string(CART_PAGE, items=items, subtotal=subtotal, delivery=delivery, total=total)


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    # Resolve cart items from DB (logged-in) or session (guest)
    if current_user.is_authenticated:
        cart_items = Cart.query.filter_by(user_id=current_user.id).all()
        uid = current_user.id
    else:
        guest_cart = flask_session.get('guest_cart', [])
        # Build lightweight cart_item-like objects for guests
        class _GuestItem:
            def __init__(self, product_id, quantity=1):
                self.product_id = product_id
                self.quantity = quantity
        cart_items = [_GuestItem(e['product_id'], e.get('quantity', 1)) for e in guest_cart]
        uid = 0  # guest user_id

    if not cart_items:
        return redirect('/')

    if request.method == 'POST':
        fname   = request.form.get('fname', '')
        lname   = request.form.get('lname', '')
        phone   = request.form.get('phone', '')
        address = request.form.get('address', '')
        city    = request.form.get('city', '')
        pin     = request.form.get('pin', '')
        state   = request.form.get('state', '')
        payment = request.form.get('payment', 'UPI')
        full_address = f"{fname} {lname}, {address}, {city} - {pin}, {state} | 📞 {phone}"
        subtotal = sum(db.session.get(Product, i.product_id).price * (i.quantity or 1)
                       for i in cart_items if db.session.get(Product, i.product_id))
        delivery = 0 if subtotal >= 999 else 99
        total    = subtotal + delivery
        order = Order(user_id=uid, total=total, status='Processing',
                      address=full_address, payment=payment)
        db.session.add(order)
        db.session.flush()
        for ci in cart_items:
            p = db.session.get(Product, ci.product_id)
            if p:
                qty = getattr(ci, 'quantity', None) or 1
                for _ in range(qty):
                    db.session.add(OrderItem(order_id=order.id, product_id=p.id,
                        product_name=p.name, product_emoji=p.emoji, price=p.price))
        if current_user.is_authenticated:
            Cart.query.filter_by(user_id=uid).delete()
        else:
            flask_session.pop('guest_cart', None)
        db.session.commit()
        # Store order id in session so guest can view success page
        flask_session['last_order_id'] = order.id
        return redirect(f'/order-success/{order.id}')

    products = []
    subtotal = 0
    for ci in cart_items:
        p = db.session.get(Product, ci.product_id)
        if p:
            qty = getattr(ci, 'quantity', None) or 1
            products.append({'name': p.name, 'emoji': p.emoji, 'category': p.category, 'price': p.price, 'quantity': qty})
            subtotal += p.price * qty
    delivery = 0 if subtotal >= 999 else 99
    total    = subtotal + delivery
    saved_addresses = SavedAddress.query.filter_by(user_id=uid).order_by(SavedAddress.is_default.desc(), SavedAddress.created_at.desc()).all() if current_user.is_authenticated else []
    return render_template_string(CHECKOUT_PAGE, items=products, subtotal=subtotal, total=total, discount=0, paypal_client_id=PAYPAL_CLIENT_ID, razorpay_key_id=RAZORPAY_KEY_ID, saved_addresses=saved_addresses, is_guest=not current_user.is_authenticated)


@app.route('/order-success/<int:order_id>')
def order_success(order_id):
    if current_user.is_authenticated:
        order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    else:
        # Allow guest to see the order they just placed (stored in session)
        if flask_session.get('last_order_id') != order_id:
            return redirect('/')
        order = Order.query.get_or_404(order_id)
    return render_template_string(SUCCESS_PAGE, order=order)


@app.route('/orders')
@login_required
def orders():
    user_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template_string(ORDERS_PAGE, orders=user_orders)



# ── UPDATE PROFILE (username + email) ─────────────────────────
@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    data = request.get_json()
    new_username = (data.get('username') or '').strip()
    new_email    = (data.get('email')    or '').strip()
    current_pw   =  data.get('current_password', '')

    if not current_user.check_password(current_pw):
        return jsonify({'success': False, 'message': 'Current password is incorrect.'})

    if not new_username:
        return jsonify({'success': False, 'message': 'Username cannot be empty.'})

    # check username taken by another user
    existing = User.query.filter_by(username=new_username).first()
    if existing and existing.id != current_user.id:
        return jsonify({'success': False, 'message': 'Username already taken. Choose another.'})

    # check email taken
    if new_email:
        ex_email = User.query.filter_by(email=new_email).first()
        if ex_email and ex_email.id != current_user.id:
            return jsonify({'success': False, 'message': 'Email already in use by another account.'})

    current_user.username = new_username
    current_user.email    = new_email if new_email else current_user.email
    db.session.commit()
    return jsonify({'success': True, 'message': 'Profile updated successfully!'})


# ── UPDATE PASSWORD ───────────────────────────────────────────
@app.route('/update-password', methods=['POST'])
@login_required
def update_password():
    data    = request.get_json()
    cur_pw  = data.get('current_password', '')
    new_pw  = data.get('new_password', '')

    if not current_user.check_password(cur_pw):
        return jsonify({'success': False, 'message': 'Current password is incorrect.'})

    if len(new_pw) < 6:
        return jsonify({'success': False, 'message': 'New password must be at least 6 characters.'})

    if cur_pw == new_pw:
        return jsonify({'success': False, 'message': 'New password must be different from current.'})

    current_user.set_password(new_pw)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Password changed successfully!'})



# ================= EMAIL HELPER =================
def send_welcome_email(recipient_email):
    """Send a beautifully formatted welcome/deals email to a new subscriber."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'🎉 Welcome to {STORE_NAME} – Exclusive Deals Inside!'
    msg['From']    = f'{STORE_NAME} <{MAIL_SENDER}>'
    msg['To']      = recipient_email

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to {STORE_NAME}</title>
</head>
<body style="margin:0;padding:0;background:#0d0d0d;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d0d;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#1a1a2e;border-radius:16px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.4);">

          <!-- Header Banner -->
          <tr>
            <td style="background:linear-gradient(135deg,#0f3460,#16213e);padding:40px 40px 30px;text-align:center;">
              <h1 style="margin:0;color:#00d4aa;font-size:32px;font-weight:800;letter-spacing:-1px;">
                🛍️ {STORE_NAME}
              </h1>
              <p style="margin:8px 0 0;color:#a0a0c0;font-size:14px;letter-spacing:2px;text-transform:uppercase;">
                Your Premium Shopping Destination
              </p>
            </td>
          </tr>

          <!-- Welcome Message -->
          <tr>
            <td style="padding:36px 40px 20px;text-align:center;">
              <h2 style="margin:0 0 12px;color:#ffffff;font-size:26px;font-weight:700;">
                You're In the Loop! 🎊
              </h2>
              <p style="margin:0;color:#9090b0;font-size:15px;line-height:1.7;">
                Thank you for subscribing to <strong style="color:#00d4aa;">{STORE_NAME}</strong>.<br>
                Get ready for exclusive deals, flash sales, and new arrivals delivered straight to your inbox.
              </p>
            </td>
          </tr>

          <!-- Promo Code Box -->
          <tr>
            <td style="padding:10px 40px 30px;text-align:center;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background:linear-gradient(135deg,#00d4aa22,#0f346022);border:2px dashed #00d4aa;border-radius:12px;padding:24px;text-align:center;">
                    <p style="margin:0 0 6px;color:#9090b0;font-size:12px;text-transform:uppercase;letter-spacing:2px;">
                      Welcome Gift – Use Code
                    </p>
                    <p style="margin:0;color:#00d4aa;font-size:30px;font-weight:900;letter-spacing:6px;">
                      LOOP10
                    </p>
                    <p style="margin:6px 0 0;color:#ffffff;font-size:13px;">
                      Get <strong>10% OFF</strong> your first order 🎁
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Deals Section -->
          <tr>
            <td style="padding:0 40px 10px;">
              <h3 style="color:#ffffff;font-size:18px;margin:0 0 16px;border-left:4px solid #00d4aa;padding-left:12px;">
                🔥 Today's Hot Deals
              </h3>
            </td>
          </tr>

          <!-- Deal Cards -->
          <tr>
            <td style="padding:0 40px 30px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <!-- Row 1 -->
                <tr>
                  <td width="48%" style="background:#16213e;border-radius:10px;padding:20px;vertical-align:top;">
                    <div style="font-size:28px;margin-bottom:8px;">📱</div>
                    <p style="margin:0 0 4px;color:#ffffff;font-size:14px;font-weight:700;">Electronics</p>
                    <p style="margin:0 0 10px;color:#9090b0;font-size:12px;">Phones, Laptops & More</p>
                    <p style="margin:0;color:#00d4aa;font-weight:700;font-size:16px;">Up to 20% OFF</p>
                  </td>
                  <td width="4%"></td>
                  <td width="48%" style="background:#16213e;border-radius:10px;padding:20px;vertical-align:top;">
                    <div style="font-size:28px;margin-bottom:8px;">👕</div>
                    <p style="margin:0 0 4px;color:#ffffff;font-size:14px;font-weight:700;">Fashion</p>
                    <p style="margin:0 0 10px;color:#9090b0;font-size:12px;">Top Brands on Sale</p>
                    <p style="margin:0;color:#00d4aa;font-weight:700;font-size:16px;">Up to 40% OFF</p>
                  </td>
                </tr>
                <tr><td colspan="3" style="height:12px;"></td></tr>
                <!-- Row 2 -->
                <tr>
                  <td width="48%" style="background:#16213e;border-radius:10px;padding:20px;vertical-align:top;">
                    <div style="font-size:28px;margin-bottom:8px;">🏠</div>
                    <p style="margin:0 0 4px;color:#ffffff;font-size:14px;font-weight:700;">Home & Kitchen</p>
                    <p style="margin:0 0 10px;color:#9090b0;font-size:12px;">Upgrade Your Space</p>
                    <p style="margin:0;color:#00d4aa;font-weight:700;font-size:16px;">Up to 30% OFF</p>
                  </td>
                  <td width="4%"></td>
                  <td width="48%" style="background:#16213e;border-radius:10px;padding:20px;vertical-align:top;">
                    <div style="font-size:28px;margin-bottom:8px;">⚡</div>
                    <p style="margin:0 0 4px;color:#ffffff;font-size:14px;font-weight:700;">Flash Sales</p>
                    <p style="margin:0 0 10px;color:#9090b0;font-size:12px;">Limited Time Only!</p>
                    <p style="margin:0;color:#ff6b6b;font-weight:700;font-size:16px;">Today Only!</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- CTA Button -->
          <tr>
            <td style="padding:0 40px 36px;text-align:center;">
              <a href="#" style="display:inline-block;background:linear-gradient(135deg,#00d4aa,#00a884);color:#0d0d0d;text-decoration:none;padding:16px 48px;border-radius:50px;font-size:16px;font-weight:800;letter-spacing:0.5px;">
                Shop Now &rarr;
              </a>
            </td>
          </tr>

          <!-- What to Expect -->
          <tr>
            <td style="background:#12122a;padding:28px 40px;">
              <p style="margin:0 0 14px;color:#9090b0;font-size:12px;text-transform:uppercase;letter-spacing:2px;">
                What you'll receive
              </p>
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="color:#c0c0d0;font-size:13px;padding:4px 0;">✅ &nbsp; Early access to flash sales</td>
                </tr>
                <tr>
                  <td style="color:#c0c0d0;font-size:13px;padding:4px 0;">✅ &nbsp; Weekly exclusive discount codes</td>
                </tr>
                <tr>
                  <td style="color:#c0c0d0;font-size:13px;padding:4px 0;">✅ &nbsp; New arrivals notifications</td>
                </tr>
                <tr>
                  <td style="color:#c0c0d0;font-size:13px;padding:4px 0;">✅ &nbsp; Members-only bundle offers</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 40px;text-align:center;border-top:1px solid #2a2a4a;">
              <p style="margin:0 0 6px;color:#606080;font-size:12px;">
                © 2026 {STORE_NAME}. All rights reserved.
              </p>
              <p style="margin:0;color:#404060;font-size:11px;">
                You received this email because you subscribed at {STORE_NAME}.<br>
                <a href="#" style="color:#00d4aa;text-decoration:none;">Unsubscribe</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    msg.attach(MIMEText(html_body, 'html'))

    # Validate credentials are set before attempting send
    if 'you@gmail.com' in MAIL_SENDER or 'abcd efgh' in MAIL_PASSWORD:
        print("[Email Error] Credentials not set! Edit MAIL_SENDER and MAIL_PASSWORD in app.py")
        return False

    print(f"[Email] Sending to {recipient_email} via {MAIL_SENDER}...")
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.set_debuglevel(1)          # prints SMTP handshake to terminal
            server.login(MAIL_SENDER, MAIL_PASSWORD)
            server.sendmail(MAIL_SENDER, recipient_email, msg.as_string())
        print(f"[Email] Sent successfully to {recipient_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("[Email Error] AUTH FAILED — wrong Gmail address or App Password.")
        print("  → Make sure you're using a Gmail App Password (not your Gmail login password).")
        print("  → Generate one at: myaccount.google.com → Security → App Passwords")
        return False
    except smtplib.SMTPException as e:
        print(f"[Email Error] SMTP error: {e}")
        return False
    except Exception as e:
        print(f"[Email Error] Unexpected error: {e}")
        return False


# ================= SUBSCRIBE ROUTE =================
@app.route('/subscribe', methods=['POST'])
def subscribe():
    data  = request.get_json(silent=True) or {}
    email = (data.get('email') or request.form.get('email') or '').strip().lower()

    if not email or '@' not in email:
        return jsonify({'success': False, 'message': 'Please enter a valid email address.'})

    # Check for duplicate
    if Subscriber.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'You are already subscribed! 🎉'})

    # Save subscriber
    db.session.add(Subscriber(email=email))
    db.session.commit()

    # Send welcome email
    sent = send_welcome_email(email)
    if sent:
        return jsonify({'success': True, 'message': "You're subscribed! Check your inbox for exclusive deals 🎁"})
    else:
        return jsonify({'success': True, 'message': "Subscribed! (Email delivery may be delayed – check credentials.)"})


# ================= INFO PAGES =================

def info_page_shell(title, subtitle, emoji, content_html):
    """Shared shell for all standalone info pages — matches site design."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} – MyStore</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>
:root{{--accent:#ff3b5c;--accent2:#ffb347;--accent3:#00d4aa;--surface:#111118;--surface2:#1a1a24;--surface3:#22222e;--white:#ffffff;--gray:#9898b0;--border:rgba(255,255,255,0.07);--radius:16px;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'DM Sans',sans-serif;background:#0a0a0f;color:#fff;min-height:100vh;}}
a{{text-decoration:none;color:inherit;}}
::-webkit-scrollbar{{width:5px;}}::-webkit-scrollbar-track{{background:var(--surface);}}::-webkit-scrollbar-thumb{{background:var(--accent);border-radius:3px;}}
.topbar{{background:rgba(10,10,15,0.95);backdrop-filter:blur(20px);padding:16px 48px;display:flex;align-items:center;gap:20px;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100;}}
.brand{{font-family:'Syne',sans-serif;font-size:24px;font-weight:800;}}
.brand-my{{color:#fff;}}.brand-store{{color:var(--accent);}}.brand-dot{{width:6px;height:6px;background:var(--accent3);border-radius:50%;margin-bottom:2px;display:inline-block;margin-left:2px;}}
.back-btn{{margin-left:auto;display:flex;align-items:center;gap:8px;background:var(--surface2);border:1.5px solid var(--border);color:var(--gray);padding:8px 18px;border-radius:50px;font-size:13px;font-weight:600;cursor:pointer;transition:all .2s;}}
.back-btn:hover{{border-color:var(--accent);color:var(--accent);}}
.page-hero{{background:linear-gradient(135deg,#0d0d1a,#1a0010,#0a1020);padding:64px 48px 48px;border-bottom:1px solid var(--border);position:relative;overflow:hidden;}}
.page-hero::before{{content:'';position:absolute;right:-100px;top:-100px;width:500px;height:500px;background:radial-gradient(circle,rgba(255,59,92,0.08),transparent 65%);border-radius:50%;}}
.page-hero-em{{font-size:56px;margin-bottom:20px;display:block;}}
.page-hero h1{{font-family:'Syne',sans-serif;font-size:42px;font-weight:800;margin-bottom:10px;}}
.page-hero p{{color:var(--gray);font-size:16px;max-width:560px;line-height:1.6;}}
.breadcrumb{{font-size:13px;color:var(--gray);margin-bottom:20px;display:flex;align-items:center;gap:6px;}}
.breadcrumb a{{color:var(--accent);}}
.content{{max-width:900px;margin:0 auto;padding:56px 48px;}}
.section{{margin-bottom:40px;}}
.section h2{{font-family:'Syne',sans-serif;font-size:22px;font-weight:700;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border);}}
.section p{{color:var(--gray);line-height:1.8;font-size:15px;margin-bottom:10px;}}
.section ul{{color:var(--gray);line-height:1.9;font-size:15px;padding-left:0;list-style:none;}}
.section ul li{{padding:4px 0 4px 20px;position:relative;}}
.section ul li::before{{content:'→';position:absolute;left:0;color:var(--accent);font-size:12px;top:5px;}}
.highlight-box{{background:linear-gradient(135deg,rgba(255,59,92,0.08),rgba(0,212,170,0.05));border:1px solid rgba(255,59,92,0.2);border-radius:var(--radius);padding:24px 28px;margin-bottom:32px;}}
.highlight-box p{{color:var(--white);font-size:16px;line-height:1.7;margin:0;}}
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:32px;}}
.stat-card{{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:24px;text-align:center;}}
.stat-num{{font-family:'Syne',sans-serif;font-size:28px;font-weight:800;color:var(--accent);margin-bottom:4px;}}
.stat-label{{font-size:13px;color:var(--gray);}}
.career-card{{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;transition:all .2s;}}
.career-card:hover{{border-color:rgba(255,59,92,0.4);transform:translateX(4px);}}
.job-title{{font-size:16px;font-weight:600;margin-bottom:4px;}}
.job-meta{{font-size:13px;color:var(--gray);}}
.career-badge{{background:rgba(0,212,170,0.15);color:var(--accent3);border:1px solid rgba(0,212,170,0.3);padding:4px 14px;border-radius:50px;font-size:12px;font-weight:700;white-space:nowrap;}}
.press-card{{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px;margin-bottom:12px;transition:all .2s;}}
.press-card:hover{{border-color:rgba(255,179,71,0.4);}}
.press-source{{font-size:12px;font-weight:700;color:var(--accent2);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;}}
.press-headline{{font-size:16px;font-weight:600;color:var(--white);margin-bottom:6px;line-height:1.4;}}
.press-date{{font-size:12px;color:var(--gray);}}
.contact-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:32px;}}
.contact-card{{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:22px;text-align:center;}}
.cc-icon{{font-size:28px;margin-bottom:10px;}}
.cc-label{{font-size:12px;color:var(--gray);margin-bottom:6px;text-transform:uppercase;letter-spacing:1px;}}
.cc-val{{font-size:14px;font-weight:600;color:var(--accent3);}}
.cc-val a{{color:var(--accent3);}}
.form-field{{width:100%;padding:12px 16px;background:var(--surface3);border:1.5px solid var(--border);border-radius:10px;color:var(--white);font-size:14px;font-family:'DM Sans',sans-serif;outline:none;margin-bottom:12px;transition:border-color .2s;}}
.form-field:focus{{border-color:var(--accent);}}
.form-field::placeholder{{color:var(--gray);}}
.submit-btn{{background:linear-gradient(135deg,var(--accent),#ff6b35);color:#fff;border:none;padding:13px 32px;border-radius:50px;font-size:15px;font-weight:700;cursor:pointer;font-family:'Syne',sans-serif;transition:all .2s;}}
.submit-btn:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(255,59,92,0.4);}}
.blog-card{{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px;margin-bottom:12px;display:flex;align-items:center;gap:18px;transition:all .2s;}}
.blog-card:hover{{border-color:rgba(0,212,170,0.3);transform:translateX(4px);}}
.blog-em{{font-size:34px;}}
.blog-title{{font-size:16px;font-weight:600;margin-bottom:4px;}}
.blog-meta{{font-size:12px;color:var(--gray);}}
.faq-item{{background:var(--surface2);border:1px solid var(--border);border-radius:10px;margin-bottom:10px;overflow:hidden;}}
.faq-q{{padding:16px 20px;font-weight:600;cursor:pointer;display:flex;justify-content:space-between;align-items:center;transition:background .2s;}}
.faq-q:hover{{background:var(--surface3);}}
.faq-chevron{{font-size:12px;transition:transform .3s;color:var(--gray);}}
.faq-a{{display:none;padding:0 20px 16px;color:var(--gray);line-height:1.7;font-size:14px;}}
.faq-item.open .faq-a{{display:block;}}
.faq-item.open .faq-chevron{{transform:rotate(180deg);}}
.track-box{{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:28px;margin-bottom:28px;}}
.track-input-row{{display:flex;gap:12px;margin-bottom:0;}}
.track-result{{margin-top:24px;}}
.track-step{{display:flex;align-items:flex-start;gap:14px;padding:12px 0;border-bottom:1px solid var(--border);}}
.track-step:last-child{{border-bottom:none;}}
.track-dot{{width:14px;height:14px;border-radius:50%;border:2px solid var(--border);margin-top:3px;flex-shrink:0;}}
.track-dot.done{{background:var(--accent3);border-color:var(--accent3);}}
.track-dot.active{{background:var(--accent);border-color:var(--accent);box-shadow:0 0 10px rgba(255,59,92,0.5);animation:pulse 1.5s infinite;}}
@keyframes pulse{{0%,100%{{box-shadow:0 0 10px rgba(255,59,92,0.5)}}50%{{box-shadow:0 0 20px rgba(255,59,92,0.8)}}}}
.ts-title{{font-size:14px;font-weight:600;}}
.ts-date{{font-size:12px;color:var(--gray);margin-top:2px;}}
.footer-simple{{text-align:center;padding:32px;color:var(--gray);font-size:13px;border-top:1px solid var(--border);margin-top:40px;}}
.footer-simple a{{color:var(--accent);}}
.values-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:24px;}}
.value-card{{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:20px;}}
.value-em{{font-size:26px;margin-bottom:10px;}}
.value-title{{font-size:14px;font-weight:700;margin-bottom:6px;}}
.value-desc{{font-size:13px;color:var(--gray);line-height:1.5;}}
@media(max-width:768px){{.content{{padding:32px 20px;}}.page-hero{{padding:40px 20px 32px;}}.topbar{{padding:14px 20px;}}.page-hero h1{{font-size:28px;}}}}
</style>
</head>
<body>
<nav class="topbar">
  <a href="/" class="brand"><span class="brand-my">My</span><span class="brand-store">Store</span><span class="brand-dot"></span></a>
  <a href="/" class="back-btn">← Back to Store</a>
</nav>
<div class="page-hero">
  <div class="breadcrumb"><a href="/">Home</a> <span>›</span> <span>{title}</span></div>
  <span class="page-hero-em">{emoji}</span>
  <h1>{title}</h1>
  <p>{subtitle}</p>
</div>
<div class="content">
{content_html}
</div>
<div class="footer-simple">© 2026 MyStore. All rights reserved. Made with ❤️ in India &nbsp;|&nbsp; <a href="/">Back to Home</a></div>
<script>
function toggleFaq(el){{el.classList.toggle('open');}}
function submitContact(){{
  var n=document.getElementById('cname').value.trim();
  var e=document.getElementById('cemail').value.trim();
  var m=document.getElementById('cmsg').value.trim();
  if(!n||!e||!m){{alert('Please fill in all fields.');return;}}
  var btn=document.getElementById('contactBtn');
  btn.textContent='Sending…';btn.disabled=true;
  setTimeout(function(){{btn.textContent='Message Sent! ✅';document.getElementById('cname').value='';document.getElementById('cemail').value='';document.getElementById('cmsg').value='';}},1200);
}}
function simulateTracking(){{
  var val=document.getElementById('trackInput').value.trim();
  if(!val){{alert('Please enter an Order ID');return;}}
  var res=document.getElementById('trackResult');
  res.style.display='block';
  document.getElementById('tOrderId').textContent='#'+val;
  var today=new Date();
  var fmt=function(d){{return d.toLocaleDateString('en-IN',{{day:'numeric',month:'short',year:'numeric'}});}};
  document.getElementById('ts1').textContent=fmt(new Date(today-2*86400000))+', 10:32 AM';
  document.getElementById('ts2').textContent=fmt(new Date(today-86400000))+', 3:15 PM';
  document.getElementById('trackETA').textContent='Today by 7:00 PM';
}}
</script>
</body>
</html>"""


# ── ABOUT ──────────────────────────────────────────────────────
@app.route('/about')
def page_about():
    content = """
<div class="highlight-box"><p>MyStore is India's fastest-growing e-commerce platform, connecting millions of shoppers with top brands across Electronics, Fashion and Accessories.</p></div>
<div class="section"><h2>Our Mission</h2><p>To make quality products accessible to every Indian household with unbeatable prices, fast delivery, and a shopping experience that truly delights.</p></div>
<div class="stats-grid">
  <div class="stat-card"><div class="stat-num">2M+</div><div class="stat-label">Happy Customers</div></div>
  <div class="stat-card"><div class="stat-num">10K+</div><div class="stat-label">Products</div></div>
  <div class="stat-card"><div class="stat-num">500+</div><div class="stat-label">Cities Served</div></div>
  <div class="stat-card"><div class="stat-num">4.8★</div><div class="stat-label">Avg Rating</div></div>
</div>
<div class="section"><h2>By the Numbers</h2><ul><li>2M+ happy customers across India</li><li>10,000+ products from 500+ trusted brands</li><li>Deliveries in 500+ cities and towns</li><li>4.8 star average customer rating</li><li>Founded in 2022, headquartered in Bengaluru</li></ul></div>
<div class="section"><h2>Our Values</h2>
<div class="values-grid">
  <div class="value-card"><div class="value-em">🏆</div><div class="value-title">Customer First</div><div class="value-desc">Every decision we make starts and ends with our customers' best interests.</div></div>
  <div class="value-card"><div class="value-em">💰</div><div class="value-title">Transparent Pricing</div><div class="value-desc">No hidden fees, no surprise charges. What you see is what you pay.</div></div>
  <div class="value-card"><div class="value-em">🌱</div><div class="value-title">Sustainability</div><div class="value-desc">Committed to eco-friendly packaging across all orders by 2026.</div></div>
  <div class="value-card"><div class="value-em">🤝</div><div class="value-title">Empower Sellers</div><div class="value-desc">Supporting local businesses and small sellers to reach crores of customers.</div></div>
</div></div>
"""
    return info_page_shell("About MyStore", "Our story, mission, and values", "🛍️", content)


# ── CAREERS ─────────────────────────────────────────────────────
@app.route('/careers')
def page_careers():
    content = """
<div class="highlight-box"><p>We are hiring! Join a passionate team building the future of Indian e-commerce. Work on problems that impact millions of people every day.</p></div>
<div class="section"><h2>Open Positions</h2>
<div class="career-card"><div><div class="job-title">Frontend Engineer</div><div class="job-meta">Bengaluru · Full-time · ₹12–20 LPA</div></div><span class="career-badge">Now Hiring</span></div>
<div class="career-card"><div><div class="job-title">Product Manager</div><div class="job-meta">Mumbai · Full-time · ₹18–28 LPA</div></div><span class="career-badge">Now Hiring</span></div>
<div class="career-card"><div><div class="job-title">Growth Marketing Lead</div><div class="job-meta">Remote · Full-time · ₹10–16 LPA</div></div><span class="career-badge">Now Hiring</span></div>
<div class="career-card"><div><div class="job-title">Customer Success Associate</div><div class="job-meta">Pune · Full-time · ₹4–6 LPA</div></div><span class="career-badge">Now Hiring</span></div>
<div class="career-card"><div><div class="job-title">Supply Chain Analyst</div><div class="job-meta">Delhi · Full-time · ₹8–12 LPA</div></div><span class="career-badge">Now Hiring</span></div>
</div>
<div class="section"><h2>Perks & Benefits</h2><ul><li>Competitive salary + ESOPs</li><li>Health insurance for you and family</li><li>₹20,000/year learning budget</li><li>Flexible work-from-home policy</li><li>Employee discount on all MyStore products</li><li>Annual team retreats and events</li></ul></div>
<div class="section"><h2>Apply Now</h2><p style="color:var(--gray);margin-bottom:16px;">Send your resume and we'll reach out within 3 business days.</p>
<input class="form-field" placeholder="Your full name">
<input class="form-field" placeholder="Your email address" type="email">
<input class="form-field" placeholder="Position you're applying for">
<textarea class="form-field" rows="4" placeholder="Tell us about yourself..."></textarea>
<button class="submit-btn" onclick="this.textContent='Application Sent! ✅';this.disabled=true;">Submit Application</button>
</div>
"""
    return info_page_shell("Careers at MyStore", "Join our growing team and shape the future of e-commerce", "💼", content)


# ── PRESS ────────────────────────────────────────────────────────
@app.route('/press')
def page_press():
    content = """
<div class="section"><h2>Latest Coverage</h2>
<div class="press-card"><div class="press-source">Economic Times</div><div class="press-headline">MyStore crosses ₹500 Cr GMV milestone in just 2 years</div><div class="press-date">March 2026</div></div>
<div class="press-card"><div class="press-source">YourStory</div><div class="press-headline">How MyStore is disrupting D2C with AI-powered shopping assistant</div><div class="press-date">February 2026</div></div>
<div class="press-card"><div class="press-source">Inc42</div><div class="press-headline">MyStore raises ₹150 Cr Series B to expand to Tier-2 cities</div><div class="press-date">January 2026</div></div>
<div class="press-card"><div class="press-source">Business Standard</div><div class="press-headline">Best E-commerce Startup of the Year — MyStore wins Startup India Award</div><div class="press-date">December 2025</div></div>
<div class="press-card"><div class="press-source">Forbes India</div><div class="press-headline">30 Under 30: MyStore founders redefining online shopping in India</div><div class="press-date">November 2025</div></div>
</div>
<div class="section"><h2>Press Inquiries</h2><p>For media queries, interviews, press kits, or brand assets, please reach out to our communications team.</p>
<div class="contact-grid" style="margin-top:16px;">
  <div class="contact-card"><div class="cc-icon">📧</div><div class="cc-label">Press Email</div><div class="cc-val"><a href="mailto:press@mystore.in">press@mystore.in</a></div></div>
  <div class="contact-card"><div class="cc-icon">📞</div><div class="cc-label">Press Line</div><div class="cc-val">+91 80 4567 8900</div></div>
</div></div>
"""
    return info_page_shell("Press & Media", "MyStore in the news — coverage, milestones, and media resources", "📰", content)


# ── CONTACT ──────────────────────────────────────────────────────
@app.route('/contact')
def page_contact():
    content = """
<div class="contact-grid">
  <div class="contact-card"><div class="cc-icon">📞</div><div class="cc-label">Customer Care</div><div class="cc-val"><a href="tel:+918045678900">+91 80 4567 8900</a></div></div>
  <div class="contact-card"><div class="cc-icon">📧</div><div class="cc-label">Email Support</div><div class="cc-val"><a href="mailto:support@mystore.in">support@mystore.in</a></div></div>
  <div class="contact-card"><div class="cc-icon">🕒</div><div class="cc-label">Support Hours</div><div class="cc-val">24 × 7 × 365</div></div>
  <div class="contact-card"><div class="cc-icon">📍</div><div class="cc-label">Head Office</div><div class="cc-val">Bengaluru, Karnataka</div></div>
</div>
<div class="section"><h2>Write to Us</h2>
<input class="form-field" id="cname" placeholder="Your full name">
<input class="form-field" id="cemail" placeholder="Your email address" type="email">
<input class="form-field" placeholder="Subject">
<textarea class="form-field" id="cmsg" rows="5" placeholder="Describe your issue or question in detail..."></textarea>
<button class="submit-btn" id="contactBtn" onclick="submitContact()">Send Message</button>
</div>
<div class="section"><h2>Head Office Address</h2><p>MyStore HQ, 4th Floor, Brigade Gateway, Malleswaram West, Bengaluru – 560055, Karnataka, India.</p></div>
"""
    return info_page_shell("Contact Us", "We're here to help 24/7 — reach out any time", "💬", content)


# ── BLOG ─────────────────────────────────────────────────────────
@app.route('/blog')
def page_blog():
    content = """
<div class="section"><h2>Latest Posts</h2>
<div class="blog-card"><div class="blog-em">📱</div><div><div class="blog-title">Top 10 Smartphones Under ₹20,000 in 2026</div><div class="blog-meta">March 28, 2026 · 5 min read</div></div></div>
<div class="blog-card"><div class="blog-em">👗</div><div><div class="blog-title">Summer Fashion Guide: What's Trending This Season</div><div class="blog-meta">March 22, 2026 · 4 min read</div></div></div>
<div class="blog-card"><div class="blog-em">💡</div><div><div class="blog-title">How to Spot Fake Products Online — Expert Tips</div><div class="blog-meta">March 15, 2026 · 6 min read</div></div></div>
<div class="blog-card"><div class="blog-em">🎁</div><div><div class="blog-title">Ultimate Gift Guide for Every Budget</div><div class="blog-meta">March 10, 2026 · 7 min read</div></div></div>
<div class="blog-card"><div class="blog-em">⌚</div><div><div class="blog-title">Smartwatch vs Traditional Watch: Which One Suits You?</div><div class="blog-meta">March 5, 2026 · 5 min read</div></div></div>
<div class="blog-card"><div class="blog-em">🏠</div><div><div class="blog-title">Transform Your Home: Budget Kitchen Upgrades Under ₹5,000</div><div class="blog-meta">February 28, 2026 · 4 min read</div></div></div>
</div>
<div class="section"><h2>Subscribe for Updates</h2><p style="color:var(--gray);margin-bottom:16px;">Get the latest posts, deals, and shopping tips straight to your inbox.</p>
<div style="display:flex;gap:12px;flex-wrap:wrap;">
<input class="form-field" id="blogEmail" placeholder="Your email address" type="email" style="flex:1;min-width:200px;margin-bottom:0;">
<button class="submit-btn" onclick="var e=document.getElementById('blogEmail').value;if(e&&e.includes('@')){this.textContent='Subscribed! ✅';this.disabled=true;}else{alert('Enter a valid email.');}">Subscribe</button>
</div></div>
"""
    return info_page_shell("MyStore Blog", "Tips, trends, deals and everything shopping", "✍️", content)


# ── HELP CENTER ──────────────────────────────────────────────────
@app.route('/help')
def page_help():
    content = """
<div class="highlight-box"><p>Can't find your answer? <a href="/" style="color:var(--accent3);">Chat with our AI assistant</a> on the home page for instant support.</p></div>
<div class="section"><h2>Popular Topics</h2>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">How do I track my order? <span class="faq-chevron">▼</span></div><div class="faq-a">Go to My Orders from the navbar or visit <a href="/track-order" style="color:var(--accent3);">Track Order</a>. Each order has a Track button showing real-time delivery status.</div></div>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">Can I cancel my order? <span class="faq-chevron">▼</span></div><div class="faq-a">Yes! Orders can be cancelled within 24 hours of placing them. Go to My Orders, select the order, then tap Cancel Order. After 24 hrs contact our support team.</div></div>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">How do I change my delivery address? <span class="faq-chevron">▼</span></div><div class="faq-a">Address changes are allowed only before the order is shipped. Contact us at support@mystore.in or call +91 80 4567 8900 within 2 hours of placing the order.</div></div>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">Is Cash on Delivery available everywhere? <span class="faq-chevron">▼</span></div><div class="faq-a">COD is available in 400+ cities across India. Availability is shown at checkout based on your PIN code. Orders above ₹50,000 require prepaid payment.</div></div>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">How do I apply a coupon code? <span class="faq-chevron">▼</span></div><div class="faq-a">Add items to your cart, proceed to Checkout, enter your coupon code (e.g. FIRST10) in the coupon field and click Apply. The discount appears in your order summary.</div></div>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">What if I receive a damaged product? <span class="faq-chevron">▼</span></div><div class="faq-a">Take a photo of the damaged item and contact us within 48 hours. We'll arrange a free replacement or full refund — no questions asked.</div></div>
</div>
<div class="section"><h2>Still Need Help?</h2>
<div class="contact-grid">
  <div class="contact-card"><div class="cc-icon">📞</div><div class="cc-label">Call Us</div><div class="cc-val"><a href="tel:+918045678900">+91 80 4567 8900</a></div></div>
  <div class="contact-card"><div class="cc-icon">📧</div><div class="cc-label">Email</div><div class="cc-val"><a href="mailto:support@mystore.in">support@mystore.in</a></div></div>
</div></div>
"""
    return info_page_shell("Help Center", "Quick answers to the most common questions", "❓", content)


# ── TRACK ORDER ──────────────────────────────────────────────────
@app.route('/track-order')
def page_track():
    content = """
<div class="section"><h2>Enter Your Order ID</h2>
<div class="track-box">
  <div class="track-input-row">
    <input class="form-field" id="trackInput" placeholder="Enter Order ID e.g. 1042" type="number" style="margin-bottom:0;flex:1;">
    <button class="submit-btn" onclick="simulateTracking()">Track Order</button>
  </div>
  <div class="track-result" id="trackResult" style="display:none;margin-top:20px;">
    <div style="margin-bottom:14px;">
      <div style="font-size:13px;color:var(--gray);">Order <strong id="tOrderId" style="color:#fff;">#-</strong></div>
      <div style="font-size:12px;color:var(--accent3);margin-top:4px;">Estimated delivery: <strong id="trackETA">-</strong></div>
    </div>
    <div class="track-step"><div class="track-dot done"></div><div class="track-info"><div class="ts-title">Order Confirmed</div><div class="ts-date" id="ts1">-</div></div></div>
    <div class="track-step"><div class="track-dot done"></div><div class="track-info"><div class="ts-title">Packed &amp; Ready</div><div class="ts-date" id="ts2">-</div></div></div>
    <div class="track-step"><div class="track-dot active"></div><div class="track-info"><div class="ts-title">Out for Delivery</div><div class="ts-date">Today, estimated by 7 PM</div></div></div>
    <div class="track-step"><div class="track-dot"></div><div class="track-info"><div class="ts-title">Delivered</div><div class="ts-date">Pending</div></div></div>
  </div>
</div>
</div>
<div class="section"><h2>Need More Help?</h2><p>Can't find your order? <a href="/contact" style="color:var(--accent3);">Contact our support team</a> or call <a href="tel:+918045678900" style="color:var(--accent3);">+91 80 4567 8900</a>.</p></div>
"""
    return info_page_shell("Track Your Order", "Real-time delivery status for your orders", "🚚", content)


# ── FAQ ───────────────────────────────────────────────────────────
@app.route('/faq')
def page_faq():
    content = """
<div class="section"><h2>Orders & Payments</h2>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">What payment methods are accepted? <span class="faq-chevron">▼</span></div><div class="faq-a">We accept UPI (GPay, PhonePe, Paytm), Credit/Debit Cards (Visa, Mastercard, RuPay), Net Banking (all major Indian banks), and Cash on Delivery.</div></div>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">Is it safe to pay on MyStore? <span class="faq-chevron">▼</span></div><div class="faq-a">All transactions are secured with 256-bit SSL encryption and we are PCI DSS compliant. We never store your card details.</div></div>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">How long does delivery take? <span class="faq-chevron">▼</span></div><div class="faq-a">Standard delivery is 3–5 business days. Express delivery (1–2 days) is available in select cities. Metro cities usually get next-day delivery.</div></div>
</div>
<div class="section"><h2>Returns & Refunds</h2>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">What is the return policy? <span class="faq-chevron">▼</span></div><div class="faq-a">We offer a hassle-free 7-day return policy from the date of delivery. Items must be unused, in original packaging with all tags intact.</div></div>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">When will I get my refund? <span class="faq-chevron">▼</span></div><div class="faq-a">Refunds are processed within 5–7 business days after we receive the returned item. UPI and card refunds are instant once processed.</div></div>
</div>
<div class="section"><h2>Account & Security</h2>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">How do I reset my password? <span class="faq-chevron">▼</span></div><div class="faq-a">Contact our support at support@mystore.in with your registered email. Password reset via email will be available in the next update.</div></div>
<div class="faq-item" onclick="toggleFaq(this)"><div class="faq-q">Is my personal data safe? <span class="faq-chevron">▼</span></div><div class="faq-a">We never sell your personal data. All data is encrypted and stored securely per the Indian IT Act and DPDP Act 2023 guidelines.</div></div>
</div>
"""
    return info_page_shell("Frequently Asked Questions", "Everything you need to know about shopping on MyStore", "💡", content)


# ── SHIPPING POLICY ───────────────────────────────────────────────
@app.route('/shipping-policy')
def page_shipping():
    content = """
<div class="highlight-box"><p>FREE shipping on all orders above ₹999! Orders below ₹999 attract a flat ₹99 delivery fee.</p></div>
<div class="section"><h2>Delivery Timelines</h2><ul>
<li>Metro cities (Delhi, Mumbai, Bengaluru, Chennai, Hyderabad, Kolkata) — 1–2 business days</li>
<li>Tier-1 cities — 2–3 business days</li>
<li>Tier-2 &amp; Tier-3 cities — 3–5 business days</li>
<li>Remote areas — 5–7 business days</li>
</ul></div>
<div class="section"><h2>Express Delivery</h2><p>Same-day and next-day delivery is available in 50+ cities. The Express option is shown at checkout if available for your PIN code. An additional charge of ₹149 applies.</p></div>
<div class="section"><h2>Order Tracking</h2><p>Once your order is shipped, you'll receive an SMS and email with a tracking link. You can also track your order via <a href="/track-order" style="color:var(--accent3);">Track Order</a> on the website.</p></div>
<div class="section"><h2>Shipping Partners</h2><ul><li>Delhivery — pan-India coverage</li><li>Blue Dart — express and high-value orders</li><li>DTDC — Tier-2 and rural areas</li><li>Ekart — select regions</li></ul></div>
"""
    return info_page_shell("Shipping Policy", "Delivery terms, timelines, and shipping partners", "📦", content)


# ── PRIVACY POLICY ────────────────────────────────────────────────
@app.route('/privacy-policy')
def page_privacy():
    content = """
<div class="highlight-box"><p>Last updated: 1 January 2026. We are committed to protecting your privacy in line with the DPDP Act 2023.</p></div>
<div class="section"><h2>Data We Collect</h2><ul><li>Account info — name, email, phone number</li><li>Order and transaction history</li><li>Delivery addresses you provide</li><li>Browsing behaviour on our platform (anonymous)</li><li>Device and IP information for security purposes</li></ul></div>
<div class="section"><h2>How We Use Your Data</h2><ul><li>Processing and fulfilling your orders</li><li>Sending order confirmations and shipping updates</li><li>Personalising product recommendations</li><li>Fraud detection and account security</li><li>Improving our platform and services</li></ul></div>
<div class="section"><h2>Data Sharing</h2><p>We never sell your personal data. We share data only with logistics partners (for delivery), payment processors (for transactions), and when required by law.</p></div>
<div class="section"><h2>Your Rights</h2><ul><li>Access your personal data at any time</li><li>Request correction or deletion of your data</li><li>Opt out of marketing communications</li><li>Data portability — export your data on request</li></ul><p style="margin-top:12px;">For privacy requests email: <a href="mailto:privacy@mystore.in" style="color:var(--accent3);">privacy@mystore.in</a></p></div>
"""
    return info_page_shell("Privacy Policy", "How we collect, use, and protect your personal data", "🔒", content)


# ── TERMS OF SERVICE ──────────────────────────────────────────────
@app.route('/terms')
def page_terms():
    content = """
<div class="highlight-box"><p>By using MyStore, you agree to these Terms of Service. Last updated: 1 January 2026.</p></div>
<div class="section"><h2>1. Eligibility</h2><p>You must be 18 years or older to create an account and make purchases. By registering, you confirm you meet this requirement.</p></div>
<div class="section"><h2>2. Account Responsibility</h2><ul><li>You are responsible for maintaining account security</li><li>Do not share your password with anyone</li><li>Notify us immediately of any unauthorised access</li><li>One account per person — duplicate accounts will be suspended</li></ul></div>
<div class="section"><h2>3. Purchases & Pricing</h2><ul><li>All prices are in Indian Rupees and include applicable GST</li><li>We reserve the right to change prices without prior notice</li><li>Orders are confirmed only after payment is successful</li><li>We may cancel orders if products become out of stock</li></ul></div>
<div class="section"><h2>4. Prohibited Activities</h2><ul><li>Reselling purchased items without authorisation</li><li>Fraudulent chargebacks or return abuse</li><li>Scraping product data or automated bulk purchases</li><li>Posting fake reviews or ratings</li></ul></div>
<div class="section"><h2>5. Governing Law</h2><p>These terms are governed by the laws of India. Disputes shall be resolved in the courts of Bengaluru, Karnataka.</p><p style="margin-top:10px;">Questions? Email <a href="mailto:legal@mystore.in" style="color:var(--accent3);">legal@mystore.in</a></p></div>
"""
    return info_page_shell("Terms of Service", "Rules and guidelines for using MyStore", "📋", content)



# ================= ADMIN PANEL =================

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect('/')
        return f(*args, **kwargs)
    return decorated

ADMIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Panel – MyStore</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0a0f;--surface:#111118;--surface2:#18181f;--surface3:#1e1e28;
  --border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.13);
  --white:#f0f0f8;--gray:#7b7b95;--gray2:#404055;
  --accent:#ff3b5c;--accent2:#ff6b35;--accent3:#00d4aa;--accent4:#7c5cff;--accent5:#ffcc44;
  --green:#22c55e;--red:#ef4444;--blue:#3b82f6;--orange:#f97316;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--white);min-height:100vh;display:flex;}
a{text-decoration:none;color:inherit;}

/* SIDEBAR */
.sidebar{width:240px;min-height:100vh;background:var(--surface);border-right:1px solid var(--border);
  display:flex;flex-direction:column;position:fixed;top:0;left:0;z-index:100;}
.sidebar-brand{padding:24px 20px 20px;border-bottom:1px solid var(--border);}
.sidebar-brand .logo{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;}
.sidebar-brand .logo span{color:var(--accent);}
.sidebar-brand .badge{font-size:10px;font-weight:700;background:var(--accent4);color:#fff;
  padding:2px 8px;border-radius:20px;margin-left:8px;letter-spacing:0.5px;}
.sidebar-nav{flex:1;padding:12px 0;}
.nav-section{font-size:10px;font-weight:700;color:var(--gray2);letter-spacing:1.2px;
  text-transform:uppercase;padding:16px 20px 6px;}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 20px;font-size:13px;
  font-weight:500;color:var(--gray);cursor:pointer;transition:all 0.15s;border-left:3px solid transparent;}
.nav-item:hover{color:var(--white);background:var(--surface2);}
.nav-item.active{color:var(--white);background:var(--surface2);border-left-color:var(--accent3);}
.nav-item .icon{font-size:16px;width:20px;text-align:center;}
.sidebar-footer{padding:16px 20px;border-top:1px solid var(--border);}
.admin-user{display:flex;align-items:center;gap:10px;}
.admin-avatar{width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--accent4));
  display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex-shrink:0;}
.admin-name{font-size:13px;font-weight:600;color:var(--white);}
.admin-role{font-size:11px;color:var(--gray);}

/* MAIN */
.main{margin-left:240px;flex:1;min-height:100vh;display:flex;flex-direction:column;}
.topbar{background:var(--surface);border-bottom:1px solid var(--border);padding:0 32px;height:60px;
  display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:50;}
.topbar-title{font-family:'Syne',sans-serif;font-size:18px;font-weight:700;letter-spacing:-0.3px;}
.topbar-actions{display:flex;align-items:center;gap:12px;}
.btn{padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;
  font-family:'DM Sans',sans-serif;border:none;transition:all 0.15s;}
.btn-primary{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;}
.btn-primary:hover{opacity:0.9;transform:translateY(-1px);}
.btn-ghost{background:transparent;border:1px solid var(--border2);color:var(--gray);}
.btn-ghost:hover{color:var(--white);border-color:var(--white);}
.btn-danger{background:var(--red);color:#fff;}
.btn-danger:hover{opacity:0.85;}
.btn-success{background:var(--green);color:#fff;}
.btn-success:hover{opacity:0.85;}
.btn-sm{padding:5px 12px;font-size:12px;}

/* CONTENT */
.content{padding:28px 32px;flex:1;}

/* SECTIONS */
.section{display:none;}
.section.active{display:block;}

/* STAT CARDS */
.stats-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px;}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px;
  position:relative;overflow:hidden;transition:border-color 0.2s;}
.stat-card:hover{border-color:var(--border2);}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
.stat-card.blue::before{background:var(--blue);}
.stat-card.green::before{background:var(--green);}
.stat-card.orange::before{background:var(--orange);}
.stat-card.purple::before{background:var(--accent4);}
.stat-icon{font-size:28px;margin-bottom:12px;}
.stat-label{font-size:12px;color:var(--gray);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;}
.stat-value{font-family:'DM Sans',sans-serif;font-size:28px;font-weight:500;color:var(--white);letter-spacing:0;}
.stat-sub{font-size:12px;color:var(--gray);margin-top:4px;}
.stat-sub.up{color:var(--green);}
.stat-sub.down{color:var(--red);}

/* TABLE */
.table-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden;margin-bottom:24px;}
.table-header{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;
  align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}
.table-title{font-family:'Syne',sans-serif;font-size:15px;font-weight:700;letter-spacing:-0.3px;}
.search-box{display:flex;align-items:center;gap:8px;background:var(--surface2);border:1px solid var(--border);
  border-radius:8px;padding:6px 12px;min-width:220px;}
.search-box input{background:none;border:none;outline:none;color:var(--white);font-size:13px;
  font-family:'DM Sans',sans-serif;width:100%;}
.search-box input::placeholder{color:var(--gray2);}
table{width:100%;border-collapse:collapse;}
th{font-size:11px;font-weight:700;color:var(--gray);text-transform:uppercase;letter-spacing:0.7px;
  padding:12px 16px;text-align:left;border-bottom:1px solid var(--border);background:var(--surface2);}
td{padding:12px 16px;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.04);vertical-align:middle;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:rgba(255,255,255,0.02);}
.table-empty{text-align:center;padding:40px;color:var(--gray);font-size:14px;}

/* BADGES */
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:0.3px;}
.badge-green{background:rgba(34,197,94,0.15);color:var(--green);}
.badge-red{background:rgba(239,68,68,0.15);color:var(--red);}
.badge-orange{background:rgba(249,115,22,0.15);color:var(--orange);}
.badge-blue{background:rgba(59,130,246,0.15);color:var(--blue);}
.badge-purple{background:rgba(124,92,255,0.15);color:var(--accent4);}
.badge-gray{background:rgba(255,255,255,0.08);color:var(--gray);}

/* MODAL */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:200;
  align-items:center;justify-content:center;backdrop-filter:blur(4px);}
.modal-bg.show{display:flex;}
.modal{background:var(--surface);border:1px solid var(--border2);border-radius:16px;
  padding:28px;width:90%;max-width:520px;max-height:90vh;overflow-y:auto;}
.modal-title{font-family:'Syne',sans-serif;font-size:18px;font-weight:700;margin-bottom:20px;
  display:flex;justify-content:space-between;align-items:center;}
.modal-close{cursor:pointer;color:var(--gray);font-size:20px;line-height:1;}
.modal-close:hover{color:var(--white);}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.form-group{margin-bottom:16px;}
.form-group label{display:block;font-size:11px;font-weight:700;color:var(--gray);
  text-transform:uppercase;letter-spacing:0.8px;margin-bottom:7px;}
.form-group input,.form-group select,.form-group textarea{width:100%;background:var(--surface2);
  border:1.5px solid var(--border);border-radius:8px;padding:10px 13px;font-size:13px;
  color:var(--white);outline:none;font-family:'DM Sans',sans-serif;transition:border-color 0.2s;}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:var(--accent3);}
.form-group select option{background:var(--surface2);}
.form-group textarea{resize:vertical;min-height:70px;}
.modal-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:20px;padding-top:16px;
  border-top:1px solid var(--border);}

/* STATUS SELECT */
.status-sel{background:var(--surface2);border:1px solid var(--border);border-radius:6px;
  padding:4px 8px;font-size:12px;color:var(--white);font-family:'DM Sans',sans-serif;outline:none;cursor:pointer;}

/* TOGGLE */
.toggle{position:relative;display:inline-block;width:36px;height:20px;}
.toggle input{opacity:0;width:0;height:0;}
.toggle-slider{position:absolute;inset:0;background:var(--gray2);border-radius:20px;cursor:pointer;transition:0.2s;}
.toggle-slider::before{content:'';position:absolute;height:14px;width:14px;left:3px;bottom:3px;
  background:#fff;border-radius:50%;transition:0.2s;}
.toggle input:checked+.toggle-slider{background:var(--accent3);}
.toggle input:checked+.toggle-slider::before{transform:translateX(16px);}

/* CHART BARS */
.mini-chart{display:flex;align-items:flex-end;gap:4px;height:40px;}
.bar{background:var(--accent4);border-radius:3px 3px 0 0;width:100%;opacity:0.7;transition:opacity 0.2s;}
.bar:hover{opacity:1;}

/* PAGE NAV */
.pagination{display:flex;gap:6px;align-items:center;padding:12px 16px;border-top:1px solid var(--border);}
.page-btn{padding:5px 10px;border-radius:6px;font-size:12px;cursor:pointer;background:var(--surface2);
  border:1px solid var(--border);color:var(--gray);transition:all 0.15s;}
.page-btn:hover,.page-btn.active{border-color:var(--accent3);color:var(--accent3);}
.page-info{font-size:12px;color:var(--gray);margin-left:auto;}

/* ALERT */
.alert{padding:12px 16px;border-radius:8px;font-size:13px;margin-bottom:16px;display:none;}
.alert.show{display:flex;align-items:center;gap:8px;}
.alert-success{background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.3);color:var(--green);}
.alert-error{background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.3);color:var(--red);}

@media(max-width:900px){
  .sidebar{width:200px;}
  .main{margin-left:200px;}
  .stats-grid{grid-template-columns:1fr 1fr;}
  .content{padding:20px 16px;}
}
</style>
</head>
<body>

<!-- SIDEBAR -->
<aside class="sidebar">
  <div class="sidebar-brand">
    <div class="logo">My<span>Store</span> <span class="badge">ADMIN</span></div>
  </div>
  <nav class="sidebar-nav">
    <div class="nav-section">Overview</div>
    <div class="nav-item active" onclick="showSection('dashboard')">
      <span class="icon">📊</span> Dashboard
    </div>
    <div class="nav-section">Store</div>
    <div class="nav-item" onclick="showSection('orders')">
      <span class="icon">📦</span> Orders
    </div>
    <div class="nav-item" onclick="showSection('products')">
      <span class="icon">🛍️</span> Products
    </div>
    <div class="nav-item" onclick="showSection('users')">
      <span class="icon">👥</span> Users
    </div>
    <div class="nav-section">System</div>
    <div class="nav-item" onclick="showSection('advertisements')">
      <span class="icon">📢</span> Advertisements
    </div>
    <div class="nav-item" onclick="showSection('subscribers')">
      <span class="icon">📧</span> Subscribers
    </div>
    <div class="nav-item" onclick="window.location.href='/'">
      <span class="icon">🏠</span> Back to Store
    </div>
  </nav>
  <div class="sidebar-footer">
    <div class="admin-user">
      <div class="admin-avatar">{{ current_user.username[0].upper() }}</div>
      <div>
        <div class="admin-name">{{ current_user.username }}</div>
        <div class="admin-role">Administrator</div>
      </div>
    </div>
  </div>
</aside>

<!-- MAIN -->
<div class="main">

  <!-- TOPBAR -->
  <div class="topbar">
    <div class="topbar-title" id="topbar-title">Dashboard</div>
    <div class="topbar-actions">
      <button class="btn btn-primary btn-sm" onclick="showSection('products');setTimeout(()=>openProductModal(),100)">+ Add Product</button>
      <a href="/logout" class="btn btn-ghost btn-sm">Logout</a>
    </div>
  </div>

  <div class="content">
    <div id="alert-box" class="alert"></div>

    <!-- ═══════════════ DASHBOARD ═══════════════ -->
    <div id="section-dashboard" class="section active">
      <div class="stats-grid">
        <div class="stat-card blue">
          <div class="stat-icon">📦</div>
          <div class="stat-label">Total Orders</div>
          <div class="stat-value">{{ stats.total_orders }}</div>
          <div class="stat-sub up">All time</div>
        </div>
        <div class="stat-card green">
          <div class="stat-icon">💰</div>
          <div class="stat-label">Total Revenue</div>
          <div class="stat-value">₹{{ "{:,.0f}".format(stats.total_revenue) }}</div>
          <div class="stat-sub up">Paid orders</div>
        </div>
        <div class="stat-card orange">
          <div class="stat-icon">👥</div>
          <div class="stat-label">Total Users</div>
          <div class="stat-value">{{ stats.total_users }}</div>
          <div class="stat-sub">Registered</div>
        </div>
        <div class="stat-card purple">
          <div class="stat-icon">🛍️</div>
          <div class="stat-label">Products</div>
          <div class="stat-value">{{ stats.total_products }}</div>
          <div class="stat-sub">In catalog</div>
        </div>
      </div>

      <!-- RECENT ORDERS -->
      <div class="table-card">
        <div class="table-header">
          <div class="table-title">Recent Orders</div>
          <button class="btn btn-ghost btn-sm" onclick="showSection('orders')">View All →</button>
        </div>
        <table>
          <thead><tr>
            <th>Order ID</th><th>Customer</th><th>Amount</th><th>Payment</th><th>Status</th><th>Date</th><th>Action</th>
          </tr></thead>
          <tbody>
          {% for o in stats.recent_orders %}
          <tr>
            <td><span style="font-family:monospace;color:var(--accent3);">#{{ o.id }}</span></td>
            <td>{{ o.user.username if o.user else 'Deleted' }}</td>
            <td style="font-weight:700;color:var(--white);">₹{{ "{:,}".format(o.total) }}</td>
            <td><span style="font-size:12px;color:var(--gray);">{{ o.payment[:20] if o.payment else '—' }}</span></td>
            <td>
              <span class="badge {% if o.status in ['Confirmed','Paid via PayPal'] %}badge-green{% elif o.status=='Processing' %}badge-orange{% elif o.status=='Shipped' %}badge-blue{% elif o.status=='Delivered' %}badge-green{% elif o.status=='Cancelled' %}badge-red{% else %}badge-gray{% endif %}">
                {{ o.status }}
              </span>
            </td>
            <td style="color:var(--gray);font-size:12px;">{{ o.created_at.strftime('%d %b %Y') }}</td>
            <td>
              <select class="status-sel" onchange="updateOrderStatus({{ o.id }},this.value)">
                {% for s in ['Processing','Confirmed','Shipped','Out for Delivery','Delivered','Cancelled'] %}
                <option value="{{ s }}" {% if o.status==s %}selected{% endif %}>{{ s }}</option>
                {% endfor %}
              </select>
            </td>
          </tr>
          {% endfor %}
          {% if not stats.recent_orders %}<tr><td colspan="7" class="table-empty">No orders yet</td></tr>{% endif %}
          </tbody>
        </table>
      </div>

      <!-- STATS ROW -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
        <div class="table-card">
          <div class="table-header"><div class="table-title">Order Status Breakdown</div></div>
          <div style="padding:16px;">
            {% for status, count in stats.status_counts %}
            <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);">
              <span class="badge {% if status in ['Confirmed','Delivered','Paid via PayPal'] %}badge-green{% elif status=='Processing' %}badge-orange{% elif status=='Shipped' %}badge-blue{% elif status=='Cancelled' %}badge-red{% else %}badge-gray{% endif %}">{{ status }}</span>
              <span style="font-family:'Syne',sans-serif;font-weight:700;">{{ count }}</span>
            </div>
            {% endfor %}
          </div>
        </div>
        <div class="table-card">
          <div class="table-header"><div class="table-title">Top Products</div></div>
          <table>
            <thead><tr><th>Product</th><th>Orders</th></tr></thead>
            <tbody>
            {% for name, cnt in stats.top_products %}
            <tr>
              <td style="font-size:12px;">{{ name[:30] }}</td>
              <td><span style="font-weight:700;color:var(--accent3);">{{ cnt }}</span></td>
            </tr>
            {% endfor %}
            {% if not stats.top_products %}<tr><td colspan="2" class="table-empty">No data</td></tr>{% endif %}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ═══════════════ ORDERS ═══════════════ -->
    <div id="section-orders" class="section">
      <div class="table-card">
        <div class="table-header">
          <div class="table-title">All Orders</div>
          <div class="search-box">
            <span>🔍</span>
            <input type="text" id="order-search" placeholder="Search by ID, user, status..." oninput="filterOrders()">
          </div>
          <select id="order-status-filter" class="status-sel" style="padding:7px 10px;" onchange="filterOrders()">
            <option value="">All Statuses</option>
            <option>Processing</option><option>Confirmed</option><option>Shipped</option>
            <option>Out for Delivery</option><option>Delivered</option><option>Cancelled</option>
          </select>
        </div>
        <table>
          <thead><tr>
            <th>ID</th><th>Customer</th><th>Items</th><th>Amount</th><th>Payment</th><th>Address</th><th>Status</th><th>Date</th>
          </tr></thead>
          <tbody id="orders-tbody">
          {% for o in all_orders %}
          <tr class="order-row" data-id="{{ o.id }}" data-user="{{ o.user.username if o.user else '' }}" data-status="{{ o.status }}">
            <td><span style="font-family:monospace;color:var(--accent3);">#{{ o.id }}</span></td>
            <td>
              <div style="font-weight:600;">{{ o.user.username if o.user else 'Deleted' }}</div>
              <div style="font-size:11px;color:var(--gray);">{{ o.user.email if o.user else '' }}</div>
            </td>
            <td>
              {% for item in o.items %}
              <div style="font-size:11px;color:var(--gray);">{{ item.product_emoji }} {{ item.product_name[:20] }}</div>
              {% endfor %}
            </td>
            <td style="font-weight:700;color:var(--white);">₹{{ "{:,}".format(o.total) }}</td>
            <td style="font-size:11px;color:var(--gray);max-width:120px;overflow:hidden;text-overflow:ellipsis;">{{ o.payment[:25] if o.payment else '—' }}</td>
            <td style="font-size:11px;color:var(--gray);max-width:140px;overflow:hidden;text-overflow:ellipsis;">{{ o.address[:40] if o.address else '—' }}</td>
            <td>
              <select class="status-sel" onchange="updateOrderStatus({{ o.id }},this.value)">
                {% for s in ['Processing','Confirmed','Shipped','Out for Delivery','Delivered','Cancelled'] %}
                <option value="{{ s }}" {% if o.status==s %}selected{% endif %}>{{ s }}</option>
                {% endfor %}
              </select>
            </td>
            <td style="color:var(--gray);font-size:12px;white-space:nowrap;">{{ o.created_at.strftime('%d %b %Y') }}</td>
          </tr>
          {% endfor %}
          {% if not all_orders %}<tr><td colspan="8" class="table-empty">No orders found</td></tr>{% endif %}
          </tbody>
        </table>
      </div>
    </div>

    <!-- ═══════════════ PRODUCTS ═══════════════ -->
    <div id="section-products" class="section">
      <div class="table-card">
        <div class="table-header">
          <div class="table-title">Products ({{ all_products|length }})</div>
          <div class="search-box">
            <span>🔍</span>
            <input type="text" id="product-search" placeholder="Search products..." oninput="filterProducts()">
          </div>
          <select id="cat-filter" class="status-sel" style="padding:7px 10px;" onchange="filterProducts()">
            <option value="">All Categories</option>
            <option>Electronics</option><option>Fashion</option><option>Beauty</option>
            <option>Accessories</option><option>Sports</option><option>Home</option>
          </select>
          <button class="btn btn-primary btn-sm" onclick="openProductModal()">+ Add Product</button>
        </div>
        <table>
          <thead><tr>
            <th>Product</th><th>Category</th><th>Price</th><th>Orig Price</th><th>Rating</th><th>Flash</th><th>Actions</th>
          </tr></thead>
          <tbody id="products-tbody">
          {% for p in all_products %}
          <tr class="product-row" data-name="{{ p.name.lower() }}" data-cat="{{ p.category }}">
            <td>
              <div style="display:flex;align-items:center;gap:10px;">
                {% if p.image_url %}
                <img src="{{ p.image_url }}" style="width:40px;height:40px;object-fit:cover;border-radius:8px;border:1px solid var(--border);" onerror="this.style.display='none'">
                {% else %}
                <span style="font-size:22px;">{{ p.emoji }}</span>
                {% endif %}
                <div>
                  <div style="font-weight:600;font-size:13px;">{{ p.name }}</div>
                  <div style="font-size:11px;color:var(--gray);">{{ p.description[:40] if p.description else '' }}</div>
                </div>
              </div>
            </td>
            <td><span class="badge badge-purple">{{ p.category }}</span></td>
            <td style="font-weight:700;color:var(--accent3);">₹{{ "{:,}".format(p.price) }}</td>
            <td style="color:var(--gray);text-decoration:line-through;font-size:12px;">₹{{ "{:,}".format(p.orig_price) }}</td>
            <td>
              <span style="color:var(--accent5);">★</span>
              <span style="font-size:13px;font-weight:600;">{{ p.rating }}</span>
            </td>
            <td>
              <label class="toggle">
                <input type="checkbox" {% if p.is_flash %}checked{% endif %} onchange="toggleFlash({{ p.id }},this.checked)">
                <span class="toggle-slider"></span>
              </label>
            </td>
            <td>
              <div style="display:flex;gap:6px;">
                <button class="btn btn-ghost btn-sm" onclick="openEditProduct({{ p.id }},'{{ p.name|e }}','{{ p.emoji|e }}','{{ p.category|e }}','{{ p.subcategory|e }}',{{ p.price }},{{ p.orig_price }},'{{ p.description|e }}',{{ p.rating }},{{ p.is_flash|lower }},'{{ (p.image_url or '')|e }}')">Edit</button>
                <button class="btn btn-danger btn-sm" onclick="deleteProduct({{ p.id }},'{{ p.name|e }}')">Del</button>
              </div>
            </td>
          </tr>
          {% endfor %}
          {% if not all_products %}<tr><td colspan="7" class="table-empty">No products found</td></tr>{% endif %}
          </tbody>
        </table>
      </div>
    </div>

    <!-- ═══════════════ USERS ═══════════════ -->
    <div id="section-users" class="section">
      <div class="table-card">
        <div class="table-header">
          <div class="table-title">Users ({{ all_users|length }})</div>
          <div class="search-box">
            <span>🔍</span>
            <input type="text" id="user-search" placeholder="Search users..." oninput="filterUsers()">
          </div>
        </div>
        <table>
          <thead><tr>
            <th>ID</th><th>Username</th><th>Email</th><th>Role</th><th>Orders</th><th>Actions</th>
          </tr></thead>
          <tbody id="users-tbody">
          {% for u in all_users %}
          <tr class="user-row" data-name="{{ u.username.lower() }}" data-email="{{ (u.email or '').lower() }}">
            <td style="color:var(--gray);font-family:monospace;">#{{ u.id }}</td>
            <td>
              <div style="display:flex;align-items:center;gap:8px;">
                <div style="width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,var(--accent4),var(--accent));
                  display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0;">
                  {{ u.username[0].upper() }}
                </div>
                <span style="font-weight:600;">{{ u.username }}</span>
              </div>
            </td>
            <td style="color:var(--gray);font-size:13px;">{{ u.email or '—' }}</td>
            <td>
              {% if u.is_admin %}
              <span class="badge badge-red">Admin</span>
              {% else %}
              <span class="badge badge-gray">User</span>
              {% endif %}
            </td>
            <td><span style="font-weight:700;color:var(--accent3);">{{ u.order_count }}</span></td>
            <td>
              <div style="display:flex;gap:6px;">
                {% if not u.is_admin %}
                <button class="btn btn-ghost btn-sm" onclick="toggleAdmin({{ u.id }},true)">Make Admin</button>
                {% else %}
                <button class="btn btn-ghost btn-sm" onclick="toggleAdmin({{ u.id }},false)">Remove Admin</button>
                {% endif %}
                <button class="btn btn-danger btn-sm" onclick="deleteUser({{ u.id }},'{{ u.username|e }}')">Delete</button>
              </div>
            </td>
          </tr>
          {% endfor %}
          {% if not all_users %}<tr><td colspan="6" class="table-empty">No users found</td></tr>{% endif %}
          </tbody>
        </table>
      </div>
    </div>

    <!-- ═══════════════ SUBSCRIBERS ═══════════════ -->
    <div id="section-advertisements" class="section">
      <div class="table-card">
        <div class="table-header">
          <div class="table-title">Homepage Advertisement Banners</div>
          <button class="btn btn-primary btn-sm" onclick="openAdModal(0)">+ Add New Slide</button>
        </div>
        <div style="padding:20px;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;" id="ad-cards-grid">
          {% for ad in all_ads %}
          <div class="stat-card" style="padding:20px;position:relative;border:1px solid var(--border);border-radius:14px;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
              <span style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--gray);">Slide {{ ad.slot }}</span>
              <span style="padding:3px 10px;border-radius:50px;font-size:11px;font-weight:700;background:{% if ad.is_active %}rgba(0,212,100,0.15);color:#00d464{% else %}rgba(255,59,92,0.15);color:var(--accent){% endif %};">
                {% if ad.is_active %}● Active{% else %}○ Inactive{% endif %}
              </span>
            </div>
            <div style="font-size:36px;margin-bottom:8px;">{{ ad.emoji }}</div>
            <div style="font-size:11px;color:var(--accent);font-weight:700;margin-bottom:4px;">{{ ad.tag }}</div>
            <div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:4px;">{{ ad.title }}</div>
            <div style="font-size:12px;color:var(--gray);margin-bottom:12px;">{{ ad.subtitle }}</div>
            <div style="display:flex;gap:8px;align-items:center;justify-content:space-between;">
              <span style="font-size:11px;background:rgba(255,59,92,0.15);color:var(--accent);padding:3px 10px;border-radius:8px;font-weight:700;">{{ ad.discount }}</span>
              <div style="display:flex;gap:6px;">
                <button class="btn btn-ghost btn-sm" onclick="openAdModal({{ ad.slot }})">Edit</button>
                <button class="btn btn-danger btn-sm" onclick="deleteAd({{ ad.slot }})">Delete</button>
              </div>
            </div>
          </div>
          {% endfor %}
          {% if not all_ads %}
          <div style="grid-column:1/-1;text-align:center;color:var(--gray);padding:40px;">No advertisements configured — defaults are shown on homepage.</div>
          {% endif %}
        </div>
      </div>
    </div>

    <div id="section-subscribers" class="section">
      <div class="table-card">
        <div class="table-header">
          <div class="table-title">Email Subscribers ({{ all_subscribers|length }})</div>
          <button class="btn btn-ghost btn-sm" onclick="exportSubscribers()">Export CSV</button>
        </div>
        <table>
          <thead><tr><th>#</th><th>Email</th><th>Subscribed On</th><th>Action</th></tr></thead>
          <tbody>
          {% for s in all_subscribers %}
          <tr>
            <td style="color:var(--gray);font-family:monospace;">{{ loop.index }}</td>
            <td style="font-weight:500;">{{ s.email }}</td>
            <td style="color:var(--gray);font-size:12px;">{{ s.subscribed_at.strftime('%d %b %Y, %I:%M %p') }}</td>
            <td><button class="btn btn-danger btn-sm" onclick="deleteSubscriber({{ s.id }})">Remove</button></td>
          </tr>
          {% endfor %}
          {% if not all_subscribers %}<tr><td colspan="4" class="table-empty">No subscribers yet</td></tr>{% endif %}
          </tbody>
        </table>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /main -->

<!-- AD EDIT MODAL -->
<div class="modal-bg" id="ad-modal">
  <div class="modal" style="max-width:600px;">
    <div class="modal-title">
      <span id="ad-modal-title">Edit Advertisement</span>
      <span class="modal-close" onclick="closeAdModal()">✕</span>
    </div>
    <input type="hidden" id="ad-slot-id">
    <div class="form-row">
      <div class="form-group">
        <label>Tag Label (e.g. ⚡ Electronics Sale)</label>
        <input id="ad-tag" placeholder="⚡ Electronics Sale">
      </div>
      <div class="form-group">
        <label>Emoji Icon</label>
        <input id="ad-emoji" placeholder="📱" maxlength="6">
      </div>
    </div>
    <div class="form-group">
      <label>Headline Title</label>
      <input id="ad-title" placeholder="Latest Gadgets &amp; Tech">
    </div>
    <div class="form-group">
      <label>Subtitle / Description</label>
      <input id="ad-subtitle" placeholder="Smartphones, Laptops, Audio &amp; more">
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Discount Badge Text</label>
        <input id="ad-discount" placeholder="UP TO 40% OFF">
      </div>
      <div class="form-group">
        <label>Theme / Color</label>
        <select id="ad-theme">
          <option value="electronics">🔵 Electronics (Blue)</option>
          <option value="fashion">🟣 Fashion (Pink/Purple)</option>
          <option value="accessories">🟡 Accessories (Gold)</option>
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>CTA Button Text</label>
        <input id="ad-cta-text" placeholder="Shop Now →">
      </div>
      <div class="form-group">
        <label>CTA Link URL</label>
        <input id="ad-cta-link" placeholder="/?category=Electronics">
      </div>
    </div>
    <div class="form-group">
      <label>Status</label>
      <select id="ad-active">
        <option value="true">✅ Active (visible on homepage)</option>
        <option value="false">🚫 Inactive (hidden)</option>
      </select>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeAdModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveAd()">Save Advertisement</button>
    </div>
  </div>
</div>

<!-- PRODUCT MODAL -->
<div class="modal-bg" id="product-modal">
  <div class="modal">
    <div class="modal-title">
      <span id="modal-mode-title">Add Product</span>
      <span class="modal-close" onclick="closeProductModal()">✕</span>
    </div>
    <input type="hidden" id="edit-product-id" value="">
    <div class="form-row">
      <div class="form-group">
        <label>Product Name</label>
        <input id="p-name" placeholder="Samsung Galaxy S24">
      </div>
      <div class="form-group">
        <label>Emoji</label>
        <input id="p-emoji" placeholder="📱" maxlength="4">
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Category</label>
        <select id="p-category">
          <option>Electronics</option><option>Fashion</option><option>Beauty</option>
          <option>Accessories</option><option>Sports</option><option>Home</option>
        </select>
      </div>
      <div class="form-group">
        <label>Subcategory</label>
        <input id="p-subcategory" placeholder="Smartphones">
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Sale Price (₹)</label>
        <input id="p-price" type="number" placeholder="79999">
      </div>
      <div class="form-group">
        <label>Original Price (₹)</label>
        <input id="p-orig-price" type="number" placeholder="89999">
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Rating (0–5)</label>
        <input id="p-rating" type="number" step="0.1" min="0" max="5" placeholder="4.5">
      </div>
      <div class="form-group">
        <label>Flash Sale</label>
        <select id="p-flash"><option value="false">No</option><option value="true">Yes</option></select>
      </div>
    </div>
    <div class="form-group">
      <label>Description</label>
      <textarea id="p-description" placeholder="Short product description..."></textarea>
    </div>
    <div class="form-group">
      <label>Product Image URL</label>
      <input id="p-image-url" placeholder="https://images.unsplash.com/..." oninput="previewProductImage(this.value)">
      <div style="margin-top:10px;">
        <label style="font-size:12px;color:var(--gray);font-weight:600;display:flex;align-items:center;gap:6px;margin-bottom:6px;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          Or upload from your device
        </label>
        <label id="p-upload-label" style="display:flex;align-items:center;gap:8px;padding:9px 16px;border:1.5px dashed var(--border);border-radius:10px;cursor:pointer;background:var(--surface3);font-size:13px;color:var(--gray);transition:all 0.2s;" onmouseover="this.style.borderColor='var(--accent)';this.style.color='var(--accent)';" onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--gray)';">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
          <span id="p-upload-filename">Choose image file (JPG, PNG, WEBP, GIF · max 5 MB)</span>
          <input type="file" id="p-image-file" accept="image/jpeg,image/png,image/gif,image/webp" style="display:none;" onchange="handleLocalImageUpload(this)">
        </label>
        <div id="p-upload-progress" style="display:none;margin-top:6px;font-size:12px;color:var(--accent3);">⏳ Uploading…</div>
      </div>
      <div id="p-image-preview" style="margin-top:8px;display:none;">
        <img id="p-img-tag" src="" style="width:100%;max-height:160px;object-fit:cover;border-radius:8px;border:1px solid var(--border);">
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeProductModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveProduct()">Save Product</button>
    </div>
  </div>
</div>

<script>
// ── SECTION NAV ──────────────────────────────────────────────
var sectionTitles={dashboard:'Dashboard',orders:'Orders',products:'Products',users:'Users',subscribers:'Subscribers',advertisements:'Advertisements'};
function showSection(name){
  document.querySelectorAll('.section').forEach(function(s){s.classList.remove('active');});
  document.querySelectorAll('.nav-item').forEach(function(n){n.classList.remove('active');});
  document.getElementById('section-'+name).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(function(n){
    if(n.textContent.trim().toLowerCase().includes(name))n.classList.add('active');
  });
  document.getElementById('topbar-title').textContent=sectionTitles[name]||name;
}

// ── ALERT ────────────────────────────────────────────────────
function showAlert(msg,type){
  var el=document.getElementById('alert-box');
  el.textContent=(type==='success'?'✓ ':'✕ ')+msg;
  el.className='alert show alert-'+(type||'success');
  setTimeout(function(){el.className='alert';},3500);
}

// ── ORDER STATUS ─────────────────────────────────────────────
function updateOrderStatus(id,status){
  fetch('/admin/order/'+id+'/status',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({status:status})
  }).then(function(r){return r.json();}).then(function(d){
    if(d.ok)showAlert('Order #'+id+' updated to "'+status+'"','success');
    else showAlert('Failed to update order','error');
  });
}

// ── ORDER FILTER ─────────────────────────────────────────────
function filterOrders(){
  var q=document.getElementById('order-search').value.toLowerCase();
  var sf=document.getElementById('order-status-filter').value.toLowerCase();
  document.querySelectorAll('.order-row').forEach(function(r){
    var id=r.dataset.id||'';
    var user=r.dataset.user||'';
    var status=r.dataset.status||'';
    var match=(id.includes(q)||user.toLowerCase().includes(q)||status.toLowerCase().includes(q));
    var statusMatch=!sf||status.toLowerCase()===sf;
    r.style.display=(match&&statusMatch)?'':'none';
  });
}

// ── PRODUCT FILTER ───────────────────────────────────────────
function filterProducts(){
  var q=document.getElementById('product-search').value.toLowerCase();
  var cat=document.getElementById('cat-filter').value.toLowerCase();
  document.querySelectorAll('.product-row').forEach(function(r){
    var name=r.dataset.name||'';
    var rcat=r.dataset.cat||'';
    var match=name.includes(q)||rcat.toLowerCase().includes(q);
    var catMatch=!cat||rcat.toLowerCase()===cat;
    r.style.display=(match&&catMatch)?'':'none';
  });
}

// ── USER FILTER ──────────────────────────────────────────────
function filterUsers(){
  var q=document.getElementById('user-search').value.toLowerCase();
  document.querySelectorAll('.user-row').forEach(function(r){
    var name=r.dataset.name||'';
    var email=r.dataset.email||'';
    r.style.display=(name.includes(q)||email.includes(q))?'':'none';
  });
}

// ── PRODUCT MODAL ─────────────────────────────────────────────
function previewProductImage(url){
  var wrap=document.getElementById('p-image-preview');
  var img=document.getElementById('p-img-tag');
  if(url&&(url.startsWith('http')||url.startsWith('data:'))){
    img.src=url;
    wrap.style.display='block';
    img.onerror=function(){wrap.style.display='none';};
  }else{
    wrap.style.display='none';
  }
}

function resetUploadField(){
  var fi=document.getElementById('p-image-file');
  if(fi) fi.value='';
  var fn=document.getElementById('p-upload-filename');
  if(fn) fn.textContent='Choose image file (JPG, PNG, WEBP, GIF \u00b7 max 5 MB)';
  var prog=document.getElementById('p-upload-progress');
  if(prog) prog.style.display='none';
}

function openProductModal(){
  document.getElementById('modal-mode-title').textContent='Add Product';
  document.getElementById('edit-product-id').value='';
  ['p-name','p-emoji','p-subcategory','p-price','p-orig-price','p-rating','p-description','p-image-url'].forEach(function(id){
    document.getElementById(id).value='';
  });
  document.getElementById('p-flash').value='false';
  document.getElementById('p-image-preview').style.display='none';
  resetUploadField();
  document.getElementById('product-modal').classList.add('show');
}

function openEditProduct(id,name,emoji,cat,subcat,price,orig,desc,rating,flash,imageUrl){
  document.getElementById('modal-mode-title').textContent='Edit Product';
  document.getElementById('edit-product-id').value=id;
  document.getElementById('p-name').value=name;
  document.getElementById('p-emoji').value=emoji;
  document.getElementById('p-category').value=cat;
  document.getElementById('p-subcategory').value=subcat;
  document.getElementById('p-price').value=price;
  document.getElementById('p-orig-price').value=orig;
  document.getElementById('p-description').value=desc;
  document.getElementById('p-rating').value=rating;
  document.getElementById('p-flash').value=flash?'true':'false';
  document.getElementById('p-image-url').value=imageUrl||'';
  previewProductImage(imageUrl||'');
  resetUploadField();
  document.getElementById('product-modal').classList.add('show');
}

function closeProductModal(){
  document.getElementById('product-modal').classList.remove('show');
  resetUploadField();
}

function handleLocalImageUpload(input){
  var file=input.files&&input.files[0];
  if(!file) return;
  var fn=document.getElementById('p-upload-filename');
  var prog=document.getElementById('p-upload-progress');
  fn.textContent=file.name;
  prog.style.display='block';
  var formData=new FormData();
  formData.append('image',file);
  fetch('/admin/product/upload-image',{method:'POST',body:formData})
  .then(function(r){return r.json();})
  .then(function(d){
    prog.style.display='none';
    if(d.ok){
      document.getElementById('p-image-url').value=d.url;
      previewProductImage(d.url);
      fn.textContent='\u2713 '+file.name+' (ready)';
    }else{
      alert('Upload failed: '+(d.error||'Unknown error'));
      fn.textContent='Choose image file (JPG, PNG, WEBP, GIF \u00b7 max 5 MB)';
      input.value='';
    }
  })
  .catch(function(){
    prog.style.display='none';
    alert('Upload failed. Please try again.');
    fn.textContent='Choose image file (JPG, PNG, WEBP, GIF \u00b7 max 5 MB)';
    input.value='';
  });
}

function saveProduct(){
  var id=document.getElementById('edit-product-id').value;
  var data={
    name:document.getElementById('p-name').value.trim(),
    emoji:document.getElementById('p-emoji').value.trim()||'🛍️',
    category:document.getElementById('p-category').value,
    subcategory:document.getElementById('p-subcategory').value.trim(),
    price:parseInt(document.getElementById('p-price').value)||0,
    orig_price:parseInt(document.getElementById('p-orig-price').value)||0,
    description:document.getElementById('p-description').value.trim(),
    rating:parseFloat(document.getElementById('p-rating').value)||4.5,
    is_flash:document.getElementById('p-flash').value==='true',
    image_url:document.getElementById('p-image-url').value.trim()
  };
  if(!data.name){alert('Product name is required.');return;}
  if(!data.price){alert('Price is required.');return;}
  var url=id?'/admin/product/'+id+'/edit':'/admin/product/add';
  fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.ok){
      closeProductModal();
      showAlert(id?'Product updated!':'Product added!','success');
      setTimeout(function(){window.location.reload();},1200);
    }else{showAlert(d.error||'Failed','error');}
  });
}

function deleteProduct(id,name){
  if(!confirm('Delete product "'+name+'"? This cannot be undone.'))return;
  fetch('/admin/product/'+id+'/delete',{method:'POST'})
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.ok){
      showAlert('Product deleted','success');
      setTimeout(function(){window.location.reload();},1000);
    }else{showAlert(d.error||'Failed','error');}
  });
}

function toggleFlash(id,val){
  fetch('/admin/product/'+id+'/flash',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({is_flash:val})
  }).then(function(r){return r.json();}).then(function(d){
    if(d.ok)showAlert('Flash sale '+(val?'enabled':'disabled'),'success');
  });
}

// ── USER ACTIONS ─────────────────────────────────────────────
function toggleAdmin(id,makeAdmin){
  if(!confirm((makeAdmin?'Grant':'Revoke')+' admin rights for this user?'))return;
  fetch('/admin/user/'+id+'/admin',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({is_admin:makeAdmin})
  }).then(function(r){return r.json();}).then(function(d){
    if(d.ok){showAlert('User role updated','success');setTimeout(function(){window.location.reload();},1000);}
    else showAlert(d.error||'Failed','error');
  });
}

function deleteUser(id,name){
  if(!confirm('Delete user "'+name+'" and ALL their data? This cannot be undone.'))return;
  fetch('/admin/user/'+id+'/delete',{method:'POST'})
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.ok){showAlert('User deleted','success');setTimeout(function(){window.location.reload();},1000);}
    else showAlert(d.error||'Failed','error');
  });
}

// ── SUBSCRIBERS ──────────────────────────────────────────────
function deleteSubscriber(id){
  fetch('/admin/subscriber/'+id+'/delete',{method:'POST'})
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.ok){showAlert('Subscriber removed','success');setTimeout(function(){window.location.reload();},800);}
  });
}

function exportSubscribers(){
  window.location.href='/admin/subscribers/export';
}

// Close modal on bg click
document.getElementById('product-modal').addEventListener('click',function(e){
  if(e.target===this)closeProductModal();
});
document.getElementById('ad-modal').addEventListener('click',function(e){
  if(e.target===this)closeAdModal();
});

// ── ADVERTISEMENTS ───────────────────────────────────────────
function openAdModal(slot){
  document.getElementById('ad-modal').style.display='flex';
  if(slot===0){
    // New ad
    document.getElementById('ad-modal-title').textContent='Add New Advertisement';
    document.getElementById('ad-slot-id').value='';
    ['ad-tag','ad-title','ad-subtitle','ad-discount','ad-cta-text','ad-cta-link','ad-emoji'].forEach(function(id){document.getElementById(id).value='';});
    document.getElementById('ad-theme').value='electronics';
    document.getElementById('ad-active').value='true';
  } else {
    document.getElementById('ad-modal-title').textContent='Edit Advertisement — Slide '+slot;
    document.getElementById('ad-slot-id').value=slot;
    fetch('/admin/advertisement/'+slot)
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){
        document.getElementById('ad-tag').value=d.ad.tag||'';
        document.getElementById('ad-title').value=d.ad.title||'';
        document.getElementById('ad-subtitle').value=d.ad.subtitle||'';
        document.getElementById('ad-discount').value=d.ad.discount||'';
        document.getElementById('ad-cta-text').value=d.ad.cta_text||'';
        document.getElementById('ad-cta-link').value=d.ad.cta_link||'';
        document.getElementById('ad-emoji').value=d.ad.emoji||'';
        document.getElementById('ad-theme').value=d.ad.theme||'electronics';
        document.getElementById('ad-active').value=d.ad.is_active?'true':'false';
      }
    });
  }
}
function closeAdModal(){
  document.getElementById('ad-modal').style.display='none';
}
function saveAd(){
  var slot=document.getElementById('ad-slot-id').value;
  var payload={
    tag:document.getElementById('ad-tag').value,
    title:document.getElementById('ad-title').value,
    subtitle:document.getElementById('ad-subtitle').value,
    discount:document.getElementById('ad-discount').value,
    cta_text:document.getElementById('ad-cta-text').value,
    cta_link:document.getElementById('ad-cta-link').value,
    emoji:document.getElementById('ad-emoji').value,
    theme:document.getElementById('ad-theme').value,
    is_active:document.getElementById('ad-active').value==='true',
    slot:slot?parseInt(slot):null
  };
  fetch('/admin/advertisement/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.ok){showAlert('Advertisement saved!','success');closeAdModal();setTimeout(function(){window.location.reload();},800);}
    else{showAlert(d.error||'Save failed','error');}
  });
}
function deleteAd(slot){
  if(!confirm('Delete advertisement slot '+slot+'?'))return;
  fetch('/admin/advertisement/'+slot+'/delete',{method:'POST'})
  .then(function(r){return r.json();})
  .then(function(d){
    if(d.ok){showAlert('Advertisement deleted','success');setTimeout(function(){window.location.reload();},800);}
  });
}
</script>
</body>
</html>"""


# ── ADMIN ROUTES ─────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_panel():
    from sqlalchemy import func
    # Stats
    total_orders   = Order.query.count()
    total_revenue  = db.session.query(func.sum(Order.total)).scalar() or 0
    total_users    = User.query.count()
    total_products = Product.query.count()
    recent_orders  = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    # Attach user to each order
    for o in recent_orders:
        o.user = db.session.get(User, o.user_id)
    # Status breakdown
    status_counts = db.session.query(Order.status, func.count(Order.id))\
        .group_by(Order.status).order_by(func.count(Order.id).desc()).all()
    # Top products
    top_products = db.session.query(OrderItem.product_name, func.count(OrderItem.id).label('cnt'))\
        .group_by(OrderItem.product_name).order_by(func.count(OrderItem.id).desc()).limit(5).all()

    stats = {
        'total_orders': total_orders, 'total_revenue': total_revenue,
        'total_users': total_users,   'total_products': total_products,
        'recent_orders': recent_orders, 'status_counts': status_counts,
        'top_products': top_products
    }

    all_orders = Order.query.order_by(Order.created_at.desc()).all()
    for o in all_orders:
        o.user = db.session.get(User, o.user_id)

    all_products = Product.query.order_by(Product.category, Product.name).all()

    all_users = User.query.order_by(User.id).all()
    for u in all_users:
        u.order_count = Order.query.filter_by(user_id=u.id).count()

    all_subscribers = Subscriber.query.order_by(Subscriber.subscribed_at.desc()).all()
    all_ads = Advertisement.query.order_by(Advertisement.slot).all()

    return render_template_string(ADMIN_PAGE,
        stats=stats, all_orders=all_orders, all_products=all_products,
        all_users=all_users, all_subscribers=all_subscribers, all_ads=all_ads)


@app.route('/admin/order/<int:order_id>/status', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
    o = db.session.get(Order, order_id)
    if not o:
        return jsonify({'ok': False, 'error': 'Order not found'})
    data = request.get_json() or {}
    o.status = data.get('status', o.status)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/product/upload-image', methods=['POST'])
@admin_required
def admin_upload_product_image():
    import base64, uuid, re
    f = request.files.get('image')
    if not f:
        return jsonify({'ok': False, 'error': 'No file provided'})
    allowed = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    if f.mimetype not in allowed:
        return jsonify({'ok': False, 'error': 'Only JPG, PNG, GIF, WEBP allowed'})
    data = f.read()
    if len(data) > 5 * 1024 * 1024:
        return jsonify({'ok': False, 'error': 'Image must be under 5 MB'})
    b64 = base64.b64encode(data).decode('utf-8')
    data_url = f'data:{f.mimetype};base64,{b64}'
    return jsonify({'ok': True, 'url': data_url})


@app.route('/admin/product/add', methods=['POST'])
@admin_required
def admin_add_product():
    data = request.get_json() or {}
    p = Product(
        name=data.get('name',''), emoji=data.get('emoji','🛍️'),
        category=data.get('category',''), subcategory=data.get('subcategory',''),
        price=int(data.get('price',0)), orig_price=int(data.get('orig_price',0)),
        description=data.get('description',''), rating=float(data.get('rating',4.5)),
        is_flash=bool(data.get('is_flash',False)), sold='0',
        image_url=data.get('image_url','')
    )
    db.session.add(p)
    db.session.commit()
    return jsonify({'ok': True, 'id': p.id})


@app.route('/admin/product/<int:product_id>/edit', methods=['POST'])
@admin_required
def admin_edit_product(product_id):
    p = db.session.get(Product, product_id)
    if not p:
        return jsonify({'ok': False, 'error': 'Product not found'})
    data = request.get_json() or {}
    p.name        = data.get('name', p.name)
    p.emoji       = data.get('emoji', p.emoji)
    p.category    = data.get('category', p.category)
    p.subcategory = data.get('subcategory', p.subcategory)
    p.price       = int(data.get('price', p.price))
    p.orig_price  = int(data.get('orig_price', p.orig_price))
    p.description = data.get('description', p.description)
    p.rating      = float(data.get('rating', p.rating))
    p.is_flash    = bool(data.get('is_flash', p.is_flash))
    p.image_url   = data.get('image_url', p.image_url or '')
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/product/<int:product_id>/delete', methods=['POST'])
@admin_required
def admin_delete_product(product_id):
    p = db.session.get(Product, product_id)
    if not p:
        return jsonify({'ok': False, 'error': 'Not found'})
    # Remove from carts first
    Cart.query.filter_by(product_id=product_id).delete()
    db.session.delete(p)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/product/<int:product_id>/flash', methods=['POST'])
@admin_required
def admin_toggle_flash(product_id):
    p = db.session.get(Product, product_id)
    if not p:
        return jsonify({'ok': False})
    data = request.get_json() or {}
    p.is_flash = bool(data.get('is_flash', False))
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/user/<int:user_id>/admin', methods=['POST'])
@admin_required
def admin_toggle_admin(user_id):
    if user_id == current_user.id:
        return jsonify({'ok': False, 'error': "Can't change your own role"})
    u = db.session.get(User, user_id)
    if not u:
        return jsonify({'ok': False, 'error': 'User not found'})
    data = request.get_json() or {}
    u.is_admin = bool(data.get('is_admin', False))
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'ok': False, 'error': "Can't delete yourself"})
    u = db.session.get(User, user_id)
    if not u:
        return jsonify({'ok': False, 'error': 'Not found'})
    Cart.query.filter_by(user_id=user_id).delete()
    SavedAddress.query.filter_by(user_id=user_id).delete()
    # Keep orders for record-keeping but detach user
    db.session.delete(u)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/subscriber/<int:sub_id>/delete', methods=['POST'])
@admin_required
def admin_delete_subscriber(sub_id):
    s = db.session.get(Subscriber, sub_id)
    if s:
        db.session.delete(s)
        db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/subscribers/export')
@admin_required
def admin_export_subscribers():
    subs = Subscriber.query.order_by(Subscriber.subscribed_at.desc()).all()
    csv_lines = ['email,subscribed_at']
    for s in subs:
        csv_lines.append(f'{s.email},{s.subscribed_at.strftime("%Y-%m-%d %H:%M:%S")}')
    csv_data = '\n'.join(csv_lines)
    from flask import Response
    return Response(csv_data, mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=subscribers.csv'})

@app.route('/robots.txt')
def robots_txt():
    content = "User-agent: *\nDisallow: /"
    return Response(content, mimetype='text/plain')


# ================= ADVERTISEMENT API =================
@app.route('/admin/advertisement/<int:slot>')
@admin_required
def admin_get_advertisement(slot):
    ad = Advertisement.query.filter_by(slot=slot).first()
    if not ad:
        return jsonify({'ok': False, 'error': 'Not found'})
    return jsonify({'ok': True, 'ad': {
        'slot': ad.slot, 'tag': ad.tag, 'title': ad.title,
        'subtitle': ad.subtitle, 'cta_text': ad.cta_text, 'cta_link': ad.cta_link,
        'discount': ad.discount, 'emoji': ad.emoji, 'theme': ad.theme,
        'is_active': ad.is_active
    }})


@app.route('/admin/advertisement/save', methods=['POST'])
@admin_required
def admin_save_advertisement():
    data = request.get_json() or {}
    slot = data.get('slot')
    if not slot:
        # Auto-assign next available slot
        existing_slots = [a.slot for a in Advertisement.query.all()]
        slot = 1
        while slot in existing_slots:
            slot += 1
    ad = Advertisement.query.filter_by(slot=slot).first()
    if not ad:
        ad = Advertisement(slot=slot)
        db.session.add(ad)
    ad.tag       = data.get('tag', '')
    ad.title     = data.get('title', '')
    ad.subtitle  = data.get('subtitle', '')
    ad.cta_text  = data.get('cta_text', '')
    ad.cta_link  = data.get('cta_link', '/')
    ad.discount  = data.get('discount', '')
    ad.emoji     = data.get('emoji', '🛍️')
    ad.theme     = data.get('theme', 'electronics')
    ad.is_active = bool(data.get('is_active', True))
    ad.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True, 'slot': ad.slot})


@app.route('/admin/advertisement/<int:slot>/delete', methods=['POST'])
@admin_required
def admin_delete_advertisement(slot):
    ad = Advertisement.query.filter_by(slot=slot).first()
    if ad:
        db.session.delete(ad)
        db.session.commit()
    return jsonify({'ok': True})

# ================= RUN =================
if __name__ == '__main__':
    app.run(debug=True)
