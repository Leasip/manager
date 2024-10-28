from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from flask_socketio import SocketIO
import sqlite3
import hashlib
import os
from werkzeug.utils import secure_filename
import time
import random
import uuid

app = Flask(__name__)
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'  # Use the saved secret key
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
socketio = SocketIO(app)

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def init_db():
    conn = sqlite3.connect('casino_affiliate.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS players (
                        id INTEGER PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password TEXT NOT NULL,
                        status TEXT NOT NULL,
                        affiliate_name TEXT)''')  # Added affiliate_name column
    cursor.execute('''CREATE TABLE IF NOT EXISTS casinos (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        affiliate_url TEXT,
                        image_url TEXT,
                        price_range_min INTEGER,
                        price_range_max INTEGER,
                        limit_players INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS player_casino (
                        player_id INTEGER,
                        casino_id INTEGER,
                        status TEXT,
                        assigned_price INTEGER,
                        screenshot TEXT,
                        FOREIGN KEY (player_id) REFERENCES players(id),
                        FOREIGN KEY (casino_id) REFERENCES casinos(id),
                        UNIQUE (player_id, casino_id))''')
    conn.commit()
    conn.close()

def get_db_connection():
    retries = 5
    for i in range(retries):
        try:
            conn = sqlite3.connect('casino_affiliate.db', timeout=10)
            return conn
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and i < retries - 1:
                time.sleep(1)
            else:
                raise

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        if username == 'admin' and password == 'adminpassword':
            session['user_type'] = 'admin'
            return redirect(url_for('admin_dashboard'))
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM players WHERE username = ? AND password = ?', (username, hashed_password))
            player = cursor.fetchone()
            conn.close()
            
            if player:
                session['user_type'] = 'player'
                session['player_id'] = player[0]
                return redirect(url_for('player_dashboard', player_id=player[0]))

        error = "Invalid username or password"
    
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/reset_password', methods=['POST'])
def reset_password():
    if 'user_type' not in session or session['user_type'] != 'admin':
        return {"error": "Unauthorized"}, 403

    player_id = request.args.get('player_id')
    if not player_id:
        return {"error": "Player ID is required"}, 400

    new_password = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
    hashed_password = hashlib.sha256(new_password.encode()).hexdigest()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET password = ? WHERE id = ?', (hashed_password, player_id))
    conn.commit()
    conn.close()

    return {"success": True, "new_password": new_password}



@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    error = None
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Handle POST requests for adding, editing, deleting
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'add_player':
                username = request.form.get('username')
                password = request.form.get('password')
                affiliate_name = request.form.get('affiliate_name')  # New field for affiliate name
                hashed_password = hashlib.sha256(password.encode()).hexdigest()
                cursor.execute('INSERT INTO players (username, password, status, affiliate_name) VALUES (?, ?, ?, ?)', (username, hashed_password, 'active', affiliate_name))
                conn.commit()

            elif action == 'delete_player':
                player_id = request.form.get('player_id')
                cursor.execute('DELETE FROM players WHERE id = ?', (player_id,))
                conn.commit()
            
            elif action == 'edit_player':
                player_id = request.form.get('player_id')
                new_username = request.form.get('new_username')
                new_status = request.form.get('new_status')
                new_affiliate_name = request.form.get('new_affiliate_name')  # New field for affiliate name
                hashed_password = request.form.get('new_password')
                
                if player_id and new_username and new_status and new_affiliate_name:
                    if hashed_password:
                        hashed_password = hashlib.sha256(hashed_password.encode()).hexdigest()
                        cursor.execute('''
                            UPDATE players 
                            SET username = ?, password = ?, status = ?, affiliate_name = ? 
                            WHERE id = ?
                        ''', (new_username, hashed_password, new_status, new_affiliate_name, player_id))
                    else:
                        cursor.execute('''
                            UPDATE players 
                            SET username = ?, status = ?, affiliate_name = ? 
                            WHERE id = ?
                        ''', (new_username, new_status, new_affiliate_name, player_id))
                    conn.commit()
            
            elif action == 'add_casino':
                name = request.form.get('name')
                affiliate_url = request.form.get('affiliate_url')
                image_url = request.form.get('image_url')
                price_range_min = int(request.form.get('price_range_min'))
                price_range_max = int(request.form.get('price_range_max'))
                limit_players = int(request.form.get('limit_players'))
                cursor.execute('INSERT INTO casinos (name, affiliate_url, image_url, price_range_min, price_range_max, limit_players) VALUES (?, ?, ?, ?, ?, ?)', (name, affiliate_url, image_url, price_range_min, price_range_max, limit_players))
                conn.commit()
            
            elif action == 'edit_casino':
                casino_id = request.form.get('casino_id')
                new_name = request.form.get('new_name')
                new_affiliate_url = request.form.get('new_affiliate_url')
                new_image_url = request.form.get('new_image_url')
                new_price_range_min = int(request.form.get('new_price_range_min'))
                new_price_range_max = int(request.form.get('new_price_range_max'))
                new_limit_players = int(request.form.get('new_limit_players'))
                cursor.execute('UPDATE casinos SET name = ?, affiliate_url = ?, image_url = ?, price_range_min = ?, price_range_max = ?, limit_players = ? WHERE id = ?', (new_name, new_affiliate_url, new_image_url, new_price_range_min, new_price_range_max, new_limit_players, casino_id))
                conn.commit()
            
            elif action == 'delete_casino':
                casino_id = request.form.get('casino_id')
                cursor.execute('DELETE FROM casinos WHERE id = ?', (casino_id,))
                conn.commit()
            
            elif action == 'confirm_payment':
                player_id = request.form.get('player_id')
                casino_id = request.form.get('casino_id')
                cursor.execute('UPDATE player_casino SET status = ? WHERE player_id = ? AND casino_id = ?', ('pending_deposit', player_id, casino_id))
                conn.commit()
            
            elif action == 'approve_screenshot':
                player_id = request.form.get('player_id')
                casino_id = request.form.get('casino_id')
                cursor.execute('UPDATE player_casino SET status = ? WHERE player_id = ? AND casino_id = ?', ('done', player_id, casino_id))
                conn.commit()
                socketio.emit('update_dashboard')
            
            socketio.emit('update_dashboard')
        
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                error = "Error: Username already exists."
    
    # Handle GET requests for searching and fetching data
    search_query = request.args.get('search_query', '')
    affiliate_filter = request.args.get('affiliate_filter', '')

    if search_query:
        cursor.execute('SELECT * FROM players WHERE username LIKE ?', ('%' + search_query + '%',))
    elif affiliate_filter:
        cursor.execute('SELECT * FROM players WHERE affiliate_name LIKE ?', ('%' + affiliate_filter + '%',))
    else:
        cursor.execute('SELECT * FROM players')
    
    players = cursor.fetchall()
    
    # Fetch pending approvals, casinos, and player-casino relations
    cursor.execute('''SELECT pc.player_id, pc.casino_id, pc.status, pc.screenshot, 
                      pc.assigned_price, p.username, c.name
                      FROM player_casino pc
                      JOIN players p ON pc.player_id = p.id
                      JOIN casinos c ON pc.casino_id = c.id
                      WHERE pc.status IN ('pending_payment', 'pending_deposit', 'pending_approval')''')
    pending_casinos = cursor.fetchall()
    
    cursor.execute('''
        SELECT c.id, c.name, c.affiliate_url, c.image_url, c.price_range_min, c.price_range_max, c.limit_players,
               (SELECT COUNT(*) FROM player_casino pc WHERE pc.casino_id = c.id AND pc.status != 'done') AS active_players
        FROM casinos c
    ''')
    casinos = cursor.fetchall()
    
    cursor.execute('''
        SELECT p.id, p.username, c.id, c.name, pc.status, pc.assigned_price
        FROM players p
        JOIN player_casino pc ON p.id = pc.player_id
        JOIN casinos c ON pc.casino_id = c.id
        WHERE pc.status != 'done'
    ''')
    player_casinos = cursor.fetchall()
    
    conn.close()
    return render_template('admin_dashboard.html', players=players, casinos=casinos, pending_casinos=pending_casinos, player_casinos=player_casinos, search_query=search_query, affiliate_filter=affiliate_filter, error=error)

@app.route('/api/players', methods=['GET'])
def get_players():
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))

    offset = int(request.args.get('offset', 0))
    limit = 5
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM players LIMIT ? OFFSET ?', (limit, offset))
    players = cursor.fetchall()

    conn.close()
    
    return {"players": players}



@app.route('/player/<int:player_id>', methods=['GET', 'POST'])
def player_dashboard(player_id):
    if 'user_type' not in session or session['user_type'] != 'player':
        return redirect(url_for('login'))
    if session['player_id'] != player_id:
        return "Unauthorized access"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch player's username
    cursor.execute('SELECT username FROM players WHERE id = ?', (player_id,))
    player = cursor.fetchone()
    if not player:
        return "Player not found"
    username = player[0]

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'activate_casino':
            casino_id = request.form.get('casino_id')
            cursor.execute('SELECT price_range_min, price_range_max, limit_players FROM casinos WHERE id = ?', (casino_id,))
            casino = cursor.fetchone()
            
            # Calculate the price with a step of 5 between min and max
            min_price = casino[0]
            max_price = casino[1]
            possible_prices = list(range(min_price, max_price + 1, 5))
            price = random.choice(possible_prices)  # <-- Price is calculated here with a step of 5
            
            cursor.execute('SELECT * FROM player_casino WHERE player_id = ? AND casino_id = ?', (player_id, casino_id))
            existing_entry = cursor.fetchone()
            if not existing_entry:
                cursor.execute('SELECT COUNT(*) FROM player_casino WHERE casino_id = ? AND status != ?', (casino_id, 'done'))
                active_players = cursor.fetchone()[0]
                if active_players < casino[2]:
                    cursor.execute('INSERT INTO player_casino (player_id, casino_id, status, assigned_price) VALUES (?, ?, ?, ?)', (player_id, casino_id, 'pending_payment', price))
                    conn.commit()
                    socketio.emit('update_dashboard')
        elif action == 'upload_screenshot':
            casino_id = request.form.get('casino_id')
            if 'screenshot' in request.files:
                screenshot = request.files['screenshot']
                if screenshot.filename != '':
                    filename = secure_filename(screenshot.filename)
                    file_extension = filename.rsplit('.', 1)[1].lower()
                    unique_filename = f"{uuid.uuid4()}.{file_extension}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    screenshot.save(file_path)
                    cursor.execute('UPDATE player_casino SET status = ?, screenshot = ? WHERE player_id = ? AND casino_id = ?', ('pending_approval', unique_filename, player_id, casino_id))
                    conn.commit()
                    socketio.emit('update_dashboard')
        elif action == 'cancel_casino':
            casino_id = request.form.get('casino_id')
            cursor.execute('DELETE FROM player_casino WHERE player_id = ? AND casino_id = ?', (player_id, casino_id))
            conn.commit()
            socketio.emit('update_dashboard')
    
    cursor.execute('''SELECT c.id, c.name, c.affiliate_url, c.image_url, c.price_range_min, c.price_range_max 
                      FROM casinos c
                      WHERE c.id NOT IN (SELECT casino_id FROM player_casino WHERE player_id = ? AND status = 'done')
                      AND (SELECT COUNT(*) FROM player_casino WHERE casino_id = c.id AND status != 'done') < c.limit_players''', (player_id,))
    available_casinos = cursor.fetchall()
    
    cursor.execute('''SELECT pc.casino_id, c.name, pc.status, c.affiliate_url, pc.assigned_price, pc.screenshot
                      FROM player_casino pc 
                      JOIN casinos c ON pc.casino_id = c.id 
                      WHERE pc.player_id = ? AND pc.status != 'done' ''', (player_id,))
    active_casinos = cursor.fetchall()

    cursor.execute('''SELECT pc.casino_id, c.name, pc.status, c.affiliate_url, pc.assigned_price
                      FROM player_casino pc 
                      JOIN casinos c ON pc.casino_id = c.id 
                      WHERE pc.player_id = ? AND pc.status = 'done' ''', (player_id,))
    casino_history = cursor.fetchall()
    
    conn.close()
    return render_template('player_dashboard.html', available_casinos=available_casinos, active_casinos=active_casinos, casino_history=casino_history, player_id=player_id, username=username)
@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/player_info/<int:player_id>', methods=['GET', 'POST'])
def player_info(player_id):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'confirm_payment':
                casino_id = request.form.get('casino_id')
                cursor.execute('UPDATE player_casino SET status = ? WHERE player_id = ? AND casino_id = ?', ('pending_deposit', player_id, casino_id))
                conn.commit()

            elif action == 'approve_screenshot':
                casino_id = request.form.get('casino_id')
                cursor.execute('UPDATE player_casino SET status = ? WHERE player_id = ? AND casino_id = ?', ('done', player_id, casino_id))
                conn.commit()
                socketio.emit('update_dashboard')

            socketio.emit('update_dashboard')
        
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if "UNIQUE constraint failed" in str(e):
                return "Error: Action could not be performed."
    
    # Fetch player details
    cursor.execute('SELECT * FROM players WHERE id = ?', (player_id,))
    player = cursor.fetchone()
    
    # Fetch player casino history
    cursor.execute('''SELECT pc.casino_id, c.name, pc.status, pc.screenshot, pc.assigned_price
                      FROM player_casino pc 
                      JOIN casinos c ON pc.casino_id = c.id 
                      WHERE pc.player_id = ?''', (player_id,))
    player_casinos = cursor.fetchall()
    
    # Fetch pending approvals for the player
    cursor.execute('''SELECT pc.casino_id, c.name, pc.status, pc.screenshot, pc.assigned_price
                      FROM player_casino pc 
                      JOIN casinos c ON pc.casino_id = c.id 
                      WHERE pc.player_id = ? AND pc.status IN ('pending_payment', 'pending_deposit', 'pending_approval')''', (player_id,))
    pending_approvals = cursor.fetchall()
    
    conn.close()
    return render_template('player_info.html', player=player, player_casinos=player_casinos, pending_approvals=pending_approvals)

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='127.0.0.1', port=5001, debug=True)
