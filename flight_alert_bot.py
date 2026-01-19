"""
TELEGRAM FLIGHT ALERT BOT - WEB SERVICE VERSION
===============================================
This version includes a simple web server so it can run on Render as a Web Service
"""

import os
import time
import logging
from datetime import datetime, timedelta
import requests
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks"""
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Flight Alert Bot is running!')
    
    def log_message(self, format, *args):
        # Suppress HTTP logs to keep output clean
        pass


def run_web_server():
    """Run a simple web server for Render health checks"""
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"🌐 Web server running on port {port}")
    server.serve_forever()


class TelegramBot:
    """Simple Telegram bot using direct API calls"""
    
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send_message(self, text):
        """Send a message via Telegram API"""
        url = f"{self.base_url}/sendMessage"
        
        payload = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get('ok'):
                logger.info(f"✅ Message sent successfully to chat {self.chat_id}")
                return True
            else:
                logger.error(f"❌ Telegram API returned error: {result}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error sending message: {e}")
            return False
    
    def test_connection(self):
        """Test if bot can send messages"""
        url = f"{self.base_url}/getMe"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get('ok'):
                bot_info = result['result']
                logger.info(f"✅ Bot connected: @{bot_info['username']}")
                
                # Try sending a test message
                test_msg = "🤖 Flight Alert Bot is starting up! Testing connection..."
                return self.send_message(test_msg)
            else:
                logger.error(f"❌ Bot connection failed: {result}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False


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
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token
            
        url = "https://test.api.amadeus.com/v1/security/oauth2/token"
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.api_key,
            'client_secret': self.api_secret
        }
        
        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data['access_token']
            self.token_expiry = datetime.now() + timedelta(seconds=token_data['expires_in'] - 300)
            
            logger.info("✅ Amadeus token obtained")
            return self.access_token
            
        except Exception as e:
            logger.error(f"❌ Error getting Amadeus token: {e}")
            return None
    
    def search_flights(self, origin, destination, departure_date, max_price):
        """Search for flights between two cities"""
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
            'max': 5,
            'currencyCode': 'USD'
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
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
            logger.error(f"❌ Error searching {origin}->{destination}: {e}")
            return None


class FlightAlertBot:
    """Main bot that coordinates flight searches and sends alerts"""
    
    def __init__(self, telegram_token, amadeus_key, amadeus_secret, chat_id):
        self.telegram = TelegramBot(telegram_token, chat_id)
        self.amadeus = AmadeusAPI(amadeus_key, amadeus_secret)
        
        # Your flight routes and price thresholds
        self.routes = [
            # US Routes
            {'origins': ['AEP', 'EZE'], 'destination': 'JFK', 'city': 'New York', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'MIA', 'city': 'Miami', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'LAX', 'city': 'Los Angeles', 'max_price': 700},
            {'origins': ['AEP', 'EZE'], 'destination': 'SFO', 'city': 'San Francisco', 'max_price': 700},
            
            # Europe Routes
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
        
    def format_flight_alert(self, route, flights):
        """Format a nice message for the flight deal"""
        message = f"✈️ <b>CHEAP FLIGHT ALERT!</b> ✈️\n\n"
        message += f"<b>Route:</b> Buenos Aires → {route['city']}\n"
        message += f"<b>Max Price:</b> ${route['max_price']} USD\n\n"
        
        for i, flight in enumerate(flights[:3], 1):
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
        logger.info("🔍 Starting flight price check...")
        
        search_dates = []
        today = datetime.now()
        
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
                        self.telegram.send_message(message)
                        logger.info(f"📧 Sent alert for {len(flights)} deals to {route['city']}")
                    
                    time.sleep(1)
        
        logger.info(f"✅ Check complete. Found {deals_found} total deals.")
        return deals_found
    
    def run(self):
        """Main loop - checks flights every 6 hours"""
        logger.info("🚀 Flight Alert Bot starting...")
        
        # Test connection first
        if not self.telegram.test_connection():
            logger.error("❌ Failed to connect to Telegram! Check your token and chat ID.")
            return
        
        logger.info("✅ Bot is running and connected!")
        
        while True:
            try:
                self.check_all_routes()
                
                logger.info("😴 Sleeping for 6 hours until next check...")
                time.sleep(21600)  # 6 hours
                
            except KeyboardInterrupt:
                logger.info("⛔ Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                time.sleep(1800)  # Wait 30 minutes on error


if __name__ == "__main__":
    # Get credentials from environment variables
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    AMADEUS_API_KEY = os.getenv('AMADEUS_API_KEY')
    AMADEUS_API_SECRET = os.getenv('AMADEUS_API_SECRET')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    
    # Validate credentials
    if not all([TELEGRAM_TOKEN, AMADEUS_API_KEY, AMADEUS_API_SECRET, TELEGRAM_CHAT_ID]):
        logger.error("❌ Missing environment variables!")
        logger.error("Required: TELEGRAM_BOT_TOKEN, AMADEUS_API_KEY, AMADEUS_API_SECRET, TELEGRAM_CHAT_ID")
        exit(1)
    
    logger.info(f"📱 Using Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    logger.info(f"🤖 Using Bot Token: {TELEGRAM_TOKEN[:20]}...")
    
    # Start web server in background thread
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # Create and run bot
    bot = FlightAlertBot(
        telegram_token=TELEGRAM_TOKEN,
        amadeus_key=AMADEUS_API_KEY,
        amadeus_secret=AMADEUS_API_SECRET,
        chat_id=TELEGRAM_CHAT_ID
    )
    
    bot.run()
