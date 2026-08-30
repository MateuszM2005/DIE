from enum import Enum
from Entity import *
import json

class Square(Enum):
    EMPTY = 1
    WALL = 2
    SPIKES = 3
    RIFT = 4
    FIRE = 5

class Board():
    def __init__(self, filepath):
        with open(filepath, 'r') as f:
            dict = json.load(f)
        self.width = dict["width"]
        self.height = dict["height"]
        self.board = [[Square.EMPTY for x in range(self.width)] for y in range(self.height)]
        for y in range(self.height):
            row = dict["board"][y]
            for x in range(self.width):
                self.board[y][x] = Square(row[x])

        self.entities = []
        for entity in dict["entities"]:
            self.entities.append(make_entity(entity))
        self.moved = False

    def get_entity_at(self, x, y):
        for entity in self.entities:
            if entity.x == x and entity.y == y:
                return entity
        return None

    def update_turn(self):
        if not self.moved: return "PLAYING"
        self.moved = False
        angel = next((e for e in self.entities if isinstance(e, Angel)), None)
        devil = next((e for e in self.entities if isinstance(e, Devil)), None)

        for player in [angel, devil]:
            if player and "dead" not in player.effects:
                for item in list(self.entities):
                    if item.pick_up and item.x == player.x and item.y == player.y:
                        if isinstance(item, Crown):
                            if "crown" in player.effects:
                                player.effects["crown"].append(-1)
                            else:
                                player.effects["crown"] = [-1]
                        elif isinstance(item, Grail):
                            player.effects["grail"] = True
                        self.entities.remove(item)

        for e in self.entities:
            if self.board[e.y][e.x] == Square.SPIKES:
                e.effects["dead"] = True

        if angel:
            if "grail" in angel.effects:
                return "LOSE"
            if "crown" in angel.effects:
                angel.effects["crown"] = [x + 1 for x in angel.effects["crown"]]
                if 3 in angel.effects["crown"]:
                    angel.effects["dead"] = True
                angel.effects["crown"] = [x for x in angel.effects["crown"] if x < 3]
                if not angel.effects["crown"]:
                    angel.effects.pop("crown", None)

        if devil:
            if "crown" in devil.effects:
                return "LOSE"
            if "grail" in devil.effects:
                devil.effects["dead"] = True
                devil.effects.pop("grail", None)

        a_dead = angel and "dead" in angel.effects
        d_dead = devil and "dead" in devil.effects
        if a_dead and d_dead:
            return "WIN"
        elif a_dead or d_dead:
            if angel:
                angel.effects.pop("dead", None)
            if devil:
                devil.effects.pop("dead", None)

        self.entities = [e for e in self.entities if "dead" not in e.effects]

        return "PLAYING"
