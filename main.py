from blessings import Terminal
from copy import deepcopy
from itertools import chain
from lark import Lark, Transformer
from numpy import random
import readline
from rich.console import Console
import sys
from time import sleep
from uuid import uuid4

GRID_HEIGHT = 20
GRID_WIDTH = 40
N_TURNS = 25

GRAMMAR = """
start: (assign* expr) | quit_cmd
quit_cmd: "exit" | "quit"

%import common.CNAME

assign: CNAME "=" expr ";"

expr: move | shoot | eat | dup | if_expr | sequence
if_expr: "if" bool_expr "then" expr "else" expr
sequence: expr ("->" expr)+

move: "move" direction
shoot: "shoot" direction
eat: "eat"
dup: "dup" direction

%import common.INT
%import common.SIGNED_INT
INTEGER: INT | SIGNED_INT

num: TICK | INTEGER | arith | dim

direction: UP | RIGHT | DOWN | LEFT | HERE | RANDOM | pair | dir_plus | dir_minus | find
pair: "(" num "," num ")"
dir_plus: direction "+" direction
dir_minus: direction "-" direction
find: "find" find_expr

find_expr: DEAD

bool_expr: gt_expr | lt_expr | eq_expr | and_expr | or_expr
gt_expr: num ">" num
lt_expr: num "<" num
eq_expr: num "=" num
and_expr: bool_expr ("and" | "&") bool_expr
or_expr: bool_expr ("or" | "|") bool_expr

arith: plus | minus | modulo | absval
plus: num "+" num
minus: num "-" num
modulo: num "%" num
absval: "abs" num

dim: x | y
x: "x" direction
y: "y" direction

TICK: "tick"

UP: "up"
RIGHT: "right"
DOWN: "down"
LEFT: "left"
HERE: "here"
RANDOM: "random"

DEAD: "dead"

%ignore WHITESPACE
WHITESPACE: " " | "\\n"
"""
parser = Lark(GRAMMAR)

console = Console(highlight=False)
term = Terminal()


def new_entity(type_, x, y, **kwargs):
    return {"type": type_, "id": uuid4(), "x": x, "y": y, **kwargs}


def new_enemy():
    x, y = [random.randint(n) for n in (GRID_WIDTH, GRID_HEIGHT)]
    return new_entity("enemy", x, y, dead=False, score=0)


def new_player(code):
    x, y = [random.randint(n) for n in (GRID_WIDTH, GRID_HEIGHT)]
    return new_entity("player", x, y, active=True, dead=False, code=code, score=0)


class Evaluate(Transformer):
    def __init__(self, tick, entities, id_):
        self.assign = {}
        self.tick = tick
        self.entities = entities
        self.id_ = id_
        super().__init__()

    def start(self, child):
        return child[0]

    def assign(self, children):
        self.assign[children[0]] = children[1]

    def expr(self, child):
        cmd = child[0]
        cmd["assign"] = self.assign
        return cmd

    def direction(self, child):
        return child[0]

    def if_expr(self, children):
        if_, then_, else_ = children
        return then_ if if_ else else_

    def sequence(self, children):
        return children[self.tick % len(children)]

    def move(self, child):
        return {"type": "move", **child[0]}

    def shoot(self, child):
        return {"type": "shoot", **child[0]}

    def eat(self, _):
        return {"type": "eat"}

    def dup(self, child):
        return {"type": "dup", **child[0]}

    def quit_cmd(self, _):
        sys.exit()

    def num(self, child):
        return int(child[0])

    def pair(self, children):
        x, y = children
        return {"x": x, "y": y}

    def dir_plus(self, children):
        return {dim: children[0][dim] + children[1][dim] for dim in ["x", "y"]}

    def dir_minus(self, children):
        return {dim: children[0][dim] - children[1][dim] for dim in ["x", "y"]}

    def find(self, child):
        f = child[0]
        try:
            return [entity for entity in self.entities if f(entity)][0]
        except IndexError:
            return {"x": 0, "y": 0}

    def find_expr(self, child):
        return child[0]

    def bool_expr(self, child):
        return child[0]

    def gt_expr(self, children):
        return children[0] > children[1]

    def lt_expr(self, children):
        return children[0] < children[1]

    def eq_expr(self, children):
        return children[0] == children[1]

    def and_expr(self, children):
        return children[0] and children[1]

    def or_expr(self, children):
        return children[0] or children[1]

    def arith(self, child):
        return child[0]

    def plus(self, children):
        return children[0] + children[1]

    def minus(self, children):
        return children[0] - children[1]

    def modulo(self, children):
        return children[0] % children[1]

    def absval(self, child):
        return abs(child[0])

    def dim(self, child):
        return child[0]

    def x(self, child):
        return child[0]["x"]

    def y(self, child):
        return child[0]["y"]

    def TICK(self, _):
        return self.tick

    def UP(self, _):
        return {"x": 0, "y": -1}

    def RIGHT(self, _):
        return {"x": 1, "y": 0}

    def DOWN(self, _):
        return {"x": 0, "y": 1}

    def LEFT(self, _):
        return {"x": -1, "y": 0}

    def HERE(self, _):
        me = [entity for entity in self.entities if entity["id"] == self.id_][0]
        return {"x": me["x"], "y": me["y"]}

    def RANDOM(self, _):
        x = random.choice([-1, 0, 1])
        y = random.choice([-1, 0, 1])
        return {"x": x, "y": y}

    def DEAD(self, _):
        return lambda entity: entity["dead"]


def random_cmd():
    def random_direction():
        if random.random() > 0.75:
            return {"x": 0, "y": -1}
        elif random.random() > 0.5:
            return {"x": 1, "y": 0}
        elif random.random() > 0.25:
            return {"x": 0, "y": 1}
        else:
            return {"x": -1, "y": 0}

    if random.random() > 0.95:
        cmd_type = "dup"
    elif random.random() > 0.7:
        cmd_type = "shoot"
    else:
        cmd_type = "move"
    return {"type": cmd_type, **random_direction()}


def execute_cmd(cmd, entities, id_):
    index = [i for i, entity in enumerate(entities) if entity["id"] == id_][0]
    for var in cmd["assign"]:
        entities[index]["vars"][var] = cmd["assign"][var]
    if entities[index]["dead"]:
        return entities
    if cmd["type"] == "move":
        for dim, length in [("x", GRID_WIDTH), ("y", GRID_HEIGHT)]:
            max_ = length - 1
            new_pos = entities[index][dim] + cmd[dim]
            if new_pos > max_ or new_pos < 0:
                entities[index]["dead"] = True
            else:
                entities[index][dim] += cmd[dim]
    elif cmd["type"] == "shoot":
        x, y = entities[index]["x"], entities[index]["y"]
        x_eq = lambda entity: x == entity["x"]
        y_eq = lambda entity: y == entity["y"]
        if cmd["x"] < 0:
            dim_cmp = lambda entity: entity["x"] < x and y_eq(entity)
            rev, dim = True, "x"
        elif cmd["x"] > 0:
            dim_cmp = lambda entity: entity["x"] > x and y_eq(entity)
            rev, dim = False, "x"
        elif cmd["y"] < 0:
            dim_cmp = lambda entity: entity["y"] < y and x_eq(entity)
            rev, dim = True, "y"
        elif cmd["y"] > 0:
            dim_cmp = lambda entity: entity["y"] > y and x_eq(entity)
            rev, dim = False, "y"

        targets = filter(dim_cmp, entities)
        try:
            target = sorted(targets, key=lambda entity: entity[dim], reverse=rev)[0]
        except IndexError:
            return entities
        target_index = [
            i for i, entity in enumerate(entities) if target["id"] == entity["id"]
        ][0]
        entities[target_index]["dead"] = True
        entities[target_index]["just_shot"] = True
        entities[index]["score"] += 1
    elif cmd["type"] == "eat":
        x, y = entities[index]["x"], entities[index]["y"]
        same_tile = [
            entity for entity in entities if entity["x"] == x and entity["y"] == y
        ]
        for entity in same_tile:
            if entity["dead"]:
                del entities[entities.index(entity)]
                index -= 1
                entities[index]["score"] += 5
            else:
                entities[index]["dead"] = True
                return entities
    elif cmd["type"] == "dup":
        new_player = deepcopy(entities[index])
        new_player["x"] = entities[index]["x"] + cmd["x"]
        new_player["y"] = entities[index]["y"] + cmd["y"]
        if new_player["x"] not in range(GRID_WIDTH) or new_player["y"] not in range(
            GRID_HEIGHT
        ):
            return entities
        new_player["active"] = False
        new_player["id"] = uuid4()
        new_player["just_dup"] = True
        entities.append(new_player)
        entities[index]["score"] -= 1

    return entities


def render_entity(entity):
    if entity["type"] == "enemy":
        char = "X" if entity["dead"] else "!"
        style = "red"
    elif entity["type"] == "player":
        char = "X" if entity["dead"] else "@"
        style = "#bb88ff" if entity["active"] else "#8844bb"
    if "just_shot" in entity:
        style += " on yellow"

    return f"[{style}]{char}[/{style}]"


def render_grid(entities):
    grid = [["."] * GRID_WIDTH for _ in range(GRID_HEIGHT)]
    for entity in entities:
        x, y = entity["x"], entity["y"]
        grid[y][x] = render_entity(entity)
    return "\n".join(["".join(row) for row in grid])


def main():
    entities = []
    global_score = 0
    entities.extend([new_enemy() for _ in range(5)])
    while True:
        entities.extend([new_enemy() for _ in range(random.geometric(0.9) - 1)])

        with term.location(0, 0):
            console.print(render_grid(entities))
            print("\nPress Enter twice to submit.\n============================")
            code = "\n".join([line for line in iter(input, "")])
            print(term.move(GRID_HEIGHT + 3, 0) + term.clear_eos)

        try:
            code = parser.parse(code)
        except:
            print(term.move(GRID_HEIGHT + 3, 0) + "Failed to parse.")
            sleep(1)
            print(term.move_up + term.clear_eol)
            continue
        player = new_player(code)
        entities.append(player)

        with term.hidden_cursor():
            for tick in range(N_TURNS):
                for i, entity in enumerate(entities):
                    if "just_dup" in entity:
                        del entities[i]["just_dup"]
                        continue
                    cmd = (
                        Evaluate(tick, entities, entity["id"]).transform(entity["code"])
                        if entity["type"] == "player"
                        else random_cmd()
                    )
                    entities = execute_cmd(cmd, entities, entity["id"])
                with term.location(0, 0):
                    console.print(render_grid(entities))
                    score = [
                        entity
                        for entity in entities
                        if "active" in entity and entity["active"]
                    ][0]["score"]
                    print(
                        term.move(1, GRID_WIDTH + 1) + f"Score: {global_score + score}"
                    )
                sleep(0.1)

                for i, entity in enumerate(entities):
                    if "just_shot" in entity:
                        del entities[i]["just_shot"]

        global_score += score
        player_index = [
            i for i, entity in enumerate(entities) if entity["id"] == player["id"]
        ][0]
        entities[player_index]["active"] = False


with term.fullscreen():
    try:
        main()
    except KeyboardInterrupt:
        pass
