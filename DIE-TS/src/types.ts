export enum Square {
    EMPTY = 1,
    WALL = 2,
    SPIKES = 3,
    RIFT = 4,
    FIRE = 5
}

export type GameMode = 'MAIN_MENU' | 'LEVEL_SELECT' | 'PLAYING' | 'WIN_SCREEN' |
    'LOSE_SCREEN' | 'LEADERBOARD' | 'LOGIN_SCREEN' | 'REGISTER_SCREEN' | 'CHANGE_PASSWORD_SCREEN';

export interface EntityData {
    eid: string;
    x: number;
    y: number;
}

export interface BoardData {
    width: number;
    height: number;
    board: number[][];
    entities: EntityData[];
}

declare global {
    interface Window {
        GameConfig: {
            staticUrls: Record<string, string>;
        };
    }
}