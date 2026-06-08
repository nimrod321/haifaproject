class IslandEngine {
    constructor() {
        this.canvas = document.getElementById('island-canvas');
        this.ctx = this.canvas.getContext('2d');
        this.resize();
        window.addEventListener('resize', () => this.resize());

        this.keys = {};
        window.addEventListener('keydown', e => this.keys[e.code] = true);
        window.addEventListener('keyup', e => this.keys[e.code] = false);

        this.state = 'hidden'; 
        this.tileSize = 50;
        this.mapCols = 20;
        this.mapRows = 20;
        this.camera = { x: 0, y: 0 };
        this.player = { x: 500, y: 500, speed: 4, size: 24, frameIndex: 0, tickCount: 0 };
        
        this.npcs = [];
        this.map = []; // 2D array of integers
        this.plots = {}; // map of plotIndex -> {item_type: string}
        this.inventory = [];
        this.ownedPlots = [];
        this.totalCoins = 0;
        this.currentUsername = '';
        this.currentRoom = '';

        this.TILE_GRASS = 0;
        this.TILE_ROAD = 1;
        this.TILE_TREE = 2;
        this.TILE_BUSH = 3;
        this.TILE_PLOT = 4;
        this.TILE_FERRY = 5;
        this.TILE_STORE = 6;
        this.TILE_BOARD = 7;
        this.TILE_PORTAL = 8;

        this.grassImg = new Image();
        this.grassImg.src = 'grass.png';
        this.grassImg.onload = () => {
            this.grassPattern = this.ctx.createPattern(this.grassImg, 'repeat');
        };

        this.loop = this.loop.bind(this);
        requestAnimationFrame(this.loop);
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    async loadPrivateIsland(username) {
        this.state = 'private';
        this.currentUsername = username;
        this.canvas.style.display = 'block';
        this.player.x = this.mapCols * this.tileSize / 2;
        this.player.y = this.mapRows * this.tileSize / 2;
        this.npcs = [];
        
        document.getElementById('island-ui').style.display = 'block';
        
        this.generateMap('private');
        await this.fetchIslandData(username);

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
        this.canvas.style.display = 'block';
        this.player.x = this.mapCols * this.tileSize / 2;
        this.player.y = this.mapRows * this.tileSize - 100;
        this.npcs = [];
        document.getElementById('island-ui').style.display = 'block';
        this.generateMap('public');
    }

    async fetchIslandData(username) {
        try {
            const res = await fetch('/get_island_data?username=' + encodeURIComponent(username));
            const data = await res.json();
            
            this.plots = {};
            this.ownedPlots = [];
            if(data.plots) {
                data.plots.forEach(p => {
                    this.plots[p.index] = p;
                    this.ownedPlots.push(p.index);
                });
            }
            this.inventory = data.inventory || [];
        } catch(e) { console.log(e); }
        
        try {
            const cRes = await fetch('/get_total_coins?username=' + encodeURIComponent(username));
            const cData = await cRes.json();
            this.totalCoins = cData.total_coins || 0;
        } catch(e) { console.log(e); }
    }

    generateMap(type) {
        this.map = [];
        for (let r = 0; r < this.mapRows; r++) {
            let row = [];
            for (let c = 0; c < this.mapCols; c++) {
                row.push(this.TILE_GRASS);
            }
            this.map.push(row);
        }

        if (type === 'private') {
            // Main road down the center
            for (let r = 5; r < 18; r++) {
                this.map[r][9] = this.TILE_ROAD;
                this.map[r][10] = this.TILE_ROAD;
            }
            // Plots around the road
            this.map[8][8] = this.TILE_PLOT;
            this.map[10][8] = this.TILE_PLOT;
            this.map[12][8] = this.TILE_PLOT;
            this.map[8][11] = this.TILE_PLOT;
            this.map[10][11] = this.TILE_PLOT;
            this.map[12][11] = this.TILE_PLOT;

            // Ferry Port at the top
            this.map[4][9] = this.TILE_FERRY;
            this.map[4][10] = this.TILE_FERRY;
            
            // Portal at the bottom
            this.map[18][9] = this.TILE_PORTAL;
            this.map[18][10] = this.TILE_PORTAL;

            // Scatter trees and bushes
            for(let i=0; i<30; i++) {
                let tr = Math.floor(Math.random() * this.mapRows);
                let tc = Math.floor(Math.random() * this.mapCols);
                if (this.map[tr][tc] === this.TILE_GRASS) {
                    this.map[tr][tc] = Math.random() > 0.5 ? this.TILE_TREE : this.TILE_BUSH;
                }
            }
        } else if (type === 'public') {
            // Public Island Map
            for (let r = 8; r < 20; r++) {
                for (let c = 8; c < 12; c++) {
                    this.map[r][c] = this.TILE_ROAD;
                }
            }
            
            // Matchmaking board
            this.map[8][9] = this.TILE_BOARD;
            this.map[8][10] = this.TILE_BOARD;

            // Stores
            this.map[10][6] = this.TILE_STORE;
            this.map[10][13] = this.TILE_STORE;

            // Border trees
            for(let i=0; i<this.mapCols; i++) {
                this.map[0][i] = this.TILE_TREE;
            }
        }
    }

    hide() {
        this.state = 'hidden';
        this.canvas.style.display = 'none';
        document.getElementById('island-ui').style.display = 'none';
        
        // Hide overlay UIs
        let uis = ['island-shop-ui', 'island-inventory-ui', 'island-ferry-ui', 'island-room-overlay'];
        uis.forEach(id => {
            let el = document.getElementById(id);
            if(el) el.classList.add('hidden');
        });
    }

    isSolid(r, c) {
        if (r < 0 || r >= this.mapRows || c < 0 || c >= this.mapCols) return true;
        const t = this.map[r][c];
        if (t === this.TILE_TREE || t === this.TILE_BUSH || t === this.TILE_STORE || t === this.TILE_BOARD) return true;
        if (t === this.TILE_PLOT) {
            let pIdx = r * this.mapCols + c;
            if (this.plots[pIdx] && this.plots[pIdx].item_type !== 'empty') {
                return true; // occupied plot is solid
            }
        }
        return false;
    }

    checkPlayerCollision(newX, newY) {
        const s = this.player.size;
        const left = Math.floor((newX - s) / this.tileSize);
        const right = Math.floor((newX + s) / this.tileSize);
        const top = Math.floor((newY - s) / this.tileSize);
        const bottom = Math.floor((newY + s) / this.tileSize);

        for (let r = top; r <= bottom; r++) {
            for (let c = left; c <= right; c++) {
                if (this.isSolid(r, c)) return true;
            }
        }
        return false;
    }

    update() {
        if (this.state === 'hidden') return;
        
        // UI lock check (if shop or inv open, don't move)
        const uiOpen = !document.getElementById('island-shop-ui')?.classList.contains('hidden') || 
                       !document.getElementById('island-inventory-ui')?.classList.contains('hidden') ||
                       !document.getElementById('island-ferry-ui')?.classList.contains('hidden') ||
                       document.getElementById('island-room-overlay')?.style.display === 'flex';
        
        if (uiOpen) return;

        let dx = 0; let dy = 0;
        if (this.keys['ArrowUp'] || this.keys['KeyW']) dy -= this.player.speed;
        if (this.keys['ArrowDown'] || this.keys['KeyS']) dy += this.player.speed;
        if (this.keys['ArrowLeft'] || this.keys['KeyA']) dx -= this.player.speed;
        if (this.keys['ArrowRight'] || this.keys['KeyD']) dx += this.player.speed;

        if (dx !== 0 || dy !== 0) {
            // Move X
            if (!this.checkPlayerCollision(this.player.x + dx, this.player.y)) {
                this.player.x += dx;
            }
            // Move Y
            if (!this.checkPlayerCollision(this.player.x, this.player.y + dy)) {
                this.player.y += dy;
            }
            
            this.player.tickCount++;
            if (this.player.tickCount > 8) {
                this.player.tickCount = 0;
                this.player.frameIndex = (this.player.frameIndex + 1) % 4;
            }
        } else {
            this.player.frameIndex = 0;
        }

        // NPCs
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
            n.x = Math.max(100, Math.min(this.mapCols * this.tileSize - 100, n.x));
            n.y = Math.max(100, Math.min(this.mapRows * this.tileSize - 100, n.y));
        });

        this.camera.x = this.player.x - this.canvas.width / 2;
        this.camera.y = this.player.y - this.canvas.height / 2;

        this.handleInteractions();
    }

    handleInteractions() {
        const promptUI = document.getElementById('island-prompt');
        let promptActive = false;
        
        const pr = Math.floor(this.player.y / this.tileSize);
        const pc = Math.floor(this.player.x / this.tileSize);
        
        // Find adjacent interactive tiles
        let interacted = false;
        for (let r = pr - 1; r <= pr + 1; r++) {
            for (let c = pc - 1; c <= pc + 1; c++) {
                if (r < 0 || r >= this.mapRows || c < 0 || c >= this.mapCols) continue;
                const t = this.map[r][c];
                const pIdx = r * this.mapCols + c;
                
                if (this.state === 'private') {
                    if (t === this.TILE_PLOT) {
                        if (!this.ownedPlots.includes(pIdx)) {
                            let cost = Math.floor(400 * Math.pow(1.5, this.ownedPlots.length));
                            promptUI.textContent = `Press SPACE to Buy Plot (Cost: ${cost})`;
                            promptActive = true;
                            if (this.keys['Space']) { this.keys['Space'] = false; this.buyPlot(pIdx, cost); }
                            interacted = true;
                        } else if (this.plots[pIdx] && this.plots[pIdx].item_type === 'empty') {
                            promptUI.textContent = `Press SPACE to Build`;
                            promptActive = true;
                            if (this.keys['Space']) { this.keys['Space'] = false; this.openInventory(pIdx); }
                            interacted = true;
                        }
                    } else if (t === this.TILE_FERRY) {
                        promptUI.textContent = `Press SPACE to Travel`;
                        promptActive = true;
                        if (this.keys['Space']) { this.keys['Space'] = false; this.openFerry(); }
                        interacted = true;
                    } else if (t === this.TILE_PORTAL) {
                        promptUI.textContent = 'Press SPACE to Join Public Room';
                        promptActive = true;
                        if (this.keys['Space']) {
                            this.keys['Space'] = false;
                            document.getElementById('island-room-overlay').style.display = 'flex';
                        }
                        interacted = true;
                    }
                } else if (this.state === 'public') {
                    if (t === this.TILE_STORE) {
                        promptUI.textContent = 'Press SPACE to Shop';
                        promptActive = true;
                        if (this.keys['Space']) { this.keys['Space'] = false; this.openShop(); }
                        interacted = true;
                    } else if (t === this.TILE_BOARD) {
                        promptUI.textContent = 'Press SPACE to Join Matchmaking Queue';
                        promptActive = true;
                        if (this.keys['Space']) {
                            this.keys['Space'] = false;
                            enterMatchmaking(this.currentRoom);
                        }
                        interacted = true;
                    }
                }
                if (interacted) break;
            }
            if (interacted) break;
        }

        if (!promptActive) {
            promptUI.style.display = 'none';
        } else {
            promptUI.style.display = 'block';
        }
    }
    
    // --- API Calls ---
    async buyPlot(index, cost) {
        if(this.totalCoins < cost) {
            alert("Not enough coins!"); return;
        }
        try {
            const res = await fetch('/buy_plot', {
                method: 'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({username: this.currentUsername, plot_index: index})
            });
            const data = await res.json();
            if(data.success) {
                this.totalCoins = data.new_balance;
                this.ownedPlots.push(index);
                this.plots[index] = {item_type: 'empty'};
            } else {
                alert(data.error);
            }
        } catch(e) { console.error(e); }
    }

    openShop() {
        let ui = document.getElementById('island-shop-ui');
        if(ui) {
            ui.classList.remove('hidden');
            document.getElementById('shop-coins').innerText = this.totalCoins;
        }
    }

    async buyItem(itemType, cost) {
        if(this.totalCoins < cost) {
            alert("Not enough coins!"); return;
        }
        try {
            const res = await fetch('/buy_item', {
                method: 'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({username: this.currentUsername, item_type: itemType, cost: cost})
            });
            const data = await res.json();
            if(data.success) {
                this.totalCoins = data.new_balance;
                document.getElementById('shop-coins').innerText = this.totalCoins;
                await this.fetchIslandData(this.currentUsername); // refresh inventory
                alert("Bought " + itemType + "!");
            } else {
                alert(data.error);
            }
        } catch(e) { console.error(e); }
    }

    openInventory(plotIndex) {
        let ui = document.getElementById('island-inventory-ui');
        if(!ui) return;
        ui.classList.remove('hidden');
        let container = document.getElementById('inventory-items');
        container.innerHTML = '';
        if(this.inventory.length === 0) {
            container.innerHTML = '<i>No items. Buy some at the mainland store!</i>';
        } else {
            this.inventory.forEach(i => {
                if(i.quantity > 0) {
                    let div = document.createElement('div');
                    div.style = "background: #34495e; padding: 10px; border-radius: 5px; cursor: pointer; text-align: center;";
                    div.innerText = `${i.item_type} (${i.quantity})`;
                    div.onclick = () => {
                        this.placeItem(plotIndex, i.item_type);
                        ui.classList.add('hidden');
                    };
                    container.appendChild(div);
                }
            });
        }
    }

    async placeItem(plotIndex, itemType) {
        try {
            const res = await fetch('/place_item', {
                method: 'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({username: this.currentUsername, plot_index: plotIndex, item_type: itemType})
            });
            const data = await res.json();
            if(data.success) {
                await this.fetchIslandData(this.currentUsername);
            }
        } catch(e) { console.error(e); }
    }

    openFerry() {
        // Just dummy for now, requires proper UI setup
        alert("Ferry port is under construction! Check back later.");
    }

    // --- Drawing ---
    drawTile(r, c) {
        const x = c * this.tileSize;
        const y = r * this.tileSize;
        const t = this.map[r][c];

        // Base Grass
        if (this.grassPattern) {
            this.ctx.fillStyle = this.grassPattern;
        } else {
            this.ctx.fillStyle = '#2ecc71';
        }
        this.ctx.fillRect(x, y, this.tileSize, this.tileSize);

        if (t === this.TILE_ROAD) {
            this.ctx.fillStyle = '#95a5a6';
            this.ctx.fillRect(x, y, this.tileSize, this.tileSize);
            this.ctx.strokeStyle = '#bdc3c7';
            this.ctx.strokeRect(x, y, this.tileSize, this.tileSize);
        } else if (t === this.TILE_TREE) {
            this.ctx.fillStyle = '#8e44ad'; // dark trunk shadow
            this.ctx.beginPath();
            this.ctx.arc(x + 25, y + 25, 20, 0, Math.PI*2);
            this.ctx.fill();
            this.ctx.fillStyle = '#27ae60';
            this.ctx.beginPath();
            this.ctx.arc(x + 25, y + 20, 18, 0, Math.PI*2);
            this.ctx.fill();
        } else if (t === this.TILE_BUSH) {
            this.ctx.fillStyle = '#16a085';
            this.ctx.beginPath();
            this.ctx.arc(x + 25, y + 30, 15, 0, Math.PI*2);
            this.ctx.fill();
        } else if (t === this.TILE_PLOT) {
            this.ctx.fillStyle = '#d35400';
            this.ctx.fillRect(x+5, y+5, this.tileSize-10, this.tileSize-10);
            
            let pIdx = r * this.mapCols + c;
            if (this.ownedPlots.includes(pIdx)) {
                let item = this.plots[pIdx].item_type;
                if (item === 'house') {
                    this.ctx.fillStyle = '#c0392b';
                    this.ctx.fillRect(x+10, y+10, 30, 30);
                    this.ctx.fillStyle = '#f39c12';
                    this.ctx.beginPath(); this.ctx.moveTo(x+5, y+15); this.ctx.lineTo(x+25, y-5); this.ctx.lineTo(x+45, y+15); this.ctx.fill();
                } else if (item === 'bench') {
                    this.ctx.fillStyle = '#8e44ad';
                    this.ctx.fillRect(x+15, y+20, 20, 10);
                } else {
                    this.ctx.fillStyle = 'rgba(255,255,255,0.3)';
                    this.ctx.fillText("Empty", x+25, y+25);
                }
            } else {
                let cost = Math.floor(400 * Math.pow(1.5, this.ownedPlots.length));
                this.ctx.fillStyle = 'white';
                this.ctx.font = '12px Arial';
                this.ctx.fillText(cost + "c", x+25, y+30);
            }
        } else if (t === this.TILE_FERRY) {
            this.ctx.fillStyle = '#8e44ad';
            this.ctx.fillRect(x, y, this.tileSize, this.tileSize);
            this.ctx.fillStyle = 'white';
            this.ctx.fillText("FERRY", x+25, y+25);
        } else if (t === this.TILE_PORTAL) {
            this.ctx.fillStyle = '#3498db';
            this.ctx.fillRect(x, y, this.tileSize, this.tileSize);
            this.ctx.fillStyle = 'white';
            this.ctx.fillText("EXIT", x+25, y+25);
        } else if (t === this.TILE_STORE) {
            this.ctx.fillStyle = '#f1c40f';
            this.ctx.fillRect(x+5, y+5, 40, 40);
            this.ctx.fillStyle = 'black';
            this.ctx.fillText("STORE", x+25, y+30);
        } else if (t === this.TILE_BOARD) {
            this.ctx.fillStyle = '#34495e';
            this.ctx.fillRect(x+5, y+10, 40, 30);
            this.ctx.fillStyle = 'white';
            this.ctx.fillText("PLAY", x+25, y+30);
        }
    }

    drawCharacter(ctx, x, y, isMoving, tick, color, name, isPlayer) {
        ctx.save();
        ctx.translate(x, y - 10);
        const offset = isMoving ? Math.sin(tick * 0.4) * 8 : 0;
        ctx.fillStyle = '#ffccaa'; 
        ctx.fillRect(-15, -25, 30, 25);
        ctx.fillStyle = color;
        ctx.fillRect(-15, 0, 30, 20);
        ctx.fillStyle = '#2c3e50';
        ctx.fillRect(-12, 20, 10, 10 - offset); 
        ctx.fillRect(2, 20, 10, 10 + offset); 
        ctx.fillStyle = color;
        ctx.fillRect(-23, 0, 8, 15 + offset); 
        ctx.fillRect(15, 0, 8, 15 - offset); 
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

        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.ctx.save();
        
        // Simple camera clamp
        const mapW = this.mapCols * this.tileSize;
        const mapH = this.mapRows * this.tileSize;
        this.camera.x = Math.max(0, Math.min(mapW - this.canvas.width, this.camera.x));
        this.camera.y = Math.max(0, Math.min(mapH - this.canvas.height, this.camera.y));

        this.ctx.translate(-this.camera.x, -this.camera.y);

        this.ctx.textAlign = 'center';

        for (let r = 0; r < this.mapRows; r++) {
            for (let c = 0; c < this.mapCols; c++) {
                this.drawTile(r, c);
            }
        }

        // Sort entities by Y for depth
        let entities = [];
        entities.push({type: 'player', obj: this.player});
        this.npcs.forEach(n => entities.push({type: 'npc', obj: n}));
        
        entities.sort((a,b) => a.obj.y - b.obj.y);

        entities.forEach(e => {
            let o = e.obj;
            if (e.type === 'player') {
                let moving = (this.keys['ArrowUp'] || this.keys['ArrowDown'] || this.keys['ArrowLeft'] || this.keys['ArrowRight'] || this.keys['KeyW'] || this.keys['KeyA'] || this.keys['KeyS'] || this.keys['KeyD']);
                this.drawCharacter(this.ctx, o.x, o.y, moving, o.tickCount, '#3498db', this.currentUsername, true);
            } else {
                let moving = (o.vx !== 0 || o.vy !== 0);
                this.drawCharacter(this.ctx, o.x, o.y, moving, o.tickCount, '#e74c3c', o.name, false);
            }
        });

        this.ctx.restore();
        
        // Draw Coins UI
        if(this.state === 'private') {
            this.ctx.fillStyle = 'rgba(0,0,0,0.5)';
            this.ctx.fillRect(10, 10, 150, 40);
            this.ctx.fillStyle = '#f1c40f';
            this.ctx.font = '20px sans-serif';
            this.ctx.textAlign = 'left';
            this.ctx.fillText(`Coins: ${this.totalCoins}`, 20, 38);
        }
    }

    loop() {
        this.update();
        this.draw();
        requestAnimationFrame(this.loop);
    }
}

// Global instance
let islandEngine;
window.addEventListener('load', () => {
    islandEngine = new IslandEngine();
});
