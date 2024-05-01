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
ban_players_url = os.getenv('API_BASE_URLS') + '/api/do_perma_ban'
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
for player in players:
    ban_data = {
        'player': player['player'],
        'steam_id_64': player['steam_id_64'],
        'reason': player['reason'],
        'by': player['by']
    }
    logging.info(f"Versuch, den Spieler {player['player']} zu bannen...")
    ban_response = requests.post(ban_players_url, headers=headers, json=ban_data)
    logging.info(f"Antwort auf das Bannen von {player['player']}: {ban_response.text}")
