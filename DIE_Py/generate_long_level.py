"""
Generate a DIE level whose shortest win is as long as possible.

Objective
---------
Both characters always receive the same direction. A walk can loop forever
on almost every solvable board, so "the longest path" is infinite and not a
useful target. The finite puzzle is:

    maximize, over levels, the length of the SHORTEST winning move sequence.

Spikes do not change movement. With no boxes and no items the whole state is
the pair of positions, so a shortest win is at most W*H*W*H - 1. Finding the
level that attains the maximum is a search over tile layouts (4^(W*H)
movement-relevant boards, or 5^(W*H) if empty and spikes are counted apart).
For 5x5 that is about 10^15 boards. Each board is cheap to score. The product
is not something you enumerate.

This script therefore:
  1. Scores a board exactly, by BFS, for the no-box no-item rules.
  2. Hill-climbs / anneals layouts and start cells.
  3. Greedily inserts boxes and re-solves with the real turn rules.
  4. Replays the winner on Board.py, then writes a new tagged JSON file.
     The tag is the filename. An existing file is never replaced.

Tile codes match the game: 1 empty, 2 wall, 3 spikes, 4 rift, 5 fire.
Entity order in the file is angel, then devil, then boxes. The desktop client
moves Angel and Devil in that list order, and the solver assumes angel first.

How to use
----------
Run it from DIE_Py so Board.py imports. Each run writes a new file under
generated/. The name is the tag, for example generated/long_7x7_m77_01.json.
A later run never replaces that file; the next 77-move 7x7 would be _02.

    python generate_long_level.py
    python generate_long_level.py --width 7 --height 7 --seconds 50
    python generate_long_level.py --width 5 --height 5 --seconds 45 --boxes 2
    python generate_long_level.py --out generated --seconds 30
    python generate_long_level.py --test
    python generate_long_level.py --help

--width, --height   Board size. No maximum. Default 5x5. --seconds is what
                    stops the run. A board whose position graph does not finish
                    inside the remaining time is skipped.
--seconds           Wall-clock search budget. Default 20. Longer is a better
                    chance of a longer shortest win, not a guarantee.
--workers           Parallel searches. Default is one less than the CPU count.
--boxes             How many boxes to try adding after the terrain search.
                    A box is kept only when it makes the shortest win longer.
                    Default 2.
--out               Directory for the new file. Default is generated/ next to
                    this script. Pass a directory, not a .json path.
--test              Check the movement model against Board.py and exit.

The console prints the tag, the move count, the path as RLDU and as WASD,
and a small map. The JSON also stores "tag" and "shortest". Copy the file
into levels/ and point the game at it if you want to play it; this script
does not edit the level menu.

CODE BY GROK, NOT EVEN REVIEWED, ONE OF THE LEVELS FROM THIS GENERATOR WAS USED IN THE 15, I WON'T TELL WHICH ONE :).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import tempfile
import time
from collections import deque

from Board import Board
from Entity import Angel, Box, Crown, Devil, Grail

# Movement-tile codes used inside the search (spikes are chosen afterwards).
OPEN, WALL, FIRE, RIFT = 0, 1, 2, 3
# Game tile codes.
G_EMPTY, G_WALL, G_SPIKES, G_RIFT, G_FIRE = 1, 2, 3, 4, 5

DIR_VEC = ((1, 0), (-1, 0), (0, 1), (0, -1))  # R L D U
DIR_NAME = "RLDU"
# Above this many position pairs, distances live in dicts so a huge board
# does not allocate the full table before --seconds can stop the search.
ARRAY_STATE_LIMIT = 1_000_000


def make_next(width: int, height: int):
    """NEXT[direction][cell] = neighbor index, or -1 if the step leaves the board."""
    n = width * height
    nxt = [[-1] * n for _ in range(4)]
    for y in range(height):
        for x in range(width):
            i = y * width + x
            for d, (dx, dy) in enumerate(DIR_VEC):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    nxt[d][i] = ny * width + nx
    return nxt


def step_pair(a: int, d: int, na: int, nd: int, block_a: int, block_d: int, nxt_dir):
    """One coupled step. Angel is resolved first, matching Entity list order.

    block_* bits mark cells that character cannot enter.
    nxt_dir[i] is the geometric neighbor, or -1 off the board.
    """
    if a != d:
        if na == d:
            # Devil is in front of angel.
            d_ok = nd != -1 and (block_d & (1 << nd)) == 0
            a_ok = d_ok and (block_a & (1 << d)) == 0
            return (d if a_ok else a, nd if d_ok else d)
        if nd == a:
            # Angel is in front of devil.
            a_ok = na != -1 and (block_a & (1 << na)) == 0
            d_ok = a_ok and (block_d & (1 << a)) == 0
            return (na if a_ok else a, a if d_ok else d)
        a_ok = na != -1 and (block_a & (1 << na)) == 0
        d_ok = nd != -1 and (block_d & (1 << nd)) == 0
        return (na if a_ok else a, nd if d_ok else d)

    # Already stacked. Stacking cannot be created from distinct cells
    # (checked by the test), but it is preserved when both can advance.
    a_ok = na != -1 and (block_a & (1 << na)) == 0
    if not a_ok:
        d_ok = na != -1 and (block_d & (1 << na)) == 0
        return (a, na if d_ok else a)
    further = nxt_dir[na]
    can_leave = further != -1 and (block_a & (1 << further)) == 0
    d_ok = can_leave and (block_d & (1 << na)) == 0
    if d_ok:
        return (na, na)
    return (na, a)


def blocks_from_tiles(tiles: bytes):
    """Return (block_angel, block_devil) bitmasks. OPEN cells block neither."""
    block_a = 0
    block_d = 0
    for i, t in enumerate(tiles):
        if t == WALL or t == FIRE:
            block_a |= 1 << i
        if t == WALL or t == RIFT:
            block_d |= 1 << i
    return block_a, block_d


def open_mask(block_a: int, block_d: int, n: int) -> int:
    both = block_a | block_d
    full = (1 << n) - 1
    return full ^ both


def bfs_dist(block_a: int, block_d: int, a0: int, d0: int, nxt, n: int, deadline=None):
    """Distances from (a0, d0). Also the shortest walk of positive length back to the start.

    A move that changes nothing is not a turn, so the start is not an immediate win
    even when both already stand on spikes. Coming back to that setup is a real solution.

    Returns None if `deadline` (a perf_counter value) passes before the graph is finished.
    A partial distance table is not a proven shortest win, so the caller skips that board.
    Boards with more than ARRAY_STATE_LIMIT position pairs use dicts, so a huge grid
    does not allocate the full table before the clock can stop it.
    """
    nn = n * n
    start = a0 * n + d0
    use_dict = nn > ARRAY_STATE_LIMIT
    if use_dict:
        dist = {start: 0}
        parent = {}
        move = {}
        q = deque([start])
    else:
        dist = [-1] * nn
        parent = [-1] * nn
        move = [-1] * nn
        q = [0] * nn
        q[0] = start
        dist[start] = 0
    qh = 0
    qt = 1
    expanded = 0
    return_len = -1
    return_pred = -1
    return_move = -1

    def timed_out():
        return deadline is not None and time.perf_counter() >= deadline

    while True:
        if use_dict:
            if not q:
                break
            cur = q.popleft()
        else:
            if qh >= qt:
                break
            cur = q[qh]
            qh += 1
        expanded += 1
        if expanded % 4096 == 0 and timed_out():
            return None
        a = cur // n
        d = cur - a * n
        base = dist[cur]
        for di in range(4):
            col = nxt[di]
            na = col[a]
            nd = col[d]
            na2, nd2 = step_pair(a, d, na, nd, block_a, block_d, col)
            if na2 == a and nd2 == d:
                continue
            nxt_i = na2 * n + nd2
            step_len = base + 1
            if nxt_i == start and (return_len < 0 or step_len < return_len):
                return_len = step_len
                return_pred = cur
                return_move = di
            unseen = dist.get(nxt_i, -1) == -1 if use_dict else dist[nxt_i] == -1
            if unseen:
                dist[nxt_i] = step_len
                parent[nxt_i] = cur
                move[nxt_i] = di
                if use_dict:
                    q.append(nxt_i)
                else:
                    q[qt] = nxt_i
                qt += 1
    return dist, parent, move, return_len, return_pred, return_move


def best_spikes(dist, a0: int, d0: int, open_bits: int, n: int, return_len: int, deadline=None):
    """
    Spike cells are a subset S of cells both characters can stand on.
    Both standing in S is a win. A larger S only adds winning pairs, so the
    best S has one cell or two. If the start itself is one of those pairs,
    the walk has to leave and come back; that length is return_len, not 0.
    """
    cells = [i for i in range(n) if open_bits & (1 << i)]
    best = -1
    best_s = None
    best_target = None
    start_idx = a0 * n + d0
    as_dict = isinstance(dist, dict)

    def dist_at(idx):
        if as_dict:
            return dist.get(idx, -1)
        return dist[idx]

    def consider(s, target_dist, target):
        nonlocal best, best_s, best_target
        if target_dist > best:
            best = target_dist
            best_s = s
            best_target = target

    def rectangle(group):
        if deadline is not None and time.perf_counter() >= deadline:
            return False
        chosen = None
        chosen_d = 10**9
        if a0 in group and d0 in group and return_len > 0 and return_len < chosen_d:
            chosen_d = return_len
            chosen = -1
        for p in group:
            for q in group:
                idx = p * n + q
                if idx == start_idx:
                    continue
                d = dist_at(idx)
                if 0 < d < chosen_d:
                    chosen_d = d
                    chosen = idx
        if chosen is None:
            return True
        consider(group, chosen_d, chosen)
        return True

    for s in cells:
        if not rectangle((s,)):
            break
    else:
        for i, s1 in enumerate(cells):
            stopped = False
            for s2 in cells[i + 1 :]:
                if not rectangle((s1, s2)):
                    stopped = True
                    break
            if stopped:
                break
    return best, best_s, best_target


def path_to(parent, move, target, n: int) -> str:
    chars = []
    cur = target
    as_dict = isinstance(parent, dict)
    while True:
        prev = parent.get(cur, -1) if as_dict else parent[cur]
        if prev == -1:
            break
        step = move.get(cur, -1) if as_dict else move[cur]
        chars.append(DIR_NAME[step])
        cur = prev
    chars.reverse()
    return "".join(chars)


def score_layout(tiles: bytes, a0: int, d0: int, nxt, n: int, deadline=None):
    block_a, block_d = blocks_from_tiles(tiles)
    if block_a & (1 << a0) or block_d & (1 << d0):
        return -1, None, None, None
    found = bfs_dist(block_a, block_d, a0, d0, nxt, n, deadline)
    if found is None:
        return -1, None, None, None
    dist, parent, move, return_len, return_pred, return_move = found
    opens = open_mask(block_a, block_d, n)
    length, spikes, target = best_spikes(dist, a0, d0, opens, n, return_len, deadline)
    if length < 0 or target is None:
        return -1, None, None, None
    if target == -1:
        route = path_to(parent, move, return_pred, n) + DIR_NAME[return_move]
    else:
        route = path_to(parent, move, target, n)
    if len(route) != length:
        raise RuntimeError(f"path length {len(route)} != score {length}")
    return length, spikes, route, (block_a, block_d)


def legal_start(tiles: bytes, who: str) -> list[int]:
    out = []
    for i, t in enumerate(tiles):
        if who == "angel" and t not in (WALL, FIRE):
            out.append(i)
        elif who == "devil" and t not in (WALL, RIFT):
            out.append(i)
    return out


def random_layout(rng: random.Random, n: int, wall_p=0.28, fire_p=0.08, rift_p=0.08):
    tiles = bytearray(n)
    for i in range(n):
        r = rng.random()
        if r < wall_p:
            tiles[i] = WALL
        elif r < wall_p + fire_p:
            tiles[i] = FIRE
        elif r < wall_p + fire_p + rift_p:
            tiles[i] = RIFT
        else:
            tiles[i] = OPEN
    return bytes(tiles)


def serpent(width: int, height: int) -> bytes:
    """One-cell snake folded in rows. Cuts the off-path shortcuts with walls."""
    tiles = bytearray([OPEN]) * (width * height)
    for y in range(height):
        for x in range(width):
            i = y * width + x
            if y % 2 == 1:
                # Odd rows keep a single bridge so the snake connects.
                bridge = width - 1 if ((y - 1) // 2) % 2 == 0 else 0
                if x != bridge:
                    tiles[i] = WALL
    return bytes(tiles)


def polish(tiles, a0, d0, nxt, n, rng, deadline):
    """Coordinate descent on tile types, then the best start pair for that board."""
    tiles = bytearray(tiles)
    length, spikes, path, _ = score_layout(bytes(tiles), a0, d0, nxt, n, deadline)
    if length < 0:
        return None
    for _sweep in range(5):
        if time.perf_counter() >= deadline:
            break
        changed = False
        order = list(range(n))
        rng.shuffle(order)
        for i in order:
            base = tiles[i]
            best_t, best_l = base, length
            best_sp, best_pa = spikes, path
            for t in (OPEN, WALL, FIRE, RIFT):
                if t == base:
                    continue
                if i == a0 and t in (WALL, FIRE):
                    continue
                if i == d0 and t in (WALL, RIFT):
                    continue
                tiles[i] = t
                got, sp, pa, _ = score_layout(bytes(tiles), a0, d0, nxt, n, deadline)
                if got > best_l:
                    best_l, best_t, best_sp, best_pa = got, t, sp, pa
            tiles[i] = best_t
            if best_t != base:
                changed = True
                length, spikes, path = best_l, best_sp, best_pa
        if not changed:
            break

    frozen = bytes(tiles)
    opts_a = legal_start(frozen, "angel")
    opts_d = legal_start(frozen, "devil")
    for a in opts_a:
        if time.perf_counter() >= deadline:
            break
        for d in opts_d:
            got, sp, pa, _ = score_layout(frozen, a, d, nxt, n, deadline)
            if got > length:
                length, a0, d0, spikes, path = got, a, d, sp, pa
    return length, frozen, a0, d0, path, spikes


def kick_tiles(tiles, rng, k):
    tiles = bytearray(tiles)
    n = len(tiles)
    for _ in range(k):
        tiles[rng.randrange(n)] = rng.choice((OPEN, WALL, FIRE, RIFT))
    return bytes(tiles)


def anneal_worker(args):
    """Random seeds, then iterated local search. Exact score on every candidate."""
    seed, width, height, _iterations, seconds = args
    rng = random.Random(seed)
    n = width * height
    nxt = make_next(width, height)
    deadline = time.perf_counter() + seconds
    best = (-1, None, None, None, None, None)
    it = 0

    def note(result):
        nonlocal best
        if result is not None and result[0] > best[0]:
            best = result

    for layout in (serpent(width, height), bytes([OPEN]) * n):
        if time.perf_counter() >= deadline:
            break
        opts_a = legal_start(layout, "angel")
        opts_d = legal_start(layout, "devil")
        if not opts_a or not opts_d:
            continue
        note(polish(layout, rng.choice(opts_a), rng.choice(opts_d), nxt, n, rng, deadline))
        it += 1

    while time.perf_counter() < deadline:
        seed_best = None
        for _ in range(30):
            if time.perf_counter() >= deadline:
                break
            tiles = random_layout(
                rng,
                n,
                wall_p=rng.uniform(0.18, 0.55),
                fire_p=rng.uniform(0.0, 0.14),
                rift_p=rng.uniform(0.0, 0.14),
            )
            opts_a = legal_start(tiles, "angel")
            opts_d = legal_start(tiles, "devil")
            if not opts_a or not opts_d:
                continue
            a0, d0 = rng.choice(opts_a), rng.choice(opts_d)
            length, spikes, path, _ = score_layout(tiles, a0, d0, nxt, n, deadline)
            it += 1
            if length > best[0]:
                best = (length, tiles, a0, d0, path, spikes)
            if seed_best is None or length > seed_best[0]:
                seed_best = (length, tiles, a0, d0, path, spikes)
        if seed_best is None or seed_best[0] < 0:
            continue
        current = polish(seed_best[1], seed_best[2], seed_best[3], nxt, n, rng, deadline)
        note(current)
        it += 1
        if current is None:
            continue
        for k in (2, 3, 5):
            if time.perf_counter() >= deadline:
                break
            kicked = kick_tiles(current[1], rng, k)
            opts_a = legal_start(kicked, "angel")
            opts_d = legal_start(kicked, "devil")
            if not opts_a or not opts_d:
                continue
            a0 = current[2] if current[2] in opts_a else rng.choice(opts_a)
            d0 = current[3] if current[3] in opts_d else rng.choice(opts_d)
            nxt_local = polish(kicked, a0, d0, nxt, n, rng, deadline)
            note(nxt_local)
            it += 1
            if nxt_local is not None and nxt_local[0] >= current[0]:
                current = nxt_local
    return best, it


# --- Full rules, used for boxes and for the final replay check. ---

EID = {"angel": 0, "devil": 1, "box": 2, "crown": 3, "grail": 4}


def apply_rules(tiles, ents, timers, dx, dy):
    """Mirror Board.update_turn + Angel/Devil/Box movement.

    tiles: list of lists of game codes.
    ents: list of [eid_int, x, y], angel then devil then the rest.
    timers: list of crown counters currently on the angel (values 0, 1, or 2).
    Returns (status, ents, timers). status in PLAYING, WIN, LOSE, STUCK.
    """
    h = len(tiles)
    w = len(tiles[0])
    ents = [e[:] for e in ents]
    timers = list(timers)

    def bounds(x, y):
        return 0 <= x < w and 0 <= y < h

    def get_at(x, y, ignore=-1):
        for i, e in enumerate(ents):
            if i != ignore and e[1] == x and e[2] == y:
                return i
        return -1

    def can_and_push(i, dx, dy):
        eid, x, y = ents[i]
        nx, ny = x + dx, y + dy
        if not bounds(nx, ny):
            return False
        tile = tiles[ny][nx]
        if eid == 0:
            if tile in (G_WALL, G_FIRE):
                return False
        elif eid == 1:
            if tile in (G_WALL, G_RIFT):
                return False
        else:
            if tile not in (G_EMPTY, G_SPIKES):
                return False
        occ = get_at(nx, ny)
        if occ != -1:
            occ_eid = ents[occ][0]
            if eid in (0, 1) and occ_eid in (3, 4):
                return True
            if not will_go(occ, dx, dy):
                return False
        return True

    def will_go(i, dx, dy):
        eid = ents[i][0]
        if eid in (0, 1):
            return can_and_push(i, dx, dy)
        if can_and_push(i, dx, dy):
            ents[i][1] += dx
            ents[i][2] += dy
            return True
        return False

    moved = False
    for i, e in enumerate(list(ents)):
        if e[0] in (0, 1):
            # Find current index; a push cannot reorder the list, only coords.
            if can_and_push(i, dx, dy):
                ents[i][1] += dx
                ents[i][2] += dy
                moved = True
    if not moved:
        return "STUCK", ents, timers

    # Pickup. Angel, then devil. Skip a player already marked dead (none yet).
    dead = [False] * len(ents)
    remove = set()
    for pi, eid in ((0, 0), (1, 1)):
        # players may not be index 0 and 1 if we ever reorder; search.
        pass
    players = [i for i, e in enumerate(ents) if e[0] in (0, 1)]
    # Game iterates angel then devil, not list order, for pickup.
    players.sort(key=lambda i: 0 if ents[i][0] == 0 else 1)
    for pi in players:
        px, py = ents[pi][1], ents[pi][2]
        for ii, item in enumerate(ents):
            if ii in remove or item[0] not in (3, 4):
                continue
            if item[1] == px and item[2] == py:
                if item[0] == 3:
                    if ents[pi][0] == 0:
                        timers.append(-1)
                    else:
                        # Devil crown is an instant loss. Flag via a sentinel timer.
                        timers.append("DEVIL_CROWN")
                else:
                    if ents[pi][0] == 0:
                        timers.append("ANGEL_GRAIL")
                    else:
                        timers.append("DEVIL_GRAIL")
                remove.add(ii)
    if remove:
        ents = [e for i, e in enumerate(ents) if i not in remove]
        dead = [False] * len(ents)

    for i, e in enumerate(ents):
        if tiles[e[2]][e[1]] == G_SPIKES:
            dead[i] = True

    angel_i = next((i for i, e in enumerate(ents) if e[0] == 0), None)
    devil_i = next((i for i, e in enumerate(ents) if e[0] == 1), None)

    if "ANGEL_GRAIL" in timers:
        return "LOSE", ents, [t for t in timers if isinstance(t, int)]

    if angel_i is not None:
        numeric = [t for t in timers if isinstance(t, int)]
        if numeric:
            numeric = [t + 1 for t in numeric]
            if 3 in numeric:
                dead[angel_i] = True
            numeric = [t for t in numeric if t < 3]
        timers = numeric + [t for t in timers if not isinstance(t, int)]

    if "DEVIL_CROWN" in timers:
        return "LOSE", ents, [t for t in timers if isinstance(t, int)]

    if devil_i is not None and "DEVIL_GRAIL" in timers:
        dead[devil_i] = True
        timers = [t for t in timers if t != "DEVIL_GRAIL"]

    timers = [t for t in timers if isinstance(t, int)]

    a_dead = angel_i is not None and dead[angel_i]
    d_dead = devil_i is not None and dead[devil_i]
    if a_dead and d_dead:
        return "WIN", ents, timers
    if a_dead or d_dead:
        if angel_i is not None:
            dead[angel_i] = False
        if devil_i is not None:
            dead[devil_i] = False
    ents = [e for i, e in enumerate(ents) if not dead[i]]
    return "PLAYING", ents, timers


def state_key(ents, timers):
    angel = next(e for e in ents if e[0] == 0)
    devil = next(e for e in ents if e[0] == 1)
    boxes = tuple(sorted((e[1], e[2]) for e in ents if e[0] == 2))
    crowns = tuple(sorted((e[1], e[2]) for e in ents if e[0] == 3))
    grails = tuple(sorted((e[1], e[2]) for e in ents if e[0] == 4))
    return (angel[1], angel[2], devil[1], devil[2], boxes, crowns, grails, tuple(sorted(timers)))


def solve_full(tiles, ents, max_states=400_000):
    """BFS under the real turn rules. Returns (length, path) or (-1, '')."""
    start_ents = [[EID[e], x, y] for e, x, y in ents]
    q = deque([(start_ents, [], "")])
    seen = {state_key(start_ents, [])}
    while q:
        cur_ents, timers, path = q.popleft()
        if len(seen) > max_states:
            return -1, ""
        for name, (dx, dy) in zip("RLDU", DIR_VEC):
            status, new_ents, new_timers = apply_rules(tiles, cur_ents, timers, dx, dy)
            if status == "STUCK":
                continue
            new_path = path + name
            if status == "WIN":
                return len(new_path), new_path
            if status == "LOSE":
                continue
            key = state_key(new_ents, new_timers)
            if key in seen:
                continue
            seen.add(key)
            q.append((new_ents, new_timers, new_path))
    return -1, ""


def layout_to_game_tiles(tiles: bytes, spikes, width: int, height: int):
    spike_set = set(spikes or ())
    board = []
    for y in range(height):
        row = []
        for x in range(width):
            i = y * width + x
            t = tiles[i]
            if t == WALL:
                row.append(G_WALL)
            elif t == FIRE:
                row.append(G_FIRE)
            elif t == RIFT:
                row.append(G_RIFT)
            elif i in spike_set:
                row.append(G_SPIKES)
            else:
                row.append(G_EMPTY)
        board.append(row)
    return board


def entities_from(a: int, d: int, width: int, boxes=()):
    ents = [
        ("angel", a % width, a // width),
        ("devil", d % width, d // width),
    ]
    for b in boxes:
        ents.append(("box", b % width, b // width))
    return ents


def augment_with_boxes(tiles, a0, d0, spikes, width, height, max_boxes=2, max_states=250_000, time_limit=30.0):
    """Insert boxes one at a time wherever that strictly lengthens the shortest win."""
    board = layout_to_game_tiles(tiles, spikes, width, height)
    boxes = []
    ents = entities_from(a0, d0, width, boxes)
    best_len, best_path = solve_full(board, ents, max_states=max_states)
    if best_len < 0:
        return best_len, best_path, boxes
    deadline = time.perf_counter() + time_limit

    n = width * height
    occupied_blocked = set()
    for y in range(height):
        for x in range(width):
            if board[y][x] in (G_WALL, G_FIRE, G_RIFT):
                occupied_blocked.add(y * width + x)

    for _ in range(max_boxes):
        if time.perf_counter() >= deadline:
            break
        improved = None
        for cell in range(n):
            if time.perf_counter() >= deadline:
                break
            if cell in occupied_blocked or cell in boxes or cell in (a0, d0):
                continue
            # A box only stands on empty or spikes.
            trial_boxes = boxes + [cell]
            trial_ents = entities_from(a0, d0, width, trial_boxes)
            length, path = solve_full(board, trial_ents, max_states=max_states)
            if length > best_len and (improved is None or length > improved[0]):
                improved = (length, path, trial_boxes)
        if improved is None:
            break
        best_len, best_path, boxes = improved
    return best_len, best_path, boxes


def board_from_dict(data):
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    try:
        return Board(path)
    finally:
        os.remove(path)


def apply_real(board, dx, dy):
    moved = False
    for entity in list(board.entities):
        if isinstance(entity, (Angel, Devil)):
            ox, oy = entity.x, entity.y
            entity.move((dx, dy), board)
            if entity.x != ox or entity.y != oy:
                moved = True
    if not moved:
        return "STUCK"
    return board.update_turn()


def snapshot_real(board):
    out = []
    for e in board.entities:
        if isinstance(e, Angel):
            kind = "angel"
        elif isinstance(e, Devil):
            kind = "devil"
        elif isinstance(e, Box):
            kind = "box"
        elif isinstance(e, Crown):
            kind = "crown"
        elif isinstance(e, Grail):
            kind = "grail"
        else:
            kind = "?"
        timers = tuple(e.effects.get("crown", [])) if isinstance(e, Angel) else ()
        out.append((kind, e.x, e.y, timers, "grail" in e.effects))
    return tuple(out)


def run_tests():
    rng = random.Random(0)
    width = height = 5
    n = 25
    nxt = make_next(width, height)
    mismatches = 0
    overlap_created = 0
    checked = 0

    for trial in range(3):
        tiles_m = bytearray(random_layout(rng, n, 0.2, 0.1, 0.1))
        # Force a few open cells so starts exist.
        tiles_m[0] = OPEN
        tiles_m[n - 1] = OPEN
        block_a, block_d = blocks_from_tiles(bytes(tiles_m))
        board_tiles = layout_to_game_tiles(bytes(tiles_m), (), width, height)
        # Compare every one-step successor from every reachable separated state.
        dist = bfs_dist(block_a, block_d, 0, n - 1, nxt, n)[0]
        for s, d0 in enumerate(dist):
            if d0 < 0:
                continue
            a, d = divmod(s, n)
            if a == d:
                continue
            data = {
                "width": width,
                "height": height,
                "board": board_tiles,
                "entities": [
                    {"eid": "angel", "x": a % width, "y": a // width},
                    {"eid": "devil", "x": d % width, "y": d // width},
                ],
            }
            for di, (dx, dy) in enumerate(DIR_VEC):
                na, nd = step_pair(a, d, nxt[di][a], nxt[di][d], block_a, block_d, nxt[di])
                real = board_from_dict(data)
                apply_real(real, dx, dy)
                ra = next(e for e in real.entities if isinstance(e, Angel))
                rd = next(e for e in real.entities if isinstance(e, Devil))
                got = (rd.y * width + rd.x)  # devil
                got_a = ra.y * width + ra.x
                checked += 1
                if (got_a, got) != (na, nd):
                    mismatches += 1
                    if mismatches <= 5:
                        print("mismatch", trial, (a, d), DIR_NAME[di], "fast", (na, nd), "real", (got_a, got))
                if a != d and got_a == got:
                    overlap_created += 1

    # Box + crown + grail random walks against Board.py.
    rule_bad = 0
    rule_checked = 0
    for trial in range(30):
        board_tiles = [[G_EMPTY] * 5 for _ in range(5)]
        for y in range(5):
            for x in range(5):
                board_tiles[y][x] = rng.choice(
                    [G_EMPTY, G_EMPTY, G_EMPTY, G_WALL, G_SPIKES, G_RIFT, G_FIRE]
                )
        ents_spec = [("angel", 0, 0), ("devil", 4, 4)]
        used = {(0, 0), (4, 4)}
        for kind, count in (("box", 2), ("crown", 1), ("grail", 1)):
            for _ in range(count):
                for _try in range(20):
                    x, y = rng.randrange(5), rng.randrange(5)
                    if (x, y) not in used and board_tiles[y][x] in (G_EMPTY, G_SPIKES):
                        used.add((x, y))
                        ents_spec.append((kind, x, y))
                        break
        # Angel / devil must actually be allowed to stand on their start.
        if board_tiles[0][0] in (G_WALL, G_FIRE):
            board_tiles[0][0] = G_EMPTY
        if board_tiles[4][4] in (G_WALL, G_RIFT):
            board_tiles[4][4] = G_EMPTY
        data = {
            "width": 5,
            "height": 5,
            "board": board_tiles,
            "entities": [{"eid": k, "x": x, "y": y} for k, x, y in ents_spec],
        }
        real = board_from_dict(data)
        sim_ents = [[EID[k], x, y] for k, x, y in ents_spec]
        sim_timers = []
        for _ in range(12):
            di = rng.randrange(4)
            dx, dy = DIR_VEC[di]
            status, sim_ents, sim_timers = apply_rules(board_tiles, sim_ents, sim_timers, dx, dy)
            real_status = apply_real(real, dx, dy)
            rule_checked += 1
            if status == "STUCK":
                real_status = "STUCK" if real_status == "STUCK" else real_status
            # STUCK on the real board leaves it unchanged; apply_real returns STUCK
            # only when we detect no movement. Good.
            sim_view = []
            for e in sim_ents:
                name = ("angel", "devil", "box", "crown", "grail")[e[0]]
                sim_view.append((name, e[1], e[2]))
            real_view = []
            for e in real.entities:
                if isinstance(e, Angel):
                    real_view.append(("angel", e.x, e.y))
                elif isinstance(e, Devil):
                    real_view.append(("devil", e.x, e.y))
                elif isinstance(e, Box):
                    real_view.append(("box", e.x, e.y))
                elif isinstance(e, Crown):
                    real_view.append(("crown", e.x, e.y))
                elif isinstance(e, Grail):
                    real_view.append(("grail", e.x, e.y))
            angel_real = next(e for e in real.entities if isinstance(e, Angel))
            real_timers = list(angel_real.effects.get("crown", []))
            if status != real_status or sorted(sim_view) != sorted(real_view) or sorted(sim_timers) != sorted(real_timers):
                rule_bad += 1
                if rule_bad <= 6:
                    print("rule mismatch", status, real_status)
                    print(" sim", sorted(sim_view), sim_timers)
                    print(" real", sorted(real_view), real_timers)
                break
            if status in ("WIN", "LOSE"):
                break

    # Angel steps onto a spike, devil is already on the next spike and cannot leave.
    tiny = [
        [G_EMPTY, G_SPIKES, G_SPIKES],
        [G_EMPTY, G_EMPTY, G_EMPTY],
        [G_EMPTY, G_EMPTY, G_EMPTY],
    ]
    length, path = solve_full(tiny, [("angel", 0, 0), ("devil", 1, 0)])
    print(f"fast transitions checked={checked} mismatches={mismatches} overlap_created={overlap_created}")
    print(f"full-rule walks checked={rule_checked} mismatches={rule_bad}")
    print(f"tiny level shortest={length} path={path}")
    return mismatches == 0 and rule_bad == 0 and overlap_created == 0 and length == 1 and path == "R"


def wasd_path(path: str) -> str:
    return path.translate(str.maketrans("RLDU", "DASW"))


def render_map(board, entities) -> str:
    marks = {}
    for kind, x, y in entities:
        marks.setdefault((x, y), "")
        marks[(x, y)] += {"angel": "A", "devil": "D", "box": "B", "crown": "C", "grail": "G"}[kind]
    sym = {G_EMPTY: ".", G_WALL: "#", G_SPIKES: "^", G_RIFT: "R", G_FIRE: "F"}
    lines = []
    for y, row in enumerate(board):
        cells = []
        for x, tile in enumerate(row):
            mark = marks.get((x, y), "")
            cells.append(f"{sym[tile]}{mark}".ljust(3))
        lines.append(" ".join(cells))
    return "\n".join(lines)


def format_level(width, height, board, entities, tag, shortest) -> str:
    rows = ",\n".join("    " + json.dumps(row) for row in board)
    ents = ",\n".join(
        "    " + json.dumps({"eid": k, "x": x, "y": y}) for k, x, y in entities
    )
    return (
        "{\n"
        f'  "tag": {json.dumps(tag)},\n'
        f'  "shortest": {shortest},\n'
        f'  "width": {width},\n'
        f'  "height": {height},\n'
        '  "board": [\n'
        f"{rows}\n"
        "  ],\n"
        '  "entities": [\n'
        f"{ents}\n"
        "  ]\n"
        "}\n"
    )


def default_generated_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated")


def allocate_level_path(directory: str, width: int, height: int, shortest: int):
    """Next free tag long_{w}x{h}_m{moves}_{serial}. Never returns an existing path."""
    os.makedirs(directory, exist_ok=True)
    serial = 1
    while True:
        tag = f"long_{width}x{height}_m{shortest}_{serial:02d}"
        path = os.path.join(directory, tag + ".json")
        if not os.path.exists(path):
            return tag, path
        serial += 1


def write_level_exclusive(path: str, text: str) -> None:
    """Create the file only if it is absent. A race with another run raises FileExistsError."""
    with open(path, "x", encoding="utf-8") as f:
        f.write(text)


def replay_on_game(board, entities, path) -> str:
    data = {
        "width": len(board[0]),
        "height": len(board),
        "board": board,
        "entities": [{"eid": k, "x": x, "y": y} for k, x, y in entities],
    }
    real = board_from_dict(data)
    status = "PLAYING"
    for i, ch in enumerate(path):
        dx, dy = DIR_VEC[DIR_NAME.index(ch)]
        status = apply_real(real, dx, dy)
        if status == "WIN":
            return "WIN" if i == len(path) - 1 else f"EARLY_WIN_{i + 1}"
        if status != "PLAYING":
            return status
    return status


def search(width, height, seconds, workers, max_boxes):
    from concurrent.futures import ProcessPoolExecutor

    # Workers run together, so each one gets the whole wall-clock budget.
    jobs = [(10_000 + i * 997, width, height, 10**9, seconds) for i in range(workers)]
    best = (-1, None, None, None, None, None)
    total_iters = 0
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for result, iters in pool.map(anneal_worker, jobs):
            total_iters += iters
            if result[0] > best[0]:
                best = result
    elapsed = time.perf_counter() - t0
    length, tiles, a0, d0, path, spikes = best
    print(f"anneal {elapsed:.1f}s iterations={total_iters} no-box length={length}")
    if length < 0:
        raise SystemExit("no solvable layout found")

    box_len, box_path, boxes = augment_with_boxes(
        tiles, a0, d0, spikes, width, height, max_boxes=max_boxes
    )
    if box_len > length:
        print(f"boxes lengthened the shortest win from {length} to {box_len}")
        length, path = box_len, box_path
    else:
        boxes = []
        print(f"boxes did not beat {length}")

    board = layout_to_game_tiles(tiles, spikes, width, height)
    entities = entities_from(a0, d0, width, boxes)
    status = replay_on_game(board, entities, path)
    if status != "WIN":
        raise SystemExit(f"replay failed: {status} after {len(path)} moves")
    # Confirm nothing shorter exists under the same rules.
    # A huge board can hit the slow solver's state cap. The terrain BFS already
    # proved a no-box length, and the box search proved a boxed one. Replay
    # above checked that this path wins on Board.py.
    proven, proven_path = solve_full(board, entities)
    if proven < 0:
        print("cross-check stopped before it finished; kept the length from the search that found this level")
    elif proven != length:
        raise SystemExit(f"length mismatch replay {length} vs bfs {proven}")
    elif proven_path != path:
        path = proven_path
    return board, entities, path, spikes


def main():
    parser = argparse.ArgumentParser(
        description="Generate a DIE level with a long shortest win. Run from DIE_Py. See the module docstring for examples.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python generate_long_level.py\n"
            "  python generate_long_level.py --width 7 --height 7 --seconds 50\n"
            "  python generate_long_level.py --width 5 --height 5 --seconds 45 --boxes 2\n"
            "  python generate_long_level.py --out generated --seconds 30\n"
            "  python generate_long_level.py --test\n"
            "\n"
            "Each run writes generated/long_<W>x<H>_m<moves>_<serial>.json\n"
            "and does not replace an existing file."
        ),
    )
    parser.add_argument("--width", type=int, default=5, help="Columns. Default 5. No maximum; --seconds stops the search.")
    parser.add_argument("--height", type=int, default=5, help="Rows. Default 5. No maximum.")
    parser.add_argument("--seconds", type=float, default=20.0, help="Wall-clock search budget. Default 20.")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1), help="Parallel searches. Default is CPU count minus one.")
    parser.add_argument("--boxes", type=int, default=2, help="Max boxes to try inserting. Kept only if they lengthen the shortest win. Default 2.")
    parser.add_argument("--test", action="store_true", help="Check the solver against Board.py and exit.")
    parser.add_argument("--out", default="", help="Output directory. Default: generated/ next to this script. Existing files are left alone.")
    args = parser.parse_args()

    if args.test:
        ok = run_tests()
        print("OK" if ok else "FAILED")
        raise SystemExit(0 if ok else 1)

    if args.width < 1 or args.height < 1:
        raise SystemExit("width and height must be at least 1")

    board, entities, path, spikes = search(
        args.width, args.height, args.seconds, args.workers, args.boxes
    )
    directory = args.out or default_generated_dir()
    if directory.lower().endswith(".json"):
        raise SystemExit("--out is a directory. Each level is named from its tag so a later run cannot replace it.")
    shortest = len(path)
    while True:
        tag, out = allocate_level_path(directory, args.width, args.height, shortest)
        text = format_level(args.width, args.height, board, entities, tag, shortest)
        try:
            write_level_exclusive(out, text)
            break
        except FileExistsError:
            continue
    print(f"tag: {tag}")
    print(f"shortest win: {shortest} moves")
    print(f"path (RLDU): {path}")
    print(f"path (WASD): {wasd_path(path)}")
    print(render_map(board, entities))
    print(f"wrote {out}")
    print(text)


if __name__ == "__main__":
    main()
