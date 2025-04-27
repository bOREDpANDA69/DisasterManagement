# disaster_response_chatbot.py
import os
import re
import requests
import folium
import json
from flask import Flask, request, jsonify, render_template, send_from_directory
from geopy.geocoders import Nominatim
from dotenv import load_dotenv
import groq

load_dotenv()

app = Flask(__name__)

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")

# Initialize services
groq_client = groq.Client(api_key=GROQ_API_KEY)  # Initialize Groq client
geolocator = Nominatim(user_agent="disaster-response-chatbot")

# NLP Component
def parse_disaster_input(user_input):
    """Extract disaster information from user input using Groq"""
    try:
        # Use Groq's API to analyze the disaster input
        response = groq_client.chat.completions.create(
            model="llama3-70b-8192",  # Using Llama3 model, adjust as needed
            messages=[
                {"role": "system", "content": """
                You are an AI specialized in disaster response. Extract the following information from the user input:
                1. Disaster type (earthquake, flood, fire, hurricane, etc.)
                2. Location name (city, neighborhood, region)
                3. Severity (if mentioned)
                4. Any other critical details
                Format the response as JSON.
                """},
                {"role": "user", "content": user_input}
            ],
            temperature=0.3,
            max_tokens=500
        )
        content = response.choices[0].message.content
        
        # Try to extract JSON from the response
        match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
        if match:
            content = match.group(1)
        else:
            match = re.search(r'{.*}', content, re.DOTALL)
            if match:
                content = match.group(0)
                
        try:
            parsed_data = json.loads(content)
        except:
            # Fallback if JSON parsing fails
            parsed_data = {
                "disaster_type": extract_disaster_type(user_input),
                "location": extract_location(user_input),
                "severity": extract_severity(user_input),
                "details": ""
            }
        
        # Get coordinates for the location
        location_data = get_coordinates(parsed_data.get("location", ""))
        parsed_data.update(location_data)
        
        return parsed_data
        
    except Exception as e:
        print(f"Error parsing input: {e}")
        # Fallback to basic parsing
        return {
            "disaster_type": extract_disaster_type(user_input),
            "location": extract_location(user_input),
            "severity": extract_severity(user_input),
            "details": "",
            "lat": None,
            "lng": None
        }

def extract_disaster_type(text):
    """Simple rule-based extraction of disaster type"""
    disaster_types = {
        "earthquake": ["earthquake", "quake", "tremor", "seismic"],
        "flood": ["flood", "flooding", "water level", "dam break"],
        "fire": ["fire", "wildfire", "burning", "flames"],
        "hurricane": ["hurricane", "cyclone", "typhoon", "storm"],
        "tornado": ["tornado", "twister", "funnel cloud"],
        "tsunami": ["tsunami", "tidal wave"]
    }
    
    text = text.lower()
    for disaster, keywords in disaster_types.items():
        for keyword in keywords:
            if keyword in text:
                return disaster
    return "unknown"

def extract_location(text):
    """Extract location from text"""
    # Very basic extraction - in a real app, use NER
    location_matches = re.search(r'in ([A-Za-z\s,]+)', text)
    if location_matches:
        return location_matches.group(1).strip()
    return "unknown location"

def extract_severity(text):
    """Extract severity information if available"""
    severity_patterns = {
        "magnitude": r'magnitude (\d+\.?\d*)',
        "category": r'category (\d+)',
        "level": r'level (\d+)'
    }
    
    for key, pattern in severity_patterns.items():
        match = re.search(pattern, text.lower())
        if match:
            return {key: match.group(1)}
    return {}

def get_coordinates(location_name):
    """Get coordinates for a location using Nominatim"""
    try:
        if location_name and location_name != "unknown location":
            location = geolocator.geocode(location_name)
            if location:
                return {"lat": location.latitude, "lng": location.longitude}
    except Exception as e:
        print(f"Geocoding error: {e}")
    
    # Fallback to default coordinates (New York City)
    return {"lat": 40.7128, "lng": -74.0060}

# GIS Component
def get_critical_locations(location_info, radius=5000):
    """Get critical locations using OpenStreetMap Overpass API"""
    try:
        lat = location_info.get("lat")
        lng = location_info.get("lng")
        
        if not lat or not lng:
            return []
        
        # OpenStreetMap Overpass API query
        overpass_url = "http://overpass-api.de/api/interpreter"
        query = f"""
        [out:json];
        (
          node["amenity"="hospital"](around:{radius},{lat},{lng});
          node["amenity"="police"](around:{radius},{lat},{lng});
          node["amenity"="fire_station"](around:{radius},{lat},{lng});
          node["leisure"="park"](around:{radius},{lat},{lng});
          way["leisure"="park"](around:{radius},{lat},{lng});
          relation["leisure"="park"](around:{radius},{lat},{lng});
        );
        out center;
        """
        
        response = requests.get(overpass_url, params={"data": query})
        data = response.json()
        
        locations = []
        for element in data.get("elements", []):
            if "tags" in element:
                loc_type = element["tags"].get("amenity") or element["tags"].get("leisure")
                name = element["tags"].get("name", loc_type)
                
                # Get coordinates
                if element["type"] == "node":
                    coords = {"lat": element["lat"], "lng": element["lon"]}
                else:
                    # For ways and relations, use the center point
                    coords = {"lat": element.get("center", {}).get("lat"), 
                             "lng": element.get("center", {}).get("lon")}
                
                if coords["lat"] and coords["lng"]:
                    locations.append({
                        "type": loc_type,
                        "name": name,
                        "lat": coords["lat"],
                        "lng": coords["lng"],
                        "type_color": get_location_color(loc_type)
                    })
        
        return locations
    
    except Exception as e:
        print(f"Error getting critical locations: {e}")
        return []

def get_location_color(location_type):
    """Return color based on location type"""
    colors = {
        "hospital": "red",
        "police": "blue",
        "fire_station": "orange",
        "park": "green"
    }
    return colors.get(location_type, "gray")

# Multi-Agent System
class CoordinatorAgent:
    def process_disaster(self, disaster_info, critical_locations):
        """Coordinate the multi-agent response system"""
        # Get specialized responses from each agent
        life_preservation = LifePreservationAgent().respond(disaster_info, critical_locations)
        infrastructure = InfrastructureAgent().respond(disaster_info)
        rescue = RescueOperationsAgent().respond(disaster_info, critical_locations)
        communication = CommunicationAgent().respond(disaster_info)
        
        # Generate follow-up questions
        questions = self.generate_questions(disaster_info)
        
        # Combine responses
        combined_text = f"""
DISASTER RESPONSE PLAN: {disaster_info.get('disaster_type', 'Disaster').upper()} in {disaster_info.get('location', 'unknown location')}

{life_preservation['text']}

{rescue['text']}

{infrastructure['text']}

{communication['text']}

IMPORTANT: This is an automated initial response based on limited information.
        """
        
        return {
            'text': combined_text.strip(),
            'questions': questions,
            'routes': life_preservation['routes'] + rescue['routes']
        }
    
    def generate_questions(self, disaster_info):
        """Generate relevant follow-up questions based on disaster type and missing info"""
        disaster_type = disaster_info.get('disaster_type', '').lower()
        questions = ["Are there any reported casualties or injuries?", 
                     "Are there damaged buildings or infrastructure?"]
        
        # Add disaster-specific questions
        if disaster_type == 'earthquake':
            if 'magnitude' not in str(disaster_info.get('severity', '')):
                questions.append("What was the magnitude of the earthquake?")
            questions.append("Have there been any aftershocks?")
            
        elif disaster_type == 'flood':
            questions.append("What is the current water level?")
            questions.append("Is the water level rising or receding?")
            
        elif disaster_type == 'fire':
            questions.append("What is the approximate size of the affected area?")
            questions.append("What direction is the fire moving?")
            
        elif disaster_type == 'hurricane' or disaster_type == 'tornado':
            questions.append("What is the current wind speed?")
            questions.append("What is the projected path?")
            
        return questions[:3]  # Limit to 3 questions

class LifePreservationAgent:
    def respond(self, disaster_info, critical_locations):
        """Generate life preservation recommendations"""
        disaster_type = disaster_info.get('disaster_type', 'unknown')
        
        # Find evacuation points (parks for earthquakes, high ground for floods, etc.)
        evacuation_points = self.identify_evacuation_points(disaster_type, critical_locations)
        
        # Generate evacuation routes
        routes = self.generate_routes(disaster_info, evacuation_points)
        
        text = "LIFE SAFETY PRIORITY:\n"
        if disaster_type == 'earthquake':
            text += "- If indoors: Drop, Cover, and Hold On. Take cover under sturdy furniture.\n"
            text += "- If outdoors: Move to open areas away from buildings, utility wires, and trees.\n"
        elif disaster_type == 'flood':
            text += "- Move to higher ground immediately.\n"
            text += "- Do not walk or drive through flood waters.\n"
        elif disaster_type == 'fire':
            text += "- Evacuate immediately following designated routes.\n"
            text += "- Cover nose and mouth with wet cloth if smoke is present.\n"
        elif disaster_type == 'hurricane' or disaster_type == 'tornado':
            text += "- Seek shelter in the lowest floor of a sturdy building.\n"
            text += "- Stay away from windows and exterior walls.\n"
        
        if evacuation_points:
            text += "\nNEARBY EVACUATION POINTS:\n"
            for i, point in enumerate(evacuation_points[:3], 1):
                text += f"- {point['name']}\n"
        
        return {
            'text': text,
            'routes': routes
        }
    
    def identify_evacuation_points(self, disaster_type, critical_locations):
        """Identify appropriate evacuation points based on disaster type"""
        if disaster_type == 'earthquake' or disaster_type == 'fire':
            # Open areas like parks are best for earthquakes
            return [loc for loc in critical_locations if loc['type'] == 'park']
        elif disaster_type == 'flood':
            # Higher elevation areas for floods (simplified)
            return [loc for loc in critical_locations if loc['type'] in ['hospital', 'police', 'fire_station']]
        else:
            # Default to sturdy buildings
            return [loc for loc in critical_locations if loc['type'] in ['hospital', 'police', 'fire_station']]
    
    def generate_routes(self, disaster_info, evacuation_points):
        """Generate simple evacuation routes (straight lines in this simplified version)"""
        routes = []
        disaster_lat = disaster_info.get('lat')
        disaster_lng = disaster_info.get('lng')
        
        if not disaster_lat or not disaster_lng or not evacuation_points:
            return routes
        
        for point in evacuation_points[:2]:  # Limit to 2 routes
            routes.append({
                'name': f"Evacuation to {point['name']}",
                'coordinates': [[disaster_lat, disaster_lng], [point['lat'], point['lng']]],
                'color': 'green'
            })
        
        return routes

class InfrastructureAgent:
    def respond(self, disaster_info):
        """Generate infrastructure protection recommendations"""
        disaster_type = disaster_info.get('disaster_type', 'unknown')
        
        text = "INFRASTRUCTURE CONCERNS:\n"
        if disaster_type == 'earthquake':
            text += "- Gas leaks are common after earthquakes. If you smell gas, turn off the main valve.\n"
            text += "- Be cautious of damaged roads, bridges, and buildings.\n"
            text += "- Power outages may occur; avoid downed power lines.\n"
        elif disaster_type == 'flood':
            text += "- Avoid contact with flood water which may be contaminated.\n"
            text += "- Do not use electrical appliances that have been wet.\n"
            text += "- Water supply may be contaminated; use bottled or treated water.\n"
        elif disaster_type == 'fire':
            text += "- Turn off utilities at the main valves if instructed.\n"
            text += "- Clear flammable materials from around your home if time permits.\n"
        elif disaster_type == 'hurricane' or disaster_type == 'tornado':
            text += "- Secure outdoor objects or bring them indoors.\n"
            text += "- Power outages are likely; have flashlights and batteries ready.\n"
            text += "- Water and other utilities may be disrupted.\n"
        
        return {
            'text': text,
            'routes': []
        }

class RescueOperationsAgent:
    def respond(self, disaster_info, critical_locations):
        """Generate rescue operation recommendations"""
        # Find emergency services
        emergency_services = [loc for loc in critical_locations 
                             if loc['type'] in ['hospital', 'police', 'fire_station']]
        
        # Generate routes for emergency services
        routes = self.generate_emergency_routes(disaster_info, emergency_services)
        
        text = "EMERGENCY SERVICES RESPONSE:\n"
        
        if emergency_services:
            text += "Nearest emergency facilities:\n"
            for i, service in enumerate(emergency_services[:3], 1):
                text += f"- {service['name']} ({service['type']})\n"
        else:
            text += "No nearby emergency services identified in the system.\n"
        
        text += "\nIf you need immediate assistance:\n"
        text += "- Call emergency services (911 in the US)\n"
        text += "- If trapped, make noise to alert rescuers\n"
        text += "- If trained in first aid, assist others until help arrives\n"
        
        return {
            'text': text,
            'routes': routes
        }
    
    def generate_emergency_routes(self, disaster_info, emergency_services):
        """Generate routes for emergency services to reach the disaster area"""
        routes = []
        disaster_lat = disaster_info.get('lat')
        disaster_lng = disaster_info.get('lng')
        
        if not disaster_lat or not disaster_lng:
            return routes
        
        for service in emergency_services[:2]:  # Limit to 2 routes
            routes.append({
                'name': f"Response route from {service['name']}",
                'coordinates': [[service['lat'], service['lng']], [disaster_lat, disaster_lng]],
                'color': 'red'
            })
        
        return routes

class CommunicationAgent:
    def respond(self, disaster_info):
        """Generate communication recommendations"""
        text = "COMMUNICATION GUIDANCE:\n"
        text += "- Use text messages instead of calls to reduce network congestion\n"
        text += "- Monitor local radio/TV stations for emergency broadcasts\n"
        text += "- Report your status to friends/family via social media if possible\n"
        text += "- Share critical information about the situation with authorities\n"
        
        return {
            'text': text,
            'routes': []
        }

# Initialize agents
coordinator = CoordinatorAgent()

# Generate map visualization
def generate_map(disaster_info, critical_locations, routes):
    """Generate an interactive map with disaster location, critical facilities, and routes"""
    lat = disaster_info.get('lat', 40.7128)
    lng = disaster_info.get('lng', -74.0060)
    
    m = folium.Map(location=[lat, lng], zoom_start=14)
    
    # Add disaster marker
    folium.Marker(
        [lat, lng],
        popup=f"{disaster_info.get('disaster_type', 'Disaster')} - {disaster_info.get('location', 'Unknown')}",
        icon=folium.Icon(color='black', icon='warning-sign')
    ).add_to(m)
    
    # Add circle around disaster area
    folium.Circle(
        radius=1000,
        location=[lat, lng],
        color='crimson',
        fill=True,
        fill_opacity=0.2
    ).add_to(m)
    
    # Add critical locations
    for loc in critical_locations:
        folium.Marker(
            [loc['lat'], loc['lng']],
            popup=f"{loc['name']} ({loc['type']})",
            icon=folium.Icon(color=loc['type_color'], icon=get_icon_for_type(loc['type']))
        ).add_to(m)
    
    # Add routes
    for route in routes:
        folium.PolyLine(
            route['coordinates'],
            color=route['color'],
            weight=4,
            opacity=0.8,
            popup=route['name']
        ).add_to(m)
    
    # Save the map
    static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    os.makedirs(static_folder, exist_ok=True)
    map_file = os.path.join(static_folder, 'disaster_map.html')
    m.save(map_file)
    
    return 'disaster_map.html'

def get_icon_for_type(loc_type):
    """Return appropriate icon for location type"""
    icons = {
        'hospital': 'plus',
        'police': 'flag',
        'fire_station': 'fire-extinguisher',
        'park': 'tree'
    }
    return icons.get(loc_type, 'info-sign')

# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/api/respond', methods=['POST'])
def respond():
    data = request.json
    user_input = data.get('message', '')
    
    # Parse the disaster information
    disaster_info = parse_disaster_input(user_input)
    
    # Get critical locations
    critical_locations = get_critical_locations(disaster_info)
    
    # Process with multi-agent system
    response = coordinator.process_disaster(disaster_info, critical_locations)
    
    # Generate map
    map_file = generate_map(disaster_info, critical_locations, response['routes'])
    
    return jsonify({
        'text_response': response['text'],
        'follow_up_questions': response['questions'],
        'map_file': map_file
    })

# Create templates folder and index.html
def create_templates():
    os.makedirs('templates', exist_ok=True)
    with open('templates/index.html', 'w') as f:
        f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Disaster Response Chatbot</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            flex-grow: 1;
        }
        
        h1 {
            color: #d32f2f;
            text-align: center;
        }
        
        .content {
            display: flex;
            flex-grow: 1;
            margin-top: 20px;
        }
        
        .chat-container {
            flex: 1;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            display: flex;
            flex-direction: column;
            margin-right: 20px;
        }
        
        .map-container {
            flex: 1;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        
        #map-frame {
            width: 100%;
            height: 100%;
            border: none;
        }
        
        .chat-messages {
            flex-grow: 1;
            padding: 20px;
            overflow-y: auto;
            max-height: calc(100vh - 300px);
        }
        
        .chat-input {
            display: flex;
            padding: 10px;
            border-top: 1px solid #eee;
        }
        
        #message-input {
            flex-grow: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-right: 10px;
        }
        
        button {
            background: #d32f2f;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
        }
        
        .user-message, .bot-message {
            margin-bottom: 15px;
            padding: 10px 15px;
            border-radius: 18px;
            max-width: 80%;
        }
        
        .user-message {
            background-color: #e3f2fd;
            margin-left: auto;
            border-bottom-right-radius: 4px;
        }
        
        .bot-message {
            background-color: #f1f1f1;
            margin-right: auto;
            border-bottom-left-radius: 4px;
        }
        
        .question-button {
            background: #f1f1f1;
            color: #333;
            border: 1px solid #ddd;
            padding: 8px 15px;
            margin: 5px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
        }
        
        .questions-container {
            display: flex;
            flex-wrap: wrap;
            margin-top: 10px;
        }
        
        .loading {
            display: flex;
            justify-content: center;
            margin: 20px 0;
        }
        
        .dot {
            height: 10px;
            width: 10px;
            margin: 0 5px;
            background-color: #d32f2f;
            border-radius: 50%;
            animation: bounce 1.5s infinite alternate;
        }
        
        .dot:nth-child(2) {
            animation-delay: 0.5s;
        }
        
        .dot:nth-child(3) {
            animation-delay: 1s;
        }
        
        @keyframes bounce {
            0% { transform: translateY(0); }
            100% { transform: translateY(-10px); }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Disaster Response Chatbot</h1>
        
        <div class="content">
            <div class="chat-container">
                <div class="chat-messages" id="chat-messages">
                    <div class="bot-message">
                        I'm your disaster response assistant. Please report any disaster situation, and I'll help coordinate a response. For example, try: "An earthquake has been reported in Brooklyn, New York."
                    </div>
                </div>
                
                <div class="chat-input">
                    <input type="text" id="message-input" placeholder="Describe the disaster situation...">
                    <button id="send-button">Send</button>
                </div>
            </div>
            
            <div class="map-container">
                <iframe id="map-frame" src="/static/placeholder_map.html"></iframe>
            </div>
        </div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const messagesContainer = document.getElementById('chat-messages');
            const messageInput = document.getElementById('message-input');
            const sendButton = document.getElementById('send-button');
            const mapFrame = document.getElementById('map-frame');
            
            // Initialize with a placeholder map
            fetch('/static/placeholder_map.html')
                .catch(() => {
                    // Create a simple placeholder if file doesn't exist
                    const placeholderContent = `
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <style>
                                body {
                                    display: flex;
                                    justify-content: center;
                                    align-items: center;
                                    height: 100vh;
                                    margin: 0;
                                    background-color: #f5f5f5;
                                    font-family: Arial, sans-serif;
                                    color: #666;
                                }
                            </style>
                        </head>
                        <body>
                            <div>Report a disaster to see the response map</div>
                        </body>
                        </html>
                    `;
                    
                    const blob = new Blob([placeholderContent], {type: 'text/html'});
                    mapFrame.src = URL.createObjectURL(blob);
                });
            
            function addUserMessage(message) {
                const messageElement = document.createElement('div');
                messageElement.className = 'user-message';
                messageElement.textContent = message;
                messagesContainer.appendChild(messageElement);
                messageInput.value = '';
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            function addBotMessage(message) {
                const messageElement = document.createElement('div');
                messageElement.className = 'bot-message';
                messageElement.textContent = message;
                messagesContainer.appendChild(messageElement);
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            function addQuestions(questions) {
                if (!questions || questions.length === 0) return;
                
                const containerElement = document.createElement('div');
                containerElement.className = 'questions-container';
                
                questions.forEach(question => {
                    const questionButton = document.createElement('button');
                    questionButton.className = 'question-button';
                    questionButton.textContent = question;
                    questionButton.addEventListener('click', function() {
                        addUserMessage(question);
                        sendMessage(question);
                    });
                    containerElement.appendChild(questionButton);
                });
                
                messagesContainer.appendChild(containerElement);
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            function showLoading() {
                const loadingElement = document.createElement('div');
                loadingElement.className = 'loading';
                loadingElement.id = 'loading-indicator';
                
                for (let i = 0; i < 3; i++) {
                    const dot = document.createElement('div');
                    dot.className = 'dot';
                    loadingElement.appendChild(dot);
                }
                
                messagesContainer.appendChild(loadingElement);
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
            
            function hideLoading() {
                const loadingElement = document.getElementById('loading-indicator');
                if (loadingElement) {
                    loadingElement.remove();
                }
            }
            
            function sendMessage(message) {
                showLoading();
                
                fetch('/api/respond', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message }),
                })
                .then(response => response.json())
                .then(data => {
                    hideLoading();
                    addBotMessage(data.text_response);
                    addQuestions(data.follow_up_questions);
                    
                    // Update map
                    if (data.map_file) {
                        mapFrame.src = `/static/${data.map_file}`;
                    }
                })
                .catch(error => {
                    hideLoading();
                    console.error('Error:', error);
                    addBotMessage('Sorry, there was an error processing your request. Please try again.');
                });
            }
            
            sendButton.addEventListener('click', function() {
                const message = messageInput.value.trim();
                if (message) {
                    addUserMessage(message);
                    sendMessage(message);
                }
            });
            
            messageInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    const message = messageInput.value.trim();
                    if (message) {
                        addUserMessage(message);
                        sendMessage(message);
                    }
                }
            });
        });
    </script>
</body>
</html>
        """)

# Create placeholder map
def create_placeholder_map():
    os.makedirs('static', exist_ok=True)
    m = folium.Map(location=[40.7128, -74.0060], zoom_start=10)
    m.save('static/placeholder_map.html')

# Main function
if __name__ == '__main__':
    create_templates()
    create_placeholder_map()
    app.run(debug=True, host='0.0.0.0', port=5000)
