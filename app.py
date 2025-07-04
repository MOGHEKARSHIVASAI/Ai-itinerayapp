from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from utils.planner import get_places
from models import db, User, SavedItinerary
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import os
import json
import requests # Import for making HTTP requests
import googlemaps # Add this line
from datetime import datetime, timedelta # Add this line

from geopy.distance import geodesic

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tripplan.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Login manager setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Use environment variable for API key in production
app.config['Maps_API_KEY'] = 'AIzaSyAVDKb4hoP-iN_rJZqk7Kav79jFOemPQOo' # Your Google Maps API Key
app.config['OPENWEATHER_API_KEY'] = '734479405ebf3af5568e7a80da25f81b' # Replace with your OpenWeatherMap API Key

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        if current_user.is_authenticated:
            return redirect(url_for('questionnaire'))
        else:
            # Redirect to login if not authenticated
            flash('Please log in to plan a trip', 'info')
            return redirect(url_for('login'))
    return render_template('home.html', api_key=app.config['Maps_API_KEY'])

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))
    
    # Store the next page to redirect to after login if it exists
    next_page = request.args.get('next')
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not user.check_password(password):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))
        
        login_user(user, remember=remember)
        
        # Redirect to the stored next page if it exists, otherwise to profile
        if next_page:
            return redirect(next_page)
        return redirect(url_for('profile'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/profile')
@login_required
def profile():
    saved_itineraries = SavedItinerary.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', saved_itineraries=saved_itineraries)

@app.route('/save_itinerary', methods=['POST'])
@login_required
def save_itinerary():
    if 'city' in session:
        city = session.get('city')
        days = session.get('days')
        budget = session.get('budget')
        group_type = session.get('group_type')
        
        itinerary, _ = get_places(city, days, budget, group_type, app.config['Maps_API_KEY'])
        
        new_itinerary = SavedItinerary(
            user_id=current_user.id,
            city=city,
            days=days,
            budget=budget,
            group_type=group_type,
            itinerary_data=json.dumps(itinerary)
        )
        
        db.session.add(new_itinerary)
        db.session.commit()
        
        flash('Itinerary saved successfully!', 'success')
        return redirect(url_for('profile'))
    
    flash('No itinerary data to save', 'danger')
    return redirect(url_for('questionnaire'))

@app.route('/view_itinerary/<int:itinerary_id>')
@login_required
def view_itinerary(itinerary_id):
    itinerary = SavedItinerary.query.get_or_404(itinerary_id)
    
    if itinerary.user_id != current_user.id:
        flash('You do not have permission to view this itinerary', 'danger')
        return redirect(url_for('profile'))
    
    itinerary_data = json.loads(itinerary.itinerary_data)
    _, latlng = get_places(itinerary.city, itinerary.days, itinerary.budget, itinerary.group_type, app.config['Maps_API_KEY'])
    
    return render_template(
        'itinerary.html', 
        itinerary=itinerary_data, 
        place=itinerary.city,
        lat=latlng[0], 
        lng=latlng[1],
        api_key=app.config['Maps_API_KEY'],
        days=itinerary.days
    )

@app.route('/delete_itinerary/<int:itinerary_id>')
@login_required
def delete_itinerary(itinerary_id):
    itinerary = SavedItinerary.query.get_or_404(itinerary_id)
    
    if itinerary.user_id != current_user.id:
        flash('You do not have permission to delete this itinerary', 'danger')
        return redirect(url_for('profile'))
    
    db.session.delete(itinerary)
    db.session.commit()
    
    flash('Itinerary deleted successfully', 'success')
    return redirect(url_for('profile'))

@app.route('/questionnaire', methods=['GET', 'POST'])
@login_required
def questionnaire():
    if request.method == 'POST':
        try:
            city = request.form['place']
            days = int(request.form['days'])
            budget = request.form['budget']
            group_type = request.form['group_type']
            
            session['city'] = city
            session['days'] = days
            session['budget'] = budget
            session['group_type'] = group_type
            
            itinerary, latlng = get_places(city, days, budget, group_type, app.config['Maps_API_KEY'])
            
            if not itinerary:
                return render_template('error.html', message=f"No places found for {city}. Please try a different location.")
            
            # Fetch weather data
            weather_data = None
            if latlng: # Ensure latlng is available
                weather_response = requests.get(url_for('get_weather', lat=latlng[0], lng=latlng[1], _external=True))
                if weather_response.status_code == 200:
                    weather_data = weather_response.json()
                else:
                    app.logger.warning(f"Could not fetch weather for {city}: {weather_response.text}")

            # This is the correct and only return statement needed
            return render_template(
                'itinerary.html', 
                itinerary=itinerary, 
                place=city,
                lat=latlng[0], 
                lng=latlng[1],
                api_key=app.config['Maps_API_KEY'],
                days=days,
                weather=weather_data # Pass weather data to the template
            )
        except Exception as e:
            return render_template('error.html', message=f"An error occurred: {str(e)}")
            
    return render_template('questionnaire.html')

@app.route('/api/itinerary-data')
@login_required  # Add login_required to API route as well
def itinerary_data():
    if 'city' in session:
        city = session.get('city')
        days = session.get('days')
        budget = session.get('budget')
        group_type = session.get('group_type')
        
        itinerary, latlng = get_places(city, days, budget, group_type, app.config['Maps_API_KEY'])
        return jsonify({
            'itinerary': itinerary,
            'center': {'lat': latlng[0], 'lng': latlng[1]}
        })
    return jsonify({'error': 'No itinerary data found'})

@app.route('/directions')
def directions():
    destination_lat = request.args.get("lat", type=float)
    destination_lng = request.args.get("lng", type=float)
    destination_name = request.args.get("name", default="Destination")

    return render_template("directions.html",
                           destination_lat=destination_lat,
                           destination_lng=destination_lng,
                           destination_name=destination_name,
                           api_key="AIzaSyAVDKb4hoP-iN_rJZqk7Kav79jFOemPQOo")

@app.route('/api/directions')
def get_directions():
    origin_lat = request.args.get('origin_lat')
    origin_lng = request.args.get('origin_lng')
    destination_lat = request.args.get('destination_lat')
    destination_lng = request.args.get('destination_lng')

    if not all([origin_lat, origin_lng, destination_lat, destination_lng]):
        app.logger.error("Missing origin or destination coordinates for directions.")
        return jsonify({'error': 'All origin and destination coordinates are required'}), 400

    origin = f"{origin_lat},{origin_lng}"
    destination = f"{destination_lat},{destination_lng}"

    # Ensure googlemaps client is initialized here
    try:
        gmaps = googlemaps.Client(key=app.config['Maps_API_KEY'])
    except Exception as e:
        app.logger.error(f"Error initializing Google Maps client: {e}")
        return jsonify({'error': 'Failed to initialize Google Maps client'}), 500

    transport_modes = ['driving', 'walking', 'transit']
    directions_data = {}

    for mode in transport_modes:
        try:
            directions_result = gmaps.directions(
                origin,
                destination,
                mode=mode,
                units="metric", # or "imperial"
                # Departure time for driving to get traffic-aware data, otherwise None
                departure_time="now" if mode == 'driving' else None
            )
            if directions_result:
                # Assuming the first leg of the first route is what we care about
                if directions_result and 'legs' in directions_result[0] and len(directions_result[0]['legs']) > 0:
                    leg = directions_result[0]['legs'][0]
                    directions_data[mode] = {
                        'duration_text': leg['duration']['text'],
                        'duration_value': leg['duration']['value'], # Duration in seconds
                        'distance_text': leg['distance']['text'],
                        'distance_value': leg['distance']['value'] # Distance in meters
                    }
                    if mode == 'driving' and 'duration_in_traffic' in leg:
                        directions_data[mode]['duration_in_traffic_text'] = leg['duration_in_traffic']['text']
                        directions_data[mode]['duration_in_traffic_value'] = leg['duration_in_traffic']['value']
                else:
                    directions_data[mode] = {'status': 'No route found or incomplete data'}
            else:
                directions_data[mode] = {'status': 'No route found'}
        except Exception as e:
            app.logger.error(f"Error fetching {mode} directions from Google Maps API: {e}")
            directions_data[mode] = {'status': f'Error fetching directions: {str(e)}'}

    return jsonify(directions_data)

@app.route('/api/traffic-analysis')
def get_traffic_analysis():
    """Get traffic analysis for multiple places"""
    places = request.args.getlist('places')  # Format: "lat,lng,name"
    city_center_lat = request.args.get('city_lat')
    city_center_lng = request.args.get('city_lng')
    
    if not places or not city_center_lat or not city_center_lng:
        return jsonify({'error': 'Places and city center coordinates are required'}), 400
    
    try:
        gmaps = googlemaps.Client(key=app.config['Maps_API_KEY'])
        city_center = f"{city_center_lat},{city_center_lng}"
        
        traffic_analysis = {}
        
        for place_info in places:
            try:
                parts = place_info.split(',')
                if len(parts) < 3:
                    continue
                    
                lat, lng = parts[0], parts[1]
                name = ','.join(parts[2:])  # Handle names with commas
                destination = f"{lat},{lng}"
                
                # Get traffic data for different times of day
                traffic_data = analyze_traffic_patterns(gmaps, city_center, destination)
                
                traffic_analysis[name] = {
                    'coordinates': {'lat': float(lat), 'lng': float(lng)},
                    'traffic_patterns': traffic_data,
                    'best_time_to_visit': get_best_visit_time(traffic_data),
                    'current_conditions': get_current_traffic_conditions(gmaps, city_center, destination)
                }
                
            except Exception as e:
                app.logger.error(f"Error analyzing traffic for {place_info}: {e}")
                continue
        
        return jsonify(traffic_analysis)
        
    except Exception as e:
        app.logger.error(f"Error in traffic analysis: {e}")
        return jsonify({'error': 'Failed to analyze traffic'}), 500

def analyze_traffic_patterns(gmaps, origin, destination):
    """Analyze traffic patterns for different times of day"""
    now = datetime.now()
    traffic_patterns = {}
    
    # Define time periods to check
    time_periods = {
        'morning_rush': now.replace(hour=8, minute=0, second=0, microsecond=0),
        'midday': now.replace(hour=12, minute=0, second=0, microsecond=0),
        'evening_rush': now.replace(hour=17, minute=30, second=0, microsecond=0),
        'night': now.replace(hour=21, minute=0, second=0, microsecond=0)
    }
    
    for period, time_obj in time_periods.items():
        try:
            # Get directions with traffic for specific time
            directions_result = gmaps.directions(
                origin,
                destination,
                mode='driving',
                departure_time=time_obj,
                traffic_model='best_guess'
            )
            
            if directions_result and directions_result[0]['legs']:
                leg = directions_result[0]['legs'][0]
                
                normal_duration = leg['duration']['value']
                traffic_duration = leg.get('duration_in_traffic', {}).get('value', normal_duration)
                
                # Calculate traffic congestion level
                if normal_duration > 0:
                    congestion_ratio = traffic_duration / normal_duration
                    congestion_level = get_congestion_level(congestion_ratio)
                else:
                    congestion_level = 'Unknown'
                
                traffic_patterns[period] = {
                    'normal_duration': format_duration(normal_duration),
                    'traffic_duration': format_duration(traffic_duration),
                    'delay_minutes': round((traffic_duration - normal_duration) / 60),
                    'congestion_level': congestion_level,
                    'congestion_ratio': round(congestion_ratio, 2)
                }
                
        except Exception as e:
            app.logger.error(f"Error getting traffic for {period}: {e}")
            traffic_patterns[period] = {'error': 'Unable to fetch traffic data'}
    
    return traffic_patterns

def get_congestion_level(ratio):
    """Convert congestion ratio to readable level"""
    if ratio <= 1.1:
        return 'Light'
    elif ratio <= 1.3:
        return 'Moderate'
    elif ratio <= 1.5:
        return 'Heavy'
    else:
        return 'Very Heavy'

def get_best_visit_time(traffic_data):
    """Determine the best time to visit based on traffic patterns"""
    if not traffic_data:
        return 'No data available'
    
    # Filter out periods with errors
    valid_periods = {k: v for k, v in traffic_data.items() if 'error' not in v}
    
    if not valid_periods:
        return 'No data available'
    
    # Find period with lowest delay
    best_period = min(valid_periods.keys(), 
                     key=lambda k: valid_periods[k].get('delay_minutes', float('inf')))
    
    period_names = {
        'morning_rush': 'Morning (8:00 AM)',
        'midday': 'Midday (12:00 PM)',
        'evening_rush': 'Evening (5:30 PM)',
        'night': 'Night (9:00 PM)'
    }
    
    return period_names.get(best_period, best_period)

def get_current_traffic_conditions(gmaps, origin, destination):
    """Get current traffic conditions"""
    try:
        directions_result = gmaps.directions(
            origin,
            destination,
            mode='driving',
            departure_time='now',
            traffic_model='best_guess'
        )
        
        if directions_result and directions_result[0]['legs']:
            leg = directions_result[0]['legs'][0]
            
            normal_duration = leg['duration']['value']
            traffic_duration = leg.get('duration_in_traffic', {}).get('value', normal_duration)
            
            if normal_duration > 0:
                congestion_ratio = traffic_duration / normal_duration
                congestion_level = get_congestion_level(congestion_ratio)
            else:
                congestion_level = 'Unknown'
            
            return {
                'current_duration': format_duration(traffic_duration),
                'normal_duration': format_duration(normal_duration),
                'delay_minutes': round((traffic_duration - normal_duration) / 60),
                'congestion_level': congestion_level,
                'last_updated': datetime.now().strftime('%H:%M')
            }
            
    except Exception as e:
        app.logger.error(f"Error getting current traffic: {e}")
        return {'error': 'Unable to fetch current traffic data'}

def format_duration(seconds):
    """Format duration in seconds to readable format"""
    if seconds < 60:
        return f"{seconds} sec"
    elif seconds < 3600:
        minutes = round(seconds / 60)
        return f"{minutes} min"
    else:
        hours = seconds // 3600
        minutes = round((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"
    



@app.route('/api/smart-flight-routing')
def get_flight_routing():
    """Suggest smart long-distance routing like flights"""
    origin_city = request.args.get('origin')
    destination_city = request.args.get('destination')

    if not origin_city or not destination_city:
        return jsonify({'error': 'Origin and destination cities are required'}), 400

    try:
        gmaps = googlemaps.Client(key=app.config['Maps_API_KEY'])

        # Get geocoding info
        origin_geo = gmaps.geocode(origin_city)
        destination_geo = gmaps.geocode(destination_city)

        if not origin_geo or not destination_geo:
            return jsonify({'error': 'Could not resolve city names'}), 404

        origin_coords = origin_geo[0]['geometry']['location']
        destination_coords = destination_geo[0]['geometry']['location']

        # Calculate straight-line distance in KM
        distance_km = geodesic(
            (origin_coords['lat'], origin_coords['lng']),
            (destination_coords['lat'], destination_coords['lng'])
        ).km

        # Determine if flight is recommended
        if distance_km > 500:
            # Simulated logic for now
            route = {
                'mode': 'flight',
                'from': origin_city,
                'to': destination_city,
                'estimated_duration': f"{round(distance_km / 800, 2)} hours",
                'estimated_distance': f"{round(distance_km)} km",
                'suggested_departure_airport': get_nearest_airport(origin_city),
                'suggested_arrival_airport': get_nearest_airport(destination_city),
                'note': 'Flight recommended due to long distance'
            }
        else:
            route = {
                'mode': 'local_transport',
                'note': 'Distance short enough for local transport',
                'distance': f"{round(distance_km)} km"
            }

        return jsonify(route)

    except Exception as e:
        app.logger.error(f"Flight routing error: {e}")
        return jsonify({'error': 'Internal error calculating route'}), 500


def get_nearest_airport(city_name):
    """Dummy airport lookup — expand as needed"""
    known_airports = {
        'Hyderabad': 'Rajiv Gandhi Intl Airport (HYD)',
        'Dubai': 'Dubai Intl Airport (DXB)',
        'Delhi': 'Indira Gandhi Intl Airport (DEL)',
        'Mumbai': 'Chhatrapati Shivaji Intl Airport (BOM)',
        'Chennai': 'Chennai Intl Airport (MAA)',
        'Bangalore': 'Kempegowda Intl Airport (BLR)'
    }
    for key in known_airports:
        if key.lower() in city_name.lower():
            return known_airports[key]
    return "Nearest Major Airport"


@app.route('/api/weather')
def get_weather():
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    
    if not lat or not lng:
        return jsonify({'error': 'Latitude and longitude are required'}), 400
    
    weather_api_key = app.config['OPENWEATHER_API_KEY']
    weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lng}&appid={weather_api_key}&units=metric"
    
    try:
        response = requests.get(weather_url)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        weather_data = response.json()
        
        # Extract relevant weather information
        temperature = weather_data['main']['temp']
        description = weather_data['weather'][0]['description']
        icon = weather_data['weather'][0]['icon']
        
        return jsonify({
            'temperature': temperature,
            'description': description,
            'icon_url': f"http://openweathermap.org/img/wn/{icon}.png"
        })
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error fetching weather data: {e}")
        return jsonify({'error': 'Could not fetch weather data'}), 500
    except KeyError as e:
        app.logger.error(f"Error parsing weather data: Missing key {e}")
        return jsonify({'error': 'Could not parse weather data'}), 500

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', message="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', message="Server error occurred. Please try again."), 500

# Start the app and create tables
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True,port=5004)
