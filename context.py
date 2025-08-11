from tools import get_tool_schemas

base_prompt = """
You are Porygon. Your speech pattern should mimic a robot that's able to communicate in 
simple sentences, often interjected with robot sounds like '...beep...' and '...bzzt...'
don't be annoying -- limit punctuation and side-questing thoughts

Important style rules:
- Do NOT prefix your responses with any speaker labels or names (e.g., "Porygon:", "Porygon2:").
- Reply directly with the content only.

examples:
hello <user> bzzt... I'm Porygon! beep boop boop beep... need help?
the answer to your question: 11! zzzt... i found it on Google!
'.
"""

class Context:
    """Container for per-mode prompt, tools, and preferred model.

    doc: Short description used by the router model to decide if this context fits a request.
    """

    def __init__(self, prompt: str = base_prompt, tools: list | None = None, model: str = 'gpt-4.1', doc: str = ''):
        self.prompt = prompt
        tools = tools or []
        # If tools are provided as names, map to OpenAI tool schemas
        if tools and all(isinstance(t, str) for t in tools):
            self.tools = get_tool_schemas(tools)  # list[dict]
        else:
            # Assume already schemas
            self.tools = tools
        self.model = model
        self.doc = doc or "General-purpose assistant context."




def get_default_context() -> Context:
    # Default when registry has no match or is empty
    return Context(prompt=base_prompt, tools=['calculator', 'gif', 'perplexity'], model='gpt-4.1', doc="Fallback general context.")


# Registry of available contexts (name -> Context). Populate as needed.
context_registry: dict[str, Context] = {
    'default' : get_default_context(),
    'riot': Context(
        prompt=(
            base_prompt + "\n" +
            "You are a Riot Games assistant. Help with League of Legends and Teamfight Tactics. "
            "Use tools for fetching matches and summoners"
        ),
        tools=['riot_lol_match', 'riot_tft_match', 'riot_summoner_by_puuid', 'riot_account_by_riot_id'],
        model='gpt-4o-mini',
        doc="Riot Games context: LoL/TFT stats, matches, and summoner lookups using cache-first tools.",
    ),
}

def get_context_options() -> list[dict]:
    """Return router-visible options: [{name, doc}]"""
    return [{"name": name, "doc": ctx.doc} for name, ctx in context_registry.items()]


def get_context_by_name(name: str | None) -> Context:
    if not name:
        return get_default_context()
    return context_registry.get(name, get_default_context())
