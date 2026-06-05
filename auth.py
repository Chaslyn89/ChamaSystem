from dotenv import load_dotenv
load_dotenv()

import os
import hashlib
import secrets
from datetime import datetime, timedelta

# Simple password hashing
def hash_password(password):
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((password + salt).encode())
    return f"{salt}:{hash_obj.hexdigest()}"

def verify_password(password, stored_hash):
    salt, hash_value = stored_hash.split(':')
    hash_obj = hashlib.sha256((password + salt).encode())
    return hash_obj.hexdigest() == hash_value

def get_user_by_username(username):
    from database import get_db, return_db
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password_hash, email, role FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        if user:
            return {
                'id': user[0],
                'username': user[1],
                'password_hash': user[2],
                'email': user[3],
                'role': user[4] if len(user) > 4 else 'member'
            }
        return None
    finally:
        return_db(conn)

def get_user_by_phone(phone):
    from database import get_db, return_db
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, phone, email FROM members WHERE phone = %s AND status = %s', (phone, 'active'))
        member = cursor.fetchone()
        if member:
            return {
                'id': member[0],
                'name': member[1],
                'phone': member[2],
                'email': member[3]
            }
        return None
    finally:
        return_db(conn)

def create_member_user(username, password, email, phone, full_name):
    from database import get_db, return_db
    from database import add_member
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Check if user already exists
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            return False, "Username already exists"
        
        # Check if member already exists in members table by phone
        cursor.execute('SELECT id FROM members WHERE phone = %s', (phone,))
        existing_member = cursor.fetchone()
        
        if existing_member:
            member_id = existing_member[0]
        else:
            # Add to members table
            member_id = add_member(full_name, phone, email)
        
        # Create user account
        password_hash = hash_password(password)
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, role, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            RETURNING id
        ''', (username, password_hash, email, 'member'))
        user_id = cursor.fetchone()[0]
        
        conn.commit()
        return True, user_id
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        return_db(conn)

def create_user(username, password, email, role='treasurer'):
    from database import get_db, return_db
    conn = get_db()
    try:
        cursor = conn.cursor()
        password_hash = hash_password(password)
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, role, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        ''', (username, password_hash, email, role))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating user: {e}")
        return False
    finally:
        return_db(conn)

def update_user_password(username, new_password):
    from database import get_db, return_db
    conn = get_db()
    try:
        cursor = conn.cursor()
        password_hash = hash_password(new_password)
        cursor.execute('UPDATE users SET password_hash = %s, updated_at = NOW() WHERE username = %s',
                      (password_hash, username))
        conn.commit()
        return True
    finally:
        return_db(conn)

def get_member_id_by_username(username):
    from database import get_db, return_db
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM members WHERE phone = %s', (username,))
        result = cursor.fetchone()
        if result:
            return result[0]
        return None
    finally:
        return_db(conn)