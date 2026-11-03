
import sqlite3
import hashlib
import secrets
import re

# Database connection
def get_connection():
    return sqlite3.connect("users.db")


# Create users table
def create_table():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            salt TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# Password hashing
def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        600000
    ).hex()


# Register new user
def register_user(name, email, password):

    name = name.strip()
    email = email.strip().lower()

    if len(name) < 2:
        return False, "Enter a valid name."

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return False, "Enter a valid email."

    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    salt = secrets.token_bytes(16)
    hashed_password = hash_password(password, salt)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (name, email, password, salt)
            VALUES (?, ?, ?, ?)
        """, (name, email, hashed_password, salt.hex()))

        conn.commit()
        return True, "Registration successful!"

    except sqlite3.IntegrityError:
        return False, "Email already registered."

    finally:
        conn.close()


# Login existing user
def login_user(email, password):

    email = email.strip().lower()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    )

    user = cursor.fetchone()
    conn.close()

    if user is None:
        return None

    salt = bytes.fromhex(user[4])
    entered_password = hash_password(password, salt)

    if entered_password == user[3]:
        return {
            "id": user[0],
            "name": user[1],
            "email": user[2]
        }

    return None
