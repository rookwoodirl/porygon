import discord
from openai import OpenAI, get_openapi
import os, sys
from pydantic import Dict


import inspect
import typing
from typing import get_type_hints


from dotenv import load_dotenv
load_dotenv()

openai_client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

# Create a client instance
intents = discord.Intents.default()
intents.message_content = True  # Needed to read message content
client = discord.Client(intents=intents)



models= [
    'gpt-4',
    'o3-mini',
    'gpt-4-turbo',
    'gpt-3.5-turbo',
    'o1',
    'gpt-4o',
    'gpt-4o-mini',
    'o1-mini',
]


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message):
    # Ignore the bot's own messages
    if message.author == client.user:
        return

    response = await get_chatgpt_response(message.channel)
    await message.channel.send(response)



with open('.prompt') as f:
    PROMPT = '\n'.join(f.readlines())




TOOLS = []
# Set your OpenAI API key
async def get_chatgpt_response(channel):
    global PROMPT
    # Fetch the last 10 messages using async iteration
    messages = []

    async for msg in channel.history(limit=30):
        messages.append(msg)

    # Reverse to get oldest to newest order
    messages.reverse()

    # Convert to OpenAI chat format
    openai_messages = [{'role' : 'system', 'content' : PROMPT}]
    for msg in messages:
        role = "assistant" if msg.author.bot else "user"
        openai_messages.append({
            "role": role,
            "content": f'{msg.author} says: {msg.content}'
        })

    # Call OpenAI's Chat Completion API
    response = openai_client.chat.completions.create(
        model="o3-mini",
        messages=openai_messages,
        tools=TOOLS)

    return response.choices[0].message.content




def generate_openai_tool_spec(func: callable) -> dict:
    """
    Generate an OpenAI-compatible function tool spec from a Python function.
    Assumes function uses type hints and a docstring.
    """
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)
    doc = inspect.getdoc(func) or ""
    
    # First line of docstring is summary
    description = doc.strip().split("\n")[0] if doc else ""
    
    # Build parameters schema
    properties = {}
    required = []
    
    for name, param in sig.parameters.items():
        param_type = type_hints.get(name, str)  # fallback to str
        param_info = {
            "type": python_type_to_openapi_type(param_type),
            "description": ""  # could parse extended docstrings here
        }
        if param.default is inspect.Parameter.empty:
            required.append(name)
        properties[name] = param_info

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }

def python_type_to_openapi_type(py_type: type) -> str:
    """Convert a Python type to OpenAPI-compatible type string."""
    origin = typing.get_origin(py_type) or py_type
    if origin in (int,):
        return "integer"
    elif origin in (float,):
        return "number"
    elif origin in (bool,):
        return "boolean"
    elif origin in (list,):
        return "array"
    elif origin in (dict,):
        return "object"
    else:
        return "string"





if __name__ == '__main__':
    if '--deploy' in sys.argv:
        client.run(os.environ['DISCORD_API_KEY'])


