from blessings import Terminal
from copy import deepcopy
from itertools import chain
from lark import Lark, Transformer
from lark.visitors import CollapseAmbiguities
from numpy import random
import readline
from rich.console import Console
import sys
from textwrap import dedent
from time import sleep
from uuid import uuid4

GRID_HEIGHT = 20
GRID_WIDTH = 40
N_TURNS = 25

GRAMMAR = """
%import common.CNAME

start: (assign*) main_expr | quit_cmd
main_expr: expr
assign: CNAME "=" expr ";"
quit_cmd: "quit" | "exit"

expr: cmd | direction | bool_expr | num | find_expr | if_expr | sequence | parens | variable
if_expr: "if" expr "then" expr "else" expr
sequence: expr ("->" expr)+
parens: "(" expr ")"
variable: "$" CNAME

cmd: move | shoot | eat | dup
move: "move" expr
shoot: "shoot" expr
eat: "eat"
dup: "dup" expr

direction: UP | RIGHT | DOWN | LEFT | HERE | RANDOM | pair | dir_plus | dir_minus | find
UP: "up"
RIGHT: "right"
DOWN: "down"
LEFT: "left"
HERE: "here"
RANDOM: "random"
pair: "(" expr "," expr ")"
dir_plus: direction "+" direction
dir_minus: direction "-" direction
find: "find" expr

bool_expr: gt_expr | lt_expr | eq_expr | and_expr | or_expr | not_expr
gt_expr: expr ">" expr
lt_expr: expr "<" expr
eq_expr: expr "=" expr
and_expr: expr ("and" | "&") expr
or_expr: expr ("or" | "|") expr
not_expr: ("not" | "!") expr

%import common.INT
%import common.SIGNED_INT

num: TICK | INTEGER | arith | dim
TICK: "tick"
INTEGER: INT | SIGNED_INT

arith: plus | minus | modulo | absval
plus: expr "+" expr
minus: expr "-" expr
modulo: expr "%" expr
absval: ("abs" expr) | ("|" expr "|")

dim: x | y
x: "x" expr
y: "y" expr

find_expr: ALIVE | DEAD | PLAYER | ENEMY
ALIVE: "alive"
DEAD: "dead"
PLAYER: "player"
ENEMY: "enemy"

%ignore " " | "\\n"
"""
parser = Lark(GRAMMAR, ambiguity="explicit")

console = Console(highlight=False)
term = Terminal()


def new_entity(type_, x, y, **kwargs):
    return {"type": type_, "id": uuid4(), "x": x, "y": y, **kwargs}


def new_enemy():
    x, y = [random.randint(n) for n in (GRID_WIDTH, GRID_HEIGHT)]
    return new_entity("enemy", x, y, dead=False, score=0, store={})


def new_player(code):
    x, y = [random.randint(n) for n in (GRID_WIDTH, GRID_HEIGHT)]
    return new_entity(
        "player", x, y, active=True, dead=False, code=code, score=0, store={}
    )


class Evaluate(Transformer):
    def __init__(self, tick, entities, id_):
        self.assign_store = {}
        self.tick = tick
        self.entities = entities
        self.id_ = id_
        super().__init__()

    def start(self, child):
        return child[-1]

    def main_expr(self, child):
        cmd = child[0]
        cmd["assign"] = self.assign_store
        return cmd

    def assign(self, children):
        self.assign_store[children[0]] = children[1]

    def expr(self, child):
        return child[0]

    def cmd(self, child):
        return child[0]

    def direction(self, child):
        return child[0]

    def if_expr(self, children):
        if_, then_, else_ = children
        return then_ if if_ else else_

    def sequence(self, children):
        return children[self.tick % len(children)]

    def parens(self, child):
        return child[0]

    def variable(self, child):
        var_name = child[0]
        if var_name in self.assign_store:
            return self.assign_store[var_name]
        else:
            me = [entity for entity in self.entities if entity["id"] == self.id_]
            return me["store"][var_name]

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
            return random.choice(
                [
                    {"x": entity["x"], "y": entity["y"]}
                    for entity in self.entities
                    if f(entity)
                ]
            )
        except ValueError:
            return self.HERE(None)

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
        if callable(children[0]) and callable(children[1]):
            return lambda entity: children[0](entity) and children[1](entity)
        return children[0] and children[1]

    def or_expr(self, children):
        if callable(children[0]) and callable(children[1]):
            return lambda entity: children[0](entity) or children[1](entity)
        return children[0] or children[1]

    def not_expr(self, child):
        return not child[0]

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
        here = self.HERE(None)
        x, y = here["x"], here["y"]
        return {"x": x, "y": y - 1}

    def RIGHT(self, _):
        here = self.HERE(None)
        x, y = here["x"], here["y"]
        return {"x": x + 1, "y": y}

    def DOWN(self, _):
        here = self.HERE(None)
        x, y = here["x"], here["y"]
        return {"x": x, "y": y + 1}

    def LEFT(self, _):
        here = self.HERE(None)
        x, y = here["x"], here["y"]
        return {"x": x - 1, "y": y}

    def HERE(self, _):
        me = [entity for entity in self.entities if entity["id"] == self.id_][0]
        return {"x": me["x"], "y": me["y"]}

    def RANDOM(self, _):
        x = random.randint(GRID_WIDTH)
        y = random.choice(GRID_HEIGHT)
        return {"x": x, "y": y}

    def ALIVE(self, _):
        return lambda entity: not entity["dead"]

    def DEAD(self, _):
        return lambda entity: entity["dead"]

    def PLAYER(self, _):
        return lambda entity: entity["type"] == "player"

    def ENEMY(self, _):
        return lambda entity: entity["type"] == "enemy"


def random_cmd(entity):
    def random_direction():
        x, y = entity["x"], entity["y"]
        if random.random() > 0.75:
            return {"x": x, "y": y - 1}
        elif random.random() > 0.5:
            return {"x": x + 1, "y": y}
        elif random.random() > 0.25:
            return {"x": x, "y": y + 1}
        else:
            return {"x": x - 1, "y": y}

    if random.random() > 0.95:
        cmd_type = "dup"
    elif random.random() > 0.9:
        cmd_type = "shoot"
    else:
        cmd_type = "move"
    return {"type": cmd_type, "assign": {}, **random_direction()}


def execute_cmd(cmd, entities, id_):
    index = [i for i, entity in enumerate(entities) if entity["id"] == id_][0]
    for var in cmd["assign"]:
        entities[index]["store"][var] = cmd["assign"][var]
    if entities[index]["dead"]:
        return entities
    if cmd["type"] == "move":
        already_on_tile = [
            entity
            for entity in entities
            if entity["x"] == cmd["x"]
            and entity["y"] == cmd["y"]
            and not entity["dead"]
        ]
        if len(already_on_tile) > 0:
            return entities
        for dim, length in [("x", GRID_WIDTH), ("y", GRID_HEIGHT)]:
            max_ = length - 1
            new_pos = cmd[dim]
            if new_pos > max_ or new_pos < 0:
                entities[index]["dead"] = True
            else:
                entities[index][dim] = cmd[dim]
    elif cmd["type"] == "shoot":
        x, y = entities[index]["x"], entities[index]["y"]
        x_eq = lambda entity: x == entity["x"]
        y_eq = lambda entity: y == entity["y"]
        if cmd["x"] < x:
            dim_cmp = lambda entity: entity["x"] < x and y_eq(entity)
            rev, dim = True, "x"
        elif cmd["x"] > x:
            dim_cmp = lambda entity: entity["x"] > x and y_eq(entity)
            rev, dim = False, "x"
        elif cmd["y"] < y:
            dim_cmp = lambda entity: entity["y"] < y and x_eq(entity)
            rev, dim = True, "y"
        elif cmd["y"] > y:
            dim_cmp = lambda entity: entity["y"] > y and x_eq(entity)
            rev, dim = False, "y"
        else:
            return entities

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
            elif entity["id"] != id_:
                entities[index]["dead"] = True
                return entities
    elif cmd["type"] == "dup":
        already_on_tile = [
            entity
            for entity in entities
            if entity["x"] == cmd["x"] and entity["y"] == cmd["y"]
        ]
        if len(already_on_tile) > 0:
            return entities
        new_player = deepcopy(entities[index])
        new_player["x"] = cmd["x"]
        new_player["y"] = cmd["y"]
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


def disambiguate(code, entities, id_):
    interps = CollapseAmbiguities().transform(code)
    for interp in interps:
        try:
            for tick in range(N_TURNS):
                Evaluate(tick, entities, id_).transform(interp)
        except Exception as e:
            continue
        else:
            return interp


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

        player_index = [
            i for i, entity in enumerate(entities) if entity["id"] == player["id"]
        ][0]
        code = disambiguate(code, entities, player["id"])
        if code is None:
            print(term.move(GRID_HEIGHT + 3, 0) + "Failed to evaluate.")
            sleep(1)
            print(term.move_up + term.clear_eol)
            del entities[player_index]
            continue
        entities[player_index]["code"] = code

        with term.hidden_cursor():
            for tick in range(N_TURNS):
                for i, entity in enumerate(entities):
                    if "just_dup" in entity:
                        del entities[i]["just_dup"]
                        continue
                    cmd = (
                        Evaluate(tick, entities, entity["id"]).transform(entity["code"])
                        if entity["type"] == "player"
                        else random_cmd(entity)
                    )
                    entities = execute_cmd(cmd, entities, entity["id"])
                with term.location(0, 0):
                    console.print(render_grid(entities))
                    try:
                        score = [
                            entity
                            for entity in entities
                            if "active" in entity and entity["active"]
                        ][0]["score"]
                    except:
                        print(
                            term.move(2, GRID_WIDTH + 1)
                            + "Your player was killed and eaten!"
                        )
                        sleep(1)
                        print(term.move(2, GRID_WIDTH + 1) + term.clear_eol)
                        break
                    print(
                        term.move(1, GRID_WIDTH + 1) + f"Score: {global_score + score}"
                    )
                sleep(0.1)

                for i, entity in enumerate(entities):
                    if "just_shot" in entity:
                        del entities[i]["just_shot"]

        global_score += score
        try:
            player_index = [
                i for i, entity in enumerate(entities) if entity["id"] == player["id"]
            ][0]
            entities[player_index]["active"] = False
        except:
            pass


try:
    with term.fullscreen():
        console.print(
            dedent(
                """
                Welcome!
                You will code a bot; its goal is to shoot other bots and eat their dead bodies.

                I didn't have time to write a good tutorial, but I do have examples:

                [b]move up[/b]
                  -- moves up every turn

                [b]if tick = 0 then move (0, 0) else move down -> shoot right[/b]
                  -- on the first turn, moves to the top left.
                     then, alternates between moving down and shooting to the right

                [b]move (tick, tick) -> eat[/b]
                  -- moves diagonally from the top.
                     eats anything it lands on

                [b]if tick < 3 then dup random else move find dead -> eat[/b]
                  -- find out for yourself :)

                [b]move right -> move left[/b]
                  -- shakes

                [b]move (y here, x here)[/b]
                  -- shakes violently

                [b]move (find enemy - (1, 0)) -> shoot right -> move right -> eat[/b]
                  -- this [i]should[/i] actually get points

                I was going to add
                  1. more things to find
                  2. walls
                ...but I ran out of time.

                Press Enter to continue.
                """
            )
        )
        input()
except KeyboardInterrupt:
    sys.exit()


with term.fullscreen():
    try:
        main()
    except KeyboardInterrupt:
        pass
