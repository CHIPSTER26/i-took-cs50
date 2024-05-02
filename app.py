import os
import time
import yfinance as yf
from cs50 import SQL
from flask import Flask, flash, render_template, request, session, redirect, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///csh.db")


@app.context_processor
def utility_functions():
    return dict(usd=usd)


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

@app.route('/')
def index():
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)

@app.route("/dashboard")
@login_required
def dashboard():
    """Show portfolio of stocks"""
    user = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]['username']
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash']
    # Query for all shares owned
    summary = db.execute("SELECT * FROM ledgers WHERE user_id = ?", session["user_id"])
    user_summary = []
    total_valueshares = 0
    for item in summary:
        current_price = lookup(item['symbol'])
        if current_price is None:
            return apology("meow...no symbol index or server down", 400)
        item['price'] = current_price['price']
        item['total_shares'] = item['qty_shares']
        item['total_value'] = round(item['qty_shares'] * item['price'], 2)
        total_valueshares = round((total_valueshares + item['total_value']), 2)
        user_summary.append(item)
    total_equity = round((total_valueshares + cash), 2)
    try:
        return render_template("dashboard.html", cash=cash, user=user, user_summary=user_summary, total_valueshares=total_valueshares, total_equity=total_equity)
    except:
        return apology("meow...strange things happening", 400)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Ensure share name/symbol not blank
        if not request.form.get('symbol'):
            return apology("meow...type symbol", 400)
        # Ensure share name/symbol is available
        symbol = request.form.get('symbol').upper()
        symbolchecked = lookup(symbol)
        if symbolchecked is None:
            return apology("meow... No symbol in buy", 400)
        # Ensure shares qty not blank
        if not request.form.get('shares'):
            return apology("please provide qty of shares", 400)
        # Ensure input is positive numbers
        shares = request.form.get('shares')
        if not shares.isdigit() or int(shares) <= 0:
            return apology("please provide a positive number of shares", 400)
        # change shares to integer for calculating with stock price
        shares = int(shares)
        # look up a stock’s current price
        current_shareprice = symbolchecked['price']
        # look up a bought symbol
        bought_symbol = symbolchecked['symbol']
        # total cash required to purchase
        total_purchase = float(current_shareprice * shares)
        # check money available to purchase
        cash = (db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash'])
        if cash < total_purchase:
            return apology("meow...not enough money", 400)
        # if found no money
        if cash <= 0:
            return apology("meow...you need more cash", 400)
        # calculate
        try:
            cash = round((cash - total_purchase), 2)
        except:
            return apology("Failed to purchase, something went wrong", 400)
        # when transaction approved update cash available and handle fail
        try:
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])
        except:
            return apology("Failed to update cash", 400)
        # update transaction for buy table
        try:
            db.execute("INSERT INTO buy (user_id, symbol, bought_price, qty_shares, total_value) VALUES (?, ?, ?, ?, ?)",
                       session["user_id"], bought_symbol, current_shareprice, shares, total_purchase)
        except:
            return apology("Failed to purchase", 400)
        # update ledgers
        symbol = request.form.get('symbol').upper()
        symbol_inform = lookup(symbol)
        if symbol_inform['symbol'] is None:
            return apology("meow... No symbol in buy the market", 403)
        symbol_inledgers = db.execute("SELECT * FROM ledgers WHERE symbol = ?", symbol)
        if len(symbol_inledgers) != 0:
            try:
                result = db.execute(
                    "SELECT qty_shares, total_value, avg_price FROM ledgers WHERE symbol = ?", symbol)
                qty_shares = result[0]['qty_shares'] + shares
                total_value = result[0]['total_value'] + total_purchase
                try:
                    avg_price = round((total_value / qty_shares), 2)
                except ZeroDivisionError:
                    return apology("oops, something wrong with me", 400)
                db.execute("UPDATE ledgers SET qty_shares = ?, total_value = ?, avg_price = ? WHERE user_id = ? AND symbol = ?",
                           qty_shares, total_value, avg_price, session["user_id"], symbol)
            except RuntimeError:
                return apology("Failed to update ledgers", 400)
        else:
            try:
                avg_price = current_shareprice
                db.execute("INSERT INTO ledgers (user_id, symbol, qty_shares, total_value, avg_price) VALUES (?, ?, ?, ?, ?)",
                           session["user_id"], bought_symbol, shares, total_purchase, avg_price)
            except RuntimeError:
                return apology("Failed to update your first symbol in ledgers", 400)
        # after calculation move back to home screen
        return redirect("/dashboard")
    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]['username']
    activities = db.execute(
        "SELECT timestamp, symbol, bought_price AS price , qty_shares, total_value, 'BUY' as type FROM buy WHERE buy.user_id = ? UNION ALL SELECT timestamp, symbol, sale_price AS price, qty_shares, total_value, 'SALE' as type FROM sale WHERE sale.user_id = ? ORDER BY timestamp DESC", session["user_id"], session["user_id"])
    return render_template("history.html", user=user, activities=activities)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Record everytime user login into visitor history
        db.execute("INSERT INTO visitor_login (username) VALUES (?)",
                   request.form.get("username"))

        # Redirect user to home page
        return redirect("/about")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/dashboard")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Ensure share name/symbol not blank
        if not request.form.get("symbol"):
            return apology("please provide share symbol", 400)
        symbol = request.form.get("symbol").upper()
        symbolchecked = lookup(symbol)
        if symbolchecked is None:
            return apology("meow...no symbol found in the market", 400)
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash']
        return render_template("quoted.html", cash=cash, symbolchecked=symbolchecked)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure username typed
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure password typed
        if not request.form.get("password"):
            return apology("must provide password", 400)
        # Ensure confirmation password typed
        if not request.form.get("confirmation"):
            return apology("must re-type password", 400)
        # Ensure re-type password and password is the same char
        if not request.form.get("confirmation") == request.form.get("password"):
            return apology("re-type password not the same with password", 400)
        # Ensure non duplicate username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(rows) != 0:
            return apology("please choose different username", 400)
        # Insert new username to database
        hashed_password = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash, company) VALUES (?, ?, ?)",
                   request.form.get("username"), hashed_password, request.form.get("company"))
        # Redirect user to home page
        return redirect("/login")
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # Ensure share name/symbol not blank
        if not request.form.get("symbol"):
            return apology("meow...type symbol", 400)
        # Ensure shares qty not blank
        if not request.form.get("shares"):
            return apology("please provide qty of shares", 400)
        # Ensure input is positive numbers
        shares = request.form.get("shares")
        if not shares.isdigit() or int(shares) <= 0:
            return apology("please provide a positive number of shares", 400)
        # change shares to int for calculating with stock price
        shares = int(shares)
        # look up a bought symbol
        symbol = request.form.get("symbol").upper()
        # look up a stock’s current price
        stock_info = lookup(symbol)
        if stock_info is None:
            return apology("Invalid symbol", 400)
        current_shareprice = stock_info['price']
        # total cash required to purchase
        total_sold = float(current_shareprice * shares)
        # update ledgers
        symbol_inledgers = db.execute(
            "SELECT * FROM ledgers WHERE symbol = ? AND user_id = ?", symbol, session["user_id"])
        if len(symbol_inledgers) != 0:
            try:
                result = db.execute(
                    "SELECT qty_shares, total_value, avg_price FROM ledgers WHERE symbol = ? AND user_id = ?", symbol, session["user_id"])
                if not result:
                    return apology("oops, something wrong with database on ledgers", 400)
                if result[0]['qty_shares'] < shares:
                    return apology("oops, you don't have enough shares to sell", 400)
                if result[0]['qty_shares'] > shares:
                    qty_shares = result[0]['qty_shares'] - shares
                    total_value = result[0]['total_value'] - total_sold
                    try:
                        avg_price = round((total_value / qty_shares), 2)
                    except ZeroDivisionError:
                        return apology("oops, something wrong with me", 400)
                    db.execute("UPDATE ledgers SET qty_shares = ?, total_value = ?, avg_price = ? WHERE user_id = ? AND symbol = ?",
                               qty_shares, total_value, avg_price, session["user_id"], symbol)
                elif result[0]['qty_shares'] == shares:
                    try:
                        db.execute("DELETE FROM ledgers WHERE symbol = ? AND user_id = ?",
                                   symbol, session["user_id"])
                    except RuntimeError:
                        return apology("oops, I can't delete the stocks???", 400)
            except RuntimeError:
                return apology("Failed to update ledgers", 400)
        else:
            return apology("It seems like you don't have the stocks in ledgers", 400)
        # calculate cash
        cash = (db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash'])
        try:
            cash = round((cash + total_sold), 2)
        except:
            return apology("Failed to calculate cash plus total sold stocks", 400)
        # when transaction approved update cash available and handle fail
        try:
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])
        except:
            return apology("Failed to add cash with total sold stocks", 400)
        # update transaction for sale table
        try:
            db.execute("INSERT INTO sale (user_id, symbol, sale_price, qty_shares, total_value) VALUES (?, ?, ?, ?, ?)",
                       session["user_id"], symbol, current_shareprice, shares, total_sold)
        except:
            return apology("Failed to sell", 400)
        # after calculation move back to home screen
        return redirect("/dashboard")

    user = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]['username']
    cash = (db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash'])
    # Query for all shares owned
    summary = db.execute("SELECT * FROM ledgers WHERE user_id = ?", session["user_id"])
    user_summary = []
    total_valueshares = 0
    for item in summary:
        current_price = lookup(item['symbol'])
        if current_price is None:
            return apology("meow...no symbol at sell loop", 400)
        item['price'] = current_price['price']
        item['total_shares'] = item['qty_shares']
        item['total_value'] = round(item['qty_shares'] * item['price'], 2)
        total_valueshares = round((total_valueshares + item['total_value']), 2)
        user_summary.append(item)
    total_equity = round((total_valueshares + cash), 2)
    try:
        return render_template("sell.html", cash=cash, user=user, user_summary=user_summary, total_valueshares=total_valueshares, total_equity=total_equity)
    except RuntimeError:
        return apology("meow...strange things happening", 400)


@app.route("/fund", methods=["GET", "POST"])
@login_required
def fund():
    """add fund to user cash table"""
    if request.method == "POST":
        # Ensure fund form not blank
        if not request.form.get("fund"):
            return apology("please provide numbers", 400)
        # Ensure input is valid numbers
        try:
            fund = float(request.form.get("fund"))
        except ValueError:
            return apology("please provide a valid number of fund", 400)
        if fund <= 0:
            return apology("please provide a positive number of fund", 400)
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]['cash']
        cash += fund
        # update cash
        try:
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])
        except:
            return apology("Failed to add cash", 400)
        return redirect("/dashboard")
    return render_template("fund.html")


@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    return render_template("search.html")

@app.route("/message", methods=["GET", "POST"])
@login_required
def message():
    if request.method == "POST":
        message = request.form.get("message")
        try:
            db.execute("INSERT INTO message (user_id, message) VALUES (?, ?)", session["user_id"], message)
        except:
            return apology("Failed to record message", 400)
        return redirect("/message")
    else:
        user = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]['username']
        messages = db.execute("SELECT message, DATE(timestamp) as date, username, company FROM message JOIN users ON users.id = message.user_id ORDER BY timestamp DESC")
        return render_template("message.html", user=user, messages=messages)


@app.route("/visitor", methods=["GET"])
@login_required
def visitor():
    user = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]['username']
    visitors = db.execute("SELECT DISTINCT visitor_login.username, company, DATE(timestamp) as date FROM visitor_login JOIN users ON visitor_login.username = users.username ORDER BY timestamp DESC")
    return render_template("visitor.html", user=user, visitors=visitors)


@app.route("/about", methods=["GET"])
@login_required
def about():
    user = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]['username']
    return render_template("about.html", user=user)




@app.route("/note", methods=["GET", "POST"])
@login_required
def note():
    if request.method == "POST":
        note = request.form.get("note")
        if not note:
            return redirect("/note")

        # Insert note into database
        db.execute("INSERT INTO note (notes, user_id) VALUES(?, ?)", note, session["user_id"])
        return redirect("/note")

    else:
        # Query for all notes
        notes = db.execute("SELECT notes, DATE(timestamp) as date FROM note WHERE user_id = ?", session["user_id"])

        # Render notes page
        user = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]['username']
        return render_template("note.html", notes=notes, user=user)


@app.route("/delete", methods=["POST"])
@login_required
def delete():
    # Delete notes or rows
    id = request.form.get("id")
    if id:
        try:
            db.execute("DELETE FROM note WHERE id = ?", id)
        except RuntimeError:
            return apology("oops, I can't delete the note???", 400)
    return redirect("/note")
