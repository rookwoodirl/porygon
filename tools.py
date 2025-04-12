
import inspect
from typing import get_type_hints, Dict, Callable

import typing



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

class Tool:
    # static
    tools = []  


    def __init__(self, func):
        self.oas : dict = Tool._get_oas(func)
        self.name : str  = func.__name__
        self.func : callable = func

        Tool.tools.append(self)

    def _get_oas(func: Callable) -> Dict:
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

        oas = {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": description,
                "parameters":{
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
        
        print('oas:', oas)
        return oas
    
    def __call__(self, **kwargs):
        print(**kwargs)
        return self.func(**kwargs)
    


