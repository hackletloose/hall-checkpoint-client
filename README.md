# [HaLL] Checkpoint – Ban-Client für Hack Let Loose
Dieses Skript ist Teil des "Hack Let Loose"-Systems, das darauf ausgelegt ist, die Durchsetzung von Bans auf verschiedenen verbundenen Servern von "Hell Let Loose" zu automatisieren. Es empfängt Ban-Informationen, die durch das "Hack Let Loose"-Netzwerk geteilt werden, und führt diese auf dem lokalen Server aus.

## Voraussetzungen
Bevor du den Ban-Client installierst, stelle sicher, dass du folgende Voraussetzungen erfüllt hast:
- Python 3.8 oder höher
- `aiohttp` und `aio_pika` Bibliotheken
- `python-dotenv` Bibliothek

Diese Abhängigkeiten kannst du über pip installieren:\
`pip install -r requirements.txt`

## Installation
1. Gehe an den Ort auf deinem Server, an dem der Checkpoint Client in Zukunft ausgeführt werden soll.
1. Klone dieses Repository oder lade die neueste Version des Skripts direkt herunter.\
   `git clone https://github.com/hackletloose/hall-checkpoint-client.git`
1. Konfiguriere deine Umgebungsvariablen entsprechend der `.env.dist` Datei. Benenne diese Datei in `.env` um und fülle sie mit deinen spezifischen Daten aus:
   - `API_BASE_URLS`: Die URLs der APIs, die Ban-Befehle empfangen.
   - `BEARER_TOKEN`: Authentifizierungsdaten für die APIs.
   - `RABBITMQ_USER`, `RABBITMQ_PASS`, `RABBITMQ_HOST`, `RABBITMQ_PORT`: Konfigurationsdaten für deine RabbitMQ-Verbindung.

## Ausführung
Um das Skript manuell zu starten, führe folgenden Befehl im Terminal aus:\
`python3 checkpoint.py`

## Dauerhafte Ausführung über systemd
Um den Ban-Client dauerhaft auf deinem Server laufen zu lassen, kannst du einen systemd Service erstellen:

1. Kopiere die systemd Service-Datei:\
   `sudo cp ./checkpoint.service.dist /etc/systemd/system/checkpoint.service`
1. Ersetze `<dein-benutzername>` und `/pfad/zu/deinem/hall-checkpoint-client` durch deine tatsächlichen Benutzer- und Pfadangaben.
1. Aktiviere und starte den Service:\
   `sudo systemctl enable checkpoint.service`\
   `sudo systemctl start checkpoint.service`
1. Überprüfe den Status des Services:\
   `sudo systemctl status checkpoint.service`

## Support
Bei Fragen oder Problemen mit der Installation oder Konfiguration kontaktiere uns bitte über unser [Discord](https://discord.gg/hackletloose)!
