# General Imports
import asyncio
from collections import deque
import os
from dotenv import load_dotenv

# Yt_dlp Import
import yt_dlp

# Discord Imports
import discord
from discord.ext import commands

# Project Imports
from classes import AudioFile
from servers_dict import servers

from verifications import check_voice_client_decorator, check_song_play_type, check_server_decorator
from minio_functionality import create_minio_client, create_minio_bucket, delete_minio_bucket, get_minio_bucket_name, \
    get_presigned_url, upload_to_minio


load_dotenv()
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
minio_client = create_minio_client()

MAX_FILESIZE_MB = int(os.getenv("MAX_FILESIZE_MB"))
MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS"))

ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 256k -bufsize 64k'
}


@bot.event
async def on_guild_join(guild):
    print(f'Joined new guild: {guild.name} (ID: {guild.id})')

    create_minio_bucket(minio_client, guild.id)


@bot.event
async def on_guild_remove(guild):
    print(f'Removed from guild: {guild.name} (ID: {guild.id})')
    delete_minio_bucket(minio_client, get_minio_bucket_name(guild.id))


@bot.event
async def on_ready():
    print(f'Bot has logged in as {bot.user}')

    for guild in bot.guilds:
        print(f'Connected to guild: {guild.name} (ID: {guild.id})')

        servers[str(guild.id)] = {}
        servers[str(guild.id)]['songs'] = deque()
        servers[str(guild.id)]['just_joined_channel'] = False


@bot.command()
@check_server_decorator
@check_voice_client_decorator
async def play(ctx):
    voice_client = ctx.voice_client

    song_type_match = check_song_play_type(ctx.message.content)

    if song_type_match is None:
        await ctx.send("Invalid input.")
        return

    if servers[str(ctx.guild.id)]['just_joined_channel']:
        servers[str(ctx.guild.id)]['just_joined_channel'] = False
        voice_client.stop()

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(song_type_match[1], download=False)

    if song_type_match[0] == 'title':
        if info['entries']:
            info = info['entries'][0]
        else:
            await ctx.send("No titles found. Try again with shorter title.")
            return

    url = f"https://www.youtube.com/watch?v={info['id']}"

    if (info['filesize'] / (1024 * 1024)) > MAX_FILESIZE_MB:
        await ctx.send("File too large.")
        return
    elif info['duration'] > MAX_DURATION_SECONDS:
        await ctx.send("File duration too long.")
        return

    new_track = AudioFile(info['title'], url, info['filesize'], ctx.message.author)
    print(new_track)
    upload_to_minio(minio_client, ctx.guild.id, new_track)

    servers[str(ctx.guild.id)]['songs'].append(new_track)
    await ctx.send(f"✍️  Added to queue - **{new_track.title}**")

    if not voice_client.is_playing():
        await play_next_song(ctx)


async def play_next_song(ctx):
    if servers[str(ctx.guild.id)]['songs']:
        voice_client = ctx.voice_client
        song = servers[str(ctx.guild.id)]['songs'].popleft()
        bucket_name = get_minio_bucket_name(ctx.guild.id)

        def after_playback(e):
            if e:
                bot.loop.create_task(handle_disconnect_error(ctx, song))
            else:
                # Continue to play the next song
                bot.loop.create_task(play_next_song(ctx))

                # Delete from MinIO too
                minio_client.remove_object(bucket_name, song.suitable_name)

        presigned_url = get_presigned_url(minio_client, bucket_name, song.suitable_name)
        print(presigned_url)
        audio_source = discord.FFmpegPCMAudio(source=presigned_url, **ffmpeg_options)
        voice_client.play(audio_source, after=after_playback)

        await ctx.send(f"🔊  Now playing: **{song.title}**\n🗣️  Requested by *{song.requested_by}*.")
        await asyncio.sleep(1)


async def handle_disconnect_error(ctx, song):
    error_message = await ctx.send(f"⚠️ An error occurred while playing the song.\n"
                                   f"React with 👍 to retry or 👎 to cancel.")

    await error_message.add_reaction("👍")
    await error_message.add_reaction("👎")

    def check(check_reaction, user):
        return user in ctx.author.voice.channel.members and str(check_reaction.emoji) in ["👍", "👎"]

    try:
        reaction, _ = await bot.wait_for("reaction_add", check=check, timeout=15)

        if str(reaction.emoji) == "👍":
            await ctx.send('🔁 Replaying...')
            servers[str(ctx.guild.id)]['songs'].appendleft(song)
            await play_next_song(ctx)
        elif str(reaction.emoji) == "👎":
            await ctx.send('❌ Cancelling...')
    except TimeoutError:
        await ctx.send('❌ No reaction. Cancelling...')


@bot.command()
@check_server_decorator
@check_voice_client_decorator
async def skip(ctx):
    voice_client = ctx.voice_client
    if len(servers[str(ctx.guild.id)]['songs']) == 0:
        await ctx.send("Cannot skip since there are no songs in queue.")
    else:
        voice_client.stop()
        await ctx.send("Skipped the current song.")


@bot.command()
@check_server_decorator
@check_voice_client_decorator
async def queue(ctx):
    message_to_send = "\n".join(f"{i + 1}. {servers[str(ctx.guild.id)]['songs'][i].title}"
                                for i in range(0, len(servers[str(ctx.guild.id)]['songs'])))
    if message_to_send == "":
        message_to_send = "No songs in queue."
    else:
        message_to_send = "🎵  Songs Queue  🎵\n" + message_to_send

    await ctx.send(message_to_send)


@bot.command()
@check_server_decorator
@check_voice_client_decorator
async def pause(ctx):
    voice_client = ctx.voice_client

    voice_client.pause()
    await ctx.send("⏸️ Playback paused.")


@bot.command()
@check_server_decorator
@check_voice_client_decorator
async def resume(ctx):
    voice_client = ctx.voice_client

    voice_client.resume()
    await ctx.send("▶️ Playback resumed.")


@bot.command()
@check_server_decorator
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect(self_deaf=True)

        voice_client = ctx.voice_client
        intro_path = os.path.join(os.getcwd(), 'songs', 'intro_song.mp3')
        audio_source = discord.FFmpegPCMAudio(source=intro_path)
        servers[str(ctx.guild.id)]['just_joined_channel'] = True
        voice_client.play(audio_source)
    else:
        await ctx.send("Please join a voice channel!")


@bot.command()
@check_server_decorator
async def leave(ctx):
    voice_client = ctx.voice_client

    if voice_client:
        await ctx.voice_client.disconnect()
        for server in servers:
            servers[server]['songs'].clear()
    else:
        await ctx.send("I cannot leave something I am not connected to.\n"
                       "Use **!join** to connect me to a channel.")

bot.run(os.getenv("DISCORD_TOKEN"))
