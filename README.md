# Ban-Client für Hack Let Loose

## Überblick
Dieses Skript ist Teil des "Hack Let Loose"-Systems, das darauf ausgelegt ist, die Durchsetzung von Bans auf verschiedenen verbundenen Servern von "Hell Let Loose" zu automatisieren. Es empfängt Ban-Informationen, die durch das "Hack Let Loose"-Netzwerk geteilt werden, und führt diese auf dem lokalen Server aus.

## Voraussetzungen
Bevor du den Ban-Client installierst, stelle sicher, dass du folgende Voraussetzungen erfüllt hast:
- Python 3.8 oder höher
- `aiohttp` und `aio_pika` Bibliotheken
- `python-dotenv` Bibliothek

Diese Abhängigkeiten kannst du über pip installieren:
```bash
pip install aiohttp aio_pika python-dotenv
```

## Installation
1. Klone dieses Repository oder lade die neueste Version des Skripts direkt herunter.
2. Platziere die `ban-client.py` Datei auf deinem Server, wo sie ausgeführt werden soll.
3. Konfiguriere deine Umgebungsvariablen entsprechend der `example.env` Datei. Benenne diese Datei in `.env` um und fülle sie mit deinen spezifischen Daten aus:
   - `API_BASE_URLS`: Die URLs der APIs, die Ban-Befehle empfangen.
   - `BEARER_TOKEN`, `API_USER`, `API_PASS`: Authentifizierungsdaten für die APIs.
   - `RABBITMQ_USER`, `RABBITMQ_PASS`, `RABBITMQ_HOST`, `RABBITMQ_PORT`: Konfigurationsdaten für deine RabbitMQ-Verbindung.

## Ausführung
Um das Skript manuell zu starten, führe folgenden Befehl im Terminal aus:
```bash
python3 ban-client.py
```

## Dauerhafte Ausführung über systemd
Um den Ban-Client dauerhaft auf deinem Server laufen zu lassen, kannst du einen systemd Service erstellen:

1. Erstelle eine neue systemd Service-Datei:
```bash
sudo nano /etc/systemd/system/ban-client.service
```

2. Füge folgenden Inhalt hinzu:
```ini
[Unit]
Description=Ban Client Service for Hack Let Loose
After=network.target

[Service]
User=<dein-benutzername>
WorkingDirectory=/pfad/zu/deinem/ban-client
ExecStart=/usr/bin/python3 /pfad/zu/deinem/ban-client/ban-client.py
Restart=always

[Install]
WantedBy=multi-user.target
```
Ersetze `<dein-benutzername>` und `/pfad/zu/deinem/ban-client` durch deine tatsächlichen Benutzer- und Pfadangaben.

3. Aktiviere und starte den Service:
```bash
sudo systemctl enable ban-client.service
sudo systemctl start ban-client.service
```

4. Überprüfe den Status des Services:
```bash
sudo systemctl status ban-client.service
```

## Support
Bei Fragen oder Problemen mit der Installation oder Konfiguration kontaktiere uns bitte über unser Discord!