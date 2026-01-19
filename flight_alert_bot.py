"""
TELEGRAM FLIGHT ALERT BOT - SMART VERSION
=========================================
Features:
- Daily digest with best deals
- Price drop alerts (immediate when prices drop significantly)
- Google Flights booking links
- Tracks price history to detect drops
- User-friendly grouped messages
"""

import os
import time
import json
import logging
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

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
        pass


def run_web_server():
    """Run a simple web server for Render health checks"""
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"🌐 Web server running on port {port}")
    server.serve_forever()


class PriceTracker:
    """Tracks historical prices to detect significant drops"""
    
    def __init__(self):
        self.price_history = {}  # {route_key: [prices]}
        self.load_history()
    
    def get_route_key(self, origin, destination, date):
        """Generate unique key for route+date combo"""
        return f"{origin}-{destination}-{date}"
    
    def load_history(self):
        """Load price history from file if exists"""
        try:
            if os.path.exists('price_history.json'):
                with open('price_history.json', 'r') as f:
                    self.price_history = json.load(f)
                logger.info(f"📊 Loaded price history for {len(self.price_history)} routes")
        except Exception as e:
            logger.warning(f"Could not load price history: {e}")
            self.price_history = {}
    
    def save_history(self):
        """Save price history to file"""
        try:
            with open('price_history.json', 'w') as f:
                json.dump(self.price_history, f)
        except Exception as e:
            logger.error(f"Could not save price history: {e}")
    
    def add_price(self, origin, destination, date, price):
        """Add a new price observation"""
        route_key = self.get_route_key(origin, destination, date)
        
        if route_key not in self.price_history:
            self.price_history[route_key] = []
        
        self.price_history[route_key].append({
            'price': price,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 30 observations per route
        self.price_history[route_key] = self.price_history[route_key][-30:]
        self.save_history()
    
    def get_average_price(self, origin, destination, date):
        """Get average historical price for a route"""
        route_key = self.get_route_key(origin, destination, date)
        
        if route_key not in self.price_history or len(self.price_history[route_key]) < 3:
            return None
        
        prices = [obs['price'] for obs in self.price_history[route_key]]
        return sum(prices) / len(prices)
    
    def is_significant_drop(self, origin, destination, date, current_price, threshold=0.20):
        """Check if current price is significantly lower than average (default 20% drop)"""
        avg_price = self.get_average_price(origin, destination, date)
        
        if avg_price is None:
            return False
        
        drop_percentage = (avg_price - current_price) / avg_price
        
        if drop_percentage >= threshold:
            logger.info(f"🔥 PRICE DROP! {origin}->{destination}: ${current_price} (was ${avg_price:.2f}, {drop_percentage*100:.1f}% drop)")
            return True
        
        return False


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
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get('ok'):
                logger.info(f"✅ Message sent successfully")
                return True
            else:
                logger.error(f"❌ Telegram API error: {result}")
                return False
                
        except Exception as e:
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
                test_msg = "✈️ <b>Flight Alert Bot Started!</b>\n\nYou'll receive:\n• Daily digest of best deals (once per day)\n• Instant alerts when prices drop significantly\n\nHappy travels! 🌍"
                return self.send_message(test_msg)
            else:
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
        """Search for flights and return cheapest option only"""
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
            'max': 10,  # Get more options to find the cheapest
            'currencyCode': 'USD'
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if 'data' not in data or len(data['data']) == 0:
                return None
            
            # Find the absolute cheapest flight
            cheapest = None
            for offer in data['data']:
                price = float(offer['price']['total'])
                
                # Only consider if under max_price threshold
                if price > max_price:
                    continue
                
                if cheapest is None or price < cheapest['price']:
                    cheapest = {
                        'price': price,
                        'currency': offer['price']['currency'],
                        'departure': offer['itineraries'][0]['segments'][0]['departure']['at'],
                        'arrival': offer['itineraries'][0]['segments'][-1]['arrival']['at'],
                        'airline': offer['itineraries'][0]['segments'][0]['carrierCode'],
                        'stops': len(offer['itineraries'][0]['segments']) - 1,
                        'origin': origin,
                        'destination': destination
                    }
            
            return cheapest
            
        except Exception as e:
            logger.error(f"❌ Error searching {origin}->{destination}: {e}")
            return None


class FlightAlertBot:
    """Main bot with smart alerts and daily digest"""
    
    def __init__(self, telegram_token, amadeus_key, amadeus_secret, chat_id):
        self.telegram = TelegramBot(telegram_token, chat_id)
        self.amadeus = AmadeusAPI(amadeus_key, amadeus_secret)
        self.price_tracker = PriceTracker()
        self.last_digest_date = None
        
        # Your flight routes and price thresholds
        self.routes = {
            'US & Canada': [
                {'origins': ['AEP', 'EZE'], 'destination': 'JFK', 'city': 'New York', 'max_price': 700},
                {'origins': ['AEP', 'EZE'], 'destination': 'MIA', 'city': 'Miami', 'max_price': 700},
                {'origins': ['AEP', 'EZE'], 'destination': 'LAX', 'city': 'Los Angeles', 'max_price': 700},
                {'origins': ['AEP', 'EZE'], 'destination': 'SFO', 'city': 'San Francisco', 'max_price': 700},
            ],
            'Europe': [
                {'origins': ['AEP', 'EZE'], 'destination': 'MAD', 'city': 'Madrid', 'max_price': 700},
                {'origins': ['AEP', 'EZE'], 'destination': 'BCN', 'city': 'Barcelona', 'max_price': 700},
                {'origins': ['AEP', 'EZE'], 'destination': 'CDG', 'city': 'Paris', 'max_price': 700},
                {'origins': ['AEP', 'EZE'], 'destination': 'FCO', 'city': 'Rome', 'max_price': 700},
                {'origins': ['AEP', 'EZE'], 'destination': 'LHR', 'city': 'London', 'max_price': 700},
            ],
            'Asia': [
                {'origins': ['AEP', 'EZE'], 'destination': 'BKK', 'city': 'Bangkok', 'max_price': 700},
                {'origins': ['AEP', 'EZE'], 'destination': 'NRT', 'city': 'Tokyo', 'max_price': 700},
                {'origins': ['AEP', 'EZE'], 'destination': 'PEK', 'city': 'Beijing', 'max_price': 700},
            ],
            'Brazil': [
                {'origins': ['AEP', 'EZE'], 'destination': 'GRU', 'city': 'São Paulo', 'max_price': 150},
                {'origins': ['AEP', 'EZE'], 'destination': 'GIG', 'city': 'Rio de Janeiro', 'max_price': 150},
                {'origins': ['AEP', 'EZE'], 'destination': 'SSA', 'city': 'Salvador', 'max_price': 150},
                {'origins': ['AEP', 'EZE'], 'destination': 'REC', 'city': 'Recife', 'max_price': 150},
                {'origins': ['AEP', 'EZE'], 'destination': 'FOR', 'city': 'Fortaleza', 'max_price': 150},
                {'origins': ['AEP', 'EZE'], 'destination': 'FLN', 'city': 'Florianópolis', 'max_price': 150},
            ],
            'Chile': [
                {'origins': ['AEP', 'EZE'], 'destination': 'SCL', 'city': 'Santiago', 'max_price': 150},
                {'origins': ['AEP', 'EZE'], 'destination': 'PUQ', 'city': 'Punta Arenas', 'max_price': 150},
            ],
            'Argentina': [
                {'origins': ['AEP', 'EZE'], 'destination': 'BRC', 'city': 'Bariloche', 'max_price': 150},
                {'origins': ['AEP', 'EZE'], 'destination': 'CPC', 'city': 'San Martín de los Andes', 'max_price': 150},
            ]
        }
    
    def create_google_flights_link(self, origin, destination, date):
        """Create a Google Flights search link"""
        # Google Flights format: google.com/flights?hl=en#flt=ORIGIN.DESTINATION.DATE
        return f"https://www.google.com/flights?hl=en#flt={origin}.{destination}.{date};c:USD"
    
    def format_price_drop_alert(self, flight, route, avg_price, drop_percentage):
        """Format immediate alert for significant price drops"""
        dep_date = flight['departure'][:10]
        dep_time = datetime.fromisoformat(flight['departure'].replace('Z', '+00:00'))
        
        message = f"🔥 <b>PRICE DROP ALERT!</b> 🔥\n\n"
        message += f"<b>{route['city']}</b>\n"
        message += f"💰 <b>${flight['price']:.0f}</b> (was ${avg_price:.0f}, save ${avg_price - flight['price']:.0f}!)\n"
        message += f"📉 {drop_percentage:.0f}% below average\n\n"
        message += f"📅 {dep_time.strftime('%a, %b %d, %Y')}\n"
        message += f"✈️ {flight['airline']} • {flight['stops']} stop(s)\n\n"
        
        # Add booking link
        link = self.create_google_flights_link(flight['origin'], flight['destination'], dep_date)
        message += f"🔗 <a href='{link}'>Book on Google Flights</a>\n\n"
        message += "⚡ Book fast! Prices may increase soon."
        
        return message
    
    def format_daily_digest(self, deals_by_region):
        """Format daily digest with best deals grouped by region"""
        if not deals_by_region:
            return None
        
        message = f"📊 <b>DAILY FLIGHT DEALS DIGEST</b>\n"
        message += f"🗓 {datetime.now().strftime('%A, %B %d, %Y')}\n\n"
        
        total_deals = sum(len(deals) for deals in deals_by_region.values())
        message += f"Found {total_deals} great deal(s) today!\n"
        message += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for region, deals in deals_by_region.items():
            if not deals:
                continue
                
            message += f"<b>🌍 {region}</b>\n\n"
            
            for deal in deals:
                flight = deal['flight']
                route = deal['route']
                dep_date = flight['departure'][:10]
                dep_time = datetime.fromisoformat(flight['departure'].replace('Z', '+00:00'))
                
                savings = route['max_price'] - flight['price']
                savings_pct = (savings / route['max_price']) * 100
                
                message += f"<b>{route['city']}</b>\n"
                message += f"💰 ${flight['price']:.0f} (save ${savings:.0f}, {savings_pct:.0f}% off)\n"
                message += f"📅 {dep_time.strftime('%b %d')} • {flight['airline']} • {flight['stops']} stop(s)\n"
                
                link = self.create_google_flights_link(flight['origin'], flight['destination'], dep_date)
                message += f"🔗 <a href='{link}'>Book</a>\n\n"
            
            message += "\n"
        
        message += "━━━━━━━━━━━━━━━━━━━━\n"
        message += "💡 Tip: Book flexible dates for best prices!"
        
        return message
    
    def check_all_routes(self):
        """Check all routes and return deals"""
        logger.info("🔍 Checking flight prices...")
        
        # Search dates: 30, 60, 90 days ahead
        search_dates = []
        today = datetime.now()
        for days_ahead in [30, 60, 90]:
            search_date = today + timedelta(days=days_ahead)
            search_dates.append(search_date.strftime('%Y-%m-%d'))
        
        deals_by_region = {region: [] for region in self.routes.keys()}
        price_drop_alerts = []
        
        for region, routes in self.routes.items():
            for route in routes:
                # Check from both airports (AEP and EZE)
                best_flight = None
                
                for origin in route['origins']:
                    for departure_date in search_dates:
                        flight = self.amadeus.search_flights(
                            origin=origin,
                            destination=route['destination'],
                            departure_date=departure_date,
                            max_price=route['max_price']
                        )
                        
                        if flight:
                            # Check if this is the best price we've found
                            if best_flight is None or flight['price'] < best_flight['price']:
                                best_flight = flight
                        
                        time.sleep(1)  # Be nice to the API
                
                # If we found a flight, process it
                if best_flight:
                    price = best_flight['price']
                    origin = best_flight['origin']
                    destination = best_flight['destination']
                    dep_date = best_flight['departure'][:10]
                    
                    # Add to price history
                    self.price_tracker.add_price(origin, destination, dep_date, price)
                    
                    # Check if it's at least 20% below threshold (really good deal)
                    threshold_savings = (route['max_price'] - price) / route['max_price']
                    
                    if threshold_savings >= 0.20:  # 20% below max price
                        deals_by_region[region].append({
                            'flight': best_flight,
                            'route': route
                        })
                        logger.info(f"✅ Great deal: {route['city']} at ${price}")
                    
                    # Check for significant price drops
                    avg_price = self.price_tracker.get_average_price(origin, destination, dep_date)
                    if avg_price and price < avg_price:
                        drop_pct = ((avg_price - price) / avg_price)
                        
                        if drop_pct >= 0.20:  # 20% drop from average
                            price_drop_alerts.append({
                                'flight': best_flight,
                                'route': route,
                                'avg_price': avg_price,
                                'drop_percentage': drop_pct * 100
                            })
                            logger.info(f"🔥 Price drop: {route['city']} ${price} (was ${avg_price:.0f})")
        
        return deals_by_region, price_drop_alerts
    
    def should_send_daily_digest(self):
        """Check if we should send the daily digest (once per day at 9 AM)"""
        now = datetime.now()
        
        # Send digest at 9 AM (or first check after 9 AM if bot was down)
        if now.hour >= 9:
            today_date = now.date()
            
            if self.last_digest_date != today_date:
                self.last_digest_date = today_date
                return True
        
        return False
    
    def run(self):
        """Main loop - checks every 2 hours, sends digest daily, immediate alerts for drops"""
        logger.info("🚀 Flight Alert Bot starting...")
        
        if not self.telegram.test_connection():
            logger.error("❌ Failed to connect to Telegram!")
            return
        
        logger.info("✅ Bot is running!")
        
        while True:
            try:
                # Check flights
                deals_by_region, price_drop_alerts = self.check_all_routes()
                
                # Send immediate alerts for significant price drops
                for alert in price_drop_alerts:
                    message = self.format_price_drop_alert(
                        alert['flight'],
                        alert['route'],
                        alert['avg_price'],
                        alert['drop_percentage']
                    )
                    self.telegram.send_message(message)
                    time.sleep(2)  # Small delay between messages
                
                # Send daily digest if it's time
                if self.should_send_daily_digest():
                    digest = self.format_daily_digest(deals_by_region)
                    if digest:
                        self.telegram.send_message(digest)
                        logger.info("📊 Daily digest sent")
                    else:
                        # Send message that no deals found
                        no_deals_msg = f"📊 <b>Daily Digest</b>\n\nNo exceptional deals found today. I'll keep watching! ✈️"
                        self.telegram.send_message(no_deals_msg)
                
                # Wait 2 hours before next check
                logger.info("😴 Sleeping for 2 hours...")
                time.sleep(7200)
                
            except KeyboardInterrupt:
                logger.info("⛔ Bot stopped")
                break
            except Exception as e:
                logger.error(f"❌ Error: {e}")
                time.sleep(1800)  # Wait 30 min on error


if __name__ == "__main__":
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    AMADEUS_API_KEY = os.getenv('AMADEUS_API_KEY')
    AMADEUS_API_SECRET = os.getenv('AMADEUS_API_SECRET')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    
    if not all([TELEGRAM_TOKEN, AMADEUS_API_KEY, AMADEUS_API_SECRET, TELEGRAM_CHAT_ID]):
        logger.error("❌ Missing environment variables!")
        exit(1)
    
    # Start web server
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # Start bot
    bot = FlightAlertBot(
        telegram_token=TELEGRAM_TOKEN,
        amadeus_key=AMADEUS_API_KEY,
        amadeus_secret=AMADEUS_API_SECRET,
        chat_id=TELEGRAM_CHAT_ID
    )
    
    bot.run()
