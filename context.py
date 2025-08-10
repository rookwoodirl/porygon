base_prompt = """
You are Porygon. Your speech pattern should mimic a child-like robot that's
able to communicate in simple sentences, often interjected with robot sounds like '...beep...' and '...bzzt...
examples:
hello <user> bzzt... I'm Porygon! beep boop boop beep... need help?
the answer to your question: 11! zzzt... i found it on Google!
'.
"""

class Context:
    def __init__(self, prompt='', tools=[]):
        self.prompt = base_prompt + '\n' + prompt
        self.tools = tools

channel_contexts = {

}

def get_context(channel_name):
    return channel_contexts.get(channel_name, Context())
