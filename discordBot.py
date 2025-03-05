import discord
import asyncio
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from discord.ext import commands
import yt_dlp
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

load_dotenv()
# Add your discord developer token, spotify client id and spotify client secret as TOKEN, SPOTIFY_CLIENT_ID, and SPOTIFY_CLIENT_SECRET respectively. 

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents)

queues = {}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -loglevel quiet',
    'options': '-vn'
}

yt_dl_options = {
    'format': 'bestaudio/best',
    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
}

def ensure_queue(guild_id):
    """Ensure there is a queue for the guild."""
    if guild_id not in queues:
        queues[guild_id] = []


def get_youtube_url(search_query):
    """Search YouTube for a video matching the query and return its URL."""
    try:
        ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
        with YoutubeDL(ydl_opts) as ydl:
            search_result = ydl.extract_info(f"ytsearch:{search_query}", download=False)
            if search_result and 'entries' in search_result and len(search_result['entries']) > 0:
                return search_result['entries'][0]['url']
    except Exception as e:
        print(f"Error searching YouTube: {e}")
    return None


def get_spotify_tracks(spotify_url):
    """Retrieve track names from a Spotify playlist or album URL."""
    tracks = []
    try:
        if "playlist" in spotify_url:
            results = sp.playlist_tracks(spotify_url)['items']
        elif "album" in spotify_url:
            results = sp.album_tracks(spotify_url)['items']
        else:
            return []

        for track in results:
            track_name = track['track']['name']
            track_artist = track['track']['artists'][0]['name']
            search_query = f"{track_artist} - {track_name} audio"
            youtube_url = get_youtube_url(search_query)
            if youtube_url:
                tracks.append((track_name, youtube_url))
    except Exception as e:
        print(f"Error fetching Spotify tracks: {e}")
    return tracks


async def play_next_song(guild_id):
    """Plays the next song in the queue."""
    vc = discord.utils.get(client.voice_clients, guild=client.get_guild(guild_id))
    if not vc or not vc.is_connected():
        return

    ensure_queue(guild_id)
    if len(queues[guild_id]) == 0:
        await asyncio.sleep(5)
        await vc.disconnect()
        return

    song_name, song_url = queues[guild_id].pop(0)
    
    def after_playback(error):
        if error:
            print(f"Error occurred during playback: {error}")
        future = asyncio.run_coroutine_threadsafe(play_next_song(guild_id), client.loop)
        try:
            future.result()
        except Exception as e:
            print(f"Error moving to next song: {e}")

    try:
        vc.play(discord.FFmpegPCMAudio(song_url, **FFMPEG_OPTIONS), after=after_playback)
        print(f"🎵 Now playing: {song_name}")
    except Exception as e:
        print(f"Error playing song: {e}")


@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user.name}')


@client.command()
async def play(ctx, url: str):
    """Plays a song from YouTube or a Spotify track/playlist/album."""
    voice_channel = ctx.author.voice.channel
    if not voice_channel:
        await ctx.send("❌ Join a voice channel first!")
        return

    vc = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if not vc or not vc.is_connected():
        vc = await voice_channel.connect()

    ensure_queue(ctx.guild.id)

    if "spotify.com/track" in url:
        track_info = sp.track(url)
        track_name = track_info['name']
        artist_name = track_info['artists'][0]['name']
        search_query = f"{artist_name} - {track_name} audio"
        youtube_url = get_youtube_url(search_query)
        if youtube_url:
            queues[ctx.guild.id].append((track_name, youtube_url))
            await ctx.send(f"🎵 Added: {track_name} (via YouTube)")
        else:
            await ctx.send("❌ Could not find a YouTube equivalent for this Spotify track.")
            return

    elif "spotify.com/playlist" in url or "spotify.com/album" in url:
        tracks = get_spotify_tracks(url)
        if tracks:
            queues[ctx.guild.id].extend(tracks)
            await ctx.send(f"🎶 Added {len(tracks)} tracks from Spotify to queue!")
        else:
            await ctx.send("❌ Could not retrieve tracks from this Spotify playlist/album.")
            return

    else:
        youtube_url = get_youtube_url(url)
        if youtube_url:
            queues[ctx.guild.id].append((url, youtube_url))
            await ctx.send(f"🎵 Added to queue: {url}")
        else:
            await ctx.send("❌ Could not find a YouTube equivalent.")

    if not vc.is_playing():
        await play_next_song(ctx.guild.id)


@client.command()
async def skip(ctx):
    """Skips the current song and plays the next one."""
    vc = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("⏭️ Skipped! Playing next song...")
        await play_next_song(ctx.guild.id)


@client.command()
async def pause(ctx):
    """Pauses the currently playing song."""
    vc = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ Paused the song!")


@client.command()
async def resume(ctx):
    """Resumes a paused song."""
    vc = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("▶️ Resumed the song!")


@client.command()
async def leave(ctx):
    """Disconnects the bot from the voice channel."""
    vc = discord.utils.get(client.voice_clients, guild=ctx.guild)
    if vc and vc.is_connected():
        await vc.disconnect()
        await ctx.send("👋 Disconnected from voice channel.")


client.run(TOKEN)
