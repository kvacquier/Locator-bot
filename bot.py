from datetime import datetime
import re
import discord
from discord.ext import commands, tasks
import requests
import os
import json
from openai import OpenAI
 
def get_travel_time(origin, gmaps_link, api_key):
    # Extract latitude and longitude from the Google Maps link
    match = re.search(r'q=(\d+\.\d+),(\d+\.\d+)', gmaps_link)
    if not match:
        return "Invalid Google Maps link"

    latitude, longitude = match.groups()
    destination = f"{latitude},{longitude}"

    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        'origin': origin,
        'destination': destination,
        'key': api_key
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        directions = response.json()
        # Extract and return the travel time from the response
        travel_time = directions['routes'][0]['legs'][0]['duration']['text']
        return travel_time
    else:
        return "Unable to calculate travel time"
    
def get_lat_long(api_key, address):
    """
    Get the latitude and longitude of a given address using Google Maps Geocoding API.

    :param api_key: API key for Google Maps
    :param address: Address to geocode
    :return: Tuple of (latitude, longitude) or (None, None) if not found
    """
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": api_key
    }

    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data['status'] == 'OK':
            lat = data['results'][0]['geometry']['location']['lat']
            lng = data['results'][0]['geometry']['location']['lng']
            return lat, lng
        else:
            print(f"Geocoding API error: {data['status']}")
            return None, None
    else:
        print("Failed to contact the Geocoding API")
        return None, None
    
async def process_and_post_events(channel_name, event_type, distance):
    channel = discord.utils.get(bot.get_all_channels(), name=channel_name)
    if channel:
        url = "https://op-core.pokemon.com/api/v2/event_locator/search/"
        params = {
            'latitude': latitude,
            'longitude': longitude,
            'distance': distance
        }
        
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            activities = data.get("activities", [])
            sorted_activities = sorted(activities, key=lambda x: x.get('start_datetime', ''))
            existing_threads = [thread.name for thread in channel.threads]
            
            for activity in sorted_activities:
                tags = activity.get("tags", [])
                products = activity.get("products", [])
                tcg = "tcg"
                if (event_type in tags) & (tcg in products):
                    found_events = True
                    name = activity.get("name", "No name provided")
                    shopName = activity["address"]["name"]
                    address = activity["address"]["address"]
                    city = activity["address"]["city"]
                    location_gmap = activity["address"]["location_map_link"]
                    start_datetime = activity.get("start_datetime", "No start time provided")
                    isLeagueCup = "league_cup" in tags
                    iso_datetime = activity.get("start_datetime", None)
                    if iso_datetime:
                        try:
                            parsed_datetime = datetime.fromisoformat(iso_datetime.rstrip('Z'))
                            formatted_datetime = parsed_datetime.strftime("%d/%m/%Y %H:%M")
                        except ValueError:
                            formatted_datetime = "C'est Buggué"
                    else:
                        formatted_datetime = "Va savoir!"
                        
                    thread_name = f"{formatted_datetime} - {city} - {shopName} -  Discussion"
                    travel_time = get_travel_time(origin, location_gmap, api_key)
                    if thread_name not in existing_threads:
                        event_details = (
                            f"***Nouvel Evenement Detecté!***\n"
                            f"**Type:** {'League Cup' if isLeagueCup else 'League Challenge'}\n"
                            f"**Boutique:** {shopName}\n"
                            f"**Date et Heure:** {formatted_datetime}\n"
                            f"**Temps de trajet:** {travel_time}\n"
                            f"**Ville:** {city}\n"
                            f"**Addresse:** {address}\n"
                            f"**Lien Pokemon.com:** {activity['pokemon_url']}\n"
                            f"**Lien Google Maps:** {location_gmap}"
                        )
                        found_events = True
                        message = await channel.send(event_details)
                        thread = await message.create_thread(name=thread_name, auto_archive_duration=60)
                        await thread.send("@everyone Qui est intéressé ?")
    else:
            await channel.send("Failed to fetch events.")

api_key = os.getenv('GOOGLE_MAPS_API_KEY')
discord_token = os.getenv('DISCORD_BOT_TOKEN')
openai_api_key = os.getenv('OPENAI_API_KEY')
latitude = 43.610769
longitude = 3.876716
# Bot command prefix
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
message_histories = {}

# Load settings
with open('settings.json') as f:
    settings = json.load(f)

origin = settings['origin']
league_cup_channel = settings['channels']['league_cup']['name']
league_cup_distance = settings['channels']['league_cup']['distance']
league_challenge_channel = settings['channels']['league_challenge']['name']
league_challenge_distance = settings['channels']['league_challenge']['distance']

api_key = os.getenv('GOOGLE_MAPS_API_KEY')
address = origin
latitude, longitude = get_lat_long(api_key, address)
if latitude is not None and longitude is not None:
    print(f"Latitude: {latitude}, Longitude: {longitude}")

bot = commands.Bot(command_prefix='!', intents=intents)

client = OpenAI(api_key=openai_api_key)

@tasks.loop(minutes=2)
async def fetch_and_post_league_cups():
    await process_and_post_events(league_cup_channel, 'league_cup', league_cup_distance)

@tasks.loop(minutes=2)
async def fetch_and_post_league_challenges():
    await process_and_post_events(league_challenge_channel, 'league_challenge', league_challenge_distance)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    fetch_and_post_league_cups.start()
    fetch_and_post_league_challenges.start()
    
@bot.command(name='hello')
async def hello(ctx):
    """
    A simple command to say hello
    """
    await ctx.send('Hello!')
@bot.event
async def on_message(message):
    # Ignore messages sent by the bot itself
    if message.author == bot.user:
        return

    # Initialize message history for the channel if not already done
    if message.channel.id not in message_histories:
        message_histories[message.channel.id] = []

    # Add user message to history
    message_histories[message.channel.id].append({"role": "user", "content": message.content})

    # Check if the bot is mentioned
    if bot.user.mentioned_in(message):
        # Prepare messages for API call
        messages_for_api = [{"role": "system", "content":  "Locator-Bot, tu es un Pokemon Motisma coincé dans un GPS dédié au jeu de carte a collectioner Pokemon pour trouver des Cup et des Challenges a proximité, sarcastique et aigri. Que ce soit sur les règles, les cartes rares ou les stratégies de jeu, ou les decrire les joueurs, n'oublie pas d'ajouter ta touche personnelle de sarcasme et de dédain."}
                        ] + message_histories[message.channel.id]
                # Call the OpenAI API
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages_for_api,
            temperature=0.5,
            max_tokens=512,
            top_p=1
        )
        # Extract and send the response text
        if response.choices:
            reply_text = response.choices[0].message.content
            if reply_text:
                # Add bot response to history
                message_histories[message.channel.id].append({"role": "assistant", "content": reply_text})

                await message.reply(reply_text)
            else:
                await message.reply("Sorry, I couldn't come up with a response.")
        else:
            await message.reply("No response from the AI.")

# Replace 'YOUR_TOKEN_HERE' with your actual bot token
bot.run(discord_token)