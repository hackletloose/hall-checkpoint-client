import asyncio
import logging
import os
import json
from api_manager import APIClient
from dotenv import load_dotenv
import aio_pika
from aio_pika import connect_robust, ExchangeType
import aiohttp
import datetime

# Konfigurieren des Loggings
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler('app.log'),
                        logging.StreamHandler()
                    ])

# Umgebungsvariablen laden
load_dotenv()
BASE_URLS = os.getenv('API_BASE_URLS').split(',')
API_TOKEN = os.getenv('BEARER_TOKEN')
YOUR_CLIENT_ID = os.getenv('CLIENT_ID')
RABBITMQ_USER = os.getenv('RABBITMQ_USER')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', '5672'))

# API-Client-Instanzen erstellen
api_clients = [APIClient(url.strip(), API_TOKEN) for url in BASE_URLS if url.strip()]

# Authentifizierung bei den API-Clients
for api_client in api_clients:
    version = api_client.version()
    if version == "":
        logging.warning("Konnte Version vom Community RCon nicht ermitteln.")
    else:
        logging.info(f"CRCon version for {api_client.base_url}: {version}")
        api_client.api_version = version.get('version', 'unknown')

async def get_api_version(api_client):
    return api_client.api_version

async def report_api_version(client_id, version):
    url = "https://api.1bv.eu/update_client_version"
    timestamp = datetime.datetime.utcnow().isoformat()
    data = {
        'client_id': client_id,
        'api_version': version,
        'timestamp': timestamp
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            if response.status == 200:
                logging.info(f"API-Version {version} erfolgreich gemeldet für Client {client_id} mit Timestamp {timestamp}")
            else:
                logging.error(f"Fehler beim Melden der API-Version {version} für Client {client_id} mit Timestamp {timestamp}")

async def connect_to_rabbitmq(client_id):
    logging.info(f"Versuche, eine Verbindung zu RabbitMQ herzustellen für Client {client_id}...")
    connection = await aio_pika.connect_robust(
        f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/",
        loop=asyncio.get_running_loop(),
        heartbeat=600,
        client_properties={'connection_name': f'my_connection_{client_id}'}
    )
    channel = await connection.channel()
    queue_name = f'bans_queue_{client_id}'
    queue = await channel.declare_queue(queue_name, durable=True)
    logging.info(f"RabbitMQ Queue {queue_name} deklariert und gebunden.")
    return connection, channel, queue

async def consume_messages(connection, channel, queue, api_clients):
    logging.info("Beginne mit dem Empfang von Nachrichten...")
    async with connection, aiohttp.ClientSession() as session:
        async for message in queue:
            logging.info(f"Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
            try:
                ban_data = json.loads(message.body.decode())
                logging.info(f"Empfangene Ban-Daten: {ban_data}")

                player_name = ban_data.get('player_name', ban_data.get('player'))
                player_id = ban_data.get('player_id', ban_data.get('steam_id_64'))

                # Überprüfen auf fehlende oder ungültige Daten
                if not player_name:
                    logging.error(f"Fehlendes 'player_name' in den Ban-Daten: {ban_data}")
                    await message.nack(requeue=False)
                    continue
                if not player_id:
                    logging.error(f"Fehlendes 'player_id' in den Ban-Daten: {ban_data}")
                    await message.nack(requeue=False)
                    continue
                
                # Verarbeite den Bann für jeden API-Client
                for api_client in api_clients:
                    version = api_client.api_version
                    steam_id = player_id  # In allen Versionen wird jetzt die korrekte steam_id verwendet

                    # Permanent-Ban durchführen
                    if api_client.do_perma_ban(player_name, steam_id, ban_data['reason'], ban_data['by']):
                        logging.info(f"Permanent-Bann erfolgreich für Steam ID: {steam_id}")
                    else:
                        logging.error(f"Permanent-Bann fehlgeschlagen für Steam ID: {steam_id}")

                    # Kommentar posten
                    comment_message = f"Ban Detail: https://hackletloose.eu/ban_detail.php?steam_id={steam_id}"
                    if api_client.post_player_comment(steam_id, comment_message):
                        logging.info(f"Erfolgreich Kommentar gepostet für Steam ID: {steam_id}")
                    else:
                        logging.error(f"Fehler beim Posten des Kommentars für Steam ID: {steam_id}. Kommentar: {comment_message}")

                    # Spieler auf die Blacklist setzen
                    if api_client.do_blacklist_player(steam_id, player_name, ban_data['reason'], ban_data['by']):
                        logging.info(f"Spieler erfolgreich auf die Blacklist gesetzt: {steam_id}")
                    else:
                        logging.error(f"Fehler beim Setzen auf die Blacklist für Steam ID: {steam_id}")

                await message.ack()
            except json.JSONDecodeError:
                logging.error("Fehler beim Parsen der JSON-Daten")
                await message.nack(requeue=False)
            except Exception as e:
                logging.error(f"Unerwarteter Fehler beim Verarbeiten der Nachricht: {e}")
                await message.nack(requeue=False)

async def connect_to_unban_rabbitmq(client_id):
    logging.info(f"Versuche, eine Verbindung zu RabbitMQ für Unban-Nachrichten herzustellen für Client {client_id}...")
    unban_connection = await aio_pika.connect_robust(
        f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/",
        loop=asyncio.get_running_loop(),
        heartbeat=600,
        client_properties={'connection_name': f'unban_connection_{client_id}'}
    )
    unban_channel = await unban_connection.channel()
    queue_name = f'unbans_queue_{client_id}'
    unban_queue = await unban_channel.declare_queue(queue_name, durable=True)
    logging.info(f"RabbitMQ Queue {queue_name} deklariert und gebunden.")
    return unban_connection, unban_channel, unban_queue

async def consume_unban_messages(connection, channel, queue, api_clients):
    logging.info("Beginne mit dem Empfang von Unban-Nachrichten...")
    async with connection, aiohttp.ClientSession() as session:
        async for message in queue:
            logging.info(f"Unban-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
            try:
                unban_data = json.loads(message.body.decode())
                logging.info(f"Empfangene Unban-Daten: {unban_data}")
                
                player_name = unban_data.get('player_name', unban_data.get('player'))
                player_id = unban_data.get('player_id', unban_data.get('steam_id_64'))

                if not player_name:
                    logging.error(f"Fehlendes 'player_name' in den Unban-Daten: {unban_data}")
                if not player_id:
                    logging.error(f"Fehlendes 'player_id' in den Unban-Daten: {unban_data}")
                if not player_name or not player_id:
                    await message.nack(requeue=True)
                    continue

                for api_client in api_clients:
                    version = api_client.api_version
                    logging.info(f"Verarbeite Unban für API-Client: {api_client.base_url}")
                    
                    if api_client.do_unban(player_id):
                        logging.info(f"Unban erfolgreich für Player ID: {player_id}")
                    else:
                        logging.error(f"Unban-Vorgang fehlgeschlagen für Player ID: {player_id}")

                    logging.info(f"Versuche, den Spieler von der Blacklist zu entfernen: Player ID: {player_id}")
                    if api_client.unblacklist_player(player_id):
                        logging.info(f"Spieler erfolgreich von der Blacklist entfernt: Player ID: {player_id}")
                    else:
                        logging.error(f"Unblacklist-Vorgang fehlgeschlagen für Player ID: {player_id}")
                await message.ack()
            except json.JSONDecodeError:
                logging.error("Fehler beim Parsen der JSON-Daten")
                await message.nack(requeue=True)
            except Exception as e:
                logging.error(f"Unerwarteter Fehler beim Verarbeiten der Nachricht: {e}")
                await message.nack(requeue=True)

async def connect_to_tempban_rabbitmq(client_id):
    try:
        logging.info(f"Versuche, eine Verbindung zu RabbitMQ für Tempban-Nachrichten herzustellen für Client {client_id}...")
        
        tempban_connection = await aio_pika.connect_robust(
            f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/",
            loop=asyncio.get_running_loop(),
            heartbeat=600,
            client_properties={'connection_name': f'tempban_connection_{client_id}'}
        )
        
        tempban_channel = await tempban_connection.channel()
        exchange_name = f'tempbans_fanout_{client_id}'
        
        tempban_exchange = await tempban_channel.declare_exchange(exchange_name, ExchangeType.FANOUT, durable=True)
        queue_name = f'tempbans_queue_{client_id}'
        tempban_queue = await tempban_channel.declare_queue(queue_name, durable=True)
        
        await tempban_queue.bind(tempban_exchange, routing_key='')
        logging.info(f"RabbitMQ Queue {queue_name} deklariert und gebunden.")
        
        return tempban_connection, tempban_channel, tempban_queue
    
    except Exception as e:
        logging.error(f"Fehler beim Verbinden mit RabbitMQ für Tempban-Nachrichten: {e}")
        raise  # Optional: Weiterleiten des Fehlers oder Versuch eines erneuten Verbindungsaufbaus

async def consume_tempban_messages(connection, channel, queue, api_clients):
    logging.info("Beginne mit dem Empfang von Tempban-Nachrichten...")
    async with connection, aiohttp.ClientSession() as session:
        async for message in queue:
            logging.info(f"Tempban-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
            async with message.process():
                try:
                    ban_data = json.loads(message.body.decode())
                    logging.info(f"Empfangene Tempban-Daten: {ban_data}")
                    
                    # Dynamische Zuordnung von player_id und player_name basierend auf der API-Version
                    player_name = ban_data.get('player_name') or ban_data.get('player')
                    player_id = ban_data.get('player_id') or ban_data.get('steam_id_64')

                    if not player_name:
                        logging.error(f"Fehlendes 'player_name' in den Tempban-Daten: {ban_data}")
                    if not player_id:
                        logging.error(f"Fehlendes 'player_id' in den Tempban-Daten: {ban_data}")
                    if not player_name or not player_id:
                        await message.nack(requeue=True)
                        continue

                    for api_client in api_clients:
                        version = api_client.api_version
                        duration_hours = ban_data.get('duration_hours', 24)  # Default to 24 hours if not provided
                        
                        if api_client.do_temp_ban(player_name, player_id, duration_hours, ban_data['reason'], ban_data['by']):
                            logging.info(f"Tempban erfolgreich für Steam ID: {player_id}")
                        else:
                            logging.error(f"Tempban-Vorgang fehlgeschlagen für Steam ID: {player_id}")
                except json.JSONDecodeError:
                    logging.error("Fehler beim Parsen der JSON-Daten")
                    await message.nack(requeue=True)
                except Exception as e:
                    logging.error(f"Unerwarteter Fehler beim Verarbeiten der Nachricht: {e}")
                    await message.nack(requeue=True)

async def connect_to_watchlist_rabbitmq(client_id):
    logging.info(f"Versuche, eine Verbindung zu RabbitMQ für Watchlist-Nachrichten herzustellen für Client {client_id}...")
    watchlist_connection = await aio_pika.connect_robust(
        f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/",
        loop=asyncio.get_running_loop(),
        heartbeat=600,
        client_properties={'connection_name': f'watchlist_connection_{client_id}'}
    )
    watchlist_channel = await watchlist_connection.channel()
    queue_name = f'watchlists_queue_{client_id}'
    watchlist_queue = await watchlist_channel.declare_queue(queue_name, durable=True)
    logging.info(f"RabbitMQ Queue {queue_name} deklariert und gebunden.")
    return watchlist_connection, watchlist_channel, watchlist_queue

async def consume_watchlist_messages(connection, channel, queue, api_clients):
    logging.info("Beginne mit dem Empfang von Watchlist-Nachrichten...")
    async with connection, aiohttp.ClientSession() as session:
        async for message in queue:
            logging.info(f"Watchlist-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
            try:
                watchlist_data = json.loads(message.body.decode())
                logging.info(f"Empfangene Watchlist-Daten: {watchlist_data}")

                processed = False  # Flag to track if the message has been processed

                # Iteriere über die API-Clients, um die Nachricht an den richtigen API-Client zu senden
                for api_client in api_clients:
                    version = api_client.api_version

                    if version.startswith("v10"):
                        # v10 API verwendet player_name und player_id
                        player_name = watchlist_data.get('player_name')
                        player_id = watchlist_data.get('player_id')
                    else:
                        # v9.x API verwendet player und steam_id_64
                        player_name = watchlist_data.get('player')
                        player_id = watchlist_data.get('steam_id_64')

                    # Überprüfung auf fehlende oder ungültige player_id
                    if not player_id:
                        logging.error(f"Fehlendes 'player_id' oder 'steam_id_64' in den Watchlist-Daten: {watchlist_data}")
                        break  # Verlassen der Schleife, um die Nachricht nicht weiter zu verarbeiten

                    # Überprüfung auf fehlende erforderliche Felder
                    if not player_name:
                        logging.error(f"Fehlende erforderliche Datenfelder in den Watchlist-Daten: {watchlist_data}")
                        break  # Verlassen der Schleife, um die Nachricht nicht weiter zu verarbeiten

                    # Call the appropriate API method based on the client version
                    if api_client.do_watch_player(player_name, player_id, watchlist_data['reason'], watchlist_data['by']):
                        logging.info(f"Spieler erfolgreich zur Watchlist hinzugefügt: {player_id}")
                        processed = True
                    else:
                        logging.error(f"Fehler beim Hinzufügen zur Watchlist für Player ID: {player_id}")
                        break  # Nachricht nicht weiterverarbeiten

                if processed:
                    await message.ack()
                else:
                    await message.nack(requeue=False)

            except json.JSONDecodeError:
                logging.error("Fehler beim Parsen der JSON-Daten")
                try:
                    await message.nack(requeue=True)
                except aio_pika.exceptions.MessageProcessError:
                    logging.error("Nachricht konnte nicht zurückgestellt werden, da sie bereits verarbeitet wurde.")

            except Exception as e:
                logging.error(f"Unerwarteter Fehler beim Verarbeiten der Nachricht: {e}")
                try:
                    await message.nack(requeue=True)
                except aio_pika.exceptions.MessageProcessError:
                    logging.error("Nachricht konnte nicht zurückgestellt werden, da sie bereits verarbeitet wurde.")

async def connect_to_unwatch_rabbitmq(client_id):
    logging.info(f"Versuche, eine Verbindung zu RabbitMQ für Unwatch-Nachrichten herzustellen für Client {client_id}...")
    unwatch_connection = await aio_pika.connect_robust(
        f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/",
        loop=asyncio.get_running_loop(),
        heartbeat=600,
        client_properties={'connection_name': f'unwatch_connection_{client_id}'}
    )
    unwatch_channel = await unwatch_connection.channel()
    queue_name = f'unwatch_queue_{client_id}'
    unwatch_queue = await unwatch_channel.declare_queue(queue_name, durable=True)
    logging.info(f"RabbitMQ Queue {queue_name} deklariert und gebunden.")
    return unwatch_connection, unwatch_channel, unwatch_queue

async def consume_unwatch_messages(connection, channel, queue, api_clients):
    logging.info("Beginne mit dem Empfang von Unwatch-Nachrichten...")
    async with connection, aiohttp.ClientSession() as session:
        async for message in queue:
            logging.info(f"Unwatch-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
            try:
                unwatch_data = json.loads(message.body.decode())
                logging.info(f"Empfangene Unwatch-Daten: {unwatch_data}")

                player_name = unwatch_data.get('player_name', unwatch_data.get('player'))
                player_id = unwatch_data.get('player_id', unwatch_data.get('steam_id_64'))

                if not player_name:
                    logging.error(f"Fehlendes 'player_name' in den Unwatch-Daten: {unwatch_data}")
                if not player_id:
                    logging.error(f"Fehlendes 'player_id' in den Unwatch-Daten: {unwatch_data}")
                if not player_name or not player_id:
                    logging.error(f"Fehlende erforderliche Datenfelder in den Unwatch-Daten: {unwatch_data}")
                    await message.nack(requeue(True))
                    continue

                for api_client in api_clients:
                    version = api_client.api_version

                    if api_client.do_unwatch_player(player_name, player_id):
                        logging.info(f"Spieler erfolgreich von der Watchlist entfernt: {player_id}")
                    else:
                        logging.error(f"Fehler beim Entfernen von der Watchlist für Player ID: {player_id}")
                await message.ack()
            except json.JSONDecodeError:
                logging.error("Fehler beim Parsen der JSON-Daten")
                await message.nack(requeue(True))
            except Exception as e:
                logging.error(f"Unerwarteter Fehler beim Verarbeiten der Nachricht: {e}")
                await message.nack(requeue(True))

async def main():
    api_client = api_clients[0]
    try:
        client_id = YOUR_CLIENT_ID
        version = await get_api_version(api_client)
        logging.info(f"API Version: {version}")

        # API-Version an den Server melden
        await report_api_version(client_id, version)

        # Restlicher Code zum Verbinden mit RabbitMQ und Verarbeiten von Nachrichten
        ban_connection, ban_channel, ban_queue = await connect_to_rabbitmq(client_id)
        unban_connection, unban_channel, unban_queue = await connect_to_unban_rabbitmq(client_id)
        tempban_connection, tempban_channel, tempban_queue = await connect_to_tempban_rabbitmq(client_id)
        watchlist_connection, watchlist_channel, watchlist_queue = await connect_to_watchlist_rabbitmq(client_id)
        unwatch_connection, unwatch_channel, unwatch_queue = await connect_to_unwatch_rabbitmq(client_id)

        task_consume_ban = asyncio.create_task(consume_messages(ban_connection, ban_channel, ban_queue, api_clients))
        task_consume_unban = asyncio.create_task(consume_unban_messages(unban_connection, unban_channel, unban_queue, api_clients))
        task_consume_tempban = asyncio.create_task(consume_tempban_messages(tempban_connection, tempban_channel, tempban_queue, api_clients))
        task_consume_watchlist = asyncio.create_task(consume_watchlist_messages(watchlist_connection, watchlist_channel, watchlist_queue, api_clients))
        task_consume_unwatch = asyncio.create_task(consume_unwatch_messages(unwatch_connection, unwatch_channel, unwatch_queue, api_clients))

        await asyncio.gather(task_consume_ban, task_consume_unban, task_consume_tempban, task_consume_watchlist, task_consume_unwatch)
    finally:
        if 'ban_connection' in locals() and ban_connection:
            await ban_connection.close()
        if 'unban_connection' in locals() and unban_connection:
            await unban_connection.close()
        if 'tempban_connection' in locals() and tempban_connection:
            await tempban_connection.close()
        if 'watchlist_connection' in locals() and watchlist_connection:
            await watchlist_connection.close()
        if 'unwatch_connection' in locals() and unwatch_connection:
            await unwatch_connection.close()

if __name__ == '__main__':
    asyncio.run(main())
