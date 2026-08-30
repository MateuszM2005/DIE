import { Square } from './types';
import { Board } from './board';
import { Angel, Devil, Box, Crown, Grail } from './entity';
import { BitmapFontManager } from './font';

export class GameRenderer {
    private ctx: CanvasRenderingContext2D;
    private width: number;
    private height: number;

    constructor(ctx: CanvasRenderingContext2D, width: number, height: number) {
        this.ctx = ctx;
        this.width = width;
        this.height = height;
    }

    public drawMenu(font: BitmapFontManager, options: string[], selectedIndex: number): void {
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.width, this.height);

        font.drawString(this.ctx, 'DIE', this.width / 2, this.height / 4, 'center', 0.4);

        options.forEach((opt, idx) => {
            const isSelected = idx === selectedIndex;

            this.ctx.save();
            if (isSelected) {
                this.ctx.globalAlpha = 1.0; // Active option fully visible
            } else {
                this.ctx.globalAlpha = 180 / 255; // Exactly your set_alpha(180) from Pygame!
            }

            font.drawString(this.ctx, opt, this.width / 2, this.height / 2 + idx * 70, 'center', 0.15);
            this.ctx.restore(); // Restores globalAlpha = 1.0 for the rest of drawing
        });
    }

    public drawLevelSelect(font: BitmapFontManager, numLevels: number, currentSelection: number): void {
        // Clearing the screen to deep black
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.width, this.height);

        const cols = 5;
        const rows = Math.ceil(numLevels / cols); // For 15 levels it will come out to exactly 3 rows

        // We increase the gaps between tiles so the menu looks better on a large screen
        const spacingX = 150;
        const spacingY = 110;

        // We calculate the total dimensions of the digit grid itself
        const gridWidth = (cols - 1) * spacingX;
        const gridHeight = (rows - 1) * spacingY;

        // DYNAMIC CENTER: We determine the starting point (top-left corner of the grid)
        const gridStartX = (this.width - gridWidth) / 2;
        const gridStartY = (this.height - gridHeight) / 2;

        // "LEVELS" header drawn symmetrically above the level grid
        font.drawString(this.ctx, 'LEVELS', this.width / 2, gridStartY - 120, 'center', 0.2);

        // Rendering the level digits
        for (let i = 1; i <= numLevels; i++) {
            const col = (i - 1) % cols;
            const row = Math.floor((i - 1) / cols);

            // Each digit lands perfectly in its grid cell
            const x = gridStartX + col * spacingX;
            const y = gridStartY + row * spacingY;

            this.ctx.save();
            if (i === currentSelection) {
                this.ctx.globalAlpha = 1.0; // Active selection has full visibility
                font.drawString(this.ctx, String(i), x, y, 'center', 0.18);
            } else {
                this.ctx.globalAlpha = 140 / 255; // Inactive levels are transparent (set_alpha 140)
                font.drawString(this.ctx, String(i), x, y, 'center', 0.15);
            }
            this.ctx.restore();
        }

        // BACK button drawn symmetrically below the level grid
        this.ctx.save();
        this.ctx.globalAlpha = currentSelection === 0 ? 1.0 : 140 / 255;
        font.drawString(this.ctx, 'BACK', this.width / 2, gridStartY + gridHeight + 120, 'center', 0.15);
        this.ctx.restore();
    }

    public drawBoard(board: Board, textures: Record<string, HTMLImageElement | HTMLCanvasElement>, font: BitmapFontManager, movesCount: number): void {
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.width, this.height);

        const tileW = Math.floor(this.width / board.width);
        const tileH = Math.floor(this.height / board.height);
        const ts = Math.min(tileW, tileH);

        const offsetX = (this.width - board.width * ts) / 2;
        const offsetY = (this.height - board.height * ts) / 2;

        // Rendering background tiles and walls
        for (let row = 0; row < board.height; row++) {
            for (let col = 0; col < board.width; col++) {
                const x = offsetX + col * ts;
                const y = offsetY + row * ts;
                const tileType = Square[board.board[row][col]];

                if (tileType !== 'WALL' && tileType !== 'RIFT') {
                    if (textures['EMPTY']) this.ctx.drawImage(textures['EMPTY'], x, y, ts, ts);
                }
                if (textures[tileType] && tileType !== 'EMPTY') {
                    this.ctx.drawImage(textures[tileType], x, y, ts, ts);
                }
            }
        }

        // Rendering movable objects
        for (const entity of board.entities) {
            if ('dead' in entity.effects) continue;

            const ex = offsetX + entity.x * ts;
            const ey = offsetY + entity.y * ts;
            let key = '';

            if (entity instanceof Angel) {
                key = 'crown' in entity.effects ? 'ANGEL_CROWN' : 'ANGEL';
            } else if (entity instanceof Devil) {
                key = 'DEVIL';
            } else if (entity instanceof Box) {
                key = 'BOX';
            } else if (entity instanceof Crown) {
                key = 'CROWN';
            } else if (entity instanceof Grail) {
                key = 'GRAIL';
            }

            if (textures[key]) {
                this.ctx.drawImage(textures[key], ex, ey, ts, ts);
            }
        }

        // Move counter rendered from the original font graphics in the top-right corner
        font.drawString(this.ctx, String(movesCount), this.width - 40, 40, 'right', 0.15);
    }

    public drawLeaderboard(font: BitmapFontManager, records: any[]): void {
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.width, this.height);

        font.drawString(this.ctx, 'LEADERBOARD', this.width / 2, 80, 'center', 0.2);

        // If there are no scores at all in the database
        if (records.length === 0) {
            font.drawString(this.ctx, 'NO RECORDS YET', this.width / 2, this.height / 2, 'center', 0.1);
        } else {
            // Drawing table rows
            records.forEach((player, idx) => {
                const yPos = 180 + idx * 45;

                // We format the text: Rank, Nick (left-aligned), Levels, Moves
                const rankStr = `${player.rank}`;
                const nameStr = player.username.padEnd(12, ' ');
                const statsStr = `LVLS ${player.levels}  MOVES ${player.moves}`;

                // Full text line for one player
                const fullRow = `${rankStr}  ${nameStr}  ${statsStr}`;
                font.drawString(this.ctx, fullRow, this.width / 2, yPos, 'center', 0.09);
            });
        }

        this.ctx.save();
        this.ctx.globalAlpha = 150 / 255;
        font.drawString(this.ctx, 'PRESS ESC TO RETURN', this.width / 2, this.height - 60, 'center', 0.08);
        this.ctx.restore();
    }

    public drawLoginScreen(font: BitmapFontManager, username: string, password: string, activeField: number, errorMsg: string): void {
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.width, this.height);

        font.drawString(this.ctx, 'SIGN IN', this.width / 2, 80, 'center', 0.2);

        // Displaying the error (if it exists)
        if (errorMsg) {
            this.ctx.save();
            this.ctx.fillStyle = '#ff4d4d'; // Red color for network errors
            font.drawString(this.ctx, errorMsg, this.width / 2, 160, 'center', 0.08);
            this.ctx.restore();
        }

        // Field: USERNAME
        this.ctx.save();
        this.ctx.globalAlpha = activeField === 0 ? 1.0 : 140 / 255;
        const userDisplay = username ? username : '_';
        font.drawString(this.ctx, `LOGIN  ${userDisplay}`, this.width / 2, this.height / 2 - 80, 'center', 0.12);
        this.ctx.restore();

        // Field: PASSWORD (masked with X letters)
        this.ctx.save();
        this.ctx.globalAlpha = activeField === 1 ? 1.0 : 140 / 255;
        const maskedPassword = password ? 'X'.repeat(password.length) : '_';
        font.drawString(this.ctx, `PASS   ${maskedPassword}`, this.width / 2, this.height / 2, 'center', 0.12);
        this.ctx.restore();

        // Button: SUBMIT
        this.ctx.save();
        this.ctx.globalAlpha = activeField === 2 ? 1.0 : 140 / 255;
        font.drawString(this.ctx, 'CONFIRM', this.width / 2, this.height / 2 + 100, 'center', 0.12);
        this.ctx.restore();

        // Button: BACK
        this.ctx.save();
        this.ctx.globalAlpha = activeField === 3 ? 1.0 : 140 / 255;
        font.drawString(this.ctx, 'BACK', this.width / 2, this.height / 2 + 180, 'center', 0.12);
        this.ctx.restore();
    }

    public drawRegisterScreen(font: BitmapFontManager, username: string, password: string, activeField: number, errorMsg: string): void {
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.width, this.height);

        font.drawString(this.ctx, 'CREATE ACCOUNT', this.width / 2, 80, 'center', 0.2);

        if (errorMsg) {
            this.ctx.save();
            this.ctx.fillStyle = '#ff4d4d';
            font.drawString(this.ctx, errorMsg, this.width / 2, 160, 'center', 0.08);
            this.ctx.restore();
        }

        this.ctx.save();
        this.ctx.globalAlpha = activeField === 0 ? 1.0 : 140 / 255;
        const userDisplay = username ? username : '_';
        font.drawString(this.ctx, `NEW LOGIN  ${userDisplay}`, this.width / 2, this.height / 2 - 80, 'center', 0.12);
        this.ctx.restore();

        this.ctx.save();
        this.ctx.globalAlpha = activeField === 1 ? 1.0 : 140 / 255;
        const maskedPassword = password ? 'X'.repeat(password.length) : '_';
        font.drawString(this.ctx, `NEW PASS   ${maskedPassword}`, this.width / 2, this.height / 2, 'center', 0.12);
        this.ctx.restore();

        this.ctx.save();
        this.ctx.globalAlpha = activeField === 2 ? 1.0 : 140 / 255;
        font.drawString(this.ctx, 'REGISTER AND LOG IN', this.width / 2, this.height / 2 + 100, 'center', 0.12);
        this.ctx.restore();

        this.ctx.save();
        this.ctx.globalAlpha = activeField === 3 ? 1.0 : 140 / 255;
        font.drawString(this.ctx, 'BACK', this.width / 2, this.height / 2 + 180, 'center', 0.12);
        this.ctx.restore();
    }

    public drawChangePasswordScreen(font: BitmapFontManager, password: string, activeField: number, errorMsg: string, successMsg: string): void {
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, this.width, this.height);

        font.drawString(this.ctx, 'CHANGE PASSWORD', this.width / 2, 80, 'center', 0.2);

        if (errorMsg) {
            this.ctx.save();
            this.ctx.fillStyle = '#ff4d4d';
            font.drawString(this.ctx, errorMsg, this.width / 2, 160, 'center', 0.08);
            this.ctx.restore();
        }
        if (successMsg) {
            this.ctx.save();
            this.ctx.fillStyle = '#4dff4d'; // Green success message
            font.drawString(this.ctx, successMsg, this.width / 2, 160, 'center', 0.08);
            this.ctx.restore();
        }

        this.ctx.save();
        this.ctx.globalAlpha = activeField === 0 ? 1.0 : 140 / 255;
        const maskedPassword = password ? 'X'.repeat(password.length) : '_';
        font.drawString(this.ctx, `NEW PASS   ${maskedPassword}`, this.width / 2, this.height / 2 - 40, 'center', 0.12);
        this.ctx.restore();

        this.ctx.save();
        this.ctx.globalAlpha = activeField === 1 ? 1.0 : 140 / 255;
        font.drawString(this.ctx, 'SAVE NEW PASSWORD', this.width / 2, this.height / 2 + 60, 'center', 0.12);
        this.ctx.restore();

        this.ctx.save();
        this.ctx.globalAlpha = activeField === 2 ? 1.0 : 140 / 255;
        font.drawString(this.ctx, 'BACK', this.width / 2, this.height / 2 + 140, 'center', 0.12);
        this.ctx.restore();
    }
}