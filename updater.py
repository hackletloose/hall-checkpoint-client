import os
import sys
import zipfile
import io
import aiohttp
import asyncio
import logging
import shutil
import subprocess

from packaging import version  # Für robuste Versionsvergleiche

# Konfigurieren des Loggings
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler('updater.log'),
                        logging.StreamHandler()
                    ])

GITHUB_API_URL = 'https://api.github.com/repos/hackletloose/hall-checkpoint-client/releases/latest'

async def download_update(zip_url, temp_dir):
    logging.info(f"Updater: Starte Download des Updates von {zip_url}...")
    async with aiohttp.ClientSession() as session:
        async with session.get(zip_url) as response:
            if response.status != 200:
                logging.error(f"Updater: Fehler beim Herunterladen des Updates: {response.status}")
                return False
            zip_content = await response.read()
    with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
        z.extractall(temp_dir)
    logging.info("Updater: Update-Archiv erfolgreich extrahiert.")
    return True

def replace_files(extracted_path, destination_dir):
    logging.info("Updater: Ersetze alte Dateien durch die neuen Dateien...")
    for root, dirs, files in os.walk(extracted_path):
        relative_path = os.path.relpath(root, extracted_path)
        dest_dir = os.path.join(destination_dir, relative_path)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        for file in files:
            source_file = os.path.join(root, file)
            dest_file = os.path.join(dest_dir, file)
            temp_dest_file = dest_file + ".tmp"
            logging.info(f"Updater: Kopiere Datei {file}...")
            shutil.copy2(source_file, temp_dest_file)
            shutil.move(temp_dest_file, dest_file)
    logging.info("Updater: Alle Dateien wurden erfolgreich ersetzt.")
    return True

def restart_main_script():
    logging.info("Updater: Starte das Hauptskript neu...")
    try:
        subprocess.Popen(['python', 'checkpoint.py'])
        logging.info("Updater: Hauptskript erfolgreich neu gestartet.")
    except Exception as e:
        logging.error(f"Updater: Fehler beim Neustarten des Hauptskripts: {e}")

async def main():
    try:
        # Abrufen der neuesten Version und des Zip-URL
        async with aiohttp.ClientSession() as session:
            async with session.get(GITHUB_API_URL) as response:
                if response.status != 200:
                    logging.error(f"Updater: Fehler beim Abrufen der GitHub-API: {response.status}")
                    return
                data = await response.json()
                latest_version = data.get('tag_name', '').lstrip('v')
                zip_url = data.get('zipball_url')
                if not latest_version or not zip_url:
                    logging.error("Updater: Konnte die neueste Version oder Zipball-URL nicht ermitteln.")
                    return

        # Feststellen der aktuellen Version aus dem Hauptskript
        current_dir = os.path.dirname(os.path.abspath(__file__))
        checkpoint_path = os.path.join(current_dir, 'checkpoint.py')
        if not os.path.exists(checkpoint_path):
            logging.error("Updater: Hauptskript checkpoint.py nicht gefunden.")
            return

        with open(checkpoint_path, 'r') as f:
            for line in f:
                if line.startswith('__version__'):
                    current_version = line.split('=')[1].strip().strip("'\"")
                    break
            else:
                logging.error("Updater: Aktuelle Version nicht in checkpoint.py gefunden.")
                return

        logging.info(f"Updater: Aktuelle Version: {current_version}, Neueste Version: {latest_version}")

        # Versionsvergleich
        if version.parse(latest_version) <= version.parse(current_version):
            logging.info("Updater: Keine neue Version verfügbar. Beende das Updater-Skript.")
            return

        # Temporäres Verzeichnis für das Update
        temp_dir = os.path.join(current_dir, 'temp_update')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Download und Extraktion des Updates
        success = await download_update(zip_url, temp_dir)
        if not success:
            return

        # Finden des extrahierten Verzeichnisses
        extracted_dirs = [name for name in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, name))]
        if not extracted_dirs:
            logging.error("Updater: Kein Verzeichnis im Update-Archiv gefunden.")
            return
        extracted_path = os.path.join(temp_dir, extracted_dirs[0])

        # Ersetzen der alten Dateien durch die neuen Dateien
        replace_files(extracted_path, current_dir)

        # Bereinigung des temporären Verzeichnisses
        shutil.rmtree(temp_dir)
        logging.info("Updater: Temporäres Verzeichnis bereinigt.")

        # Aktualisieren der Versionsvariable in checkpoint.py
        with open(checkpoint_path, 'r') as f:
            lines = f.readlines()
        with open(checkpoint_path, 'w') as f:
            for line in lines:
                if line.startswith('__version__'):
                    f.write(f"__version__ = '{latest_version}'\n")
                else:
                    f.write(line)
        logging.info("Updater: Versionsvariable in checkpoint.py aktualisiert.")

        # Neustarten des Hauptskripts
        restart_main_script()

    except Exception as e:
        logging.error(f"Updater: Unerwarteter Fehler: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Updater: Fehler beim Ausführen des Updater-Skripts: {e}")
