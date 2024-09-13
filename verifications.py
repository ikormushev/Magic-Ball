import os
import re
from functools import wraps

from dotenv import load_dotenv
from servers_dict import servers

load_dotenv()

YOUTUBE_PATTERN = rf'{os.getenv("CHECK_PATTERN")}'


def check_voice_client_decorator(func):
    @wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        if ctx.voice_client is None:
            await ctx.send("I'm not in a voice channel! Use **!join** to make me join.")
            return
        return await func(ctx, *args, **kwargs)
    return wrapper


def check_song_play_type(content):
    match = re.match(YOUTUBE_PATTERN, content)

    if match:
        song_groups = match.groupdict()
        print(song_groups)
        if song_groups['title']:
            return ("title", f"ytsearch1:{song_groups['title']}")
        elif song_groups['url']:
            return ("url", song_groups['url'])


def check_server_decorator(func):
    @wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        if str(ctx.guild.id) not in servers:
            await ctx.send("Server not allowed.")
            return  # Stop execution if the server is not allowed
        return await func(ctx, *args, **kwargs)
    return wrapper
