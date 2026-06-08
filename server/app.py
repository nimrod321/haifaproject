from flask import Flask, request, jsonify, make_response
from flask_socketio import SocketIO, emit
import sqlite3
import bcrypt
import os
import time
import json
import random
import threading
from game_bots import create_bot

game_lock = threading.Lock()

import sys
sys.stdout = open('server_log.txt', 'a', encoding='utf-8')
sys.stderr = sys.stdout

app = Flask(__name__, static_folder='../client', static_url_path='')
app.secret_key = 'super-secret-key-123'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'games.db')

def get_db():
    # Adding a timeout for PythonAnywhere stability
    db = sqlite3.connect(DATABASE, timeout=20)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_type TEXT,
                player1 TEXT,
                player2 TEXT,
                state TEXT,
                logs TEXT
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS prison_games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                trial INTEGER,
                player1 TEXT,
                player2 TEXT,
                p1_choice TEXT,
                p2_choice TEXT,
                code TEXT,
                p1_points INTEGER,
                p2_points INTEGER,
                room_password TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            # Safe schema migrations for existing database
            try: db.execute('ALTER TABLE prison_games ADD COLUMN room_password TEXT')
            except: pass
            try: db.execute('ALTER TABLE prison_games ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP')
            except: pass
            try: db.execute('ALTER TABLE prison_games ADD COLUMN matrix_id TEXT')
            except: pass
            try: db.execute('ALTER TABLE prison_games ADD COLUMN trial INTEGER')
            except: pass
            try: db.execute('ALTER TABLE prison_games ADD COLUMN file_id TEXT')
            except: pass
            try: db.execute('ALTER TABLE users ADD COLUMN session_counter INTEGER DEFAULT 0')
            except: pass
            try: db.execute('ALTER TABLE users ADD COLUMN total_coins INTEGER DEFAULT 0')
            except: pass
            
            db.execute('''CREATE TABLE IF NOT EXISTS banned_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE
            )''')
            
            try: db.execute('ALTER TABLE prison_rooms ADD COLUMN description TEXT')
            except: pass

            db.execute('''CREATE TABLE IF NOT EXISTS past_input_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE,
                sessions_data TEXT
            )''')
            
            db.execute('''CREATE TABLE IF NOT EXISTS prison_rooms (
                password TEXT PRIMARY KEY,
                num_sessions INTEGER,
                allowed_bots TEXT,
                custom_sessions TEXT,
                description TEXT
            )''')
            
            db.execute('''CREATE TABLE IF NOT EXISTS island_plots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                plot_index INTEGER,
                item_type TEXT
            )''')
            
            db.execute('''CREATE TABLE IF NOT EXISTS user_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                item_type TEXT,
                quantity INTEGER
            )''')
            
            db.commit()
        finally:
            db.close()

init_db()


rooms = {}  # password -> {'waiting': [], 'active': [], 'settings': {'num_sessions': 10}}

# Default PrisonerDilemma sessions. Replace with Excel data import if needed.
prison_sessions = [
    {'AA1':19,'AA2':19,'AB1':2,'AB2':19,'BA1':19,'BA2':2,'BB1':2,'BB2':2},
    {'AA1':19,'AA2':19,'AB1':2,'AB2':19,'BA1':19,'BA2':2,'BB1':2,'BB2':2},
    {'AA1':19,'AA2':19,'AB1':1,'AB2':20,'BA1':20,'BA2':1,'BB1':2,'BB2':2},
    {'AA1':64,'AA2':5,'AB1':40,'AB2':40,'BA1':53,'BA2':53,'BB1':5,'BB2':64},
    {'AA1':60,'AA2':4,'AB1':28,'AB2':28,'BA1':45,'BA2':45,'BB1':4,'BB2':60},
    {'AA1':1,'AA2':68,'AB1':23,'AB2':23,'BA1':9,'BA2':9,'BB1':68,'BB2':1},
    {'AA1':14,'AA2':14,'AB1':70,'AB2':3,'BA1':3,'BA2':70,'BB1':32,'BB2':32},
    {'AA1':53,'AA2':53,'AB1':5,'AB2':64,'BA1':64,'BA2':5,'BB1':40,'BB2':40},
    {'AA1':41,'AA2':41,'AB1':69,'AB2':0,'BA1':0,'BA2':69,'BB1':55,'BB2':55},
    {'AA1':2,'AA2':68,'AB1':22,'AB2':22,'BA1':5,'BA2':5,'BB1':68,'BB2':2}
]

def get_prison_value(session, p1_row, p2_col):
    # p1 row/col are 'A' or 'B'. return (p1_points, p2_points)
    mapping = {
        ('A','A'): ('AA1','AA2'), ('A','B'): ('AB1','AB2'),
        ('B','A'): ('BA1','BA2'), ('B','B'): ('BB1','BB2')
    }
    key1,key2 = mapping[(p1_row,p2_col)]
    return int(session[key1]), int(session[key2])


def prison_matrix_for_player(session, player):
    # player == 'p1' or 'p2'; p2 sees swapped rows/columns and reversed pairs
    if player == 'p1':
        return {
            'AA1': int(session['AA1']), 'AA2': int(session['AA2']),
            'AB1': int(session['AB1']), 'AB2': int(session['AB2']),
            'BA1': int(session['BA1']), 'BA2': int(session['BA2']),
            'BB1': int(session['BB1']), 'BB2': int(session['BB2'])
        }
    return {
        'AA1': int(session['AA2']), 'AA2': int(session['AA1']),
        'AB1': int(session['BA2']), 'AB2': int(session['BA1']),
        'BA1': int(session['AB2']), 'BA2': int(session['AB1']),
        'BB1': int(session['BB2']), 'BB2': int(session['BB1'])
    }


@app.route('/prison/results', methods=['GET'])
def prison_results():
    db = get_db()
    rows = db.execute('SELECT * FROM prison_games ORDER BY id DESC LIMIT 100').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route('/prison/sessions', methods=['GET'])
def prison_sessions_api():
    return jsonify(prison_sessions)

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.get_json()
    password = data.get('password')
    num_sessions = data.get('num_sessions', 10)
    allowed_bots = data.get('allowed_bots', ['Random', 'CBot'])
    custom_sessions = data.get('sessions')
    description = data.get('description', '')
    filename = data.get('filename', '')
    
    if custom_sessions:
        cleaned_list = []
        for s in custom_sessions:
            c = {}
            for k, v in s.items():
                kw = str(k).upper().strip()
                try:
                    c[kw] = int(float(v)) if str(v).strip() != '' else 0
                except:
                    c[kw] = str(v).strip()
            for req in ['AA1','AA2','AB1','AB2','BA1','BA2','BB1','BB2']:
                if req not in c: c[req] = 0
            cleaned_list.append(c)
        custom_sessions = cleaned_list
    
    if not password:
        return jsonify({'error': 'Password required'}), 400
        
    db = None
    try:
        db = get_db()
        existing = db.execute('SELECT 1 FROM prison_rooms WHERE password = ?', (password,)).fetchone()
        if existing:
            return jsonify({'error': 'Room already exists'}), 400
            
        db.execute('''INSERT INTO prison_rooms (password, num_sessions, allowed_bots, custom_sessions, description)
                      VALUES (?, ?, ?, ?, ?)''', 
                   (password, num_sessions, json.dumps(allowed_bots), json.dumps(custom_sessions) if custom_sessions else None, description))
        
        if filename and custom_sessions:
            try:
                db.execute('INSERT OR IGNORE INTO past_input_files (filename, sessions_data) VALUES (?, ?)',
                           (filename, json.dumps(custom_sessions)))
            except: pass
        
        db.commit()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if db: db.close()

    return jsonify({'message': 'Room created'})

@app.route('/get_rooms', methods=['GET'])
def get_rooms():
    room_list = []
    db = None
    try:
        db = get_db()
        db_rooms = db.execute('SELECT password, description FROM prison_rooms').fetchall()
        for r in db_rooms:
            password = r['password']
            description = r['description']
            
            # Keep active match data for admin viewing if the global mem exists
            active_games_list = []
            if password in rooms:
                for game_id, game in rooms[password].get('active', {}).items():
                    active_games_list.append({
                        'game_id': game_id,
                        'players': game['players'],
                        'session': game.get('session', 0)
                    })
                    
            room_list.append({
                'password': password,
                'description': description,
                'active_games': len(active_games_list),
                'games': active_games_list
            })
    finally:
        if db: db.close()
        
    return jsonify(room_list)

@app.route('/get_past_files', methods=['GET'])
def get_past_files():
    db = None
    try:
        db = get_db()
        rows = db.execute('SELECT id, filename, sessions_data FROM past_input_files').fetchall()
        return jsonify([{'id': r['id'], 'filename': r['filename'], 'sessions_data': json.loads(r['sessions_data'])} for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if db: db.close()

@app.route('/get_room_logs', methods=['POST'])
def get_room_logs():
    data = request.get_json()
    password = data.get('password')
    if not password:
        return jsonify({'error': 'Password required'}), 400
    
    db = None
    try:
        db = get_db()
        cursor = db.execute('''SELECT * FROM prison_games WHERE room_password = ? ORDER BY id''', (password,))
        rows = cursor.fetchall()
        
        logs = []
        for r in rows:
            logs.append({
                'game_id': r['game_id'],
                'trial': r['trial'] if 'trial' in r.keys() else '',
                'player1': r['player1'],
                'player2': r['player2'],
                'p1_choice': r['p1_choice'],
                'p2_choice': r['p2_choice'],
                'code': r['code'],
                'p1_points': r['p1_points'],
                'p2_points': r['p2_points'],
                'session_number': r['file_id'] if 'file_id' in r.keys() else '',
                'matrix_id': r['matrix_id'] if 'matrix_id' in r.keys() else '',
                'timestamp': r['timestamp'] if 'timestamp' in r.keys() else ''
            })
    finally:
        if db: db.close()
        
    return jsonify({'password': password, 'logs': logs})

@app.route('/delete_room', methods=['POST'])
def delete_room():
    data = request.get_json()
    password = data.get('password')
    db = None
    try:
        db = get_db()
        res = db.execute('DELETE FROM prison_rooms WHERE password = ?', (password,))
        db.commit()
    finally:
        if db: db.close()
        
    # Free memory queue tracking
    if password in rooms:
        del rooms[password]
        
    return jsonify({'message': 'Room deleted'})

@app.route('/terminate_game', methods=['POST'])
def terminate_game():
    data = request.get_json()
    game_id = data.get('game_id')
    delete_logs = data.get('delete_logs', False)
    
    found = False
    for room in rooms.values():
        if game_id in room['active']:
            del room['active'][game_id]
            found = True
            break
            
    if delete_logs:
        db = None
        try:
            db = get_db()
            db.execute('DELETE FROM prison_games WHERE game_id = ?', (game_id,))
            db.commit()
        finally:
            if db: db.close()
        
    if found:
        return jsonify({'message': 'Game terminated'})
    return jsonify({'error': 'Game not found'}), 404

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if username == 'NIS':
        return jsonify({'error': 'Username not allowed'}), 400
    # Lower rounds to 4 to prevent heavy CPU throttling on PythonAnywhere 
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(4))
    db = None
    try:
        db = get_db()
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed))
        db.commit()
        return jsonify({'message': 'User created'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already exists'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if db: db.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    db = get_db()
    
    if username == 'NIS' and password == 'NIS5760':
        db.close()
        return jsonify({'message': 'Logged in', 'user': {'id': 0, 'username': 'NIS', 'role': 'admin'}})
        
    try:
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password']):
            db.close()
            return jsonify({'error': 'Invalid credentials'}), 401
        
        is_banned = db.execute('SELECT 1 FROM banned_users WHERE username = ?', (username,)).fetchone()
        db.close()
        if is_banned:
            return jsonify({'error': 'This account has been banned from the platform.'}), 403
            
        return jsonify({'message': 'Logged in', 'user': {'id': user['id'], 'username': user['username'], 'role': 'player'}})
    except Exception as e:
        if db: db.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@app.route('/get_players', methods=['POST'])
def get_players():
    db = None
    try:
        db = get_db()
        rows = db.execute('SELECT username, session_counter FROM users').fetchall()
        banned = db.execute('SELECT username FROM banned_users').fetchall()
        banned_set = set([b['username'] for b in banned])
    finally:
        if db: db.close()
    
    players = []
    for r in rows:
        if r['username'] not in banned_set:
            players.append({'username': r['username'], 'session_counter': r['session_counter']})
    return jsonify(players)

@app.route('/ban_player', methods=['POST'])
def ban_player():
    data = request.get_json()
    username = data.get('username')
    db = None
    try:
        db = get_db()
        db.execute('INSERT INTO banned_users (username) VALUES (?)', (username,))
        db.commit()
    except: pass
    finally:
        if db: db.close()
    # If the user is currently in active games or queues, you could eject them here as an enhancement.
    return jsonify({'message': 'User banned'})

@app.route('/')
def index():
    resp = make_response(app.send_static_file('index.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/get_total_coins', methods=['GET'])
def get_total_coins():
    username = request.args.get('username')
    if not username:
        return jsonify({'error': 'username required'}), 400
    db = None
    try:
        db = get_db()
        row = db.execute('SELECT total_coins FROM users WHERE username = ?', (username,)).fetchone()
        if not row:
            return jsonify({'error': 'User not found'}), 404
        return jsonify({'total_coins': row['total_coins'] or 0})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if db: db.close()

@app.route('/get_island_friends', methods=['GET'])
def get_island_friends():
    username = request.args.get('username')
    if not username:
        return jsonify({'error': 'username required'}), 400
    db = None
    try:
        db = get_db()
        # Find all games where this user was player1 or player2
        rows = db.execute('''SELECT player1, player2 FROM prison_games WHERE player1 = ? OR player2 = ?''', (username, username)).fetchall()
        friends = set()
        for r in rows:
            if r['player1'] != username: friends.add(r['player1'])
            if r['player2'] != username: friends.add(r['player2'])
        return jsonify({'friends': list(friends)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if db: db.close()


@app.route('/add_coins', methods=['POST'])
def add_coins():
    data = request.get_json()
    username = data.get('username')
    amount = data.get('amount', 0)
    if not username:
        return jsonify({'error': 'username required'}), 400
    db = None
    try:
        db = get_db()
        db.execute('UPDATE users SET total_coins = total_coins + ? WHERE username = ?', (int(amount), username))
        db.commit()
        row = db.execute('SELECT total_coins FROM users WHERE username = ?', (username,)).fetchone()
        return jsonify({'total_coins': row['total_coins'] or 0})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if db: db.close()



def ensure_room_loaded(password):
    if password in rooms:
        return True
    db = None
    try:
        db = get_db()
        row = db.execute('SELECT * FROM prison_rooms WHERE password = ?', (password,)).fetchone()
        if row:
            rooms[password] = {
                'waiting': [],
                'active': {},
                'sessions': json.loads(row['custom_sessions']) if row['custom_sessions'] else None,
                'settings': {'num_sessions': row['num_sessions'], 'allowed_bots': json.loads(row['allowed_bots'])},
                'last_join_time': 0
            }
            return True
    except Exception as e:
        print("DB Load Error:", e)
    finally:
        if db: db.close()
    return False

@app.route('/enter_room', methods=['POST'])
def enter_room():
    data = request.get_json()
    password = data.get('password')
    if not password or not ensure_room_loaded(password):
        return jsonify({'error': 'Invalid room password'}), 404
    return jsonify({'message': 'Room found'})

@app.route('/join_queue', methods=['POST'])
def join_queue():
  with game_lock:
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not password or not ensure_room_loaded(password):
        return jsonify({'error': 'Invalid or missing password'}), 404
    
    room = rooms[password]
    waiting = room['waiting']
    
    # Check if already in queue
    for p in waiting:
        if p['username'] == username:
            return jsonify({'status': 'waiting'})
    
    # Check if already in an active game
    for gid, game in room['active'].items():
        if username in game['players'] and game['session'] < room['settings']['num_sessions']:
            return jsonify({'status': 'matched', 'gameData': build_game_data(game, gid, room, username)})
    
    if len(waiting) >= 1:
        p1 = waiting.pop(0)
        print(f"[Queue] Matching human {p1['username']} with human {username}")
        game_id, game_data_p1, game_data_p2 = start_game_human_vs_human(room, p1['username'], username, password)
        # Store pending game data for the OTHER player (p1) to pick up via polling
        room['active'][game_id]['pending_start'] = {p1['username']: game_data_p1}
        return jsonify({'status': 'matched', 'gameData': game_data_p2})
    else:
        waiting.append({'username': username})
        return jsonify({'status': 'waiting'})

@app.route('/check_queue', methods=['POST'])
def check_queue():
  with game_lock:
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not password or not ensure_room_loaded(password):
        return jsonify({'status': 'waiting'})
    
    room = rooms[password]
    
    # Check if matched into a game
    for gid, game in room['active'].items():
        if username in game['players'] and game['session'] < room['settings']['num_sessions']:
            # Check if there's pending start data
            pending = game.get('pending_start', {})
            if username in pending:
                data = pending.pop(username)
                return jsonify({'status': 'matched', 'gameData': data})
            else:
                return jsonify({'status': 'matched', 'gameData': build_game_data(game, gid, room, username)})
    
    return jsonify({'status': 'waiting'})

@app.route('/trigger_bot', methods=['POST'])
def trigger_bot():
  with game_lock:
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not password or not ensure_room_loaded(password):
        return jsonify({'error': 'Room not found'}), 404
    
    room = rooms[password]
    for p in list(room['waiting']):
        if p['username'] == username:
            room['waiting'].remove(p)
            print(f"[Queue] 10s passed. Matching {username} with bot.")
            game_id, game_data = start_game_human_vs_bot(room, username, password)
            return jsonify({'status': 'matched', 'gameData': game_data})
    
    # Maybe already matched
    for gid, game in room['active'].items():
        if username in game['players']:
            return jsonify({'status': 'matched', 'gameData': build_game_data(game, gid, room, username)})
    
    return jsonify({'status': 'waiting'})

def build_game_data(game, game_id, room, username):
    """Build game start data for a specific player."""
    sessions_list = room.get('sessions') or prison_sessions
    session = sessions_list[0]
    if game['players'][0] == username:
        role = 'p1'
        matrix = prison_matrix_for_player(session, 'p1')
    else:
        role = 'p2'
        matrix = prison_matrix_for_player(session, 'p2')
    return {
        'gameId': game_id,
        'session': 1,
        'total_sessions': room['settings']['num_sessions'],
        'matrix': matrix,
        'role': role,
        'opponent': 'Player 2'
    }

def setup_game_state(room, p1_username, p2_username, pw, is_bot=False, bot_obj=None):
    game_id = str(os.urandom(8).hex())
    room['active'][game_id] = {
        'id': game_id,
        'players': [p1_username, p2_username],
        'sockets': [],
        'session': 0,
        'total': {p1_username: 0, p2_username: 0},
        'choices': {'p1': None, 'p2': None},
        'codes': [],
        'room': pw,
        'is_bot': is_bot,
        'bot_obj': bot_obj,
        'last_result': None
    }
    return game_id

def start_game_human_vs_human(room, p1_username, p2_username, pw):
    game_id = setup_game_state(room, p1_username, p2_username, pw)
    sessions_list = room.get('sessions') or prison_sessions
    session = sessions_list[0]
    p1_matrix = prison_matrix_for_player(session, 'p1')
    p2_matrix = prison_matrix_for_player(session, 'p2')
    
    game_data_p1 = {
        'gameId': game_id, 'session': 1, 'total_sessions': room['settings']['num_sessions'],
        'matrix': p1_matrix, 'role': 'p1', 'opponent': 'Player 2'
    }
    game_data_p2 = {
        'gameId': game_id, 'session': 1, 'total_sessions': room['settings']['num_sessions'],
        'matrix': p2_matrix, 'role': 'p2', 'opponent': 'Player 2'
    }
    return game_id, game_data_p1, game_data_p2

def start_game_human_vs_bot(room, username, pw):
    bot_types = room['settings'].get('allowed_bots', ['Random'])
    if not bot_types: bot_types = ['Random']
    bot_type = random.choice(bot_types)
    bots_name = f"Bot_{bot_type}"
    
    sessions_list = room.get('sessions') or prison_sessions
    bot_obj = create_bot(bot_type, False, sessions_list[0])
    
    game_id = setup_game_state(room, username, bots_name, pw, True, bot_obj)
    
    session = sessions_list[0]
    p1_matrix = prison_matrix_for_player(session, 'p1')
    
    game_data = {
        'gameId': game_id, 'session': 1, 'total_sessions': room['settings']['num_sessions'],
        'matrix': p1_matrix, 'role': 'p1', 'opponent': 'Player 2'
    }
    return game_id, game_data

@app.route('/submit_choice', methods=['POST'])
def submit_choice():
  with game_lock:
    try:
        data = request.get_json()
        game_id = data.get('gameId')
        row = data.get('row')
        username = data.get('username')
        if not game_id or not row:
            return jsonify({'error': 'Missing data'}), 400

        game = None
        room = None
        for r in rooms.values():
            if game_id in r['active']:
                game = r['active'][game_id]
                room = r
                break
        if not game:
            return jsonify({'error': 'Game not found'}), 404

        # Determine player slot by username
        if game['players'][0] == username:
            player_slot = 'p1'
        elif game['players'][1] == username:
            player_slot = 'p2'
        else:
            return jsonify({'error': 'Player not in game'}), 403

        print(f"[Game] Player {player_slot} ({username}) chose {row}")
        game['choices'][player_slot] = row
        game['last_result'] = None  # Clear previous round result

        # If it's a bot game, trigger bot decision immediately
        if game.get('is_bot'):
            try:
                bot_eval = game['bot_obj'].get_choice()
                bot_row = 'A' if bot_eval == 'C' else 'B'
                game['choices']['p2'] = bot_row
                game['bot_ready_time'] = time.time() + random.uniform(3.0, 5.0)
                print(f"[Game] Bot (p2) chose {bot_row} (Eval: {bot_eval})")
            except Exception as e:
                print(f"[Game] Bot Logic Error: {e}")
                game['choices']['p2'] = 'B'
                game['bot_ready_time'] = time.time()

        # Resolve round if both selections exist
        if game['choices']['p1'] and game['choices']['p2']:
            if game.get('is_bot') and time.time() < game.get('bot_ready_time', 0):
                return jsonify({'status': 'waiting'})

            result = resolve_round(game, game_id, room)
            # Return the result tailored for the submitting player
            if player_slot == 'p1':
                return jsonify({'status': 'resolved', 'result': result['p1']})
            else:
                return jsonify({'status': 'resolved', 'result': result['p2']})
        else:
            return jsonify({'status': 'waiting'})
            
    except Exception as e:
        print(f"[Game] Fatal Execution Error: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/check_round', methods=['POST'])
def check_round():
  with game_lock:
    data = request.get_json()
    game_id = data.get('gameId')
    username = data.get('username')
    
    game = None
    room = None
    for r in rooms.values():
        if game_id in r['active']:
            game = r['active'][game_id]
            room = r
            break
    
    if not game:
        # Game might have ended
        return jsonify({'status': 'resolved', 'result': {'done': True, 'game_ended': True}})
    
    # Check if there's a pending result for this player
    if game.get('last_result'):
        if game['players'][0] == username:
            return jsonify({'status': 'resolved', 'result': game['last_result']['p1']})
        else:
            return jsonify({'status': 'resolved', 'result': game['last_result']['p2']})
            
    if game['choices']['p1'] and game['choices']['p2']:
        if game.get('is_bot') and time.time() < game.get('bot_ready_time', 0):
            return jsonify({'status': 'waiting'})
            
        result = resolve_round(game, game_id, room)
        if game['players'][0] == username:
            return jsonify({'status': 'resolved', 'result': result['p1']})
        else:
            return jsonify({'status': 'resolved', 'result': result['p2']})
    
    return jsonify({'status': 'waiting'})

def resolve_round(game, game_id, room):
    p1_choice = game['choices']['p1']
    p2_choice = game['choices']['p2']
    print(f"[Game] Resolving Round: p1={p1_choice}, p2={p2_choice}")

    sessions_list = room.get('sessions') or prison_sessions
    session_idx = game['session']
    if session_idx >= len(sessions_list):
        session_idx = len(sessions_list) - 1
    session = sessions_list[session_idx]

    p1_score, p2_score = get_prison_value(session, p1_choice, p2_choice)
    p1_code = 'C' if p1_choice == 'A' else 'D'
    p2_code = 'C' if p2_choice == 'A' else 'D'
    code = p1_code + p2_code

    game['codes'].append(code)
    player1 = game['players'][0]
    player2 = game['players'][1]
    game['total'][player1] += p1_score
    game['total'][player2] += p2_score

    # DB Log
    db = None
    try:
        db = get_db()
        room_pwd = game.get('room', '')
        mat_id = str(session.get('MATRIX_ID', ''))
        file_id = str(session.get('SESSION_NUMBER', session.get('FILE_ID', '')))
        db.execute('''INSERT INTO prison_games (game_id, trial, player1, player2, p1_choice, p2_choice, code, p1_points, p2_points, room_password, matrix_id, file_id)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (game_id, session_idx + 1, player1, player2, p1_choice, p2_choice, code, p1_score, p2_score, room_pwd, mat_id, file_id))
        db.commit()
    except Exception as e:
        print(f"[Game] DB Error: {e}")
    finally:
        if db: db.close()

    # Bot Update
    if game.get('is_bot'):
        bot_my_eval = 'C' if p2_choice == 'A' else 'D'
        bot_op_eval = 'C' if p1_choice == 'A' else 'D'
        game['bot_obj'].record_result(bot_my_eval, bot_op_eval)

    game['session'] += 1
    game['choices'] = {'p1': None, 'p2': None}

    done = (game['session'] >= room['settings']['num_sessions'])
    
    if done:
        db = None
        try:
            db = get_db()
            db.execute('UPDATE users SET session_counter = session_counter + 1 WHERE username IN (?, ?)', (player1, player2))
            db.commit()
        except:
            pass
        finally:
            if db: db.close()

    # Prepare next round matrix
    next_p1_matrix = None
    next_p2_matrix = None
    if not done:
        next_session = sessions_list[min(game['session'], len(sessions_list)-1)]
        next_p1_matrix = prison_matrix_for_player(next_session, 'p1')
        next_p2_matrix = prison_matrix_for_player(next_session, 'p2')

    # Build result for both players
    result = {
        'p1': {
            'op_choice': p2_choice,
            'code': code,
            'my_score': p1_score,
            'op_score': p2_score,
            'done': done,
            'next_matrix': next_p1_matrix,
            'next_session': game['session'] + 1
        },
        'p2': {
            'op_choice': p1_choice,
            'code': code,
            'my_score': p2_score,
            'op_score': p1_score,
            'done': done,
            'next_matrix': next_p2_matrix,
            'next_session': game['session'] + 1
        }
    }
    
    # Store result so the other player can fetch it via polling
    game['last_result'] = result

    if done:
        print(f"[Game] Session {game_id} Complete")
        # Don't delete the game yet - let the other player poll for the result
        # It will be cleaned up on next game start or disconnect
    
    return result



@socketio.on('disconnect')
def disconnect():
    pass  # Game state is now managed via HTTP, no cleanup needed

# --- ISLAND EXPANSION API ---

@app.route('/get_island_data', methods=['GET'])
def get_island_data():
    username = request.args.get('username')
    db = None
    try:
        db = get_db()
        plots = db.execute('SELECT plot_index, item_type FROM island_plots WHERE username = ?', (username,)).fetchall()
        inv = db.execute('SELECT item_type, quantity FROM user_inventory WHERE username = ?', (username,)).fetchall()
        return jsonify({
            'plots': [{'index': p['plot_index'], 'item_type': p['item_type']} for p in plots],
            'inventory': [{'item_type': i['item_type'], 'quantity': i['quantity']} for i in inv]
        })
    finally:
        if db: db.close()

@app.route('/buy_plot', methods=['POST'])
def buy_plot():
    data = request.get_json()
    username = data.get('username')
    plot_index = data.get('plot_index')
    db = None
    try:
        db = get_db()
        # Check current owned plots to calculate cost
        owned_count = db.execute('SELECT COUNT(*) as c FROM island_plots WHERE username = ?', (username,)).fetchone()['c']
        cost = int(400 * (1.5 ** owned_count))
        
        # Check coins
        user_row = db.execute('SELECT total_coins FROM users WHERE username = ?', (username,)).fetchone()
        if not user_row or user_row['total_coins'] < cost:
            return jsonify({'error': 'Not enough coins', 'cost': cost}), 400
            
        # Check if already owned
        existing = db.execute('SELECT * FROM island_plots WHERE username = ? AND plot_index = ?', (username, plot_index)).fetchone()
        if existing:
            return jsonify({'error': 'Plot already owned'}), 400
            
        # Deduct coins and add plot
        db.execute('UPDATE users SET total_coins = total_coins - ? WHERE username = ?', (cost, username))
        db.execute('INSERT INTO island_plots (username, plot_index, item_type) VALUES (?, ?, ?)', (username, plot_index, 'empty'))
        db.commit()
        return jsonify({'success': True, 'new_balance': user_row['total_coins'] - cost})
    finally:
        if db: db.close()

@app.route('/buy_item', methods=['POST'])
def buy_item():
    data = request.get_json()
    username = data.get('username')
    item_type = data.get('item_type')
    cost = data.get('cost', 100) # Simple fixed cost for now
    
    db = None
    try:
        db = get_db()
        user_row = db.execute('SELECT total_coins FROM users WHERE username = ?', (username,)).fetchone()
        if not user_row or user_row['total_coins'] < cost:
            return jsonify({'error': 'Not enough coins'}), 400
            
        db.execute('UPDATE users SET total_coins = total_coins - ? WHERE username = ?', (cost, username))
        
        # add to inv
        inv_row = db.execute('SELECT * FROM user_inventory WHERE username = ? AND item_type = ?', (username, item_type)).fetchone()
        if inv_row:
            db.execute('UPDATE user_inventory SET quantity = quantity + 1 WHERE id = ?', (inv_row['id'],))
        else:
            db.execute('INSERT INTO user_inventory (username, item_type, quantity) VALUES (?, ?, 1)', (username, item_type))
        db.commit()
        return jsonify({'success': True, 'new_balance': user_row['total_coins'] - cost})
    finally:
        if db: db.close()

@app.route('/place_item', methods=['POST'])
def place_item():
    data = request.get_json()
    username = data.get('username')
    plot_index = data.get('plot_index')
    item_type = data.get('item_type')
    
    db = None
    try:
        db = get_db()
        inv_row = db.execute('SELECT * FROM user_inventory WHERE username = ? AND item_type = ? AND quantity > 0', (username, item_type)).fetchone()
        if not inv_row:
            return jsonify({'error': 'Item not in inventory'}), 400
            
        plot_row = db.execute('SELECT * FROM island_plots WHERE username = ? AND plot_index = ?', (username, plot_index)).fetchone()
        if not plot_row:
            return jsonify({'error': 'Plot not owned'}), 400
            
        db.execute('UPDATE user_inventory SET quantity = quantity - 1 WHERE id = ?', (inv_row['id'],))
        db.execute('UPDATE island_plots SET item_type = ? WHERE id = ?', (item_type, plot_row['id']))
        db.commit()
        return jsonify({'success': True})
    finally:
        if db: db.close()

@app.route('/visit_friend_island', methods=['GET'])
def visit_friend_island():
    friend_username = request.args.get('username')
    db = None
    try:
        db = get_db()
        plots = db.execute('SELECT plot_index, item_type FROM island_plots WHERE username = ?', (friend_username,)).fetchall()
        return jsonify({
            'plots': [{'index': p['plot_index'], 'item_type': p['item_type']} for p in plots]
        })
    finally:
        if db: db.close()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)