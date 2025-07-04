import googlemaps
import time

def get_places(city, days, budget, group_type, api_key):
    """Get famous places and recommended attractions based on user preferences"""
    gmaps = googlemaps.Client(key=api_key)
    geocode_result = gmaps.geocode(city)
    if not geocode_result:
        return {}, (0, 0)
    
    location = geocode_result[0]['geometry']['location']
    latlng = (location['lat'], location['lng'])
    
    # Enhanced keywords for famous attractions
    famous_keywords = ["must visit", "famous", "top attractions", "landmarks", "popular"]
    
    # Customize additional keywords based on group type
    if group_type == "couple":
        additional_keywords = ["romantic spots", "date spots", "scenic views"]
    elif group_type == "family":
        additional_keywords = ["family friendly", "kids activities", "parks"]
    elif group_type == "friends":
        additional_keywords = ["fun activities", "entertainment", "nightlife"]
    elif group_type == "solo":
        additional_keywords = ["sightseeing", "cultural spots", "local experience"]
    else:
        additional_keywords = ["tourist attractions", "places to see"]
    
    # Combine famous keywords with group-specific ones
    all_keywords = famous_keywords + additional_keywords
    
    # Map budget preferences to price levels
    if budget == "low":
        max_price_level = 1
    elif budget == "moderate":
        max_price_level = 3
    else:  # luxurious
        max_price_level = 4
    
    # Calculate needed places (3 places per day)
    places_needed = days * 3
    places = []
    
    # First search for famous places to prioritize them
    for keyword in famous_keywords:
        results = gmaps.places_nearby(
            location=latlng, 
            radius=30000,  # Increased radius to find more attractions
            type="tourist_attraction",  # Focus on tourist attractions first
            keyword=keyword,
            rank_by="prominence"  # Rank by prominence to get the most relevant results
        )
        
        # Process results
        for place in results.get('results', []):
            place_details = _process_place(place, max_price_level)
            if place_details and place_details not in places:
                places.append(place_details)
        
        # Get additional pages if needed
        while 'next_page_token' in results and len(places) < places_needed:
            # Wait required by Google API before requesting next page
            time.sleep(2)
            results = gmaps.places_nearby(
                page_token=results['next_page_token']
            )
            
            for place in results.get('results', []):
                place_details = _process_place(place, max_price_level)
                if place_details and place_details not in places:
                    places.append(place_details)
    
    # Then search for group-specific places if we need more
    if len(places) < places_needed * 2:
        for keyword in additional_keywords:
            results = gmaps.places_nearby(
                location=latlng, 
                radius=20000,
                type="point_of_interest",
                keyword=keyword
            )
            
            # Process results
            for place in results.get('results', []):
                place_details = _process_place(place, max_price_level)
                if place_details and place_details not in places:
                    places.append(place_details)
            
            # Get additional pages if needed
            while 'next_page_token' in results and len(places) < places_needed * 2:
                # Wait required by Google API before requesting next page
                time.sleep(2)
                results = gmaps.places_nearby(
                    page_token=results['next_page_token']
                )
                
                for place in results.get('results', []):
                    place_details = _process_place(place, max_price_level)
                    if place_details and place_details not in places:
                        places.append(place_details)
            
            if len(places) >= places_needed * 2:
                break
    
    # Add place details for more information
    enriched_places = []
    for place in places[:places_needed * 2]:  # Limit to avoid too many API calls
        try:
            place_id = place.get('place_id')
            if place_id:
                details = gmaps.place(place_id=place_id, fields=[
                    'name', 'rating', 'formatted_address', 'opening_hours',
                    'photo', 'website', 'price_level', 'formatted_phone_number',
                    'user_ratings_total', 'editorial_summary'  # Added fields for better recommendations
                ])
                
                place_data = details.get('result', {})
                
                # Get photo reference if available
                photo_url = None
                if 'photos' in place_data and len(place_data['photos']) > 0:
                    photo_reference = place_data['photos'][0].get('photo_reference')
                    if photo_reference:
                        photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=300&photoreference={photo_reference}&key={api_key}"
                
                # Get place description if available
                description = ""
                if 'editorial_summary' in place_data and place_data['editorial_summary']:
                    description = place_data['editorial_summary'].get('overview', '')
                
                enriched_place = {
                    'name': place_data.get('name', place.get('name')),
                    'rating': place_data.get('rating', place.get('rating', 0)),
                    'location': place.get('location'),
                    'address': place_data.get('formatted_address', place.get('address', '')),
                    'place_id': place_id,
                    'website': place_data.get('website', ''),
                    'phone': place_data.get('formatted_phone_number', ''),
                    'photo_url': photo_url,
                    'price_level': place_data.get('price_level', place.get('price_level', 2)),
                    'user_ratings_total': place_data.get('user_ratings_total', 0),
                    'description': description
                }
                enriched_places.append(enriched_place)
                
                # Add a small delay to avoid hitting API rate limits
                time.sleep(0.2)
                
        except Exception as e:
            # If there's an error, use the basic place data
            enriched_places.append(place)
    
    # Sort by a combination of rating and popularity
    # Places with higher ratings and more reviews are prioritized
    def place_score(place):
        rating = place.get('rating', 0)
        reviews = place.get('user_ratings_total', 0)
        # Normalize reviews to a 0-5 scale similar to ratings
        reviews_score = min(5, reviews / 200) if reviews else 0
        # Combined score with more weight on rating
        return (rating * 0.7) + (reviews_score * 0.3)
    
    enriched_places = sorted(enriched_places, key=place_score, reverse=True)
    
    # Create the itinerary
    itinerary = {}
    for i in range(1, days + 1):
        day_places = enriched_places[:3]
        enriched_places = enriched_places[3:]  # Remove used places
        
        # If we run out of places, reuse some from the beginning
        if not day_places and enriched_places:
            day_places = enriched_places[:3]
            enriched_places = enriched_places[3:]
        
        itinerary[f'Day {i}'] = day_places
        
        if not enriched_places:
            break
    
    return itinerary, latlng

def _process_place(place, max_price_level):
    """Process a place result from Google Maps API"""
    price_level = place.get('price_level', 2)
    
    # Skip places with missing essential data
    if not place.get('name'):
        return None
        
    # Filter based on price level if available
    if price_level > max_price_level:
        return None
        
    return {
        'name': place.get('name'),
        'rating': place.get('rating', 0),
        'location': place['geometry']['location'],
        'address': place.get('vicinity', ''),
        'price_level': price_level,
        'place_id': place.get('place_id'),
        'user_ratings_total': place.get('user_ratings_total', 0)
    }