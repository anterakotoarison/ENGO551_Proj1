import os

from flask import Flask, session, render_template, request, redirect, url_for, jsonify
from flask_session import Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from dotenv import load_dotenv
import requests
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
app = Flask(__name__)

# Check for environment variable for psql
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# Creating user and book tables
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

# Opening homepage
@app.route("/")
def index():
    return render_template("index.html")

# Signup route -- signup form page
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        # check if created username already exists in the database
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

            # create session with user
            session['user_id'] = user.id

            return redirect(url_for("search"))

    return render_template("signup.html")


# Login route -- login form page
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

# Search route -- search page
@app.route("/search", methods=["GET", "POST"])
def search():
    # user has to be logged in to search
    if "user_id" not in session:
        return redirect(url_for("login"))

    results = []
    searched = False

    # query for the book based on isbn, partial titles and author
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

# Log out route -- logs user out
@app.route("/logout")
def logout():
    session.clear()   # removes user_id and everything in session
    return redirect(url_for("index"))  # go back to home page

# GET API Json
@app.route("/api/<isbn>", methods=["GET"])
def book_api(isbn):

    # query for book using isb
    isbn_clean = isbn.strip()
    book = db.execute(
        text("SELECT * FROM book_table WHERE TRIM(isbn) = :isbn"),
        {"isbn": isbn_clean}
    ).fetchone()

    if not book:
        return jsonify({"error": "ISBN not found in database"}), 404

    # query for reviews from database
    stats = db.execute(text("""
        SELECT COUNT(id) as count, AVG(rating) as average 
        FROM reviews WHERE TRIM(isbn) = :i
    """), {"i": isbn_clean}).fetchone()

    # init vars for google books api info
    google_desc = None
    pub_date = None
    isbn_10 = None
    isbn_13 = isbn_clean # Default to the one provided
    
    # get extra info from google books api
    try:
        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn_clean}")
        if res.status_code == 200:
            data = res.json()
            if "items" in data:
                info = data["items"][0]["volumeInfo"]
                google_desc = info.get("description")
                pub_date = info.get("publishedDate")
                for identifier in info.get("industryIdentifiers", []):
                    if identifier["type"] == "ISBN_10":
                        isbn_10 = identifier["identifier"]
                    if identifier["type"] == "ISBN_13":
                        isbn_13 = identifier["identifier"]
    except:
        pass
    
    # get ai for summarized description
    summarized_desc = None
    try:
        model_to_use = "gemini-3-flash-preview" 
        
        prompt = f"Summarize the book '{book.title}' by {book.author} in 2-3 short sentences."
        response = client.models.generate_content(
            model=model_to_use, 
            contents=prompt
        )
        
        # Use .text to get the string
        summarized_desc = response.text.strip()
        
    except Exception as e:
        print(f"Gemini API error: {e}")
        summarized_desc = None

    # 5. Return the JSON exactly as required
    return jsonify({
        "title": book.title,
        "author": book.author,
        "publishedDate": pub_date,
        "ISBN_10": isbn_10,
        "ISBN_13": isbn_13,
        "reviewCount": int(stats.count) if stats.count else 0,
        "averageRating": float(round(stats.average, 1)) if stats.average else None,
        "description": google_desc,
        "summarizedDescription": summarized_desc
    })

@app.route("/book/<isbn>", methods=["GET", "POST"])
def book_page(isbn):
    # use clean isbn
    isbn = isbn.strip()
    
    # if user not logged in, cannot be in book page
    if "user_id" not in session:
        return redirect(url_for("index"))

    # get book from database
    book = db.execute(
        text("SELECT * FROM book_table WHERE TRIM(isbn) = :isbn"),
        {"isbn": isbn}
    ).fetchone()

    if not book:
        return "Book not found!", 404

    # get more info from google api
    google_data = None
    try:
        clean_isbn = isbn.strip().replace("-", "") # keep stripping isbn just in case
        
        params = {
            "q": f"isbn:{clean_isbn}",
            "key": os.getenv("GOOGLE_BOOKS_KEY") # use api key
        }
        
        # request api
        res = requests.get("https://www.googleapis.com/books/v1/volumes", params=params, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            # if isbn doesn't work, try title and author
            if data.get("totalItems", 0) == 0:
                params["q"] = f"{book.title} {book.author}"
                res = requests.get("https://www.googleapis.com/books/v1/volumes", params=params, timeout=5)
                data = res.json()
            # get all items
            if "items" in data:
                google_data = data["items"][0].get("volumeInfo")
                
                # get thumbnail
                if google_data and "imageLinks" in google_data:
                    img_url = google_data["imageLinks"].get("thumbnail")
                    if img_url:
                        google_data["imageLinks"]["thumbnail"] = img_url.replace("http://", "https://")
                
                print(f"DEBUG: SUCCESS! Found data for {book.title}")

    except Exception as e:
        print(f"API Error: {e}")
    
    ai_summary = None
    try:
        prompt = f"Provide a concise, summary of the book '{book.title}' by {book.author} in less than 50 words. Focus on the main plot and themes."
        
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt
        )
        ai_summary = response.text
    except Exception as e:
        print(f"Gemini API Error: {e}")
        ai_summary = "AI summary temporarily unavailable."

    # Reviews stuff
    if request.method == "POST":
        rating = request.form.get("rating")
        review_text = request.form.get("review_text")
        
        # check if user already reviewed this book
        exists = db.execute(text("SELECT id FROM reviews WHERE user_id = :u AND TRIM(isbn) = :i"),
                           {"u": session["user_id"], "i": isbn}).fetchone()
        
        if not exists:
            db.execute(text("INSERT INTO reviews (user_id, isbn, rating, review_text) VALUES (:u, :i, :r, :t)"),
                       {"u": session["user_id"], "i": isbn, "r": rating, "t": review_text})
            db.commit()
        
        
        return redirect(url_for('book_page', isbn=isbn))
    
    # get all reviews to be displayed
    all_reviews = db.execute(text("""
        SELECT u.username, r.rating, r.review_text, r.created_at 
        FROM reviews r JOIN users u ON r.user_id = u.id 
        WHERE TRIM(r.isbn) = :i ORDER BY r.created_at DESC"""), {"i": isbn}).fetchall()
    
    user_review = db.execute(text("SELECT id FROM reviews WHERE user_id = :u AND TRIM(isbn) = :i"),
                            {"u": session["user_id"], "i": isbn}).fetchone()
    # get stats
    stats = db.execute(text("SELECT COUNT(id) as count, ROUND(AVG(rating), 1) as average FROM reviews WHERE TRIM(isbn) = :i"),
                      {"i": isbn}).fetchone()

    return render_template("book.html", 
                           book=book,
                           reviews=all_reviews, 
                           has_reviewed=bool(user_review), 
                           stats=stats,
                           google_data=google_data,
                           ai_summary=ai_summary)
