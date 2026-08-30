class Entity():
    def __init__(self, x=0, y=0, pick_up=False):
        self.x = x
        self.y = y
        self.pick_up = pick_up
        self.effects = dict()

    def swap(self, target):
        self.x, self.y, target.x, target.y = target.x, target.y, self.x, self.y

    def move(self, dir, board):
        new_x, new_y, cond = self.get_moves(dir, board)
        if cond:
            self.x = new_x
            self.y = new_y
            return True
        return False

    def get_moves(self, dir, board):
        from Board import Square

        new_x = self.x + dir[0]
        new_y = self.y + dir[1]

        if not (0 <= new_x < board.width and 0 <= new_y < board.height):
            return 0, 0, False

        target_tile = board.board[new_y][new_x]
        if target_tile not in (Square.EMPTY, Square.SPIKES):
            return 0, 0, False

        occupant = board.get_entity_at(new_x, new_y)
        if occupant is not None and not occupant.will_go(dir, board):
            return 0, 0, False

        return new_x, new_y, True

    def will_go(self, dir, board):
        out = self.move(dir, board)
        return out


class Angel(Entity):
    def __init__(self, x, y):
        super().__init__(x, y)

    def move(self, dir, board):
        new_x, new_y, cond = self.get_moves(dir, board)
        if cond:
            self.x = new_x
            self.y = new_y
            board.moved = True

    def get_moves(self, dir, board):
        from Board import Square

        new_x = self.x + dir[0]
        new_y = self.y + dir[1]

        if not (0 <= new_x < board.width and 0 <= new_y < board.height):
            return 0, 0, False

        if board.board[new_y][new_x] in (Square.WALL, Square.FIRE):
            return 0, 0, False

        occupant = board.get_entity_at(new_x, new_y)
        if occupant is not None and not occupant.pick_up and not occupant.will_go(dir, board):
            return 0, 0, False

        return new_x, new_y, True

    def will_go(self, dir, board):
        _, _, out = self.get_moves(dir, board)
        return out


class Devil(Entity):
    def __init__(self, x, y):
        super().__init__(x, y)

    def move(self, dir, board):
        new_x, new_y, cond = self.get_moves(dir, board)
        if cond:
            self.x = new_x
            self.y = new_y
            board.moved = True

    def get_moves(self, dir, board):
        from Board import Square

        new_x = self.x + dir[0]
        new_y = self.y + dir[1]

        if not (0 <= new_x < board.width and 0 <= new_y < board.height):
            return 0, 0, False

        if board.board[new_y][new_x] in (Square.WALL, Square.RIFT):
            return 0, 0, False

        occupant = board.get_entity_at(new_x, new_y)
        if occupant is not None and not occupant.pick_up and not occupant.will_go(dir, board):
            return 0, 0, False

        return new_x, new_y, True

    def will_go(self, dir, board):
        _, _, out = self.get_moves(dir, board)
        return out


class Box(Entity):
    def __init__(self, x, y):
        super().__init__(x, y)


class Crown(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, pick_up=True)


class Grail(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, pick_up=True)


def make_entity(data):
    eid = data["eid"]
    x = data["x"]
    y = data["y"]
    if eid == "angel":
        return Angel(x, y)
    if eid == "devil":
        return Devil(x, y)
    if eid == "box":
        return Box(x, y)
    if eid == "crown":
        return Crown(x, y)
    if eid == "grail":
        return Grail(x, y)
    return None