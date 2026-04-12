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

app = Flask(__name__, static_folder='../client', static_url_path='')
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
                session_index INTEGER,
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
            try: db.execute('ALTER TABLE users ADD COLUMN session_counter INTEGER DEFAULT 0')
            except: pass
            
            db.execute('''CREATE TABLE IF NOT EXISTS banned_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE
            )''')
            
            db.execute('''CREATE TABLE IF NOT EXISTS prison_rooms (
                password TEXT PRIMARY KEY,
                num_sessions INTEGER,
                allowed_bots TEXT,
                custom_sessions TEXT
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
    
    if custom_sessions:
        cleaned_list = []
        for s in custom_sessions:
            c = {}
            for k, v in s.items():
                kw = str(k).upper().strip()
                try:
                    c[kw] = int(float(v)) if str(v).strip() != '' else 0
                except:
                    c[kw] = 0
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
            
        db.execute('''INSERT INTO prison_rooms (password, num_sessions, allowed_bots, custom_sessions)
                      VALUES (?, ?, ?, ?)''', 
                   (password, num_sessions, json.dumps(allowed_bots), json.dumps(custom_sessions) if custom_sessions else None))
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
        db_rooms = db.execute('SELECT password FROM prison_rooms').fetchall()
        for r in db_rooms:
            password = r['password']
            
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
                'active_games': len(active_games_list),
                'games': active_games_list
            })
    finally:
        if db: db.close()
        
    return jsonify(room_list)

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
                'session_index': r['session_index'],
                'player1': r['player1'],
                'player2': r['player2'],
                'p1_choice': r['p1_choice'],
                'p2_choice': r['p2_choice'],
                'code': r['code'],
                'p1_points': r['p1_points'],
                'p2_points': r['p2_points'],
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

@socketio.on('joinPrison')
def join_prison(data):
    username = data.get('username')
    password = data.get('password')
    if not password or not ensure_room_loaded(password):
        socketio.emit('prisonError', {'message': 'Invalid or missing password'}, to=request.sid)
        return
    
    room = rooms[password]
    waiting = room['waiting']
    player_obj = {'username': username, 'sid': request.sid}
    
    if len(waiting) >= 1:
        p1 = waiting.pop(0)
        print(f"[Queue] Matching human {p1['username']} with human {username}")
        start_game_human_vs_human(room, p1, player_obj, password)
    else:
        waiting.append(player_obj)
        socketio.emit('prisonWaiting', to=request.sid)

@socketio.on('triggerBotMatch')
def trigger_bot_match(data):
    password = data.get('password')
    if ensure_room_loaded(password):
        room = rooms[password]
        for p in list(room['waiting']):
            if p['sid'] == request.sid:
                room['waiting'].remove(p)
                print(f"[Queue] 10s passed via client pulse. Matching {p['username']} with bot.")
                start_game_human_vs_bot(room, p, password)
                return

def setup_game_state(room, p1_username, p2_username, sockets, pw, is_bot=False, bot_obj=None):
    game_id = str(os.urandom(16).hex())
    room['active'][game_id] = {
        'id': game_id,
        'players': [p1_username, p2_username],
        'sockets': sockets,
        'session': 0,
        'total': {p1_username: 0, p2_username: 0},
        'choices': {'p1': None, 'p2': None},
        'codes': [],
        'room': pw,
        'is_bot': is_bot,
        'bot_obj': bot_obj
    }
    return game_id

def start_game_human_vs_human(room, opp1, opp2, pw):
    game_id = setup_game_state(room, opp1['username'], opp2['username'], [opp1['sid'], opp2['sid']], pw)
    sessions_list = room.get('sessions') or prison_sessions
    session = sessions_list[0]
    p1_matrix = prison_matrix_for_player(session, 'p1')
    p2_matrix = prison_matrix_for_player(session, 'p2')
    
    # Notify both players that a match was found
    socketio.emit('prisonMatchFound', to=opp1['sid'])
    socketio.emit('prisonMatchFound', to=opp2['sid'])
    
    socketio.emit('prisonStart', {
        'gameId': game_id,
        'session': 1,
        'total_sessions': room['settings']['num_sessions'],
        'matrix': p1_matrix,
        'role': 'p1',
        'opponent': 'Player 2'
    }, to=opp1['sid'])
    
    socketio.emit('prisonStart', {
        'gameId': game_id,
        'session': 1,
        'total_sessions': room['settings']['num_sessions'],
        'matrix': p2_matrix,
        'role': 'p2',
        'opponent': 'Player 2'
    }, to=opp2['sid'])

def start_game_human_vs_bot(room, player, pw):
    bot_types = room['settings'].get('allowed_bots', ['Random'])
    if not bot_types: bot_types = ['Random']
    bot_type = random.choice(bot_types)
    bots_name = f"Bot_{bot_type}"
    
    sessions_list = room.get('sessions') or prison_sessions
    bot_obj = create_bot(bot_type, False, sessions_list[0])
    
    game_id = setup_game_state(room, player['username'], bots_name, [player['sid']], pw, True, bot_obj)
    
    session = sessions_list[0]
    p1_matrix = prison_matrix_for_player(session, 'p1')
    
    socketio.emit('prisonMatchFound', to=player['sid'])
    
    socketio.emit('prisonStart', {
        'gameId': game_id,
        'session': 1,
        'total_sessions': room['settings']['num_sessions'],
        'matrix': p1_matrix,
        'role': 'p1',
        'opponent': 'Player 2'
    }, to=player['sid'])

@socketio.on('requestBot')
def request_bot(data):
    # This remains for backward compatibility or direct client requests, 
    # but the background task handles it automatically now.
    pass

@socketio.on('prisonChooseRow')
def prison_choose_row(data):
  with game_lock:
    try:
        game_id = data.get('gameId')
        row = data.get('row') # 'A' or 'B'
        if not game_id or not row:
            return

        game = None
        for r in rooms.values():
            if game_id in r['active']:
                game = r['active'][game_id]
                break
        if not game:
            print(f"[Game] Error: Game {game_id} not found in active games")
            return

        sid = request.sid
        # Determine human slot
        if game['sockets'][0] == sid:
            player_slot = 'p1'
        elif len(game['sockets']) > 1 and game['sockets'][1] == sid:
            player_slot = 'p2'
        else:
            return

        print(f"[Game] Player {player_slot} chose {row}")
        game['choices'][player_slot] = row

        # If it's a bot game, trigger bot decision immediately
        if game.get('is_bot'):
            try:
                print(f"[Game] Bot game detected, getting bot choice...")
                bot_eval = game['bot_obj'].get_choice() # Returns 'C' or 'D'
                bot_row = 'A' if bot_eval == 'C' else 'B'
                game['choices']['p2'] = bot_row
                
                # Apply Unified Distribution Bot Delay: t ~ U(-2,2), delay = max(t, 0)
                t_val = random.uniform(-2, 2)
                bot_delay = max(t_val, 0)
                if bot_delay > 0:
                    time.sleep(bot_delay)
                    
                print(f"[Game] Bot (p2) chose {bot_row} (Eval: {bot_eval}) after {bot_delay:.2f}s delay.")
            except Exception as e:
                print(f"[Game] Bot Logic Error: {e}")
                game['choices']['p2'] = 'B' # Default to Defect if bot crashes

        # Resolve round if both selections exist
        if game['choices']['p1'] and game['choices']['p2']:
            p1_choice = game['choices']['p1']
            p2_choice = game['choices']['p2']
            print(f"[Game] Resolving Round: p1={p1_choice}, p2={p2_choice}")

            room = rooms[game['room']]
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
                db.execute('''INSERT INTO prison_games (game_id, session_index, player1, player2, p1_choice, p2_choice, code, p1_points, p2_points, room_password, matrix_id)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                           (game_id, session_idx + 1, player1, player2, p1_choice, p2_choice, code, p1_score, p2_score, room_pwd, mat_id))
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
            
            # Emit Result - Tailored for perspective
            if len(game['sockets']) > 0:
                s_id_p1 = game['sockets'][0]
                socketio.emit('prisonRoundResult', {
                    'op_choice': p2_choice,
                    'code': code,
                    'my_score': p1_score,
                    'op_score': p2_score,
                    'done': done
                }, to=s_id_p1)
                
            if len(game['sockets']) > 1:
                s_id_p2 = game['sockets'][1]
                # For P2, op_choice is p1_choice.
                socketio.emit('prisonRoundResult', {
                    'op_choice': p1_choice,
                    'code': code,
                    'my_score': p2_score,
                    'op_score': p1_score,
                    'done': done
                }, to=s_id_p2)

            if done:
                print(f"[Game] Session {game_id} Complete")
                for s_id in game['sockets']:
                    socketio.emit('prisonGameEnd', {'codes': game['codes']}, to=s_id)
                del room['active'][game_id]
                return

            # Prepare for next round
            next_session = sessions_list[min(game['session'], len(sessions_list)-1)]
            next_p1_matrix = prison_matrix_for_player(next_session, 'p1')
            next_p2_matrix = prison_matrix_for_player(next_session, 'p2')
            
            if len(game['sockets']) > 0:
                socketio.emit('prisonNextRound', {'session': game['session'] + 1, 'matrix': next_p1_matrix}, to=game['sockets'][0])
            if len(game['sockets']) > 1:
                socketio.emit('prisonNextRound', {'session': game['session'] + 1, 'matrix': next_p2_matrix}, to=game['sockets'][1])
        else:
            # Only one player chose
            socketio.emit('prisonWaitOpponent', {'chosen': player_slot}, to=sid)
            
    except Exception as e:
        print(f"[Game] Fatal Execution Error: {e}")



@socketio.on('disconnect')
def disconnect():
    for pw, room in list(rooms.items()):
        for player in list(room['waiting']):
            if player['sid'] == request.sid:
                room['waiting'].remove(player)
                break
        for game_id, game in list(room['active'].items()):
            if request.sid in game['sockets']:
                for sid in game['sockets']:
                    if sid != request.sid:
                        socketio.emit('opponentDisconnected', to=sid)
                del room['active'][game_id]
                break

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=3000, debug=True)