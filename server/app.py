from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import sqlite3
import bcrypt
import os

app = Flask(__name__, static_folder='../client', static_url_path='')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DATABASE = 'games.db'

def get_db():
    db = sqlite3.connect(DATABASE)
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

prison_waiting_players = []
prison_active_games = {}

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
    return session[key1], session[key2]


def prison_matrix_for_player(session, player):
    # player == 'p1' or 'p2'; p2 sees swapped rows/columns and reversed pairs
    if player == 'p1':
        return {
            'AA1': session['AA1'], 'AA2': session['AA2'],
            'AB1': session['AB1'], 'AB2': session['AB2'],
            'BA1': session['BA1'], 'BA2': session['BA2'],
            'BB1': session['BB1'], 'BB2': session['BB2']
        }
    return {
        'AA1': session['AA2'], 'AA2': session['AA1'],
        'AB1': session['BA2'], 'AB2': session['BA1'],
        'BA1': session['AB2'], 'BA2': session['AB1'],
        'BB1': session['BB2'], 'BB2': session['BB1']
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
    if not password:
        return jsonify({'error': 'Password required'}), 400
    if password in rooms:
        return jsonify({'error': 'Room already exists'}), 400
    rooms[password] = {
        'waiting': [],
        'active': {},
        'settings': {'num_sessions': num_sessions}
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
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    db.close()
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    return jsonify({'message': 'Logged in', 'user': {'id': user['id'], 'username': user['username']}})

@app.route('/')
def index():
    return app.send_static_file('index.html')

@socketio.on('joinTicTacToe')
def join_tic_tac_toe(data):
    username = data['username']
    if waiting_players:
        opponent = waiting_players.pop(0)
        game_id = str(os.urandom(16).hex())
        active_games[game_id] = {
            'id': game_id,
            'players': [opponent['username'], username],
            'board': [''] * 9,
            'current_player': 0,
            'sockets': [opponent['sid'], request.sid]
        }
        emit('gameStart', {'game': active_games[game_id], 'yourTurn': True}, to=opponent['sid'])
        emit('gameStart', {'game': active_games[game_id], 'yourTurn': False}, to=request.sid)
    else:
        waiting_players.append({'username': username, 'sid': request.sid})
        emit('waiting')

@socketio.on('joinPrison')
def join_prison(data):
    username = data['username']
    password = data.get('password')
    if not password or password not in rooms:
        emit('prisonError', {'message': 'Invalid or missing password'})
        return
    room = rooms[password]
    if room['waiting']:
        opponent = room['waiting'].pop(0)
        game_id = str(os.urandom(16).hex())
        room['active'][game_id] = {
            'id': game_id,
            'players': [opponent['username'], username],
            'sockets': [opponent['sid'], request.sid],
            'session': 0,
            'total': {opponent['username']: 0, username: 0},
            'choices': {'p1': None, 'p2': None},
            'codes': [],
            'room': password
        }
        session = prison_sessions[0]
        p1_matrix = prison_matrix_for_player(session, 'p1')
        p2_matrix = prison_matrix_for_player(session, 'p2')

        emit('prisonStart', {
            'gameId': game_id,
            'session': 1,
            'total_sessions': room['settings']['num_sessions'],
            'total': room['active'][game_id]['total'],
            'matrix': p1_matrix,
            'role': 'p1',
            'opponent': opponent['username']
        }, to=opponent['sid'])

        emit('prisonStart', {
            'gameId': game_id,
            'session': 1,
            'total_sessions': room['settings']['num_sessions'],
            'total': room['active'][game_id]['total'],
            'matrix': p2_matrix,
            'role': 'p2',
            'opponent': username
        }, to=request.sid)
    else:
        room['waiting'].append({'username': username, 'sid': request.sid})
        emit('prisonWaiting')

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
    elif game['sockets'][1] == sid:
        game['choices']['p2'] = row
        player_slot = 'p2'
    else:
        return

    # if both chose, resolve session
    if game['choices']['p1'] and game['choices']['p2']:
        p1_choice = game['choices']['p1']
        p2_choice = game['choices']['p2']

        p1_remain = 'A' if p1_choice == 'B' else 'B'
        p2_remain = 'A' if p2_choice == 'B' else 'B'

        session_index = game['session']
        if session_index >= len(prison_sessions):
            session_index = len(prison_sessions) - 1
        session = prison_sessions[session_index]

        p1_score, p2_score = get_prison_value(session, p1_remain, p2_remain)

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

        game['session'] += 1
        game['choices'] = {'p1': None, 'p2': None}

        room = rooms[game['room']]
        done = (game['session'] >= room['settings']['num_sessions'])
        next_idx = min(game['session'], len(prison_sessions) - 1)
        next_session = prison_sessions[next_idx]

        emit('prisonRoundResult', {'p1_choice': p1_choice, 'p2_choice': p2_choice, 'code': code, 'p1_score': p1_score, 'p2_score': p2_score, 'total': game['total'], 'done': done}, to=game['sockets'][0])
        emit('prisonRoundResult', {'p1_choice': p1_choice, 'p2_choice': p2_choice, 'code': code, 'p1_score': p1_score, 'p2_score': p2_score, 'total': game['total'], 'done': done}, to=game['sockets'][1])

        if done:
            emit('prisonGameEnd', {'codes': game['codes']}, to=game['sockets'][0])
            emit('prisonGameEnd', {'codes': game['codes']}, to=game['sockets'][1])
            del room['active'][game_id]
            return

        next_p1_matrix = prison_matrix_for_player(next_session, 'p1')
        next_p2_matrix = prison_matrix_for_player(next_session, 'p2')
        emit('prisonNextRound', {'session': game['session'] + 1, 'matrix': next_p1_matrix, 'total': game['total']}, to=game['sockets'][0])
        emit('prisonNextRound', {'session': game['session'] + 1, 'matrix': next_p2_matrix, 'total': game['total']}, to=game['sockets'][1])
    else:
        emit('prisonWaitOpponent', {'chosen': player_slot}, to=sid)

@socketio.on('move')
def make_move(data):
    game_id = data['gameId']
    index = data['index']
    game = active_games.get(game_id)
    if not game or game['sockets'][game['current_player']] != request.sid:
        return
    if game['board'][index]:
        return
    game['board'][index] = 'X' if game['current_player'] == 0 else 'O'
    game['current_player'] = 1 - game['current_player']
    if check_win(game['board']):
        winner = game['players'][1 - game['current_player']]
        db = get_db()
        db.execute('INSERT INTO games (game_type, player1, player2, state, logs) VALUES (?, ?, ?, ?, ?)',
                   ('tictactoe', game['players'][0], game['players'][1], str(game['board']), f'Winner: {winner}'))
        db.commit()
        db.close()
        for sid in game['sockets']:
            emit('gameEnd', {'winner': winner, 'board': game['board']}, to=sid)
        del active_games[game_id]
    elif all(cell for cell in game['board']):
        db = get_db()
        db.execute('INSERT INTO games (game_type, player1, player2, state, logs) VALUES (?, ?, ?, ?, ?)',
                   ('tictactoe', game['players'][0], game['players'][1], str(game['board']), 'Draw'))
        db.commit()
        db.close()
        for sid in game['sockets']:
            emit('gameEnd', {'winner': None, 'board': game['board']}, to=sid)
        del active_games[game_id]
    else:
        for i, sid in enumerate(game['sockets']):
            emit('gameUpdate', {'board': game['board'], 'status': 'Your turn' if i == game['current_player'] else 'Opponent\'s turn'}, to=sid)

def check_win(board):
    lines = [
        [0,1,2], [3,4,5], [6,7,8],
        [0,3,6], [1,4,7], [2,5,8],
        [0,4,8], [2,4,6]
    ]
    for line in lines:
        if board[line[0]] and board[line[0]] == board[line[1]] == board[line[2]]:
            return True
    return False

@socketio.on('disconnect')
def disconnect():
    for player in waiting_players:
        if player['sid'] == request.sid:
            waiting_players.remove(player)
            break
    for game_id, game in list(active_games.items()):
        if request.sid in game['sockets']:
            for sid in game['sockets']:
                if sid != request.sid:
                    emit('opponentDisconnected', to=sid)
            del active_games[game_id]
            break

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=3000, debug=True)