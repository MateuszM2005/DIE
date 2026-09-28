"""
Exact solver for DIE levels.

Both characters receive the same direction on every turn. Search states are
configurations: both positions, every remaining box and item, and the angel's
crown timers. Shortest wins are breadth-first search on that graph.

With the number of boxes and items held fixed, the configuration count is
polynomial in the number of cells. It is not polynomial in the number of
boxes; that part is the same shape as Sokoban. Consecutive identical objects
in the entity list are interchangeable, so each such run is stored sorted
and is not explored once per permutation.

Movement order, pushes, pickups, spikes, crown timers, and the simultaneous
death rule follow Board.py and Entity.py, including entity-list order.
Every reported path is replayed on those classes before it is kept.

CODE BY GROK
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import deque
from heapq import heappop, heappush

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from Board import Board
from Entity import Angel, Box, Crown, Devil, Grail

EMPTY, WALL, SPIKES, RIFT, FIRE = 1, 2, 3, 4, 5
ANGEL, DEVIL, BOX, CROWN, GRAIL = 0, 1, 2, 3, 4
SEP = 255

DIRS = (
    (0, -1, "W"),
    (0, 1, "S"),
    (-1, 0, "A"),
    (1, 0, "D"),
)
LETTER = {name: i for i, (_, _, name) in enumerate(DIRS)}


def canonicalize(ents: list) -> tuple:
    """Sort positions inside each consecutive run of boxes, crowns, or grails.

    A box listed before a player is not swapped with a box listed after one.
    get_entity_at returns the earliest entity on a shared cell, so list order
    relative to other kinds is part of the rules.
    """
    e = [list(t) for t in ents]
    n = len(e)
    i = 0
    while i < n:
        kind = e[i][0]
        j = i + 1
        if kind >= BOX:
            while j < n and e[j][0] == kind:
                j += 1
            if j - i > 1:
                e[i:j] = sorted(e[i:j], key=lambda t: (t[1], t[2]))
        i = j
    return tuple((a, b, c) for a, b, c in e)


def pack(ents: tuple, timers: tuple) -> bytes:
    raw = bytearray()
    for eid, x, y in ents:
        raw.append(eid)
        raw.append(x)
        raw.append(y)
    raw.append(SEP)
    for t in timers:
        raw.append(t)
    return bytes(raw)


def unpack(key: bytes) -> tuple[list, tuple]:
    ents = []
    i = 0
    n = len(key)
    while i < n and key[i] != SEP:
        ents.append([key[i], key[i + 1], key[i + 2]])
        i += 3
    return ents, tuple(key[i + 1 :])


def _join(spikes: bool, extra: str | None) -> str:
    parts = []
    if spikes:
        parts.append("spikes")
    if extra:
        parts.append(extra)
    return "+".join(parts) if parts else "none"


class Rules:
    """step() mirrors player movement and Board.update_turn for one level."""

    def __init__(self, tiles: list[list[int]]):
        self.h = len(tiles)
        self.w = len(tiles[0])
        self.flat = [cell for row in tiles for cell in row]
        self.e: list = []
        self.occ: dict = {}
        self.dx = 0
        self.dy = 0

    def _build_occ(self) -> None:
        occ = {}
        for i, e in enumerate(self.e):
            p = (e[1], e[2])
            if p not in occ:
                occ[p] = i
        self.occ = occ

    def _relocate(self, i: int, nx: int, ny: int) -> None:
        e = self.e[i]
        ox, oy = e[1], e[2]
        old = (ox, oy)
        if self.occ.get(old) == i:
            repl = None
            for j, o in enumerate(self.e):
                if j != i and o[1] == ox and o[2] == oy:
                    repl = j
                    break
            if repl is None:
                del self.occ[old]
            else:
                self.occ[old] = repl
        e[1] = nx
        e[2] = ny
        new = (nx, ny)
        cur = self.occ.get(new)
        if cur is None or i < cur:
            self.occ[new] = i

    def _can(self, i: int) -> bool:
        e = self.e[i]
        eid = e[0]
        nx = e[1] + self.dx
        ny = e[2] + self.dy
        if nx < 0 or ny < 0 or nx >= self.w or ny >= self.h:
            return False
        tile = self.flat[ny * self.w + nx]
        if eid == ANGEL:
            if tile == WALL or tile == FIRE:
                return False
        elif eid == DEVIL:
            if tile == WALL or tile == RIFT:
                return False
        elif tile != EMPTY and tile != SPIKES:
            return False
        j = self.occ.get((nx, ny))
        if j is None:
            return True
        oe = self.e[j][0]
        if eid <= DEVIL and oe >= CROWN:
            return True
        return self._will_go(j)

    def _will_go(self, i: int) -> bool:
        # Players only answer whether they could move. Boxes and items move now.
        # Checking a player still pushes whatever is in front of them.
        if self.e[i][0] <= DEVIL:
            return self._can(i)
        if not self._can(i):
            return False
        self._relocate(i, self.e[i][1] + self.dx, self.e[i][2] + self.dy)
        return True

    def _move_player(self, i: int) -> bool:
        if not self._can(i):
            return False
        self._relocate(i, self.e[i][1] + self.dx, self.e[i][2] + self.dy)
        return True

    def step(self, ents, timers, dx: int, dy: int):
        self.e = [list(t) for t in ents]
        self.dx = dx
        self.dy = dy
        self._build_occ()
        moved = False
        for i in range(len(self.e)):
            if self.e[i][0] <= DEVIL and self._move_player(i):
                moved = True
        if not moved:
            return ("STUCK",)

        timers = list(timers)
        angel_grail = False
        devil_crown = False
        devil_grail = False
        remove: set[int] = set()

        def take(pid: int, player_eid: int) -> None:
            nonlocal angel_grail, devil_crown, devil_grail
            px, py = self.e[pid][1], self.e[pid][2]
            for ii, item in enumerate(self.e):
                if ii in remove or item[0] < CROWN:
                    continue
                if item[1] != px or item[2] != py:
                    continue
                if item[0] == CROWN:
                    if player_eid == ANGEL:
                        timers.append(-1)
                    else:
                        devil_crown = True
                elif player_eid == ANGEL:
                    angel_grail = True
                else:
                    devil_grail = True
                remove.add(ii)

        angel_i = next((i for i, e in enumerate(self.e) if e[0] == ANGEL), None)
        devil_i = next((i for i, e in enumerate(self.e) if e[0] == DEVIL), None)
        if angel_i is not None:
            take(angel_i, ANGEL)
        if devil_i is not None:
            take(devil_i, DEVIL)
        if remove:
            self.e = [e for i, e in enumerate(self.e) if i not in remove]

        dead = [False] * len(self.e)
        for i, e in enumerate(self.e):
            if self.flat[e[2] * self.w + e[1]] == SPIKES:
                dead[i] = True

        angel_i = next((i for i, e in enumerate(self.e) if e[0] == ANGEL), None)
        devil_i = next((i for i, e in enumerate(self.e) if e[0] == DEVIL), None)
        angel_spikes = angel_i is not None and dead[angel_i]
        devil_spikes = devil_i is not None and dead[devil_i]

        if angel_grail:
            return ("LOSE",)

        crown_kill = False
        if angel_i is not None and timers:
            timers = [t + 1 for t in timers]
            if 3 in timers:
                dead[angel_i] = True
                crown_kill = True
            timers = [t for t in timers if t < 3]

        if devil_crown:
            return ("LOSE",)

        if devil_i is not None and devil_grail:
            dead[devil_i] = True

        a_dead = angel_i is not None and dead[angel_i]
        d_dead = devil_i is not None and dead[devil_i]
        if a_dead and d_dead:
            ax, ay = self.e[angel_i][1], self.e[angel_i][2]
            dvx, dvy = self.e[devil_i][1], self.e[devil_i][2]
            return (
                "WIN",
                _join(angel_spikes, "crown" if crown_kill else None),
                _join(devil_spikes, "grail" if devil_grail else None),
                ax,
                ay,
                dvx,
                dvy,
            )

        if a_dead or d_dead:
            if angel_i is not None:
                dead[angel_i] = False
            if devil_i is not None:
                dead[devil_i] = False
        if any(dead):
            self.e = [ent for ent, flag in zip(self.e, dead) if not flag]

        timers_t = tuple(sorted(timers))
        return ("OK", canonicalize(self.e), timers_t)

    def local_act(self, ents, dx: int, dy: int):
        """Move the one player who lives in this region.

        Pickups are reported and removed. Spiked boxes and items are removed.
        Crown timers and the simultaneous-death rule are decided by the caller,
        because the other character is in another region.
        Returns ("stay",), ("lose",), or ("go", ents, picked_crowns, picked_grails).
        """
        self.e = [list(t) for t in ents]
        self.dx = dx
        self.dy = dy
        self._build_occ()
        moved = False
        for i in range(len(self.e)):
            if self.e[i][0] <= DEVIL and self._move_player(i):
                moved = True
        if not moved:
            return ("stay",)

        pid = next(i for i, e in enumerate(self.e) if e[0] <= DEVIL)
        peid = self.e[pid][0]
        px, py = self.e[pid][1], self.e[pid][2]
        picked_c = 0
        picked_g = 0
        remove: set[int] = set()
        for ii, item in enumerate(self.e):
            if item[0] < CROWN or item[1] != px or item[2] != py:
                continue
            if item[0] == CROWN:
                picked_c += 1
            else:
                picked_g += 1
            remove.add(ii)
        # Angel + grail, and devil + crown, lose before a double death can count.
        if peid == ANGEL and picked_g:
            return ("lose",)
        if peid == DEVIL and picked_c:
            return ("lose",)
        if remove:
            self.e = [e for i, e in enumerate(self.e) if i not in remove]
        kept = []
        for e in self.e:
            if e[0] > DEVIL and self.flat[e[2] * self.w + e[1]] == SPIKES:
                continue
            kept.append(e)
        return ("go", canonicalize(kept), picked_c, picked_g)


def load_level(number: int) -> dict:
    path = os.path.join(ROOT, "levels", f"{number}.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_path"] = path
    return data


def initial_state(data: dict) -> tuple[list, tuple]:
    ents = []
    for ent in data["entities"]:
        eid = ent["eid"]
        code = {"angel": ANGEL, "devil": DEVIL, "box": BOX, "crown": CROWN, "grail": GRAIL}.get(eid)
        if code is None:
            continue
        ents.append((code, ent["x"], ent["y"]))
    return list(canonicalize(ents)), ()


INF = 10**9


def flood_cells(tiles, start, blocked: set[int]) -> set[tuple[int, int]]:
    h = len(tiles)
    w = len(tiles[0])
    sx, sy = start
    if tiles[sy][sx] in blocked:
        return set()
    seen = set()
    stack = [(sx, sy)]
    while stack:
        x, y = stack.pop()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        for dx, dy, _ in DIRS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and tiles[ny][nx] not in blocked and (nx, ny) not in seen:
                stack.append((nx, ny))
    return seen


class Side:
    """Every configuration of one character, the boxes, and the items on their side."""

    def __init__(self, rules: Rules, ents, who: int):
        self.rules = rules
        self.who = who
        self.keys: list[bytes] = []
        self.index: dict[bytes, int] = {}
        self.trans: list = []
        self.spikes: list[bool] = []
        self.pos: list[tuple[int, int]] = []
        self.d_item = []  # angel: moves until a crown pickup; devil: until a grail pickup
        self.d_spike = []
        self.overflow = False
        start = self._add(ents)
        q = deque([start])
        while q:
            if len(self.keys) > 350_000:
                self.overflow = True
                break
            i = q.popleft()
            if self.trans[i] is not None:
                continue
            ents_i, _ = unpack(self.keys[i])
            row = []
            for dx, dy, _ in DIRS:
                act = rules.local_act(ents_i, dx, dy)
                if act[0] == "stay":
                    row.append(("stay",))
                elif act[0] == "lose":
                    row.append(("lose",))
                else:
                    _, new_ents, pc, pg = act
                    nid = self._add(new_ents)
                    row.append(("go", nid, pc, pg))
                    if self.trans[nid] is None:
                        q.append(nid)
            self.trans[i] = tuple(row)
        if not self.overflow:
            self._distances()

    def _add(self, ents) -> int:
        canon = canonicalize(ents)
        key = pack(canon, ())
        found = self.index.get(key)
        if found is not None:
            return found
        i = len(self.keys)
        self.index[key] = i
        self.keys.append(key)
        self.trans.append(None)
        on = False
        px = py = 0
        flat = self.rules.flat
        w = self.rules.w
        for eid, x, y in canon:
            if eid <= DEVIL:
                px, py = x, y
                if flat[y * w + x] == SPIKES:
                    on = True
        self.spikes.append(on)
        self.pos.append((px, py))
        return i

    def _distances(self) -> None:
        n = len(self.keys)
        rev: list[list[int]] = [[] for _ in range(n)]
        item_targets = []
        for s, row in enumerate(self.trans):
            for edge in row:
                if edge[0] != "go":
                    continue
                rev[edge[1]].append(s)
                picked = edge[2] if self.who == ANGEL else edge[3]
                if picked:
                    item_targets.append(edge[1])
        self.d_item = self._rev_dist(rev, item_targets, n)
        spike_targets = [s for s in range(n) if self.spikes[s]]
        dist_spike = self._rev_dist(rev, spike_targets, n)
        self.d_spike = []
        for s in range(n):
            if self.spikes[s]:
                # Already standing on spikes. The next resolving turn kills
                # only if this character is still there at the end of it.
                # One turn is a lower bound (the other side can move).
                self.d_spike.append(1)
            else:
                self.d_spike.append(dist_spike[s])

    @staticmethod
    def _rev_dist(rev, targets, n: int) -> list[int]:
        dist = [INF] * n
        q = deque()
        for t in targets:
            if dist[t] == INF:
                dist[t] = 0
                q.append(t)
        while q:
            v = q.popleft()
            dv = dist[v]
            for u in rev[v]:
                if dist[u] > dv + 1:
                    dist[u] = dv + 1
                    q.append(u)
        return dist


class SplitModel:
    """Exact search when the angel and the devil can never reach the same cell.

    Each side is a small automaton. A turn feeds both the same direction.
    The joint state is the pair of sides plus the angel's crown timers.
    """

    def __init__(self, rules: Rules, angel: Side, devil: Side):
        self.rules = rules
        self.angel = angel
        self.devil = devil

    @staticmethod
    def build(data: dict):
        rules = Rules(data["board"])
        ents, _ = initial_state(data)
        angel_at = next((x, y) for eid, x, y in ents if eid == ANGEL)
        devil_at = next((x, y) for eid, x, y in ents if eid == DEVIL)
        a_cells = flood_cells(data["board"], angel_at, {WALL, FIRE})
        d_cells = flood_cells(data["board"], devil_at, {WALL, RIFT})
        if a_cells & d_cells:
            return None
        a_ents = []
        d_ents = []
        for e in ents:
            p = (e[1], e[2])
            if e[0] == ANGEL or p in a_cells:
                a_ents.append(e)
            elif e[0] == DEVIL or p in d_cells:
                d_ents.append(e)
            else:
                return None
        if not any(e[0] == ANGEL for e in a_ents) or not any(e[0] == DEVIL for e in d_ents):
            return None
        # Four or more boxes on one side is an open Sokoban; the automaton does not fit.
        if sum(e[0] == BOX for e in a_ents) > 3 or sum(e[0] == BOX for e in d_ents) > 3:
            return None
        t0 = time.perf_counter()
        angel = Side(rules, a_ents, ANGEL)
        if angel.overflow:
            print("    angel side exceeded 350k configs", flush=True)
            return None
        devil = Side(rules, d_ents, DEVIL)
        if devil.overflow:
            print("    devil side exceeded 350k configs", flush=True)
            return None
        print(
            f"    sides: angel {len(angel.keys)} configs, devil {len(devil.keys)} configs "
            f"in {time.perf_counter() - t0:.2f}s",
            flush=True,
        )
        model = SplitModel(rules, angel, devil)
        model.audit(data)
        return model

    def heuristic(self, sa: int, sd: int, timers: tuple) -> int:
        if timers:
            ha = 3 - max(timers)
        else:
            d = self.angel.d_item[sa]
            ha = d + 3 if d < INF else INF
        hs = self.angel.d_spike[sa]
        ha = hs if hs < ha else ha
        dg = self.devil.d_item[sd]
        ds = self.devil.d_spike[sd]
        hd = dg if dg < ds else ds
        if ha >= INF or hd >= INF:
            return INF
        return ha if ha > hd else hd

    def apply(self, sa: int, sd: int, timers: tuple, di: int):
        ta = self.angel.trans[sa][di]
        td = self.devil.trans[sd][di]
        if ta[0] == "lose" or td[0] == "lose":
            return ("LOSE",)
        moved = ta[0] == "go" or td[0] == "go"
        if not moved:
            return ("STUCK",)
        nsa = ta[1] if ta[0] == "go" else sa
        nsd = td[1] if td[0] == "go" else sd
        pc = ta[2] if ta[0] == "go" else 0
        pg = td[3] if td[0] == "go" else 0
        timers_l = list(timers)
        for _ in range(pc):
            timers_l.append(-1)
        crown_kill = False
        if timers_l:
            timers_l = [t + 1 for t in timers_l]
            if 3 in timers_l:
                crown_kill = True
            timers_l = [t for t in timers_l if t < 3]
        a_spikes = self.angel.spikes[nsa]
        d_spikes = self.devil.spikes[nsd]
        a_dead = a_spikes or crown_kill
        d_dead = d_spikes or pg > 0
        ax, ay = self.angel.pos[nsa]
        dvx, dvy = self.devil.pos[nsd]
        if a_dead and d_dead:
            sig = (
                _join(a_spikes, "crown" if crown_kill else None),
                _join(d_spikes, "grail" if pg else None),
                ax,
                ay,
                dvx,
                dvy,
            )
            return ("WIN", sig, tuple(sorted(timers_l)))
        return ("OK", nsa, nsd, tuple(sorted(timers_l)))

    def audit(self, data: dict, episodes: int = 12, steps: int = 20) -> None:
        rng = random.Random(1009 + data["width"] * 17 + data["height"])
        for ep in range(episodes):
            board = Board(data["_path"])
            sa = sd = 0
            timers: tuple = ()
            seq = []
            for _ in range(steps):
                di = rng.randrange(4)
                seq.append(DIRS[di][2])
                result = self.apply(sa, sd, timers, di)
                real = apply_real(board, DIRS[di][0], DIRS[di][1])
                if result[0] == "STUCK":
                    if real != "STUCK":
                        raise AssertionError(f"split stuck {''.join(seq)} real {real}")
                    continue
                if result[0] == "LOSE":
                    if real != "LOSE":
                        raise AssertionError(f"split lose {''.join(seq)} real {real}")
                    break
                if result[0] == "WIN":
                    if real != "WIN":
                        raise AssertionError(f"split win {''.join(seq)} real {real}")
                    break
                _, sa, sd, timers = result
                ents = unpack(self.angel.keys[sa])[0] + unpack(self.devil.keys[sd])[0]
                if real != "PLAYING" or snapshot_board(board) != snapshot_sim(ents, timers):
                    raise AssertionError(
                        f"split diverge {''.join(seq)}\n sim {snapshot_sim(ents, timers)}\n real {snapshot_board(board)} {real}"
                    )

    def solve(self, cap: int, deadline: float):
        """A* on the product. The heuristic is a lower bound, so the first win is shortest."""
        start_h = self.heuristic(0, 0, ())
        print(f"    product heuristic at the start: {start_h if start_h < INF else 'impossible'}", flush=True)
        heap = [(start_h, 0, 0, 0, 0, ())]  # f, g, tie, sa, sd, timers
        best = {(0, 0, ()) : 0}
        parent = {}
        tie = 0
        expanded = 0
        best_win = None
        wins = {}
        while heap:
            if expanded > cap or time.perf_counter() > deadline:
                break
            f, g, _, sa, sd, timers = heappop(heap)
            if best_win is not None and f > best_win:
                break
            key = (sa, sd, timers)
            if g != best.get(key):
                continue
            expanded += 1
            if expanded % 200000 == 0:
                print(f"    ...product {expanded} expanded, f={f}", flush=True)
            for di in range(4):
                result = self.apply(sa, sd, timers, di)
                kind = result[0]
                if kind == "STUCK" or kind == "LOSE":
                    continue
                if kind == "WIN":
                    _, sig, _timers_unused = result
                    length = g + 1
                    path = self._path(parent, key) + DIRS[di][2]
                    if sig not in wins or length < wins[sig][0]:
                        wins[sig] = (length, path)
                    if best_win is None or length < best_win:
                        best_win = length
                    continue
                _, nsa, nsd, ntimers = result
                ng = g + 1
                nkey = (nsa, nsd, ntimers)
                old = best.get(nkey)
                if old is not None and ng >= old:
                    continue
                nh = self.heuristic(nsa, nsd, ntimers)
                if nh >= INF:
                    continue
                best[nkey] = ng
                parent[nkey] = (key, DIRS[di][2])
                tie += 1
                heappush(heap, (ng + nh, ng, tie, nsa, nsd, ntimers))
        if best_win is not None:
            lower = best_win
            proven = (not heap) or heap[0][0] > best_win
        elif heap:
            lower = heap[0][0]
            proven = False
        else:
            lower = None
            proven = True
        exhausted = not heap and best_win is None
        return wins, expanded, exhausted, lower, proven

    @staticmethod
    def _path(parent, key) -> str:
        out = []
        while key in parent:
            key, mv = parent[key]
            out.append(mv)
        out.reverse()
        return "".join(out)


def best_first(rules: Rules, ents, timers, spike_cells, cap: int, deadline: float):
    """Directed search used when the plain graph is too wide to finish.

    The ordering prefers getting each character closer to a way to die.
    The path it returns is a real win; it is not necessarily the shortest.
    """
    start_ents = canonicalize(ents)
    start_timers = tuple(timers)
    start_key = pack(start_ents, start_timers)
    pool = [start_key]
    parents = [-1]
    moves = [-1]
    dist = [0]
    seen = {start_key: 0}
    h0 = _guide(start_ents, start_timers, spike_cells)
    heap = [(h0, 0, 0)]
    expanded = 0
    while heap:
        if expanded > cap or time.perf_counter() > deadline:
            break
        _h, g, idx = heappop(heap)
        if g != dist[idx]:
            continue
        expanded += 1
        if expanded % 100000 == 0:
            print(f"    ...directed {expanded}", flush=True)
        cur_ents, cur_timers = unpack(pool[idx])
        for di, (dx, dy, _) in enumerate(DIRS):
            result = rules.step(cur_ents, cur_timers, dx, dy)
            if result[0] == "STUCK" or result[0] == "LOSE":
                continue
            if result[0] == "WIN":
                _, ca, cd, ax, ay, dvx, dvy = result
                path = reconstruct(parents, moves, idx, di)
                return (ca, cd, ax, ay, dvx, dvy), g + 1, path, expanded
            _, new_ents, new_timers = result
            key = pack(new_ents, new_timers)
            if key in seen:
                continue
            seen[key] = len(pool)
            parents.append(idx)
            moves.append(di)
            dist.append(g + 1)
            pool.append(key)
            nh = _guide(new_ents, new_timers, spike_cells)
            heappush(heap, (nh + (g + 1) * 0.05, g + 1, len(pool) - 1))
    return None


def _guide(ents, timers, spike_cells) -> int:
    ax = ay = dx = dy = None
    crowns = []
    grails = []
    for eid, x, y in ents:
        if eid == ANGEL:
            ax, ay = x, y
        elif eid == DEVIL:
            dx, dy = x, y
        elif eid == CROWN:
            crowns.append((x, y))
        elif eid == GRAIL:
            grails.append((x, y))

    def nearest(x, y, cells):
        if not cells:
            return 999
        return min(abs(x - cx) + abs(y - cy) for cx, cy in cells)

    if timers:
        ha = 3 - max(timers)
    else:
        ha = nearest(ax, ay, crowns) + 3 if crowns else 999
    ha = min(ha, nearest(ax, ay, spike_cells))
    hd = nearest(dx, dy, grails) if grails else 999
    hd = min(hd, nearest(dx, dy, spike_cells))
    return ha + hd


def players_of(ents) -> tuple[tuple[int, int], tuple[int, int]]:
    angel = devil = None
    for eid, x, y in ents:
        if eid == ANGEL:
            angel = (x, y)
        elif eid == DEVIL:
            devil = (x, y)
    return angel, devil


def apply_real(board: Board, dx: int, dy: int) -> str:
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


def snapshot_board(board: Board):
    boxes, crowns, grails = [], [], []
    angel = devil = None
    timers = []
    for e in board.entities:
        if isinstance(e, Angel):
            angel = (e.x, e.y)
            timers = sorted(e.effects.get("crown", []))
        elif isinstance(e, Devil):
            devil = (e.x, e.y)
        elif isinstance(e, Box):
            boxes.append((e.x, e.y))
        elif isinstance(e, Crown):
            crowns.append((e.x, e.y))
        elif isinstance(e, Grail):
            grails.append((e.x, e.y))
    return angel, devil, tuple(sorted(boxes)), tuple(sorted(crowns)), tuple(sorted(grails)), tuple(timers)


def snapshot_sim(ents, timers):
    boxes, crowns, grails = [], [], []
    angel = devil = None
    for eid, x, y in ents:
        if eid == ANGEL:
            angel = (x, y)
        elif eid == DEVIL:
            devil = (x, y)
        elif eid == BOX:
            boxes.append((x, y))
        elif eid == CROWN:
            crowns.append((x, y))
        elif eid == GRAIL:
            grails.append((x, y))
    return angel, devil, tuple(sorted(boxes)), tuple(sorted(crowns)), tuple(sorted(grails)), tuple(sorted(timers))


def fuzz_level(number: int, episodes: int = 30, steps: int = 25, seed: int = 0) -> None:
    data = load_level(number)
    rules = Rules(data["board"])
    rng = random.Random(seed + number * 10007)
    start_ents, start_timers = initial_state(data)
    for ep in range(episodes):
        board = Board(data["_path"])
        ents, timers = start_ents, start_timers
        seq = []
        for _ in range(steps):
            di = rng.randrange(4)
            dx, dy, name = DIRS[di]
            seq.append(name)
            result = rules.step(ents, timers, dx, dy)
            real = apply_real(board, dx, dy)
            if result[0] == "STUCK":
                if real != "STUCK" or snapshot_board(board) != snapshot_sim(ents, timers):
                    raise AssertionError(f"level {number} ep {ep} stuck diverge {''.join(seq)}")
                continue
            if result[0] == "LOSE":
                if real != "LOSE":
                    raise AssertionError(f"level {number} ep {ep} lose diverge {''.join(seq)} real={real}")
                break
            if result[0] == "WIN":
                if real != "WIN":
                    raise AssertionError(f"level {number} ep {ep} win diverge {''.join(seq)} real={real}")
                break
            _, ents, timers = result
            if real != "PLAYING" or snapshot_board(board) != snapshot_sim(ents, timers):
                raise AssertionError(
                    f"level {number} ep {ep} state diverge after {''.join(seq)}\n"
                    f" sim {snapshot_sim(ents, timers)}\n"
                    f" real {snapshot_board(board)} status {real}"
                )


def reconstruct(parents: list[int], moves: list[int], idx: int, last: int) -> str:
    out = []
    while idx > 0:
        out.append(DIRS[moves[idx]][2])
        idx = parents[idx]
    out.reverse()
    out.append(DIRS[last][2])
    return "".join(out)


def search(rules: Rules, start_ents, start_timers, cap: int, deadline: float):
    """BFS. First win is a shortest win. Later wins are shortest for their ending.

    Returns (wins, states, exhausted).
    wins: dict (angel_cause, devil_cause, ax, ay, dx, dy) -> (length, path)
    """
    start_key = pack(canonicalize(start_ents), tuple(start_timers))
    pool = [start_key]
    parents = [-1]
    moves = [-1]
    dist = [0]
    seen = {start_key: 0}
    q = deque([0])
    wins = {}
    qh = 0
    exhausted = True
    shortest = None
    while q:
        if len(pool) > cap or time.perf_counter() > deadline:
            exhausted = False
            break
        idx = q.popleft()
        if shortest is not None and dist[idx] > shortest + 4:
            # Every win of length <= shortest + 5 has already been generated.
            exhausted = False
            break
        qh += 1
        if qh % 200000 == 0:
            print(f"    ...{qh} expanded, {len(pool)} reached", flush=True)
        ents, timers = unpack(pool[idx])
        base = dist[idx]
        for di, (dx, dy, _) in enumerate(DIRS):
            result = rules.step(ents, timers, dx, dy)
            kind = result[0]
            if kind == "STUCK" or kind == "LOSE":
                continue
            if kind == "WIN":
                _, ca, cd, ax, ay, dvx, dvy = result
                sig = (ca, cd, ax, ay, dvx, dvy)
                length = base + 1
                if shortest is None or length < shortest:
                    shortest = length
                if sig not in wins:
                    wins[sig] = (length, reconstruct(parents, moves, idx, di))
                continue
            _, new_ents, new_timers = result
            key = pack(new_ents, new_timers)
            if key in seen:
                continue
            seen[key] = len(pool)
            parents.append(idx)
            moves.append(di)
            dist.append(length := base + 1)
            pool.append(key)
            q.append(len(pool) - 1)
    if q:
        lower = dist[q[0]] + 1
    else:
        lower = None
    return wins, len(pool), exhausted and not q, lower


def low_overlap_path(rules: Rules, start_ents, start_timers, forbidden: set, cap: int, deadline: float):
    """Shortest win among paths that share as few angel/devil pairs as possible.

    Cost is (shared pairs, then length). The start pair is not charged.
    """
    shift = 100000
    start_ents_c = canonicalize(start_ents)
    start_timers_t = tuple(start_timers)
    start_pair = players_of(start_ents_c)
    start_key = pack(start_ents_c, start_timers_t)
    pool = [start_key]
    parents = [-1]
    moves = [-1]
    best = {start_key: 0}
    heap = [(0, 0, 0)]  # cost, dist, idx
    expanded = 0
    best_win = None
    while heap:
        if expanded > cap or time.perf_counter() > deadline:
            break
        cost, dist, idx = heappop(heap)
        if best_win is not None and cost >= best_win[0]:
            break
        if cost != best.get(pool[idx]):
            continue
        expanded += 1
        ents, timers = unpack(pool[idx])
        for di, (dx, dy, _) in enumerate(DIRS):
            result = rules.step(ents, timers, dx, dy)
            kind = result[0]
            if kind == "STUCK" or kind == "LOSE":
                continue
            if kind == "WIN":
                _, ca, cd, ax, ay, dvx, dvy = result
                pair = ((ax, ay), (dvx, dvy))
                extra = 0 if pair == start_pair or pair not in forbidden else 1
                win_cost = cost + extra * shift + 1
                if best_win is None or win_cost < best_win[0]:
                    path = reconstruct(parents, moves, idx, di)
                    best_win = (win_cost, dist + 1, path, (ca, cd, ax, ay, dvx, dvy))
                continue
            _, new_ents, new_timers = result
            pair = players_of(new_ents)
            extra = 0 if pair == start_pair or pair not in forbidden else 1
            new_cost = cost + extra * shift + 1
            key = pack(new_ents, new_timers)
            old = best.get(key)
            if old is not None and new_cost >= old:
                continue
            best[key] = new_cost
            parents.append(idx)
            moves.append(di)
            pool.append(key)
            heappush(heap, (new_cost, dist + 1, len(pool) - 1))
    if best_win is None:
        return None
    _, length, path, sig = best_win
    shared = best_win[0] // shift
    return length, path, sig, shared, expanded


def replay_board(path_file: str, moves: str) -> str:
    board = Board(path_file)
    status = "PLAYING"
    for ch in moves:
        dx, dy, _ = DIRS[LETTER[ch]]
        status = apply_real(board, dx, dy)
        if status == "WIN":
            return "WIN"
        if status != "PLAYING":
            return status
    return status


def trajectory(rules: Rules, start_ents, start_timers, moves: str):
    """Replay a winning path. Return pair list (including start) and event lines."""
    ents, timers = canonicalize(start_ents), tuple(start_timers)
    pairs = [players_of(ents)]
    events = []
    for n, ch in enumerate(moves, 1):
        dx, dy, _ = DIRS[LETTER[ch]]
        before = snapshot_sim(ents, timers)
        result = rules.step(ents, timers, dx, dy)
        if result[0] == "WIN":
            _, ca, cd, ax, ay, dvx, dvy = result
            pairs.append(((ax, ay), (dvx, dvy)))
            events.append(f"move {n}: win, angel {ca} at ({ax},{ay}), devil {cd} at ({dvx},{dvy})")
            return pairs, events
        if result[0] != "OK":
            events.append(f"move {n}: unexpected {result[0]}")
            return pairs, events
        _, ents, timers = result
        after = snapshot_sim(ents, timers)
        pairs.append(players_of(ents))
        notes = []
        if len(after[4]) < len(before[4]):
            notes.append("grail removed")
        if len(after[3]) < len(before[3]):
            notes.append("crown removed")
        if len(after[2]) < len(before[2]):
            notes.append(f"{len(before[2]) - len(after[2])} box destroyed")
        if len(after[5]) > len(before[5]):
            notes.append(f"angel now holds {len(after[5])} crown timer(s) {list(after[5])}")
        elif after[5] != before[5] and after[5]:
            notes.append(f"crown timers {list(after[5])}")
        elif before[5] and not after[5]:
            notes.append("crown charge spent")
        if notes:
            events.append(f"move {n} {ch}: " + "; ".join(notes))
    return pairs, events


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def shared_prefix(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def select_paths(wins: dict, primary_path: str, primary_pairs: set):
    """Pick the shortest win, other death mechanics, and a different ending cell."""
    ranked = sorted(wins.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    chosen = []
    seen_paths = set()

    def add(sig, length, path, why: str):
        if path in seen_paths:
            return
        seen_paths.add(path)
        chosen.append((sig, length, path, why))

    if not ranked:
        return chosen
    sig0, (len0, path0) = ranked[0]
    add(sig0, len0, path0, "shortest")

    by_cause = {}
    for sig, (length, path) in ranked:
        cause = (sig[0], sig[1])
        if cause not in by_cause:
            by_cause[cause] = (sig, length, path)
    for cause, (sig, length, path) in by_cause.items():
        if (sig[0], sig[1]) == (sig0[0], sig0[1]):
            continue
        add(sig, length, path, "different death")

    # Same mechanic, different cells, preferably a short one that shares little.
    best_cell = None
    for sig, (length, path) in ranked:
        if path in seen_paths:
            continue
        if (sig[0], sig[1]) != (sig0[0], sig0[1]):
            continue
        if length > len0 + 4:
            continue
        cell = (sig[2], sig[3], sig[4], sig[5])
        cell0 = (sig0[2], sig0[3], sig0[4], sig0[5])
        if cell == cell0:
            continue
        if best_cell is None or length < best_cell[1]:
            best_cell = (sig, length, path)
    if best_cell:
        add(*best_cell, "different cells")
    return chosen


def solve_level(number: int, cap: int, seconds: float, diverse: bool) -> dict:
    data = load_level(number)
    rules = Rules(data["board"])
    ents, timers = initial_state(data)
    boxes = sum(1 for e in ents if e[0] == BOX)
    crowns = sum(1 for e in ents if e[0] == CROWN)
    grails = sum(1 for e in ents if e[0] == GRAIL)
    spikes = sum(cell == SPIKES for row in data["board"] for cell in row)
    spike_cells = [(x, y) for y, row in enumerate(data["board"]) for x, cell in enumerate(row) if cell == SPIKES]
    t0 = time.perf_counter()
    split = SplitModel.build(data)
    deadline = time.perf_counter() + seconds
    proven = True
    lower = None
    if split is not None:
        wins, states, exhausted, lower, proven = split.solve(cap, deadline)
    else:
        wins, states, exhausted, lower = search(rules, ents, timers, cap, deadline)
        if not wins and time.perf_counter() < deadline:
            print("    directed search for a win that may not be shortest", flush=True)
            found = best_first(rules, ents, timers, spike_cells, cap, deadline)
            if found is not None:
                sig, length, path, extra = found
                wins = {sig: (length, path)}
                states += extra
                proven = lower is not None and length == lower
    elapsed = time.perf_counter() - t0

    verified = []
    for sig, (length, path) in wins.items():
        status = replay_board(data["_path"], path)
        if status != "WIN":
            raise AssertionError(f"level {number} path failed on Board.py: {status} {path}")
        verified.append((sig, length, path))
    wins = {sig: (length, path) for sig, length, path in verified}

    report = {
        "level": number,
        "width": data["width"],
        "height": data["height"],
        "boxes": boxes,
        "crowns": crowns,
        "grails": grails,
        "spikes": spikes,
        "states": states,
        "exhausted": exhausted,
        "seconds": round(elapsed, 3),
        "solutions": [],
        "lower_bound": lower,
        "proven": proven,
    }
    if not wins:
        report["status"] = "exhausted-unsolvable" if exhausted else "cap"
        return report

    ranked = sorted(wins.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    sig0, (len0, path0) = ranked[0]
    pairs0, events0 = trajectory(rules, ents, timers, path0)
    set0 = set(pairs0)
    chosen = select_paths(wins, path0, set0)

    have = {path for _, _, path, _ in chosen}
    if diverse and (len(chosen) < 2 or True):
        # A route that avoids the shortest path's squares, when the graph is small
        # enough to search again. Skip when we already spent the budget.
        remain = deadline - time.perf_counter()
        if states <= 250000 and remain > 1.5:
            forbid = set(pairs0[1:])  # keep the opening cell free
            alt = low_overlap_path(
                rules, ents, timers, forbid, cap=min(cap, 250000), deadline=time.perf_counter() + min(remain, 20)
            )
            if alt is not None:
                length, path, sig, shared, _exp = alt
                if path not in have and replay_board(data["_path"], path) == "WIN":
                    chosen.append((sig, length, path, "low overlap with shortest"))

    for sig, length, path, why in chosen:
        pairs, events = trajectory(rules, ents, timers, path) if path != path0 else (pairs0, events0)
        report["solutions"].append(
            {
                "why": why,
                "length": length,
                "path": path,
                "angel_death": sig[0],
                "devil_death": sig[1],
                "angel_cell": [sig[2], sig[3]],
                "devil_cell": [sig[4], sig[5]],
                "shared_prefix_with_shortest": shared_prefix(path0, path),
                "pair_jaccard_with_shortest": round(jaccard(set0, set(pairs)), 3),
                "levenshtein_with_shortest": levenshtein(path0, path),
                "events": events if why == "shortest" else events[:8],
            }
        )
    if proven and lower is not None and len0 == lower:
        proven = True
    report["status"] = "solved" if proven else "upper"
    report["proven"] = proven
    report["shortest"] = len0
    report["endings"] = len(wins)
    if not proven:
        for sol in report["solutions"]:
            if sol["why"] == "shortest":
                sol["why"] = "a win, shortest not proven"
    return report


def format_report(rep: dict) -> str:
    head = (
        f"Level {rep['level']}  {rep['width']}x{rep['height']}  "
        f"boxes={rep['boxes']} crowns={rep['crowns']} grails={rep['grails']} spikes={rep['spikes']}  "
        f"states={rep['states']} {'full graph' if rep['exhausted'] else 'stopped at cap'}  "
        f"{rep['seconds']}s"
    )
    lines = [head]
    if rep["status"] not in ("solved", "upper"):
        if rep["status"] == "exhausted-unsolvable":
            lines.append("  No win exists.")
        else:
            bound = rep.get("lower_bound")
            if bound:
                lines.append(
                    f"  No win found before the cap. A shortest win is at least {bound} moves."
                )
            else:
                lines.append("  No win found before the state/time cap. This is not a proof the level is impossible.")
        return "\n".join(lines)
    kind = "Shortest win" if rep.get("proven", True) else "Win found (shortest not proven)"
    lines.append(f"  Distinct endings found: {rep['endings']}. {kind}: {rep['shortest']} moves.")
    if not rep.get("proven", True) and rep.get("lower_bound"):
        lines.append(f"  Search proved no shorter win exists below {rep['lower_bound']} moves.")
    for sol in rep["solutions"]:
        lines.append(
            f"  [{sol['why']}] {sol['length']} moves  "
            f"angel {sol['angel_death']} @({sol['angel_cell'][0]},{sol['angel_cell'][1]})  "
            f"devil {sol['devil_death']} @({sol['devil_cell'][0]},{sol['devil_cell'][1]})"
        )
        lines.append(f"    path: {sol['path']}")
        if sol["why"] != "shortest":
            lines.append(
                f"    vs shortest: shared prefix {sol['shared_prefix_with_shortest']}, "
                f"position-pair overlap {sol['pair_jaccard_with_shortest']}, "
                f"edit distance {sol['levenshtein_with_shortest']}"
            )
        for ev in sol["events"]:
            lines.append(f"    {ev}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Solve DIE levels 1-15")
    parser.add_argument("levels", nargs="*", type=int, help="level numbers (default 1-15)")
    parser.add_argument("--cap", type=int, default=700_000)
    parser.add_argument("--seconds", type=float, default=40.0)
    parser.add_argument("--skip-fuzz", action="store_true")
    parser.add_argument("--no-diverse", action="store_true")
    parser.add_argument("--out", default=os.path.join(ROOT, "solver_results.json"))
    args = parser.parse_args()
    levels = args.levels or list(range(1, 16))

    if not args.skip_fuzz:
        print("Checking the rules against Board.py ...", flush=True)
        for n in levels:
            fuzz_level(n)
        print(f"Fuzz passed for levels {levels[0]}-{levels[-1]}.", flush=True)

    reports = []
    for n in levels:
        print(f"Solving level {n} ...", flush=True)
        rep = solve_level(n, args.cap, args.seconds, diverse=not args.no_diverse)
        reports.append(rep)
        print(format_report(rep), flush=True)
        print(flush=True)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
