import asyncio
import logging
import os
import json
from api_manager import APIClient
from dotenv import load_dotenv
import aio_pika
import aiohttp

# Konfigurieren des Loggings
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler('app.log'),  # Log-Ausgabe in Datei
                        logging.StreamHandler()  # Log-Ausgabe in die Konsole
                    ])

# Umgebungsvariablen laden
load_dotenv()
BASE_URLS = os.getenv('API_BASE_URLS').split(',')
API_TOKEN = os.getenv('BEARER_TOKEN')
API_USER = os.getenv('API_USER')
API_PASS = os.getenv('API_PASS')
YOUR_CLIENT_ID = os.getenv('CLIENT_ID')
RABBITMQ_USER = os.getenv('RABBITMQ_USER')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', '5672'))

# API-Client-Instanzen erstellen
api_clients = [APIClient(url.strip(), API_TOKEN) for url in BASE_URLS if url.strip()]

# Authentifizierung bei den API-Clients
for api_client in api_clients:
    if api_client.login(API_USER, API_PASS):
        logging.info(f"Erfolgreich bei der API angemeldet für URL: {api_client.base_url}")
    else:
        logging.error(f"Fehler bei der Anmeldung an der API für URL: {api_client.base_url}")
        raise Exception(f"Fehler bei der Anmeldung an der API für URL: {api_client.base_url}")

async def connect_to_rabbitmq():
    logging.info("Versuche, eine Verbindung zu RabbitMQ herzustellen...")
    connection = await aio_pika.connect_robust(
        f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/",
        loop=asyncio.get_running_loop(),
        heartbeat=600,
        client_properties={'connection_name': 'my_connection'}
    )
    channel = await connection.channel()
    exchange = await channel.declare_exchange('bans_fanout', aio_pika.ExchangeType.FANOUT, durable=True)
    queue = await channel.declare_queue('', exclusive=True)
    await queue.bind(exchange)
    logging.info("RabbitMQ Exchange und Queue deklariert und gebunden.")
    return connection, channel, queue

async def consume_messages(connection, channel, queue):
    logging.info("Beginne mit dem Empfang von Nachrichten...")
    async with connection, aiohttp.ClientSession() as session:  # Starte eine ClientSession für HTTP-Anfragen
        async for message in queue:
            logging.info(f"Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
            async with message.process():
                try:
                    ban_data = json.loads(message.body.decode())
                    logging.info(f"Empfangene Ban-Daten: {ban_data}")
                    for api_client in api_clients:
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
                            # Führe eine asynchrone POST-Anfrage aus
                            async with session.post("https://api.1bv.eu/update_ban_status", json=data_to_send) as response:
                                if response.status != 200:
                                    response_text = await response.text()
                                    logging.error(f"Fehler beim Aktualisieren des Status von {ban_data['player']}: {response_text}")
                except json.JSONDecodeError:
                    logging.error("Fehler beim Parsen der JSON-Daten")
                    await message.nack(requeue=True)  # Nachricht wird zur Wiederverarbeitung in die Queue zurückgestellt
                except Exception as e:
                    logging.error(f"Unerwarteter Fehler beim Verarbeiten der Nachricht: {e}")
                    await message.nack(requeue=True)  # Nachricht wird zur Wiederverarbeitung in die Queue zurückgestellt


async def main():
    try:
        connection, channel, queue = await connect_to_rabbitmq()
        await consume_messages(connection, channel, queue)
    except Exception as e:
        logging.error(f"Fehler beim Verbinden zu RabbitMQ oder beim Empfangen von Nachrichten: {e}")

if __name__ == '__main__':
    asyncio.run(main())
