

from tools import tool
from pathlib import Path

@tool('readme')
def readme() -> str:
    """
    Return README.md, which can be used to answer user questions about what Pory is capable of.
    Don't give the user the whole README -- try to understand what the user wants to know, 
    and then use the README to answer that question.
    """
    
    with open(Path(__file__).parent.parent / "README.md") as f:
        return '\n'.join(f.readlines())


__all__ = ["readme"]