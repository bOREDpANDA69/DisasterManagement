from flask import Flask, request, jsonify, render_template, session
import os
import json
import requests
from groq import Groq
from functools import lru_cache
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Initialize Groq client
# Replace with your actual API key
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

# TomTom API key
# Replace with your actual API key
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")

# Store chat history
chat_histories = {}

@lru_cache(maxsize=100)
def get_nearby_places(location, radius=5000, categories=None):
    """
    Get nearby important places using TomTom API
    
    Args:
        location (str): Location name or coordinates
        radius (int): Search radius in meters
        categories (list): Categories of places to search for
        
    Returns:
        dict: JSON response with nearby places
    """
    # First convert location name to coordinates if not already coordinates
    if not (isinstance(location, tuple) or ',' in location):
        geocode_url = f"https://api.tomtom.com/search/2/geocode/{location}.json?key={TOMTOM_API_KEY}"
        response = requests.get(geocode_url)
        data = response.json()
        if 'results' in data and len(data['results']) > 0:
            position = data['results'][0]['position']
            lat, lon = position['lat'], position['lon']
        else:
            return {"error": "Location not found"}
    else:
        if isinstance(location, tuple):
            lat, lon = location
        else:
            lat, lon = map(float, location.split(','))
    
    # If no categories specified, use default critical infrastructure
    if not categories:
        categories = ['hospital', 'police station', 'fire station', 'shelter', 'open space']
    
    # Get nearby places for each category
    all_places = {}
    for category in categories:
        poi_url = f"https://api.tomtom.com/search/2/poiSearch/{category}.json?lat={lat}&lon={lon}&radius={radius}&key={TOMTOM_API_KEY}"
        response = requests.get(poi_url)
        data = response.json()
        all_places[category] = data.get('results', [])
    
    return {
        "center": {"lat": lat, "lon": lon},
        "places": all_places
    }

def get_route(from_location, to_location):
    """
    Get the shortest route between two locations using TomTom API
    """
    # Convert locations to coordinates if needed
    # [Implementation for geocoding addresses omitted for brevity]
    
    # For now, we'll assume locations are provided as "lat,lon"
    from_lat, from_lon = map(float, from_location.split(','))
    to_lat, to_lon = map(float, to_location.split(','))
    
    # Get route
    route_url = f"https://api.tomtom.com/routing/1/calculateRoute/{from_lat},{from_lon}:{to_lat},{to_lon}/json?key={TOMTOM_API_KEY}"
    response = requests.get(route_url)
    return response.json()

def analyze_disaster(disaster_type, location, additional_info=None):
    """
    Analyze disaster and determine appropriate response
    """
    # Get nearby critical infrastructure
    nearby_places = get_nearby_places(location)
    
    # Prepare context for the LLM
    disaster_context = {
        "disaster_type": disaster_type,
        "location": location,
        "additional_info": additional_info,
        "nearby_places": nearby_places
    }
    
    return disaster_context

def get_chatbot_response(user_message, chat_history=None):
    """
    Get response from the LLM using Groq
    """
    if chat_history is None:
        chat_history = []
    
    # Prepare the prompt with disaster response expertise and multi-agent simulation
    system_prompt = """
    You are a disaster response AI coordinator with expertise in emergency management.
    You have multiple specialized agents working together:
    1. Safety Agent: Prioritizes minimizing human casualties
    2. Infrastructure Agent: Assesses damage to buildings and critical infrastructure
    3. Rescue Agent: Coordinates search and rescue operations 
    4. Communication Agent: Manages information flow and public messaging
    
    When responding to disaster situations:
    - Identify the disaster type and severity
    - Ask relevant questions to gather important information
    - Identify critical locations (hospitals, police, fire stations, shelters, open spaces)
    - Suggest evacuation routes or safe zones
    - Provide actionable advice for the current disaster phase
    
    Format your responses for readability:
    - Use line breaks to separate paragraphs
    - Use **bold** for important information or warnings
    - Use bullet points (- ) for lists of actions or recommendations
    - Structure your response with clear sections
    - Use numbered lists (1. 2. etc.) for sequential steps
    
    Maintain a calm, clear, and authoritative tone. Prioritize life safety above all else.
    """
    
    # Create messages list with system prompt and chat history
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add chat history
    for msg in chat_history:
        messages.append(msg)
    
    # Add the current user message
    messages.append({"role": "user", "content": user_message})
    
    # Get response from Groq
    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",  # or another appropriate model
        messages=messages,
        temperature=0.5,
        max_tokens=1024
    )
    
    return response.choices[0].message.content

@app.route('/')
def home():
    # Generate a session ID if one doesn't exist
    if 'chat_id' not in session:
        session['chat_id'] = str(uuid.uuid4())
    
    chat_id = session['chat_id']
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    
    return render_template('index.html', tomtom_api_key=TOMTOM_API_KEY)

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')
    
    # Get chat ID from session
    chat_id = session.get('chat_id', str(uuid.uuid4()))
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    
    # Add user message to history
    chat_histories[chat_id].append({"role": "user", "content": user_message})
    
    # Get chatbot response
    bot_response = get_chatbot_response(user_message, chat_histories[chat_id])
    
    # Add bot response to history
    chat_histories[chat_id].append({"role": "assistant", "content": bot_response})
    
    # Check if we need to fetch location data
    location_data = None
    disaster_type = None
    
    # Simple keyword detection for disaster types and locations
    # In a real implementation, you'd use NER or more sophisticated NLP
    disaster_keywords = {
        "earthquake": ["earthquake", "quake", "tremor", "seismic"],
        "flood": ["flood", "flooding", "inundation", "water level"],
        "hurricane": ["hurricane", "cyclone", "typhoon", "storm"],
        "fire": ["fire", "wildfire", "blaze", "burning"],
        "tornado": ["tornado", "twister", "funnel cloud"]
    }
    
    # Check for disaster types in user message
    for disaster, keywords in disaster_keywords.items():
        if any(keyword in user_message.lower() for keyword in keywords):
            disaster_type = disaster
            break
    
    # Extract location (this is a simplified approach)
    # In a real implementation, use a proper NER model or geocoding service
    if disaster_type:
        # This is a very basic location extraction - would need improvements
        words = user_message.replace(',', ' ').replace('.', ' ').split()
        for i, word in enumerate(words):
            if word.lower() in ["in", "at", "near"]:
                if i + 1 < len(words):
                    location = words[i + 1]
                    # If we have a location and disaster type, get nearby places
                    location_data = get_nearby_places(location)
                    break
    
    return jsonify({
        "response": bot_response,
        "location_data": location_data,
        "disaster_type": disaster_type
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    chat_id = session.get('chat_id')
    if not chat_id or chat_id not in chat_histories:
        return jsonify([])
    
    return jsonify(chat_histories[chat_id])

if __name__ == '__main__':
    app.run(debug=True)