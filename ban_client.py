import asyncio
import logging
import os
import json
from api_manager import APIClient
from dotenv import load_dotenv
import aio_pika
from aio_pika import IncomingMessage, connect_robust, ExchangeType
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

async def consume_messages(connection, channel, queue, api_client):
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

async def connect_to_unban_rabbitmq():
    logging.info("Versuche, eine Verbindung zu RabbitMQ für Unban-Nachrichten herzustellen...")
    unban_connection = await aio_pika.connect_robust(
        f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/",
        loop=asyncio.get_running_loop(),
        heartbeat=600,
        client_properties={'connection_name': 'unban_connection'}
    )
    unban_channel = await unban_connection.channel()
    unban_exchange = await unban_channel.declare_exchange('unbans_fanout', aio_pika.ExchangeType.FANOUT, durable=True)
    unban_queue = await unban_channel.declare_queue('', exclusive=True)
    await unban_queue.bind(unban_exchange)
    logging.info("Unban RabbitMQ Exchange und Queue deklariert und gebunden.")
    return unban_connection, unban_channel, unban_queue

async def consume_unban_messages(connection, channel, queue, api_client):
    logging.info("Beginne mit dem Empfang von Unban-Nachrichten...")
    async with connection:
        async for message in queue:
            logging.info(f"Unban-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
            async with message.process():
                try:
                    unban_data = json.loads(message.body.decode())
                    logging.info(f"Empfangene Unban-Daten: {unban_data}")
                    # Verwende do_unban Methode, um den Unban durchzuführen
                    if api_client.do_unban(unban_data['steam_id_64']):
                        logging.info(f"Unban successful for steam_id_64: {unban_data['steam_id_64']}")
                    else:
                        logging.error(f"Unban operation failed for steam_id_64: {unban_data['steam_id_64']}")
                except json.JSONDecodeError:
                    logging.error("Fehler beim Parsen der JSON-Daten")
                    await message.nack(requeue=True)
                except Exception as e:
                    logging.error(f"Unerwarteter Fehler beim Verarbeiten der Nachricht: {e}")
                    await message.nack(requeue=True)

async def connect_to_tempban_rabbitmq():
    logging.info("Versuche, eine Verbindung zu RabbitMQ für Tempban-Nachrichten herzustellen...")
    tempban_connection = await aio_pika.connect_robust(
        f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/",
        loop=asyncio.get_running_loop(),
        heartbeat=600,
        client_properties={'connection_name': 'tempban_connection'}
    )
    tempban_channel = await tempban_connection.channel()
    tempban_exchange = await tempban_channel.declare_exchange('tempbans_fanout', aio_pika.ExchangeType.FANOUT, durable=True)
    tempban_queue = await tempban_channel.declare_queue('', exclusive=True)
    await tempban_queue.bind(tempban_exchange)
    logging.info("Tempban RabbitMQ Exchange und Queue deklariert und gebunden.")
    return tempban_connection, tempban_channel, tempban_queue

async def consume_tempban_messages(connection, channel, queue, api_client):
    logging.info("Beginne mit dem Empfang von Tempban-Nachrichten...")
    async with connection:
        async for message in queue:
            logging.info(f"Tempban-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
            async with message.process():
                try:
                    ban_data = json.loads(message.body.decode())
                    logging.info(f"Empfangene Tempban-Daten: {ban_data}")
                    
                    # Verwende do_temp_ban Methode, um den Tempban durchzuführen
                    # Achten Sie darauf, dass alle erforderlichen Daten vorhanden sind
                    if 'steam_id_64' in ban_data and 'player' in ban_data and 'reason' in ban_data and 'by' in ban_data:
                        if api_client.do_temp_ban(ban_data['player'], ban_data['steam_id_64'], 24, ban_data['reason'], ban_data['by']):
                            logging.info(f"Tempban erfolgreich für Steam ID: {ban_data['steam_id_64']}")
                        else:
                            logging.error(f"Tempban-Vorgang fehlgeschlagen für Steam ID: {ban_data['steam_id_64']}")
                    else:
                        logging.error("Not all required data fields are available in the tempban data")
                        await message.nack(requeue=False)  # Nack without requeue if data is missing

                except json.JSONDecodeError:
                    logging.error("Fehler beim Parsen der JSON-Daten")
                    await message.nack(requeue=True)
                except Exception as e:
                    logging.error(f"Unerwarteter Fehler beim Verarbeiten der Nachricht: {e}")
                    await message.nack(requeue=True)

async def main():
    # Stellen Sie sicher, dass die API Clients korrekt initialisiert sind
    api_client = api_clients[0]  # oder einen spezifischen Client auswählen
    try:
        ban_connection, ban_channel, ban_queue = await connect_to_rabbitmq()
        unban_connection, unban_channel, unban_queue = await connect_to_unban_rabbitmq()
        tempban_connection, tempban_channel, tempban_queue = await connect_to_tempban_rabbitmq()

        # Starten Sie die Verarbeitungsaufgaben
        task_consume_ban = asyncio.create_task(consume_messages(ban_connection, ban_channel, ban_queue, api_client))
        task_consume_unban = asyncio.create_task(consume_unban_messages(unban_connection, unban_channel, unban_queue, api_client))
        task_consume_tempban = asyncio.create_task(consume_tempban_messages(tempban_connection, tempban_channel, tempban_queue, api_client))

        await asyncio.gather(task_consume_ban, task_consume_unban, task_consume_tempban)
    finally:
        # Verbindungen schließen
        if ban_connection:
            await ban_connection.close()
        if unban_connection:
            await unban_connection.close()
        if tempban_connection:
            await tempban_connection.close()

if __name__ == '__main__':
    asyncio.run(main())


