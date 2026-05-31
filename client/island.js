class IslandEngine {
    constructor() {
        this.canvas = document.getElementById('island-canvas');
        this.ctx = this.canvas.getContext('2d');
        this.resize();
        window.addEventListener('resize', () => this.resize());

        this.keys = {};
        window.addEventListener('keydown', e => this.keys[e.code] = true);
        window.addEventListener('keyup', e => this.keys[e.code] = false);

        this.state = 'hidden'; // hidden, private, public
        this.player = { x: 500, y: 500, speed: 4, size: 64, frameIndex: 0, tickCount: 0 };
        this.npcs = [];
        
        this.assets = {
            privateBg: new Image(),
            publicBg: new Image()
        };
        this.assets.privateBg.src = 'private_island.png';
        this.assets.publicBg.src = 'public_island.png';

        this.boardArea = { x: 450, y: 400, w: 100, h: 100 }; // Matchmaking board area on public island
        this.portalArea = { x: 500, y: 800, w: 100, h: 100 }; // Portal to enter room on private island

        this.loop = this.loop.bind(this);
        requestAnimationFrame(this.loop);
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    async loadPrivateIsland(username) {
        this.state = 'private';
        this.canvas.style.display = 'block';
        this.player.x = 500;
        this.player.y = 500;
        this.npcs = [];
        
        document.getElementById('island-ui').style.display = 'block';
        
        // Fetch friends
        try {
            const res = await fetch('/get_island_friends?username=' + encodeURIComponent(username));
            const data = await res.json();
            if (data.friends) {
                data.friends.forEach(f => {
                    this.npcs.push({
                        name: f,
                        x: 300 + Math.random() * 400,
                        y: 300 + Math.random() * 400,
                        vx: (Math.random() - 0.5) * 1,
                        vy: (Math.random() - 0.5) * 1,
                        timer: Math.random() * 100,
                        frameIndex: 0, tickCount: 0
                    });
                });
            }
        } catch(e) { console.error('Error fetching friends', e); }
    }

    loadPublicIsland(roomCode) {
        this.state = 'public';
        this.currentRoom = roomCode;
        this.player.x = 500;
        this.player.y = 800;
        this.npcs = []; // Public island could also have players, but let's keep it simple for now
    }

    hide() {
        this.state = 'hidden';
        this.canvas.style.display = 'none';
        document.getElementById('island-ui').style.display = 'none';
    }

    update() {
        if (this.state === 'hidden') return;

        // Player movement
        let dx = 0; let dy = 0;
        if (this.keys['ArrowUp'] || this.keys['KeyW']) dy -= this.player.speed;
        if (this.keys['ArrowDown'] || this.keys['KeyS']) dy += this.player.speed;
        if (this.keys['ArrowLeft'] || this.keys['KeyA']) dx -= this.player.speed;
        if (this.keys['ArrowRight'] || this.keys['KeyD']) dx += this.player.speed;

        if (dx !== 0 || dy !== 0) {
            this.player.x += dx;
            this.player.y += dy;
            this.player.tickCount++;
            if (this.player.tickCount > 8) {
                this.player.tickCount = 0;
                this.player.frameIndex = (this.player.frameIndex + 1) % 4;
            }
        } else {
            this.player.frameIndex = 0;
        }

        // Keep player in bounds (approximate 1000x1000 island size)
        this.player.x = Math.max(100, Math.min(900, this.player.x));
        this.player.y = Math.max(100, Math.min(900, this.player.y));

        // NPC movement
        this.npcs.forEach(n => {
            n.timer--;
            if (n.timer <= 0) {
                n.vx = (Math.random() - 0.5) * 1.5;
                n.vy = (Math.random() - 0.5) * 1.5;
                n.timer = 50 + Math.random() * 100;
            }
            if (n.vx !== 0 || n.vy !== 0) {
                n.x += n.vx;
                n.y += n.vy;
                n.tickCount++;
                if (n.tickCount > 12) {
                    n.tickCount = 0;
                    n.frameIndex = (n.frameIndex + 1) % 4;
                }
            }
            n.x = Math.max(200, Math.min(800, n.x));
            n.y = Math.max(200, Math.min(800, n.y));
        });

        // Interactions
        const promptUI = document.getElementById('island-prompt');
        let promptActive = false;

        if (this.state === 'private') {
            // Check portal proximity
            if (this.checkCollision(this.player, this.portalArea)) {
                promptUI.textContent = 'Press SPACE to Travel to a Public Room';
                promptUI.style.display = 'block';
                promptActive = true;
                if (this.keys['Space']) {
                    this.keys['Space'] = false; // consume
                    document.getElementById('island-room-overlay').style.display = 'flex';
                }
            }
        } else if (this.state === 'public') {
            // Check matchmaking board proximity
            if (this.checkCollision(this.player, this.boardArea)) {
                promptUI.textContent = 'Press SPACE to Join Matchmaking Queue';
                promptUI.style.display = 'block';
                promptActive = true;
                if (this.keys['Space']) {
                    this.keys['Space'] = false;
                    // Trigger original queue log
                    enterMatchmaking(this.currentRoom);
                }
            }
        }

        if (!promptActive) {
            promptUI.style.display = 'none';
        }
    }

    checkCollision(p, area) {
        return (p.x > area.x - p.size && p.x < area.x + area.w + p.size &&
                p.y > area.y - p.size && p.y < area.y + area.h + p.size);
    }

    drawCharacter(ctx, x, y, isMoving, tick, color, name, isPlayer) {
        ctx.save();
        ctx.translate(x, y - 10);
        
        // Wobble factor for arms/legs
        const offset = isMoving ? Math.sin(tick * 0.4) * 8 : 0;
        
        // Head
        ctx.fillStyle = '#ffccaa'; 
        ctx.fillRect(-15, -25, 30, 25);
        // Shirt
        ctx.fillStyle = color;
        ctx.fillRect(-15, 0, 30, 20);
        
        // Legs
        ctx.fillStyle = '#2c3e50';
        ctx.fillRect(-12, 20, 10, 10 - offset); 
        ctx.fillRect(2, 20, 10, 10 + offset); 
        
        // Arms
        ctx.fillStyle = color;
        ctx.fillRect(-23, 0, 8, 15 + offset); 
        ctx.fillRect(15, 0, 8, 15 - offset); 
        
        // Eyes
        ctx.fillStyle = 'black';
        ctx.fillRect(-8, -15, 4, 4);
        ctx.fillRect(4, -15, 4, 4);

        ctx.restore();
        
        ctx.fillStyle = isPlayer ? '#f1c40f' : 'white';
        ctx.font = isPlayer ? '20px sans-serif' : '16px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(name, x, y - 45);
    }

    draw() {
        if (this.state === 'hidden') return;

        // Camera tracking
        const camX = this.canvas.width / 2 - this.player.x;
        const camY = this.canvas.height / 2 - this.player.y;

        this.ctx.fillStyle = '#1e90ff'; // Ocean blue
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        this.ctx.save();
        this.ctx.translate(camX, camY);

        // Draw Map
        const bg = this.state === 'private' ? this.assets.privateBg : this.assets.publicBg;
        if (bg.complete) {
            // Assume 1000x1000 world size
            this.ctx.drawImage(bg, 0, 0, 1000, 1000);
        }

        // Draw Interactive Zones
        this.ctx.fillStyle = 'rgba(255, 255, 0, 0.3)';
        if (this.state === 'private') {
            this.ctx.fillRect(this.portalArea.x, this.portalArea.y, this.portalArea.w, this.portalArea.h);
            this.ctx.fillStyle = 'white';
            this.ctx.font = '20px "Bubblegum Sans"';
            this.ctx.fillText("BOAT TO PUBLIC ISLAND", this.portalArea.x - 20, this.portalArea.y - 10);
        } else if (this.state === 'public') {
            this.ctx.fillRect(this.boardArea.x, this.boardArea.y, this.boardArea.w, this.boardArea.h);
            this.ctx.fillStyle = 'white';
            this.ctx.font = '20px "Bubblegum Sans"';
            this.ctx.fillText("MATCHMAKING BOARD", this.boardArea.x - 20, this.boardArea.y - 10);
        }

        // Draw NPCs
        this.npcs.forEach(n => {
            const isMoving = n.vx !== 0 || n.vy !== 0;
            this.drawCharacter(this.ctx, n.x, n.y, isMoving, n.tickCount, '#9b59b6', n.name, false);
        });

        // Draw Player
        const pMoving = this.keys['ArrowUp'] || this.keys['KeyW'] || this.keys['ArrowDown'] || this.keys['KeyS'] || this.keys['ArrowLeft'] || this.keys['KeyA'] || this.keys['ArrowRight'] || this.keys['KeyD'];
        this.drawCharacter(this.ctx, this.player.x, this.player.y, pMoving, this.player.tickCount, '#e74c3c', "YOU", true);

        this.ctx.restore();
    }

    loop() {
        this.update();
        this.draw();
        requestAnimationFrame(this.loop);
    }
}

let islandEngine = null;

// Initialize island when window loads
window.addEventListener('load', () => {
    islandEngine = new IslandEngine();
});

// Exposed function for the HTML UI
function travelToRoom() {
    const pw = document.getElementById('island-room-input').value;
    if (!pw) return;
    
    fetch('/enter_room', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pw })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            alert(data.error);
        } else {
            document.getElementById('island-room-overlay').style.display = 'none';
            islandEngine.loadPublicIsland(pw);
        }
    });
}

function enterMatchmaking(roomCode) {
    islandEngine.hide();
    document.getElementById('prison-join-form').style.display = 'none';
    document.getElementById('prison-password').value = roomCode; // inject room code
    document.getElementById('game').classList.remove('hidden');
    document.getElementById('room-lobby').classList.remove('hidden');
    queueForGame(); // triggers existing logic
}
