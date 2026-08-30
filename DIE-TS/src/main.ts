export {};

import { GameMode, BoardData } from './types';
import { Board } from './board';
import { GameRenderer } from './renderer';
import { BitmapFontManager } from './font';
import { Angel, Devil } from './entity';

class GameController {
    private canvas: HTMLCanvasElement;
    private ctx: CanvasRenderingContext2D;
    private renderer: GameRenderer;
    private font: BitmapFontManager;
    private mode: GameMode = 'MAIN_MENU';

    private textures: Record<string, HTMLImageElement | HTMLCanvasElement> = {};
    private texturesLoaded = false;

    // DYNAMIC MENU (Starting values changed dynamically by checkAuthStatus)
    private menuOptions: string[] = [];
    private menuIdx = 0;
    private lvlSelectIdx = 1;
    private maxLevels = 15;

    // SESSION STATE
    private isLoggedIn = false;
    private currentUsername = '';

    // REMOVED: private leaderboardInterval: any = null;
    private leaderboardSource: EventSource | null = null;
    private leaderboardData: any[] = [];
    // SHARED FORM STATES
    private inputUsername = '';
    private inputPassword = '';
    private formActiveField = 0;
    private formError = '';
    private formSuccess = '';

    private board: Board | null = null;
    private gameStatus: 'PLAYING' | 'WIN' | 'LOSE' = 'PLAYING';
    private movesCount = 0;
    private history: string[] = [];

    private dirMap: Record<string, [number, number]> = {
        'w': [0, -1], 'arrowup': [0, -1],
        's': [0, 1],  'arrowdown': [0, 1],
        'a': [-1, 0], 'arrowleft': [-1, 0],
        'd': [1, 0],  'arrowright': [1, 0]
    };

    constructor(canvasId: string) {
        console.log("🚀 URGENT: Script main.js started and the constructor works!");
        this.canvas = document.getElementById(canvasId) as HTMLCanvasElement;
        this.ctx = this.canvas.getContext('2d')!;

        this.resizeCanvas();
        this.ctx.imageSmoothingEnabled = true;
        this.ctx.imageSmoothingQuality = 'high';

        this.renderer = new GameRenderer(this.ctx, this.canvas.width, this.canvas.height);

        window.addEventListener('resize', () => {
            this.resizeCanvas();
            this.renderer = new GameRenderer(this.ctx, this.canvas.width, this.canvas.height);
            this.ctx.imageSmoothingEnabled = true;
            this.ctx.imageSmoothingQuality = 'high';
        });

        this.font = new BitmapFontManager();
        this.init();
    }

    private async init(): Promise<void> {
        this.setupInput();
        try {
            await this.loadTextures();
            await this.font.loadFont();
            await this.checkAuthStatus();
            this.loop();
        } catch (error) {
            console.error("💥 Resource initialization error:", error);
        }
    }

    private async checkAuthStatus(): Promise<void> {
        try {
            const res = await fetch('/api/auth/status/');
            const data = await res.json();
            this.isLoggedIn = data.logged_in;
            this.currentUsername = data.username;
            this.updateMenuLabels();
        } catch (e) {
            console.error("Failed to fetch session status:", e);
        }
    }

    private updateMenuLabels(): void {
        if (this.isLoggedIn) {
            this.menuOptions = ['PLAY', 'LEADERBOARD', 'CHANGE PASS', 'LOG OUT'];
        } else {
            this.menuOptions = ['PLAY', 'LEADERBOARD', 'LOG IN', 'REGISTER'];
        }
        // Guard against the index going out of the array when changing mode
        if (this.menuIdx >= this.menuOptions.length) this.menuIdx = 0;
    }

    private async handleLogout(): Promise<void> {
        try {
            const res = await fetch('/api/auth/logout/');
            const data = await res.json();
            if (data.success) {
                this.isLoggedIn = false;
                this.currentUsername = '';
                this.updateMenuLabels();
            }
        } catch (e) {
            console.error("Logout error:", e);
        }
    }

    private async handleLoginSubmit(): Promise<void> {
        this.formError = '';
        if (!this.inputUsername || !this.inputPassword) {
            this.formError = 'FIELDS CAN NOT BE EMPTY';
            return;
        }
        try {
            const res = await fetch('/api/auth/login/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: this.inputUsername, password: this.inputPassword })
            });
            const data = await res.json();
            if (data.success) {
                this.isLoggedIn = true;
                this.currentUsername = data.username;
                this.updateMenuLabels();
                this.clearForm();
                this.mode = 'MAIN_MENU';
            } else {
                this.formError = data.error.toUpperCase();
            }
        } catch (e) { this.formError = 'SERVER ERROR'; }
    }

    private async handleRegisterSubmit(): Promise<void> {
        this.formError = '';
        if (!this.inputUsername || !this.inputPassword) {
            this.formError = 'FIELDS CAN NOT BE EMPTY';
            return;
        }
        try {
            const res = await fetch('/api/auth/register/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: this.inputUsername, password: this.inputPassword })
            });
            const data = await res.json();
            if (data.success) {
                this.isLoggedIn = true;
                this.currentUsername = data.username;
                this.updateMenuLabels();
                this.clearForm();
                this.mode = 'MAIN_MENU';
            } else {
                this.formError = data.error.toUpperCase();
            }
        } catch (e) { this.formError = 'SERVER ERROR'; }
    }

    private async handleChangePasswordSubmit(): Promise<void> {
        this.formError = '';
        this.formSuccess = '';
        if (!this.inputPassword) {
            this.formError = 'FIELD CAN NOT BE EMPTY';
            return;
        }
        try {
            const res = await fetch('/api/auth/change-password/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: this.inputPassword })
            });
            const data = await res.json();
            if (data.success) {
                this.formSuccess = 'PASSWORD CHANGED';
                this.inputPassword = '';
                setTimeout(() => { this.mode = 'MAIN_MENU'; }, 1500);
            } else {
                this.formError = data.error.toUpperCase();
            }
        } catch (e) { this.formError = 'SERVER ERROR'; }
    }

    private async submitLevelScore(level: number, moves: number): Promise<void> {
        if (!this.isLoggedIn) return; // Guest mode does not save scores

        console.log(`📡 [Score] Sending score in the background: Level ${level}, Moves: ${moves}`);
        try {
            await fetch('/api/score/submit/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ level: level, moves: moves })
            });
        } catch (e) {
            console.error("Failed to submit the score to the server:", e);
        }
    }

    private clearForm(): void {
        this.inputUsername = '';
        this.inputPassword = '';
        this.formActiveField = 0;
        this.formError = '';
        this.formSuccess = '';
    }

    private resizeCanvas(): void {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    private async loadTextures(): Promise<void> {
        const urls = window.GameConfig.staticUrls;
        const keysWithColorKey = ['FIRE', 'RIFT', 'SPIKES', 'BOX', 'ANGEL', 'DEVIL', 'CROWN', 'GRAIL', 'ANGEL_CROWN'];
        const promises = Object.entries(urls).map(([key, url]) => {
            return new Promise<void>((resolve) => {
                const img = new Image();
                img.src = url;
                img.onload = () => {
                    const uppercaseKey = key.toUpperCase();
                    if (keysWithColorKey.includes(uppercaseKey)) {
                        this.textures[uppercaseKey] = this.applyColorKeyFilter(img, 0, 0, 0);
                    } else {
                        this.textures[uppercaseKey] = img;
                    }
                    resolve();
                };
                img.onerror = () => {
                    const fallback = document.createElement('canvas');
                    fallback.width = 64;
                    fallback.height = 64;
                    this.textures[key.toUpperCase()] = fallback as any;
                    resolve();
                };
            });
        });
        await Promise.all(promises);
        this.texturesLoaded = true;
    }

    private applyColorKeyFilter(img: HTMLImageElement, r: number, g: number, b: number): HTMLCanvasElement {
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = img.width;
        tempCanvas.height = img.height;
        const tempCtx = tempCanvas.getContext('2d')!;
        tempCtx.drawImage(img, 0, 0);
        const imageData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
        const data = imageData.data;
        for (let i = 0; i < data.length; i += 4) {
            if (data[i] === r && data[i + 1] === g && data[i + 2] === b) {
                data[i + 3] = 0;
            }
        }
        tempCtx.putImageData(imageData, 0, 0);
        return tempCanvas;
    }

    private async loadLevel(num: number): Promise<void> {
        try {
            const res = await fetch(`/static/game/levels/${num}.json`);
            const data: BoardData = await res.json();
            this.board = new Board(data);
            this.movesCount = 0;
            this.history = [];
            this.gameStatus = 'PLAYING';
            this.mode = 'PLAYING';
        } catch (e) {
            console.error("Level load error:", e);
            this.mode = 'LEVEL_SELECT';
        }
    }

    private setupInput(): void {
        window.addEventListener('keydown', (e: KeyboardEvent) => {
            this.handleInput(e);
        });
    }

    private handleInput(e: KeyboardEvent): void {
        const key = e.key.toLowerCase();

        if (this.mode === 'MAIN_MENU') {
            if (key === 'w' || key === 'arrowup') {
                this.menuIdx = (this.menuIdx - 1 + this.menuOptions.length) % this.menuOptions.length;
            } else if (key === 's' || key === 'arrowdown') {
                this.menuIdx = (this.menuIdx + 1) % this.menuOptions.length;
            } else if (key === 'enter' || key === ' ') {
                const choice = this.menuOptions[this.menuIdx];
                if (choice === 'PLAY') {
                    this.mode = 'LEVEL_SELECT';
                    this.lvlSelectIdx = 1;
                } else if (choice === 'LEADERBOARD') {
                    this.leaderboardData = [];
                    this.leaderboardSource = new EventSource('/api/leaderboard/stream/');
                    this.leaderboardSource.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        this.leaderboardData = data.leaderboard;
                    };
                    this.leaderboardSource.onerror = (err) => {
                        console.error(" SSE stream error:", err);
                        if (this.leaderboardSource) this.leaderboardSource.close();
                    };
                    this.mode = 'LEADERBOARD';
                } else if (choice === 'LOG IN') {
                    this.clearForm();
                    this.mode = 'LOGIN_SCREEN';
                } else if (choice === 'REGISTER') {
                    this.clearForm();
                    this.mode = 'REGISTER_SCREEN';
                } else if (choice === 'CHANGE PASS') {
                    this.clearForm();
                    this.mode = 'CHANGE_PASSWORD_SCREEN';
                } else if (choice === 'LOG OUT') {
                    this.handleLogout();
                }
            }
        }
        else if (this.mode === 'LOGIN_SCREEN' || this.mode === 'REGISTER_SCREEN') {
            if (key === 'escape') { this.mode = 'MAIN_MENU'; return; }

            if (key === 'arrowup') {
                this.formActiveField = (this.formActiveField - 1 + 4) % 4;
                return;
            }
            if (key === 'arrowdown' || key === 'tab') {
                e.preventDefault();
                this.formActiveField = (this.formActiveField + 1) % 4;
                return;
            }
            if (key === 'enter') {
                if (this.formActiveField === 2) {
                    if (this.mode === 'LOGIN_SCREEN') this.handleLoginSubmit();
                    else this.handleRegisterSubmit();
                }
                else if (this.formActiveField === 3) this.mode = 'MAIN_MENU';
                else this.formActiveField = (this.formActiveField + 1) % 4;
                return;
            }
            if (e.key === 'Backspace') {
                if (this.formActiveField === 0) this.inputUsername = this.inputUsername.slice(0, -1);
                if (this.formActiveField === 1) this.inputPassword = this.inputPassword.slice(0, -1);
                return;
            }
            if (e.key.length === 1) {
                const char = e.key.toUpperCase();
                const allowed = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
                if (allowed.includes(char)) {
                    if (this.formActiveField === 0 && this.inputUsername.length < 12) this.inputUsername += char;
                    else if (this.formActiveField === 1 && this.inputPassword.length < 16) this.inputPassword += char;
                }
            }
        }
        else if (this.mode === 'CHANGE_PASSWORD_SCREEN') {
            if (key === 'escape') { this.mode = 'MAIN_MENU'; return; }

            if (key === 'arrowup') {
                this.formActiveField = (this.formActiveField - 1 + 3) % 3;
                return;
            }
            if (key === 'arrowdown' || key === 'tab') {
                e.preventDefault();
                this.formActiveField = (this.formActiveField + 1) % 3;
                return;
            }
            if (key === 'enter') {
                if (this.formActiveField === 1) this.handleChangePasswordSubmit();
                else if (this.formActiveField === 2) this.mode = 'MAIN_MENU';
                else this.formActiveField = (this.formActiveField + 1) % 3;
                return;
            }
            if (e.key === 'Backspace' && this.formActiveField === 0) {
                this.inputPassword = this.inputPassword.slice(0, -1);
                return;
            }
            if (e.key.length === 1 && this.formActiveField === 0) {
                const char = e.key.toUpperCase();
                const allowed = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
                if (allowed.includes(char)) {
                    if (this.inputPassword.length < 16) this.inputPassword += char;
                }
            }
        }
        else if (this.mode === 'LEADERBOARD') {
            if (key === 'escape' || key === 'enter' || key === ' ') {
                if (this.leaderboardSource) {
                    this.leaderboardSource.close();
                    this.leaderboardSource = null;
                    console.log("🔌 SSE stream was safely disconnected.");
                }
                this.mode = 'MAIN_MENU';
            }
        }
        else if (this.mode === 'LEVEL_SELECT') {
            if (key === 'a' || key === 'arrowleft') {
                this.lvlSelectIdx = this.lvlSelectIdx === 0 ? this.maxLevels : this.lvlSelectIdx - 1;
            } else if (key === 'd' || key === 'arrowright') {
                this.lvlSelectIdx = (this.lvlSelectIdx + 1) % (this.maxLevels + 1);
            } else if (key === 'w' || key === 'arrowup') {
                if (this.lvlSelectIdx === 0) this.lvlSelectIdx = 13;
                else if (this.lvlSelectIdx >= 1 && this.lvlSelectIdx <= 5) this.lvlSelectIdx = 0;
                else this.lvlSelectIdx -= 5;
            } else if (key === 's' || key === 'arrowdown') {
                if (this.lvlSelectIdx === 0) this.lvlSelectIdx = 3;
                else if (this.lvlSelectIdx >= 11 && this.lvlSelectIdx <= 15) this.lvlSelectIdx = 0;
                else this.lvlSelectIdx += 5;
            } else if (key === 'enter' || key === ' ') {
                if (this.lvlSelectIdx === 0) this.mode = 'MAIN_MENU';
                else this.loadLevel(this.lvlSelectIdx);
            } else if (key === 'escape') {
                this.mode = 'MAIN_MENU';
            }
        }
        else if (this.mode === 'PLAYING' && this.board) {
            if (key === 'escape') { this.mode = 'LEVEL_SELECT'; return; }
            if (key === 'q' && this.history.length > 0) {
                const previousState = this.history.pop()!;
                this.board = new Board(JSON.parse(previousState));
                this.gameStatus = 'PLAYING';
                this.movesCount--;
                return;
            }
            if (this.gameStatus === 'PLAYING' && key in this.dirMap) {
                const dir = this.dirMap[key];
                const stateSnapshot = JSON.stringify({
                    width: this.board.width,
                    height: this.board.height,
                    board: this.board.board,
                    entities: this.board.entities.map(e => ({ eid: e.eid, x: e.x, y: e.y }))
                });
                this.history.push(stateSnapshot);
                let moved = false;
                const players = this.board.entities.filter(e => e instanceof Angel || e instanceof Devil);
                const oldPositions = players.map(p => ({ e: p, x: p.x, y: p.y }));
                for (const player of players) player.move(dir, this.board);
                for (const pos of oldPositions) if (pos.e.x !== pos.x || pos.e.y !== pos.y) moved = true;
                if (moved) this.movesCount++;
                else this.history.pop();
                this.gameStatus = this.board.updateTurn();
                if (this.gameStatus === 'WIN'){
                    this.submitLevelScore(this.lvlSelectIdx, this.movesCount);
                    setTimeout(() => { this.mode = 'LEVEL_SELECT'; }, 1500);
                }
            }
        }
    }

    private loop = (): void => {
        this.render();
        requestAnimationFrame(this.loop);
    };

    private render(): void {
        if (!this.texturesLoaded || !this.font.loaded) {
            this.ctx.fillStyle = '#000000';
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
            return;
        }

        switch (this.mode) {
            case 'MAIN_MENU':
                this.renderer.drawMenu(this.font, this.menuOptions, this.menuIdx);
                break;
            case 'LEVEL_SELECT':
                this.renderer.drawLevelSelect(this.font, this.maxLevels, this.lvlSelectIdx);
                break;
            case 'LEADERBOARD':
                this.renderer.drawLeaderboard(this.font, this.leaderboardData);
                break;
            case 'LOGIN_SCREEN':
                this.renderer.drawLoginScreen(this.font, this.inputUsername, this.inputPassword, this.formActiveField, this.formError);
                break;
            case 'REGISTER_SCREEN':
                this.renderer.drawRegisterScreen(this.font, this.inputUsername, this.inputPassword, this.formActiveField, this.formError);
                break;
            case 'CHANGE_PASSWORD_SCREEN':
                this.renderer.drawChangePasswordScreen(this.font, this.inputPassword, this.formActiveField, this.formError, this.formSuccess);
                break;
            case 'PLAYING':
                if (this.board) this.renderer.drawBoard(this.board, this.textures, this.font, this.movesCount);
                break;
        }
    }
}

if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', () => { new GameController('gameCanvas'); });
} else { new GameController('gameCanvas'); }