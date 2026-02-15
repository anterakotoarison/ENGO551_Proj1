import psycopg2
import pandas as pd

# creating connections
conn = psycopg2.connect(
    dbname="proj1db",
    user="antenainarakotoarison",
    password="yourpassword",
    host="localhost"
)

# creating cursor
cur = conn.cursor()

# reading csv

df = pd.read_csv("books.csv")

# queries
create_table_query = """
CREATE TABLE IF NOT EXISTS book_table (
    isbn CHAR(13) PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    year SMALLINT
);
"""
insert_query = """
INSERT INTO book_table (isbn, title, author, year)
VALUES (%s, %s, %s, %s)
"""

cur.execute(create_table_query)
conn.commit()
print("Table created successfully.")


for book in df.itertuples(index=False):
    isbn, title, author, year = book
    book_data = (isbn, title, author, year)
    cur.execute(insert_query, book_data)
    conn.commit()


print("Book inserted successfully.")


cur.close()
conn.close()
