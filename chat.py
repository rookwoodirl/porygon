

import os
import json
from tools import Tool

from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()




client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

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


with open('.prompt') as f:
    PROMPT = '\n'.join(f.readlines())

async def get_chatgpt_response(channel):
    global PROMPT
    global TOOLS

    # Fetch the last 30 messages using async iteration
    messages = []
    async for msg in channel.history(limit=30):
        messages.append(msg)
    messages.reverse()

    # Convert to OpenAI chat format
    openai_messages = [{'role': 'system', 'content': PROMPT}]
    for msg in messages:
        role = "assistant" if msg.author.bot else "user"
        openai_messages.append({
            "role": role,
            "content": f'{msg.author} says: {msg.content}'
        })

    # Call OpenAI's Chat Completion API
    response = client.chat.completions.create(
        model="o3-mini",
        messages=openai_messages,
        tools=[tool.oas for tool in Tool.tools]
    )

    choice = response.choices[0].message

    # If a tool call is required
    if choice.tool_calls:
        tool_call = choice.tool_calls[0]
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)

        # Find the matching tool
        tool_func = next((t for t in Tool.tools if t.name == tool_name), None)
        if tool_func is None:
            return f"Tool '{tool_name}' not found."

        # Execute the tool
        print('args', tool_args)
        tool_result = await tool_func(**tool_args)

        # Append the tool call and result to the messages
        openai_messages.append({
            "role": "assistant",
            "tool_calls": [tool_call]
        })
        openai_messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": tool_result
        })

        # Call the model again with the tool result
        followup = client.chat.completions.create(
            model="o3-mini",
            messages=openai_messages
        )

        return followup.choices[0].message.content

    return choice.content



