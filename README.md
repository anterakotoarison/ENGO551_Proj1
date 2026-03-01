# Project 1

ENGO 551 - Adv. Topics on Geospatial Technologies

**Project Owner**: Antenaina Rakotoarison

**Date Submitted**: February 14 2026


### Description:
A book review website created using Flask, Python, and SQL. The user will be able to create an account, login, logout, and search a book based on its title, isbn, and author. After a search query, the user will be able to see more info about the book by clicking on its title link. 

### Files:

#### HTML files:
- index.html: the home page which includes a header, a login button, and a sign up link
- login.html: login page with two boxes to input username and password, error message will show if wrong info, exit button to go to back to home, leads to search page if login is successful
- signup.html: signup page with boxes to input username and password, error message will show if username already exists, exit button to go back to home, and leads to search page if account creation is successful
- search.html: page to search book with a box that takes title, isbn, or author, will show results even with partial input, will show error message if no matching results found. results is an unordered list of books with title and author. title is a link to the book page.
- book.html: page that shows more info about the book including title, author, isbn, year, and generic book cover image

#### Static files:
- styles.css: css stylesheet for all the html pages
- placeholder-book.jpg: generic image for book page

#### py files:
- application.py: runs the website
- import.py: separate program to import the books csv into postgresql

## New Features from Lab 2
- Review feature:
    - user is able to write **ONE** review for each book
    - a display of all reviews written is shown on the book page
    - the average rating and the number of "local" reviews are shown
- Google Book API:
    - use google books to get cover image
    - use google books to get review info and other extra ones 
- Gemini API
    - use gemini to generate summary of book


#### Screencast link
**Lab 1** https://youtu.be/qwuWExM36Pc
**Lab 2** https://youtu.be/V26OpqsWmwE

