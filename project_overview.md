# Dilemma Street - Project Overview & Technical Specification

## 1. Project Concept
**Dilemma Street** is a high-fidelity, real-time multiplayer platform for the classic **Prisoner's Dilemma** game. It prioritizes psychological tension through tactile UI elements, cinematic reveal sequences, and adaptive AI bots.

---

## 2. Visual Aesthetic & UI/UX
*   **Theme**: "Floating Nature" (Glassmorphism over a serene nature background).
*   **Game Board**: A heavy, symmetric **Aged Oak** game table. Features vertical-grain wooden curtains (sliding doors) for each cell.
*   **Magical Elements**: 
    *   **The Chest**: A 3D-styled **Magical Purple Chest** with gold trim and a glowing heart lock.
    *   **Point Bubbles**: Glowing circular bubbles (15, 30, 45 style) that float and zoom into the chest upon round resolution.
*   **Matchmaking UI**: Anonymous matchmaking labeling opponents simply as "Player 2" with shadowy mask avatars.

---

## 3. Core Gameplay Loop & Animation Sequence (The "Sacred Sequence")
The animation timing is critical for the "Dilemma Street" experience:
1.  **Round Initialize**: All 4 wooden doors slide **OPEN** simultaneously to reveal the new score matrix for the round.
2.  **Selection Interaction**:
    *   When a player clicks Row A or Row B, the **unchosen row curtains close instantly**.
    *   The choice is visually locked once the "שלח" (Submit) button is clicked. No decision changes allowed after submission.
3.  **The Reveal (3-Phase Sequence)**:
    *   **Phase 1 (Countdown)**: A pulsing **3-2-1 overlay** appears once both players (or the bot) have locked in moves.
    *   **Phase 2 (Isolatory Close)**: The **column NOT chosen** by the opponent slides shut, leaving exactly one intersection cell visible—the winning square.
    *   **Phase 3 (Reward)**: Result popup appears + points bubble into the Purple Chest.
4.  **Reset Transition**:
    *   After 3 seconds, **ALL 4 squares slide SHUT** simultaneously to clear the data.
    *   After a 1-second pause, they all **slide OPEN fresh** with the next round's matrix numbers and cleared state.

---

## 4. Matchmaking & Queue Logic
*   **Human-First**: The server prioritizes matching human players in the queue.
*   **The 10-Second Rule**: When a player joins a room, the server waits **10 seconds**. If no second human joins, a **Bot Match** is automatically triggered.
*   **Anonymous Play**: Players never see each other's real usernames during gameplay to maintain the "Dilemma" psychological integrity.

---

## 5. Administrative Dashboard (NIS Authenticated)
Admins (Credentials: `NIS` / `NIS5760`) have full control over the environment:
*   **Matrix Management**: Upload `.xlsx` files to define round-by-round points. Expected keys: `AA1, AA2, AB1, AB2, BA1, BA2, BB1, BB2`.
*   **Bot Configuration**: 
    *   Toggle specific bots: **Random**, **CBot** (Always Cooperate), **Tit-For-Tat**, etc.
    *   **SERS Bots**: Configurable adaptive bots with variable "Memory Stacks" (e.g., SERS_5 remembers the last 5 interactions to calculate expected rewards).
*   **Room Control**: Stop active games, delete rooms, and wipe session logs.
*   **Persistence**: All room data and session outcomes are logged to a localized SQLite database for historical analysis.

---

## 6. Adaptive AI (SERS Logic)
The **SERS Bot** (State Expected Reward Synchronizer) uses Bayesian-style logic:
1.  **Probability Calculation (ps)**: Calculates the likelihood of the opponent matching the bot's move based on the history stack.
2.  **EV Assessment**: Calculates the **Expected Value (EV)** for picking Row A (C) vs. Row B (D) based on current matrix values and `ps`.
3.  **Decision**: Picks the row with the statistically highest reward, allowing it to adapt to human patterns (Cooperative vs. Defective).

---

## 7. Technical Stack
*   **Backend**: Python (Flask) + Flask-SocketIO (Real-time).
*   **Frontend**: Vanilla HTML5, CSS3, JavaScript (SheetJS for Excel).
*   **Database**: SQLite (local persistence).
*   **Real-time Protocol**: Event-based socket communication for synchronized animations across all clients.