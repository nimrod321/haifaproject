# HaiFa Project Overview

## What I Did
I helped fix and enhance a multiplayer game application built with Flask and SocketIO. The app supports Tic-Tac-Toe and Prisoner's Dilemma games. Here are the main changes I made:

### Database Fixes
- Fixed SQLite database connection issues by ensuring all connections are properly closed
- Moved the database file to avoid filesystem conflicts
- Added proper error handling for database operations

### Room System for Prisoner's Dilemma
- Created a password-protected room system where players can only join games with the correct password
- Admins can create rooms with custom settings (number of sessions)
- Players are queued within their room and paired up automatically

### Admin Interface
- Added an admin view to create rooms, monitor active rooms, and view game results
- Rooms show waiting players and active games in real-time
- Results table displays all completed game data

### UI Improvements
- Added forms for joining Prisoner's Dilemma games with password input
- Improved navigation between admin sections
- Better error messages and feedback

## File Descriptions

### requirements.txt
This file lists all the Python packages needed to run the application. It includes Flask (web framework), Flask-SocketIO (real-time communication), and bcrypt (password hashing).

### client/index.html
This is the main web page that users see in their browser. It contains:
- Login and signup forms
- Buttons to join different games
- The game interfaces for Tic-Tac-Toe and Prisoner's Dilemma
- Admin controls for creating and monitoring rooms
- JavaScript code that connects to the server and handles game logic

### server/app.py
This is the main server file written in Python. It:
- Sets up a Flask web server
- Handles user authentication (signup/login)
- Manages game rooms and player matching
- Processes game moves and calculates results
- Stores game data in a SQLite database
- Uses SocketIO for real-time communication between players

### README.md
This is a documentation file that explains how to set up and use the application. It includes installation instructions, usage guide, and troubleshooting tips.

### games.db (created automatically)
This is a SQLite database file that stores:
- User accounts
- Game results and statistics
- Prisoner's Dilemma game data

The database is created when the server first runs and stores all persistent data.