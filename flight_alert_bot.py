"""
TELEGRAM FLIGHT ALERT BOT
========================
This bot monitors flight prices and sends you Telegram alerts when cheap flights are found.

How it works:
1. Checks flight prices every 6 hours using Amadeus API
2. Compares prices against your thresholds
3. Sends instant Telegram notifications for good deals
"""

import os
import time
import logging
from datetime import datetime, timedelta
import requests
from telegram import Bot
from telegram.error import TelegramError

# Set up logging to track what the bot is doing
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AmadeusAPI:
    """Handles communication with Amadeus Flight API"""
    
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = None
        self.token_expiry = None
        self.base_url = "https://test.api.amadeus.com/v2"
        
    def get_access_token(self):
        """Get authentication token from Amadeus"""
        # Check if we already have a valid token
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token
            
        # Request new token
        url = "https://test.api.amadeus.com/v1/security/oauth2/token"
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.api_key,
            'client_secret': self.api_secret
        }
        
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data['access_token']
            # Token expires in seconds, we'll refresh 5 minutes before
            self.token_expiry = datetime.now() + timedelta(seconds=token_data['expires_in'] - 300)
            
            logger.info("Successfully obtained Amadeus access token")
            return self.access_token
            
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            return None
    
    def search_flights(self, origin, destination, departure_date, max_price):
        """
        Search for flights between two cities
        
        Args:
            origin: Airport code (e.g., 'AEP' for Aeroparque or 'EZE' for Ezeiza)
            destination: Airport code (e.g., 'JFK', 'MIA', 'GRU')
            departure_date: Date in YYYY-MM-DD format
            max_price: Maximum price threshold in USD
        """
        token = self.get_access_token()
        if not token:
            return None
            
        url = f"{self.base_url}/shopping/flight-offers"
        headers = {'Authorization': f'Bearer {token}'}
        
        params = {
            'originLocationCode': origin,
            'destinationLocationCode': destination,
            'departureDate': departure_date,
            'adults': 1,
            'max': 5,  # Get top 5 cheapest flights
            'currencyCode': 'USD'
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Filter flights below max price
            cheap_flights = []
            if 'data' in data:
                for offer in data['data']:
                    price = float(offer['price']['total'])
                    if price <= max_price:
                        cheap_flights.append({
                            'price': price,
                            'currency': offer['price']['currency'],
                            'departure': offer['itineraries'][0]['segments'][0]['departure']['at'],
                            'arrival': offer['itineraries'][0]['segments'][-1]['arrival']['at'],
                            'airline': offer['itineraries'][0]['segments'][0]['carrierCode'],
                            'stops': len(offer['itineraries'][0]['segments']) - 1
                        })
            
            return cheap_flights
            
        except Exception as e:
            logger.error(f"Error searching flights {origin}->{destination}: {e}")
            return None


class FlightAlertBot:
    """Main bot that coordinates flight searches and sends alerts"""
    
    def __init__(self, telegram_token, amadeus_key, amadeus_secret, chat_id):
        self.telegram_bot = Bot(token=telegram_token)
        self.amadeus = AmadeusAPI(amadeus_key, amadeus_secret)
        self.chat_id = chat_id
        
        # Your flight routes and price thresholds
        self.routes = [
            # US Routes
            {'origins': ['AEP', 'EZE'], 'destination': 'JFK', 'city': 'New York', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'MIA', 'city': 'Miami', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'LAX', 'city': 'Los Angeles', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'SFO', 'city': 'San Francisco', 'max_price': 700},
            
            # Europe Routes (major hubs)
            {'origins': ['AEP', 'EZE'], 'destination': 'MAD', 'city': 'Madrid', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'BCN', 'city': 'Barcelona', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'CDG', 'city': 'Paris', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'FCO', 'city': 'Rome', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'LHR', 'city': 'London', 'max_price': 700},
            
            # Asia Routes
            {'origins': ['AEP', 'EZE'], 'destination': 'BKK', 'city': 'Bangkok', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'NRT', 'city': 'Tokyo', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'PEK', 'city': 'Beijing', 'max_price': 700},
            
            # Brazil Routes
            {'origins': ['AEP', 'EZE'], 'destination': 'GRU', 'city': 'São Paulo', 'max_price': 150},
            {'origins': ['AEP', 'EZE'], 'destination': 'GIG', 'city': 'Rio de Janeiro', 'max_price': 150},
            {'origins': ['AEP', 'EZE'], 'destination': 'SSA', 'city': 'Salvador (Beach)', 'max_price': 150},
            {'origins': ['AEP', 'EZE'], 'destination': 'REC', 'city': 'Recife (Beach)', 'max_price': 150},
            {'origins': ['AEP', 'EZE'], 'destination': 'FOR', 'city': 'Fortaleza (Beach)', 'max_price': 150},
            {'origins': ['AEP', 'EZE'], 'destination': 'FLN', 'city': 'Florianópolis (Beach)', 'max_price': 150},
            
            # Chile Routes
            {'origins': ['AEP', 'EZE'], 'destination': 'SCL', 'city': 'Santiago', 'max_price': 150},
            {'origins': ['AEP', 'EZE'], 'destination': 'PUQ', 'city': 'Punta Arenas (South)', 'max_price': 150},
            
            # Argentina Routes
            {'origins': ['AEP', 'EZE'], 'destination': 'BRC', 'city': 'Bariloche', 'max_price': 150},
            {'origins': ['AEP', 'EZE'], 'destination': 'CPC', 'city': 'San Martín de los Andes', 'max_price': 150},
        ]
        
    def send_telegram_message(self, message):
        """Send a message via Telegram"""
        try:
            self.telegram_bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
            logger.info("Telegram message sent successfully")
            return True
        except TelegramError as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    def format_flight_alert(self, route, flights):
        """Format a nice message for the flight deal"""
        message = f"✈️ <b>CHEAP FLIGHT ALERT!</b> ✈️\n\n"
        message += f"<b>Route:</b> Buenos Aires → {route['city']}\n"
        message += f"<b>Max Price:</b> ${route['max_price']} USD\n\n"
        
        for i, flight in enumerate(flights[:3], 1):  # Show top 3 deals
            departure_time = datetime.fromisoformat(flight['departure'].replace('Z', '+00:00'))
            arrival_time = datetime.fromisoformat(flight['arrival'].replace('Z', '+00:00'))
            
            message += f"<b>Deal #{i}:</b>\n"
            message += f"💰 Price: ${flight['price']} {flight['currency']}\n"
            message += f"📅 Departure: {departure_time.strftime('%Y-%m-%d %H:%M')}\n"
            message += f"🛬 Arrival: {arrival_time.strftime('%Y-%m-%d %H:%M')}\n"
            message += f"✈️ Airline: {flight['airline']}\n"
            message += f"🔄 Stops: {flight['stops']}\n\n"
        
        message += "Book soon! Prices can change quickly. 🎉"
        return message
    
    def check_all_routes(self):
        """Check all routes for deals"""
        logger.info("Starting flight price check...")
        
        # Search for flights in the next 30-90 days
        search_dates = []
        today = datetime.now()
        
        # Check departures: in 30 days, 60 days, and 90 days
        for days_ahead in [30, 60, 90]:
            search_date = today + timedelta(days=days_ahead)
            search_dates.append(search_date.strftime('%Y-%m-%d'))
        
        deals_found = 0
        
        for route in self.routes:
            for origin in route['origins']:
                for departure_date in search_dates:
                    logger.info(f"Checking {origin} -> {route['destination']} on {departure_date}")
                    
                    flights = self.amadeus.search_flights(
                        origin=origin,
                        destination=route['destination'],
                        departure_date=departure_date,
                        max_price=route['max_price']
                    )
                    
                    if flights and len(flights) > 0:
                        deals_found += len(flights)
                        message = self.format_flight_alert(route, flights)
                        self.send_telegram_message(message)
                        logger.info(f"Found {len(flights)} deals for {route['city']}")
                    
                    # Be nice to the API - wait 1 second between requests
                    time.sleep(1)
        
        logger.info(f"Completed check. Found {deals_found} total deals.")
        return deals_found
    
    def run(self):
        """Main loop - checks flights every 6 hours"""
        logger.info("Flight Alert Bot started! 🚀")
        self.send_telegram_message("✈️ Flight Alert Bot is now running! I'll notify you when I find cheap flights.")
        
        while True:
            try:
                self.check_all_routes()
                
                # Wait 6 hours before next check (21600 seconds)
                logger.info("Sleeping for 6 hours until next check...")
                time.sleep(21600)
                
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                # Wait 30 minutes before retrying if there's an error
                time.sleep(1800)


if __name__ == "__main__":
    # These will come from environment variables (we'll set them up next)
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    AMADEUS_API_KEY = os.getenv('AMADEUS_API_KEY')
    AMADEUS_API_SECRET = os.getenv('AMADEUS_API_SECRET')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    
    # Check if all credentials are provided
    if not all([TELEGRAM_TOKEN, AMADEUS_API_KEY, AMADEUS_API_SECRET, TELEGRAM_CHAT_ID]):
        logger.error("Missing required environment variables!")
        logger.error("Please set: TELEGRAM_BOT_TOKEN, AMADEUS_API_KEY, AMADEUS_API_SECRET, TELEGRAM_CHAT_ID")
        exit(1)
    
    # Create and run the bot
    bot = FlightAlertBot(
        telegram_token=TELEGRAM_TOKEN,
        amadeus_key=AMADEUS_API_KEY,
        amadeus_secret=AMADEUS_API_SECRET,
        chat_id=TELEGRAM_CHAT_ID
    )
    
    bot.run()
