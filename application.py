import os

from flask import Flask, session, render_template, request, redirect, url_for
from flask_session import Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

db.execute(text("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
"""))

db.execute(text("""CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    isbn CHAR(13) REFERENCES book_table(isbn),
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    review_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, isbn) -- One review per user, per book
)"""))

db.commit()


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        existing_user = db.execute(
            text("SELECT * FROM users WHERE username = :username"),
            {"username": username}
        ).fetchone()

        if existing_user:
            message = "Username already taken"
            color = "red"
            return render_template("signup.html", message=message, color=color)
        else:
            db.execute(
                text("INSERT INTO users (username, password) VALUES (:username, :password)"),
                {"username": username, "password": password}
            )
            db.commit()

            user = db.execute(
                text("SELECT * FROM users WHERE username = :username"),
                {"username": username}
            ).fetchone()

            session['user_id'] = user.id

            return redirect(url_for("search"))

    return render_template("signup.html")


# Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    message = None
    color = ""
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        user = db.execute(
            text("SELECT * FROM users WHERE username = :username AND password = :password"),
            {"username": username, "password": password}
        ).fetchone()

        if user:
            session["user_id"] = user.id
            return redirect(url_for("search"))
        else:
            message = "Invalid username or password"
            color = "red"

    return render_template("login.html", message=message, color=color)

@app.route("/search", methods=["GET", "POST"])
def search():
    if "user_id" not in session:
        return redirect(url_for("login"))

    results = []
    searched = False

    if request.method == "POST":
        searched = True
        search_query = request.form.get("query")
        results = db.execute(text("""
            SELECT * FROM book_table
            WHERE isbn ILIKE :q
            OR title ILIKE :q
            OR author ILIKE :q
        """), {"q": f"%{search_query}%"}).fetchall()

    return render_template("search.html", results=results, searched=searched)


@app.route("/logout")
def logout():
    session.clear()   # removes user_id and everything in session
    return redirect(url_for("index"))  # go back to home page

@app.route("/book/<isbn>", methods=["GET", "POST"])
def book_page(isbn):
    isbn = isbn.strip()
    if "user_id" not in session:
        return redirect(url_for("index"))

    book = db.execute(
        text("SELECT * FROM book_table WHERE isbn = :isbn"),
        {"isbn": isbn}
    ).fetchone()

    if not book:
        return "Book not found!", 404
    
    # reviews
    if request.method == "POST":
        rating = request.form.get("rating")
        review_text = request.form.get("review_text")
        
        exists = db.execute(text("SELECT id FROM reviews WHERE user_id = :u AND isbn = :i"),
                           {"u": session["user_id"], "i": isbn}).fetchone()
        if not exists:
            db.execute(text("INSERT INTO reviews (user_id, isbn, rating, review_text) VALUES (:u, :i, :r, :t)"),
                       {"u": session["user_id"], "i": isbn, "r": rating, "t": review_text})
            db.commit()
        return redirect(url_for('book_page', isbn=isbn))
    
    all_reviews = db.execute(text("""
        SELECT u.username, r.rating, r.review_text, r.created_at 
        FROM reviews r JOIN users u ON r.user_id = u.id 
        WHERE r.isbn = :i ORDER BY r.created_at DESC"""), {"i": isbn}).fetchall()
    
    # Check if the logged-in user has already reviewed
    user_review = db.execute(text("SELECT id FROM reviews WHERE user_id = :u AND isbn = :i"),
                            {"u": session["user_id"], "i": isbn}).fetchone()
    
    # Get internal stats (average of YOUR users' ratings)
    stats = db.execute(text("SELECT COUNT(id) as count, ROUND(AVG(rating), 1) as average FROM reviews WHERE isbn = :i"),
                      {"i": isbn}).fetchone()

    return render_template("book.html", 
                           book=book,
                           reviews=all_reviews, 
                           has_reviewed=bool(user_review), 
                           stats=stats)

