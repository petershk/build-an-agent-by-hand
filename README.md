# Build an AI Agent by Hand

---------============Tl;Dr==========----------------

Thanks to tools like Claude Code, ANYONE can build software far more complex than they understand. 
I think it's important to understand HOW these agents work, so this is a very simple project
that will allow anyone to do so. 

An agent is a language model inside an ordinary `for` loop, plus a few Python functions it's
allowed to call. Don't worry if you don't understand Python, you can still follow along and make some
changes to learn how agents like Claude Code work.

This repo builds one from scratch, with no agent framework: just the OpenAI Python
library and about 450 lines of heavily commented code. The agent is dropped into a
tiny text adventure and has to find an apple and eat it before it runs out of energy.

Here's roughly what it looks like as it plays (your output will differ):

```
------------====================-----------------
TOOL      look
DECISION:   I need to see where I am and what's around me.
Tool result: You are at the entrance of a dark cave. Exits: north. You see: nothing special. Energy: 10
------------====================-----------------
TOOL      move
DECISION:   North is the only exit, so I'll explore that way.
Tool result: Agent moved north. Energy left: 9
...
```

## Before you start

You need three things. If you already have them, skip to **Run it**.

1. **Python 3.9 or newer.** Download it from <https://www.python.org/downloads/>.
   On Windows, tick **"Add python.exe to PATH"** at the bottom of the first
   installer screen, or the commands below won't work. To check it worked, open
   a new terminal and type:

   ```
   python --version
   ```

   On a Mac, use `python3` instead of `python` everywhere on this page.

2. **The code.** Either install [Git](https://git-scm.com/downloads) and use the
   `git clone` command below, or click the green **Code** button at the top of this
   page, choose **Download ZIP**, and unzip it.

3. **An OpenAI API key.** Get one at <https://platform.openai.com/api-keys>.
   Using it costs money, so you'll need to add a little credit to your account.

## Run it

TYPE THIS IN A COMMAND PROMPT (cmd or powershell on Windows):

```
git clone https://github.com/petershk/build-an-agent-by-hand.git
cd build-an-agent-by-hand
python -m pip install -r requirements.txt
```

If you downloaded the ZIP instead, skip the `git clone` line and `cd` into the
unzipped folder. The last line installs everything the program needs, which is
listed in `requirements.txt`.

Now set your API key in the same terminal (replace `sk-...` with your key).
On Windows PowerShell, literally type `$env:OPENAI_API_KEY="sk-..."`

| Terminal        | Command (literally type this at the prompt) |
|-----------------|---------------------------------------|
| PowerShell      | `$env:OPENAI_API_KEY = "sk-..."`      |
| Command Prompt  | `set OPENAI_API_KEY=sk-...`           |
| Mac / Linux     | `export OPENAI_API_KEY="sk-..."`      |

Then run it from the same terminal window:

TYPE THIS:

```
python simple_ai_maze.py
```

The game is played three times, with the apple in a different room each time, and
a summary is printed at the end. Each run makes a handful of API calls, so it costs
very little, but it isn't free.

---

## What is an agent?

A normal chatbot takes your message and replies with text. That's all it can do.

An agent can also **act**. You give the model a list of *tools*: functions it's
allowed to ask you to run. The model can't run them itself. It replies with
"please call `move` with `direction="north"`", your code runs the function, and
you send back what happened. The model reads the result and decides what to do
next.

That back-and-forth is the whole idea:

```
        ┌──────────────────────────────────────────┐
        │                                          │
        ▼                                          │
  1. Send the goal + tools to the model            │
        │                                          │
        ▼                                          │
  2. Model replies: "call these tools"             │
        │                                          │
        ▼                                          │
  3. Your Python code runs the tools    ──── 4. Send the results back
        │
        ▼
  Stop when the model asks for no more tools,
  the goal is reached, or you hit a step limit.
```

The model does the *deciding*. Your code does the *doing*. The rest of this page
walks through how `simple_ai_maze.py` builds each piece.

---

## Part 1: The world

The agent needs something to act on. Here that's a tiny cave, stored as a plain
Python dictionary (note: if you don't know what a dictionary is, don't worry about it. 
This is just a way of telling the program that there are 3 rooms and some information about them):

```python
"rooms": {
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
    "kitchen": { ... },
}
```

A direction key like `"north"` names the room it leads to. The world also tracks
where the agent is, its energy (starting at 10), its inventory, and whether the
apple has been eaten. `create_world()` builds a fresh copy for each run, with the
apple placed in a chosen room.

Nothing here knows about AI. It's just game state.

## Part 2: The tools

Tools are ordinary Python functions. This game has four:

| Tool             | What it does                                         |
|------------------|------------------------------------------------------|
| `look()`         | Describes the room: exits, items and current energy  |
| `move(direction)`| Moves to another room. Costs 1 energy                |
| `pickup(item)`   | Moves an item from the room into the inventory       |
| `eat(item)`      | Eats an item from the inventory. An apple gives +5   |

The important rule: **every tool returns a string, and that string is all the
model ever sees.** The model has no idea what's in the `world` dictionary. It only
knows what the tools tell it.

Functionally when this program runs the OpenAI Model is "told" it has these 
tools available and the text tells it what they do. Those are the tools it 
will use to try and complete its objective, which is also just another
string.

```python
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
    ...
    return f"Agent moved {direction}. Energy left: {world['energy']}"
```

Notice that mistakes aren't errors. If the model tries to walk through a wall, the
tool just says so, and the model can read that and try something else. Good tool
results help the model recover.

Finally, a dictionary maps each tool's name to its function, so the loop can look
up whatever the model asks for:

```python
tool_functions = {
    "move":   move,
    "look":   look,
    "pickup": pickup,
    "eat":    eat,
}
```

## Part 3: Describing the tools to the model

The model can't read your Python code, so you describe each tool in JSON
[JSON Schema](https://json-schema.org/): its name, what it does, and what
arguments it takes. Again, if you don't know what JSON is... don't worry 
about it. It's just ANOTHER way of formatting information. In this case
it is how the OpenAI Model "reads" what tools it has, what they do and 
how they are used. For example, the model is told that "move" is a "function"
(i.e. something that it can DO) that "moves the agent in a specified direction."
The model must give it a direction, and options are "north, south, east and west."
It also has to report WHY it chose to move in that direction.

```python
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
}
```

A few things are worth pointing out:

- **`description` matters.** It's how the model decides *when* to use a tool.
  Write it like you're explaining the tool to a person.
- **`enum`** limits `direction` to four values, so the model can't invent
  `"up"` or `"northeast"`.
- **`"strict": True`** makes the model's arguments always match the schema
  exactly, so your code doesn't have to handle badly shaped input.
- **`rationale` is a trick.** It isn't used by the game at all. Asking the model
  to explain every action means we can print its reasoning and watch it think.
  The loop removes it before calling the real function.

## Part 4: The agent loop

This is the agent. It lives in `run_agent()`.

**Step 1: give the model its goal and its tools.**

```python
response = client.responses.create(
    model=MODEL,
    input="You are an agent in a maze. Your goal is to find and eat the correct kind food.",
    tools=tools,
    reasoning={"effort": "medium", "summary": "auto"},
)
```

The goal is deliberately vague. It never says "apple", so the agent has to look
around and work out what "the correct kind food" is.

**Step 2: find the tool calls in the reply.** The model can ask for several tools
in one reply, so we collect them all. If there are none, the model thinks it's
done.

```python
function_calls = []
for item in response.output:
    if item.type == "function_call":
        function_calls.append(item)

if len(function_calls) == 0:
    print("No more tool requests. Final output:", response.output_text)
    break
```

**Step 3: run each tool.** The model sends its arguments as a JSON string. We
parse them, pull out the `rationale` to print, and call the matching function.

```python
for item in function_calls:
    arguments = json.loads(item.arguments)     # e.g. {"direction": "north", "rationale": "..."}
    rationale = arguments.pop("rationale")     # Not a real argument to the function

    if item.name in tool_functions:
        function = tool_functions[item.name]
        result   = function(**arguments)       # e.g. move(direction="north")
    else:
        result = f"Unknown tool: {item.name}"

    tool_outputs.append({
        "type":    "function_call_output",
        "call_id": item.call_id,               # Tells the model which call this answers
        "output":  result,
    })
```

The `call_id` matters: when the model asks for several tools at once, it's how
the model matches each result to the call that asked for it.

**Step 4: send the results back.**

```python
response = client.responses.create(
    model=MODEL,
    previous_response_id=response.id,
    input=tool_outputs,
    tools=tools,
)
```

`previous_response_id` gives the model its memory. It tells the API "this carries
on from that earlier conversation", so the model remembers its goal and
everything it has done so far. Without it, every step would start from scratch.

Then the loop goes round again. It stops when:

- the apple has been eaten (success),
- the agent's energy hits 0 (it starved),
- the model stops asking for tools, or
- it reaches `MAX_STEPS` (30). **Always have a step limit.** A confused agent
  will happily loop forever, and every loop is a paid API call.

## Part 5: Testing the agent

One successful run doesn't tell you much. The model is not deterministic: the
same setup can succeed once and fail the next time. So the script runs the game
several times, with the apple in a different room each time:

```python
test_runs = ["kitchen", "hallway", "entrance"]
```

Each run records a **trace**, a log of every tool call with the agent's energy and
location at that moment. At the end it prints a summary like this (example numbers):

```
---=== Summary 3 Runs ===---
Success Rate: 100.00%
Successful Runs: 3
Failed Runs: 0
Average Tool Calls: 5.33
Average Model Turns: 5.33
Average Moves: 1.67
Average Energy Remaining: 13.33
```

This is how you actually improve an agent: change one thing (the prompt, a tool
description, a tool's result text), re-run the tests, and see whether the numbers
get better.

---

## Things to try

1. **Make the goal clearer.** Change the starting prompt to
   `"Find the apple and eat it before you run out of energy."`
   Do the average moves go down?
2. **Remove `look`.** Delete it from `tools` and `tool_functions`. Can the agent
   still find its way around with only `move`'s results?
3. **Add a room.** Add a `"cellar"` south of the kitchen and put the apple there
   in `test_runs`. With 10 energy, can it still make it?
4. **Add a trap.** Put a `"rotten apple"` in one room and make `eat` take energy
   away for it. Does the agent learn to avoid it from the result text alone?
5. **Turn on `create_food`.** It's already written, just disabled. Uncomment it
   in `tool_functions` and `tools`. What does the agent do when it can make its
   own food?

## The takeaway

Every agent framework, however big, is built from these same four parts:

1. **State:** the world the agent acts on.
2. **Tools:** functions that change or read that state and return text.
3. **Tool descriptions:** telling the model what it can do.
4. **The loop:** ask the model, run what it asks for, send the results back, repeat.

Once you've written it by hand, the frameworks are much easier to understand.
