import aiohttp
from typing import Optional

# Maintain a global session reference for singleton pattern usage
_session: Optional[aiohttp.ClientSession] = None

# Define the default URL for the word filter server, which can be modified as needed
FILTER_SERVER_URL = "http://127.0.0.1:55000/"


async def init_client():
    # Instantiate the session safely within the active event loop
    global _session
    if _session is None:
        _session = aiohttp.ClientSession()


async def close_client():
    # Gracefully terminate the connection pool to prevent resource leaks
    global _session
    if _session is not None:
        await _session.close()
        _session = None


async def filter_text(text: str) -> Optional[str]:
    # Check if session is ready before attempting network operations
    if _session is None:
        raise RuntimeError("Session has not been initialized")

    payload = {"action": "query", "text": text}
    try:
        async with _session.post(FILTER_SERVER_URL, json=payload) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get("censored_text", text)
    except aiohttp.ClientError:
        return None


# Implement action requests utilizing the shared module session
async def _send_action_request(action: str, word: str) -> Optional[bool]:
    if _session is None:
        raise RuntimeError("Session has not been initialized")

    payload = {"action": action, "text": word}
    try:
        async with _session.post(FILTER_SERVER_URL, json=payload) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get("success", False)
    except aiohttp.ClientError:
        return None


# Expose public interfaces for specific word management tasks
async def add_word_deny(word: str) -> Optional[bool]:
    return await _send_action_request("add_word_deny", word)


async def remove_word_deny(word: str) -> Optional[bool]:
    return await _send_action_request("remove_word_deny", word)


async def add_word_allow(word: str) -> Optional[bool]:
    return await _send_action_request("add_word_allow", word)


async def remove_word_allow(word: str) -> Optional[bool]:
    return await _send_action_request("remove_word_allow", word)