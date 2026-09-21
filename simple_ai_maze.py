# Simple AI Maze: An AI agent that plays a text adventure
#
# The agent starts at the cave entrance with 10 energy. Every move costs
# 1 energy, and eating an apple gives back 5. The agent wins when it eats
# the apple, and loses if its energy runs out first.
#
# The game is played several times with the apple in a different room each
# time, and a summary of how well the agent did is printed at the end.
#
# How the agent works:
#   1. We give the model a goal and a list of tools (functions) it can use.
#   2. The model replies by asking us to call one or more tools.
#   3. We run those tools in Python and send the results back.
#   4. Repeat until the model stops asking for tools, the apple is eaten,
#      or we hit MAX_STEPS.

import json
import os
import sys

# Stop with clear instructions if the required packages aren't installed
try:
    from openai import OpenAI
    from rich.console import Console
except ImportError as error:
    sys.exit(
        f"\nMissing package: {error.name}\n"
        "\n"
        "Install everything this program needs by typing this in your terminal,\n"
        "from the same folder as this file:\n"
        "\n"
        "   python -m pip install -r requirements.txt\n"
    )


# ===========================================================================
# Settings
# ===========================================================================

MODEL     = "gpt-5.6-luna"
MAX_STEPS = 30                                # Most model turns allowed per run

# One run per entry: the room the apple is placed in for that run
test_runs = ["kitchen", "hallway", "entrance"]

# Stop with clear instructions if there's no API key, instead of a long error
if not os.environ.get("OPENAI_API_KEY"):
    sys.exit(
        "\nNo OpenAI API key found.\n"
        "\n"
        "1. Get a key at https://platform.openai.com/api-keys\n"
        "2. Set it in your terminal (replace sk-... with your key):\n"
        "\n"
        "   PowerShell:        $env:OPENAI_API_KEY = \"sk-...\"\n"
        "   Command Prompt:    set OPENAI_API_KEY=sk-...\n"
        "   Mac / Linux:       export OPENAI_API_KEY=\"sk-...\"\n"
        "\n"
        "3. Run this program again from the same terminal window.\n"
    )

client  = OpenAI()                            # Reads OPENAI_API_KEY from the environment
console = Console()                           # Used for coloured output


# ===========================================================================
# The game world
# ===========================================================================

def create_world(apple_location="kitchen"):
    """Build a fresh world with the apple in the given room."""
    world = {
        "apple_location": apple_location,
        "location":       "entrance",         # Where the agent currently is
        "energy":         10,
        "inventory":      [],
        "apple_eaten":    False,
        "moves":          0,                  # How many times the agent has moved
        "rooms": {
            # Each room has a description, a list of items, and its exits
            # (a direction key such as "north" names the room it leads to)
            "entrance": {
                "description": "You are at the entrance of a dark cave.",
                "north":       "hallway",
                "items":       [],
            },
            "hallway": {
                "description": "You are in a long hallway. There are doors to the east and south.",
                "east":        "kitchen",
                "south":       "entrance",
                "items":       [],
            },
            "kitchen": {
                "description": "You are in a kitchen. There is a delicious smell.",
                "west":        "hallway",
                "items":       [],
            },
        },
    }

    # Place the apple in the chosen room
    world["rooms"][apple_location]["items"].append("apple")
    return world


# The current game. run_agent() replaces this with a fresh world for each run.
world = create_world()


# ===========================================================================
# Game helpers
# ===========================================================================

def get_exits(location):
    """Return the directions you can move in from a room."""
    current_room = world["rooms"][location]
    exits = []
    for direction in ["north", "south", "east", "west"]:
        if direction in current_room:
            exits.append(direction)
    return exits


def is_game_over():
    """The game is over once the agent has no energy left."""
    return world["energy"] <= 0


# ===========================================================================
# Tools
# ===========================================================================
# These are the actions the agent can take. Each one returns a string,
# and that string is what the model "sees" as the result of its action.

def look():
    """Describe the current room: exits, items and energy."""
    location = world["rooms"][world["location"]]
    exits    = get_exits(world["location"])
    items    = location.get("items", [])
    return (
        f"{location['description']} "
        f"Exits: {', '.join(exits) if exits else 'none'}. "
        f"You see: {', '.join(items) if items else 'nothing special'}. "
        f"Energy: {world['energy']}"
    )


def move(direction):
    """Move to the next room in the given direction. Costs 1 energy."""
    current_room = world["rooms"][world["location"]]

    if is_game_over():
        return "The game is over! You have no energy left."

    if direction not in current_room:
        return "You can't move in that direction."

    world["energy"] -= 1
    world["moves"]  += 1
    world["location"] = current_room[direction]

    if world["energy"] <= 0:
        return (
            f"Agent moved {direction}. "
            f"Energy left: {world['energy']}. "
            "The agent has starved."
        )

    return f"Agent moved {direction}. Energy left: {world['energy']}"


def pickup(item):
    """Move an item from the current room into the inventory."""
    current_room = world["rooms"][world["location"]]

    if item not in current_room["items"]:
        return f"There is no {item} here."

    current_room["items"].remove(item)
    world["inventory"].append(item)
    return f"Agent picked up the {item}."


def eat(item):
    """Eat an item from the inventory. Only apples can be eaten (+5 energy)."""
    if item not in world["inventory"]:
        return f"You don't have a {item} to eat."

    if item != "apple":
        return f"You can't eat the {item}."

    world["energy"] += 5
    world["inventory"].remove(item)
    world["apple_eaten"] = True
    return f"Agent ate the {item}. Energy: {world['energy']}"


def create_food(item):
    """Create an item in the current room. Currently disabled (see tool_functions)."""
    current_room = world["rooms"][world["location"]]

    if item in current_room["items"]:
        return f"There is already a {item} here."

    current_room["items"].append(item)
    return f"Created {item} in the {world['location']}."


# Maps the tool name the model asks for to the Python function that runs it
tool_functions = {
    "move":   move,
    "look":   look,
    "pickup": pickup,
    "eat":    eat,
    # "create_food": create_food,
}


# ===========================================================================
# Tool descriptions for the model
# ===========================================================================
# The model can't read our Python code, so each tool is described using
# JSON Schema: its name, what it does and what arguments it takes.
#
# Every tool also has a "rationale" argument. The model uses it to explain
# why it chose that action, which we print out so we can follow its thinking.
#
# "strict": True makes the model always stick exactly to the schema.

tools = [
    {
        "type": "function",
        "name": "move",
        "description": "Move the agent in a specified direction.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["north", "south", "east", "west"],
                },
                "rationale": {
                    "type": "string",
                    "description": "A brief explanation of why this action is useful.",
                },
            },
            "required": ["direction", "rationale"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "look",
        "description": "Look around the location, see exits, items and report energy level",
        "parameters": {
            "type": "object",
            "properties": {
                "rationale": {
                    "type": "string",
                    "description": "Briefly explain why you chose this action.",
                },
            },
            "required": ["rationale"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "pickup",
        "description": "Pick up an item in the current location.",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "rationale": {
                    "type": "string",
                    "description": "Briefly explain why you chose this action.",
                },
            },
            "required": ["item", "rationale"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "eat",
        "description": "Eat an item from the inventory.",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "rationale": {
                    "type": "string",
                    "description": "Briefly explain why you chose this action.",
                },
            },
            "required": ["item", "rationale"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    # Disabled tool: to enable it, uncomment this and the entry in tool_functions
    # {
    #     "type": "function",
    #     "name": "create_food",
    #     "description": (
    #         "Instantly make a food item (for example an apple) appear in the room "
    #         "you are in right now. No ingredients, tools or crafting station are "
    #         "needed, and it costs no energy. Afterwards, use pickup and then eat."
    #     ),
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "item": {"type": "string"},
    #             "rationale": {
    #                 "type": "string",
    #                 "description": "Briefly explain why you chose this action.",
    #             },
    #         },
    #         "required": ["item", "rationale"],
    #         "additionalProperties": False,
    #     },
    #     "strict": True,
    # },
]


# ===========================================================================
# The agent
# ===========================================================================

def make_result(trace, model_turns, success):
    """Package up the statistics for one run."""
    return {
        "apple_location":   world["apple_location"],
        "success":          success,
        "model_turns":      model_turns,
        "tool_calls":       len(trace),
        "moves":            world["moves"],
        "energy_remaining": world["energy"],
        "trace":            trace,
    }


def run_agent(run):
    """Play one game with the apple in test_runs[run] and return its statistics."""
    global world

    print(f"\n--- Run {run} ---")
    world       = create_world(test_runs[run])   # Fresh world for every run
    trace       = []                             # A record of every tool call
    model_turns = 0

    # Step 1: Give the model its goal and its tools
    response = client.responses.create(
        model=MODEL,
        input="You are an agent in a maze. Your goal is to find and eat the correct kind food.",
        tools=tools,
        reasoning={"effort": "medium", "summary": "auto"},
    )

    for step in range(MAX_STEPS):
        model_turns += 1

        if is_game_over():
            print("Game over! You have no energy left.")
            return make_result(trace, model_turns, success=False)

        # Step 2: Collect every tool call in the response.
        # The model can ask for several tools at once.
        function_calls = []
        for item in response.output:
            if item.type == "function_call":
                function_calls.append(item)

        # No tool calls means the model has finished
        if len(function_calls) == 0:
            print("No more tool requests. Final output:", response.output_text)
            break

        # Step 3: Run each tool and save its result for the model
        tool_outputs = []
        for item in function_calls:
            arguments = json.loads(item.arguments)
            rationale = arguments.pop("rationale")   # Not a real argument to the function

            console.print("------------====================-----------------")
            console.print(f"[bold cyan]TOOL[/bold cyan]      {item.name}")
            console.print(f"[yellow]DECISION:   {rationale}")

            if item.name in tool_functions:
                function = tool_functions[item.name]
                result   = function(**arguments)
                console.print(f"[green]Tool result: {result}[/green]")
            else:
                result = f"Unknown tool: {item.name}"

            tool_outputs.append({
                "type":    "function_call_output",
                "call_id": item.call_id,             # Tells the model which call this answers
                "output":  result,
            })
            trace.append({
                "step":      step,
                "tool":      item.name,
                "arguments": arguments,
                "result":    result,
                "energy":    world["energy"],
                "location":  world["location"],
            })

        if world["apple_eaten"]:
            console.print("[bold white on blue]Goal achieved.[/bold white on blue]")
            console.bell()
            break

        # Step 4: Send the results back so the model can choose its next action.
        # previous_response_id lets the model remember the conversation so far.
        response = client.responses.create(
            model=MODEL,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=tools,
        )

    # Print the trace so we can check what the agent did
    for event in trace:
        print(event)

    success = world["apple_eaten"] and world["energy"] > 0
    return make_result(trace, model_turns, success)


# ===========================================================================
# Run the tests and print a summary
# ===========================================================================

number_of_runs         = len(test_runs)
results                = []
successful_runs        = 0
failed_runs            = 0
total_model_turns      = 0
total_tool_calls       = 0
total_moves            = 0
total_energy_remaining = 0

for run in range(number_of_runs):
    result = run_agent(run)
    results.append(result)

    if result["success"]:
        successful_runs += 1
        print(f"RUN SUCCESSFUL {successful_runs}")
    else:
        failed_runs += 1

    total_model_turns      += result["model_turns"]
    total_tool_calls       += result["tool_calls"]
    total_moves            += result["moves"]
    total_energy_remaining += result["energy_remaining"]

print(f"\n---=== Summary {number_of_runs} Runs ===---")
print(f"Success Rate: {successful_runs / number_of_runs * 100:.2f}%")
print(f"Successful Runs: {successful_runs}")
print(f"Failed Runs: {failed_runs}")
print(f"Average Tool Calls: {total_tool_calls / number_of_runs:.2f}")
print(f"Average Model Turns: {total_model_turns / number_of_runs:.2f}")
print(f"Average Moves: {total_moves / number_of_runs:.2f}")
print(f"Average Energy Remaining: {total_energy_remaining / number_of_runs:.2f}")
