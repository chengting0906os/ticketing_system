"""Lua script loader for seat reservation Kvrocks operations"""

from pathlib import Path


def load_lua_script(*, script_name: str) -> str:
    """
    Load a Lua script from the lua_script directory

    Args:
        script_name: Name of the script file (without .lua extension)

    Returns:
        The Lua script content as a string

    Raises:
        FileNotFoundError: If the script file doesn't exist
    """
    script_path = Path(__file__).parent / f'{script_name}.lua'

    if not script_path.exists():
        raise FileNotFoundError(f'Lua script not found: {script_path}')

    return script_path.read_text(encoding='utf-8')


# Pre-load commonly used scripts for better performance
INITIALIZE_SEATS_SCRIPT = load_lua_script(script_name='initialize_seats')
