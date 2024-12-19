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
CLIENT_ID = os.getenv('CLIENT_ID')
RABBITMQ_USER = os.getenv('RABBITMQ_USER')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', '5672'))


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
    try:
        async with connection, aiohttp.ClientSession() as session:
            async for message in queue:
                async with message.process():
                    logging.info(f"Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
                    ban_data = json.loads(message.body.decode())
                    logging.info(f"Empfangene Ban-Daten: {ban_data}")

                    player_name = ban_data.get('player_name', ban_data.get('player'))
                    player_id = ban_data.get('player_id', ban_data.get('steam_id_64'))

                    if not player_name:
                        logging.error(f"Fehlendes 'player_name' in den Ban-Daten: {ban_data}")
                        raise ValueError("player_name fehlt")
                    if not player_id:
                        logging.error(f"Fehlendes 'player_id' in den Ban-Daten: {ban_data}")
                        raise ValueError("player_id fehlt")

                    for api_client in api_clients:
                        steam_id = player_id
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

    except asyncio.CancelledError:
        logging.info("Task consume_messages wurde abgebrochen.")
    except Exception as e:
        logging.error(f"Unerwarteter Fehler in consume_messages: {e}")

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
    try:
        async with connection, aiohttp.ClientSession() as session:
            async for message in queue:
                async with message.process():
                    logging.info(f"Unban-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
                    unban_data = json.loads(message.body.decode())
                    logging.info(f"Empfangene Unban-Daten: {unban_data}")

                    player_name = unban_data.get('player_name', unban_data.get('player'))
                    player_id = unban_data.get('player_id', unban_data.get('steam_id_64'))

                    if not player_name or not player_id:
                        logging.error(f"Fehlende Daten in Unban-Daten: {unban_data}")
                        raise ValueError("Unban Daten unvollständig")

                    for api_client in api_clients:
                        if api_client.do_unban(player_id):
                            logging.info(f"Unban erfolgreich für Player ID: {player_id}")
                        else:
                            logging.error(f"Unban-Vorgang fehlgeschlagen für Player ID: {player_id}")

                        logging.info(f"Versuche, den Spieler von der Blacklist zu entfernen: Player ID: {player_id}")
                        if api_client.unblacklist_player(player_id):
                            logging.info(f"Spieler erfolgreich von der Blacklist entfernt: Player ID: {player_id}")
                        else:
                            logging.error(f"Unblacklist-Vorgang fehlgeschlagen für Player ID: {player_id}")

    except asyncio.CancelledError:
        logging.info("Task consume_unban_messages wurde abgebrochen.")
    except Exception as e:
        logging.error(f"Unerwarteter Fehler in consume_unban_messages: {e}")

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
        raise

async def consume_tempban_messages(connection, channel, queue, api_clients):
    logging.info("Beginne mit dem Empfang von Tempban-Nachrichten...")
    try:
        async with connection, aiohttp.ClientSession() as session:
            async for message in queue:
                async with message.process():
                    logging.info(f"Tempban-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
                    ban_data = json.loads(message.body.decode())
                    logging.info(f"Empfangene Tempban-Daten: {ban_data}")

                    player_name = ban_data.get('player_name') or ban_data.get('player')
                    player_id = ban_data.get('player_id') or ban_data.get('steam_id_64')

                    if not player_name or not player_id:
                        logging.error(f"Fehlende Daten in Tempban-Daten: {ban_data}")
                        raise ValueError("Tempban Daten unvollständig")

                    for api_client in api_clients:
                        duration_hours = ban_data.get('duration_hours', 24)

                        if api_client.do_temp_ban(player_name, player_id, duration_hours, ban_data['reason'], ban_data['by']):
                            logging.info(f"Tempban erfolgreich für Steam ID: {player_id}")
                        else:
                            logging.error(f"Tempban-Vorgang fehlgeschlagen für Steam ID: {player_id}")

    except asyncio.CancelledError:
        logging.info("Task consume_tempban_messages wurde abgebrochen.")
    except Exception as e:
        logging.error(f"Unerwarteter Fehler in consume_tempban_messages: {e}")

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
    try:
        async with connection, aiohttp.ClientSession() as session:
            async for message in queue:
                async with message.process():
                    logging.info(f"Watchlist-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
                    watchlist_data = json.loads(message.body.decode())
                    logging.info(f"Empfangene Watchlist-Daten: {watchlist_data}")

                    processed = False

                    for api_client in api_clients:
                        player_name = None
                        player_id = None
                        version = api_client.api_version
                        # Für v10 und höher player_name / player_id
                        # Für darunter player / steam_id_64
                        if version.startswith("v10"):
                            player_name = watchlist_data.get('player_name')
                            player_id = watchlist_data.get('player_id')
                        else:
                            player_name = watchlist_data.get('player')
                            player_id = watchlist_data.get('steam_id_64')

                        if not player_id or not player_name:
                            logging.error(f"Fehlende erforderliche Datenfelder in den Watchlist-Daten: {watchlist_data}")
                            raise ValueError("Watchlist Daten unvollständig")

                        if api_client.do_watch_player(player_name, player_id, watchlist_data['reason'], watchlist_data['by']):
                            logging.info(f"Spieler erfolgreich zur Watchlist hinzugefügt: {player_id}")
                            processed = True
                        else:
                            logging.error(f"Fehler beim Hinzufügen zur Watchlist für Player ID: {player_id}")
                            raise RuntimeError("Fehler beim Watchlist-Hinzufügen")

                    if not processed:
                        raise RuntimeError("Nachricht konnte nicht verarbeitet werden")

    except asyncio.CancelledError:
        logging.info("Task consume_watchlist_messages wurde abgebrochen.")
    except Exception as e:
        logging.error(f"Unerwarteter Fehler in consume_watchlist_messages: {e}")

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
    try:
        async with connection, aiohttp.ClientSession() as session:
            async for message in queue:
                async with message.process():
                    logging.info(f"Unwatch-Nachricht empfangen, beginne Verarbeitung: {message.body.decode()[:100]}")
                    unwatch_data = json.loads(message.body.decode())
                    logging.info(f"Empfangene Unwatch-Daten: {unwatch_data}")

                    player_name = unwatch_data.get('player_name', unwatch_data.get('player'))
                    player_id = unwatch_data.get('player_id', unwatch_data.get('steam_id_64'))

                    if not player_name or not player_id:
                        logging.error(f"Fehlende Daten in Unwatch-Daten: {unwatch_data}")
                        raise ValueError("Unwatch Daten unvollständig")

                    for api_client in api_clients:
                        if api_client.do_unwatch_player(player_name, player_id):
                            logging.info(f"Spieler erfolgreich von der Watchlist entfernt: {player_id}")
                        else:
                            logging.error(f"Fehler beim Entfernen von der Watchlist für Player ID: {player_id}")
                            raise RuntimeError("Fehler beim Unwatch")

    except asyncio.CancelledError:
        logging.info("Task consume_unwatch_messages wurde abgebrochen.")
    except Exception as e:
        logging.error(f"Unerwarteter Fehler in consume_unwatch_messages: {e}")

async def main():
    api_clients = [APIClient(url.strip(), API_TOKEN, CLIENT_ID) for url in BASE_URLS if url.strip()]

    try:
        ban_connection, ban_channel, ban_queue = await connect_to_rabbitmq(CLIENT_ID)
        unban_connection, unban_channel, unban_queue = await connect_to_unban_rabbitmq(CLIENT_ID)
        tempban_connection, tempban_channel, tempban_queue = await connect_to_tempban_rabbitmq(CLIENT_ID)
        watchlist_connection, watchlist_channel, watchlist_queue = await connect_to_watchlist_rabbitmq(CLIENT_ID)
        unwatch_connection, unwatch_channel, unwatch_queue = await connect_to_unwatch_rabbitmq(CLIENT_ID)

        task_consume_ban = asyncio.create_task(consume_messages(ban_connection, ban_channel, ban_queue, api_clients))
        task_consume_unban = asyncio.create_task(consume_unban_messages(unban_connection, unban_channel, unban_queue, api_clients))
        task_consume_tempban = asyncio.create_task(consume_tempban_messages(tempban_connection, tempban_channel, tempban_queue, api_clients))
        task_consume_watchlist = asyncio.create_task(consume_watchlist_messages(watchlist_connection, watchlist_channel, watchlist_queue, api_clients))
        task_consume_unwatch = asyncio.create_task(consume_unwatch_messages(unwatch_connection, unwatch_channel, unwatch_queue, api_clients))

        tasks = [
            task_consume_ban,
            task_consume_unban,
            task_consume_tempban,
            task_consume_watchlist,
            task_consume_unwatch
        ]

        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt erhalten, beende das Programm...")
        tasks = [
            task_consume_ban,
            task_consume_unban,
            task_consume_tempban,
            task_consume_watchlist,
            task_consume_unwatch
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        logging.info("Schließe Verbindungen...")
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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Programm wurde durch KeyboardInterrupt beendet.")
