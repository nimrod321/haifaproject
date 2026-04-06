from flask import Flask, request, jsonify, make_response
from flask_socketio import SocketIO, emit
import sqlite3
import bcrypt
import os
import time
import random
from game_bots import create_bot

app = Flask(__name__, static_folder='../client', static_url_path='')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=None)

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
                p2_points INTEGER
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
    if password in rooms:
        return jsonify({'error': 'Room already exists'}), 400
        
    rooms[password] = {
        'waiting': [],
        'active': {},
        'sessions': custom_sessions,
        'settings': {'num_sessions': num_sessions, 'allowed_bots': allowed_bots},
        'last_join_time': 0
    }
    return jsonify({'message': 'Room created'})

@app.route('/get_rooms', methods=['GET'])
def get_rooms():
    room_list = []
    for password, room in rooms.items():
        active_games = []
        for game_id, game in room['active'].items():
            active_games.append({
                'game_id': game_id,
                'players': game['players']
            })
        room_list.append({
            'password': password,
            'settings': room['settings'],
            'waiting': room['waiting'],
            'active': active_games
        })
    return jsonify(room_list)

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if username == 'NIS':
        return jsonify({'error': 'Username not allowed'}), 400
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    db = get_db()
    try:
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed))
        db.commit()
        return jsonify({'message': 'User created'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already exists'}), 400
    finally:
        db.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    db = get_db()
    
    if username == 'NIS' and password == 'NIS5760':
        return jsonify({'message': 'Logged in', 'user': {'id': 0, 'username': 'NIS', 'role': 'admin'}})
        
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    db.close()
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    return jsonify({'message': 'Logged in', 'user': {'id': user['id'], 'username': user['username'], 'role': 'player'}})

@app.route('/')
def index():
    resp = make_response(app.send_static_file('index.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp



@socketio.on('enterRoom')
def enter_room(data):
    password = data.get('password')
    if not password or password not in rooms:
        emit('prisonError', {'message': 'Invalid room password'})
        return
    emit('roomEntered')

@socketio.on('joinPrison')
def join_prison(data):
    username = data['username']
    password = data.get('password')
    if not password or password not in rooms:
        emit('prisonError', {'message': 'Invalid or missing password'})
        return
    
    room = rooms[password]
    waiting = room['waiting']
    player_obj = {'username': username, 'sid': request.sid}
    
    if len(waiting) >= 1:
        p1 = waiting.pop(0)
        start_game_human_vs_human(room, p1, player_obj, password)
    else:
        waiting.append(player_obj)
        emit('prisonWaiting')

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
    bots_name = f"Bot_{bot_type}_{str(os.urandom(2).hex())}"
    
    sessions_list = room.get('sessions') or prison_sessions
    bot_obj = create_bot(bot_type, False, sessions_list[0])
    
    game_id = setup_game_state(room, player['username'], bots_name, [player['sid']], pw, True, bot_obj)
    
    session = sessions_list[0]
    p1_matrix = prison_matrix_for_player(session, 'p1')
    
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
    password = data.get('password')
    if not password or password not in rooms:
        return
    
    room = rooms[password]
    waiting = room['waiting']
    
    for p in list(waiting):
        if p['sid'] == request.sid:
            waiting.remove(p)
            start_game_human_vs_bot(room, p, password)
            return

@socketio.on('prisonChooseRow')
def prison_choose_row(data):
    game_id = data['gameId']
    row = data['row']  # A/B
    # find the game in rooms
    game = None
    for r in rooms.values():
        if game_id in r['active']:
            game = r['active'][game_id]
            break
    if not game:
        return

    # discover player slot
    sid = request.sid
    if game['sockets'][0] == sid:
        game['choices']['p1'] = row
        player_slot = 'p1'
    elif len(game['sockets']) > 1 and game['sockets'][1] == sid:
        game['choices']['p2'] = row
        player_slot = 'p2'
    else:
        return
        
    if game.get('is_bot'):
        bot_eval = game['bot_obj'].get_choice()
        game['choices']['p2'] = 'A' if bot_eval == 'C' else 'B'

    # if both chose, resolve session
    if game['choices']['p1'] and game['choices']['p2']:
        p1_choice = game['choices']['p1']
        p2_choice = game['choices']['p2']

        room = rooms[game['room']]
        sessions_list = room.get('sessions') or prison_sessions
        session_index = game['session']
        if session_index >= len(sessions_list):
            session_index = len(sessions_list) - 1
        session = sessions_list[session_index]

        p1_score, p2_score = get_prison_value(session, p1_choice, p2_choice)

        p1_code = 'C' if p1_choice == 'A' else 'D'
        p2_code = 'C' if p2_choice == 'A' else 'D'
        code = p1_code + p2_code

        game['codes'].append(code)

        player1 = game['players'][0]
        player2 = game['players'][1]
        game['total'][player1] += p1_score
        game['total'][player2] += p2_score

        db = get_db()
        db.execute('''INSERT INTO prison_games (game_id, session_index, player1, player2, p1_choice, p2_choice, code, p1_points, p2_points)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (game_id, session_index + 1, player1, player2, p1_choice, p2_choice, code, p1_score, p2_score))
        db.commit()
        db.close()

        if game.get('is_bot'):
            bot_my_eval = 'C' if game['choices']['p2'] == 'A' else 'D'
            bot_op_eval = 'C' if game['choices']['p1'] == 'A' else 'D'
            game['bot_obj'].record_result(bot_my_eval, bot_op_eval)

        game['session'] += 1
        game['choices'] = {'p1': None, 'p2': None}

        room = rooms[game['room']]
        done = (game['session'] >= room['settings']['num_sessions'])
        next_idx = min(game['session'], len(sessions_list) - 1)
        next_session = sessions_list[next_idx]

        for socket_id in game['sockets']:
            emit('prisonRoundResult', {'p1_choice': p1_choice, 'p2_choice': p2_choice, 'code': code, 'p1_score': p1_score, 'p2_score': p2_score, 'done': done}, to=socket_id)

        if done:
            for socket_id in game['sockets']:
                emit('prisonGameEnd', {'codes': game['codes']}, to=socket_id)
            del room['active'][game_id]
            return

        next_p1_matrix = prison_matrix_for_player(next_session, 'p1')
        next_p2_matrix = prison_matrix_for_player(next_session, 'p2')
        
        if len(game['sockets']) > 0:
            emit('prisonNextRound', {'session': game['session'] + 1, 'matrix': next_p1_matrix}, to=game['sockets'][0])
        if len(game['sockets']) > 1:
            emit('prisonNextRound', {'session': game['session'] + 1, 'matrix': next_p2_matrix}, to=game['sockets'][1])
    else:
        emit('prisonWaitOpponent', {'chosen': player_slot}, to=sid)



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
                        emit('opponentDisconnected', to=sid)
                del room['active'][game_id]
                break

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=3000, debug=True)