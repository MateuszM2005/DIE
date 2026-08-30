import { Square } from './types';
import { Board } from './board';

export class Entity {
    public x: number;
    public y: number;
    public pickUp: boolean;
    public eid: string;
    public effects: Record<string, any> = {};

    constructor(eid: string, x = 0, y = 0, pickUp = false) {
        this.eid = eid;
        this.x = x;
        this.y = y;
        this.pickUp = pickUp;
    }

    public swap(target: Entity): void {
        const tempX = this.x;
        const tempY = this.y;
        this.x = target.x;
        this.y = target.y;
        target.x = tempX;
        target.y = tempY;
    }

    public move(dir: [number, number], board: Board): boolean {
        const [newX, newY, cond] = this.getMoves(dir, board);
        if (cond) {
            this.x = newX;
            this.y = newY;
            return true;
        }
        return false;
    }

    public getMoves(dir: [number, number], board: Board): [number, number, boolean] {
        const newX = this.x + dir[0];
        const newY = this.y + dir[1];

        if (!(0 <= newX && newX < board.width && 0 <= newY && newY < board.height)) {
            return [0, 0, false];
        }

        const targetTile = board.board[newY][newX];
        if (targetTile !== Square.EMPTY && targetTile !== Square.SPIKES) {
            return [0, 0, false];
        }

        const occupant = board.getEntityAt(newX, newY);
        if (occupant !== null && !occupant.willGo(dir, board)) {
            return [0, 0, false];
        }

        return [newX, newY, true];
    }

    public willGo(dir: [number, number], board: Board): boolean {
        return this.move(dir, board);
    }
}

export class Angel extends Entity {
    constructor(x: number, y: number) {
        super('angel', x, y, false);
    }

    public override move(dir: [number, number], board: Board): boolean {
        const [newX, newY, cond] = this.getMoves(dir, board);
        if (cond) {
            this.x = newX;
            this.y = newY;
            board.moved = true;
            return true;
        }
        return false;
    }

    public override getMoves(dir: [number, number], board: Board): [number, number, boolean] {
        const newX = this.x + dir[0];
        const newY = this.y + dir[1];

        if (!(0 <= newX && newX < board.width && 0 <= newY && newY < board.height)) {
            return [0, 0, false];
        }

        const tile = board.board[newY][newX];
        if (tile === Square.WALL || tile === Square.FIRE) {
            return [0, 0, false];
        }

        const occupant = board.getEntityAt(newX, newY);
        if (occupant !== null && !occupant.pickUp && !occupant.willGo(dir, board)) {
            return [0, 0, false];
        }

        return [newX, newY, true];
    }

    public override willGo(dir: [number, number], board: Board): boolean {
        const [,, out] = this.getMoves(dir, board);
        return out;
    }
}

export class Devil extends Entity {
    constructor(x: number, y: number) {
        super('devil', x, y, false);
    }

    public override move(dir: [number, number], board: Board): boolean {
        const [newX, newY, cond] = this.getMoves(dir, board);
        if (cond) {
            this.x = newX;
            this.y = newY;
            board.moved = true;
            return true;
        }
        return false;
    }

    public override getMoves(dir: [number, number], board: Board): [number, number, boolean] {
        const newX = this.x + dir[0];
        const newY = this.y + dir[1];

        if (!(0 <= newX && newX < board.width && 0 <= newY && newY < board.height)) {
            return [0, 0, false];
        }

        const tile = board.board[newY][newX];
        if (tile === Square.WALL || tile === Square.RIFT) {
            return [0, 0, false];
        }

        const occupant = board.getEntityAt(newX, newY);
        if (occupant !== null && !occupant.pickUp && !occupant.willGo(dir, board)) {
            return [0, 0, false];
        }

        return [newX, newY, true];
    }

    public override willGo(dir: [number, number], board: Board): boolean {
        const [,, out] = this.getMoves(dir, board);
        return out;
    }
}

export class Box extends Entity {
    constructor(x: number, y: number) {
        super('box', x, y, false);
    }
}

export class Crown extends Entity {
    constructor(x: number, y: number) {
        super('crown', x, y, true);
    }
}

export class Grail extends Entity {
    constructor(x: number, y: number) {
        super('grail', x, y, true);
    }
}

export function makeEntity(eid: string, x: number, y: number): Entity | null {
    if (eid === 'angel') return new Angel(x, y);
    if (eid === 'devil') return new Devil(x, y);
    if (eid === 'box') return new Box(x, y);
    if (eid === 'crown') return new Crown(x, y);
    if (eid === 'grail') return new Grail(x, y);
    return null;
}