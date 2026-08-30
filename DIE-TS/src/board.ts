import { Square, BoardData } from './types';
import { Entity, Angel, Devil, makeEntity } from './entity';

export class Board {
    public width: number;
    public height: number;
    public board: Square[][];
    public entities: Entity[] = [];
    public moved: boolean = false;

    constructor(data: BoardData) {
        this.width = data.width;
        this.height = data.height;
        this.board = Array.from({ length: this.height }, () =>
            Array(this.width).fill(Square.EMPTY)
        );

        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                this.board[y][x] = data.board[y][x] as Square;
            }
        }

        for (const ent of data.entities) {
            const created = makeEntity(ent.eid, ent.x, ent.y);
            if (created) this.entities.push(created);
        }
    }

    public getEntityAt(x: number, y: number): Entity | null {
        for (const entity of this.entities) {
            if (entity.x === x && entity.y === y) return entity;
        }
        return null;
    }

    public updateTurn(): 'PLAYING' | 'WIN' | 'LOSE' {
        if (!this.moved) return 'PLAYING';
        this.moved = false;

        const angel = this.entities.find(e => e instanceof Angel) as Angel | undefined;
        const devil = this.entities.find(e => e instanceof Devil) as Devil | undefined;

        // 1. Collecting items
        const players = [angel, devil];
        for (const player of players) {
            if (player && !('dead' in player.effects)) {
                for (const item of [...this.entities]) {
                    if (item.pickUp && item.x === player.x && item.y === player.y) {
                        if (item.eid === 'crown') {
                            if ('crown' in player.effects) {
                                player.effects['crown'].push(-1);
                            } else {
                                player.effects['crown'] = [-1];
                            }
                        } else if (item.eid === 'grail') {
                            player.effects['grail'] = true;
                        }
                        this.entities = this.entities.filter(e => e !== item);
                    }
                }
            }
        }

        // 2. Spikes kill everything
        for (const e of this.entities) {
            if (this.board[e.y][e.x] === Square.SPIKES) {
                e.effects['dead'] = true;
            }
        }

        // 3. Angel effects logic
        if (angel) {
            if ('grail' in angel.effects) return 'LOSE';
            if ('crown' in angel.effects) {
                angel.effects['crown'] = angel.effects['crown'].map((x: number) => x + 1);
                if (angel.effects['crown'].includes(3)) {
                    angel.effects['dead'] = true;
                }
                angel.effects['crown'] = angel.effects['crown'].filter((x: number) => x < 3);
                if (angel.effects['crown'].length === 0) {
                    delete angel.effects['crown'];
                }
            }
        }

        // 4. Devil effects logic
        if (devil) {
            if ('crown' in devil.effects) return 'LOSE';
            if ('grail' in devil.effects) {
                devil.effects['dead'] = true;
                delete devil.effects['grail'];
            }
        }

        // 5. Golden Rule of Simultaneous Death
        const aDead = angel && ('dead' in angel.effects);
        const dDead = devil && ('dead' in devil.effects);

        if (aDead && dDead) {
            return 'WIN';
        } else if (aDead || dDead) {
            if (angel) delete angel.effects['dead'];
            if (devil) delete devil.effects['dead'];
        }

        // Cleaning destroyed entities (e.g. crates on spikes)
        this.entities = this.entities.filter(e => !('dead' in e.effects));

        return 'PLAYING';
    }
}