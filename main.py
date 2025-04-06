import discord
from openai import OpenAI
import os


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
    response = openai_client.chat.completions.create(model="o3-mini",
    messages=openai_messages)

    return response.choices[0].message.content




# Replace 'YOUR_BOT_TOKEN' with your actual bot token
client.run(os.environ['DISCORD_API_KEY'])


