import os
import requests
import logging
from dotenv import load_dotenv

# Umgebungsvariablen laden
load_dotenv()

# Logging-Konfiguration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API-Endpunkte und Token aus der .env-Datei
get_players_url = 'https://api.1bv.eu/all_bans'
api_base_urls = os.getenv('API_BASE_URLS').split(',')
bearer_token = os.getenv('BEARER_TOKEN')

# Authentifizierungsheader
headers = {
    'Authorization': f'Bearer {bearer_token}'
}

# Spielerdaten abrufen
logging.info("Spielerdaten werden abgerufen...")
response = requests.get(get_players_url)
players = response.json()

# Jeden Spieler bannen
logging.info("Spieler werden gebannt, bitte warten...")

for api_base_url in api_base_urls:
    ban_players_url = f"{api_base_url}/api/do_perma_ban"
    for player in players:
        ban_data = {
            'player': player['player'],
            'steam_id_64': player['steam_id_64'],
            'reason': player['reason'],
            'by': player['by']
        }
        logging.info(f"Versuch, den Spieler {player['player']} zu bannen mit URL {ban_players_url}...")
        ban_response = requests.post(ban_players_url, headers=headers, json=ban_data)
        logging.info(f"Antwort auf das Bannen von {player['player']} mit URL {ban_players_url}: {ban_response.text}")

# Für API v10
def get_api_version(api_base_url):
    url = f"{api_base_url}/api/version"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        version = response.json().get("version", "unknown")
        return version
    return "unknown"

# Spieler bannen mit Unterstützung für beide Versionen
for api_base_url in api_base_urls:
    version = get_api_version(api_base_url)
    for player in players:
        if version.startswith("v10"):
            ban_players_url = f"{api_base_url}/api/perma_ban"
            ban_data = {
                'player_name': player['player'],
                'player_id': player['steam_id_64'],
                'reason': player['reason'],
                'by': player['by']
            }
        else:
            ban_players_url = f"{api_base_url}/api/do_perma_ban"
            ban_data = {
                'player': player['player'],
                'steam_id_64': player['steam_id_64'],
                'reason': player['reason'],
                'by': player['by']
            }
        logging.info(f"Versuch, den Spieler {player['player']} zu bannen mit URL {ban_players_url}...")
        ban_response = requests.post(ban_players_url, headers=headers, json=ban_data)
        logging.info(f"Antwort auf das Bannen von {player['player']} mit URL {ban_players_url}: {ban_response.text}")
