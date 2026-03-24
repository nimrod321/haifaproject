# HaiFa Project

A Flask-SocketIO application for multiplayer games including Tic-Tac-Toe and Prisoner's Dilemma simulations.

## Features

- User authentication (signup/login)
- Tic-Tac-Toe multiplayer game
- Prisoner's Dilemma game with multiple sessions
- Real-time communication using SocketIO
- SQLite database for storing game data

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the server:
   ```
   python server/app.py
   ```

3. Open `client/index.html` in your browser to access the client interface.

## Usage

- Sign up or log in to play games.
- Join waiting players for Tic-Tac-Toe or Prisoner's Dilemma.
- Games are played in real-time with other connected users.

## Troubleshooting

- If you encounter "database is locked" errors, ensure no other instances of the server are running.
- The server runs on port 3000 by default.

## Dependencies

- Flask
- Flask-SocketIO
- bcrypt
- sqlite3 (built-in)