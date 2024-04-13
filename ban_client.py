import logging
import requests
from api_manager import APIClient
from dotenv import load_dotenv
import os
import pika
import json

# Konfigurieren des Loggings
logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Umgebungsvariablen laden
load_dotenv()
BASE_URLS = os.getenv('API_BASE_URLS')
API_TOKEN = os.getenv('BEARER_TOKEN')
API_USER = os.getenv('API_USER')
API_PASS = os.getenv('API_PASS')
YOUR_CLIENT_ID = os.getenv('CLIENT_ID')
RABBITMQ_USER = os.getenv('RABBITMQ_USER')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS')

if BASE_URLS:
    base_urls = BASE_URLS.split(',')
    api_clients = [APIClient(url.strip(), API_TOKEN) for url in base_urls if url.strip()]
else:
    logging.error("Keine API-Basis-URLs gefunden. Überprüfen Sie Ihre .env-Konfiguration.")
    raise Exception("Keine API-Basis-URLs gefunden. Überprüfen Sie Ihre .env-Konfiguration.")

for api_client in api_clients:
    if not api_client.login(API_USER, API_PASS):
        logging.error(f"Fehler bei der Anmeldung an der CRCON API für URL: {api_client.base_url}")
        raise Exception(f"Fehler bei der Anmeldung an der CRCON API für URL: {api_client.base_url}")

def connect_to_rabbitmq():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbit.1bv.eu', 5672, '/', credentials))
    channel = connection.channel()
    result = channel.queue_declare(queue='', exclusive=True)
    queue_name = result.method.queue
    channel.queue_bind(exchange='bans_fanout', queue=queue_name)
    logging.info("Verbunden mit RabbitMQ und Queue gebunden.")
    return channel, queue_name

def receive_ban_from_queue(channel, queue_name):
    def callback(ch, method, properties, body):
        ban_info = body.decode()
        try:
            ban_data = json.loads(ban_info)
            logging.debug(f"Gesendete Ban-Daten: {ban_data}")
        except json.JSONDecodeError:
            logging.error("Fehler beim Parsen der JSON-Daten")
            return

        if api_client.do_perma_ban(ban_data['player'], ban_data['steam_id_64'], ban_data['reason'], ban_data['by']):
            data_to_send = {
                'player': ban_data['player'],
                'steam_id_64': ban_data['steam_id_64'],
                'reason': ban_data['reason'],
                'banned': ban_data.get('banned', False),
                'links': ban_data.get('links', []),
                'attachments': ban_data.get('attachments', []),
                'issues': ban_data.get('issues', []),
                'by': ban_data['by'],
                'client_id': YOUR_CLIENT_ID
            }
            logging.info(f"Daten, die an die API gesendet werden: {data_to_send}")
            response = requests.post("https://api.1bv.eu/update_ban_status", json=data_to_send)
            if response.status_code != 200:
                logging.error(f"Fehler beim Aktualisieren des Status von {ban_data['player']}. Antwort: {response.text}")

    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
    logging.info('Warte auf neue Banns...')
    print('Warte auf neue Banns...')
    channel.start_consuming()

if __name__ == '__main__':
    channel, queue_name = connect_to_rabbitmq()
    receive_ban_from_queue(channel, queue_name)
