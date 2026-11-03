
import sqlite3
import json

DB_NAME = "users.db"


# Create review history table
def create_history_table():

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            language TEXT,
            code TEXT,
            review_result TEXT,
            complexity_result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# Save code review
def save_review(user_id, language, code, result, complexity):

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO review_history
        (user_id, language, code, review_result, complexity_result)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        language,
        code,
        json.dumps(result),
        json.dumps(complexity)
    ))

    conn.commit()
    conn.close()


# Get user's previous reviews
def get_user_history(user_id):

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM review_history
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,))

    history = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return history
