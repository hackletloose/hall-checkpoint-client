import requests
import os
from dotenv import load_dotenv
import datetime
import aiohttp
import logging

class APIClient:
    def __init__(self, base_url, api_token):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Connection": "keep-alive",
            "Content-Type": "application/json"
        })
        self.api_version = "unknown"

    def login(self, username, password):
        url = f'{self.base_url}/api/login'
        data = {'username': username, 'password': password}
        response = self.session.post(url, json=data)
        if response.status_code != 200:
            return None
        return response.json()
    
    def is_logged_in(self):
        check_url = f"{self.base_url}/api/is_logged_in"
        response = self.session.get(check_url)
        return response.json().get('result', False)

    def do_perma_ban(self, player_name, player_id, reason, by):
        if self.api_version.startswith("v10"):
            ban_url = f"{self.base_url}/api/perma_ban"
            payload = {
                'player_name': player_name,
                'player_id': player_id,
                'reason': reason,
                'by': by
            }
        else:
            ban_url = f"{self.base_url}/api/do_perma_ban"
            payload = {
                'player': player_name,
                'steam_id_64': player_id,
                'reason': reason,
                'by': by
            }
        try:
            response = self.session.post(ban_url, json=payload)
            print(f"do_perma_ban response: {response.status_code}, {response.text}")
            return response.ok
        except Exception as e:
            print(f"Fehler beim Aufrufen von do_perma_ban: {e}")
            return False

    def do_temp_ban(self, player_name, player_id, duration_hours, reason, by):
        if self.api_version.startswith("v10"):
            temp_ban_url = f"{self.base_url}/api/temp_ban"
            payload = {
                'player_name': player_name,
                'player_id': player_id,
                'duration_hours': duration_hours,
                'reason': reason,
                'by': by
            }
        else:
            temp_ban_url = f"{self.base_url}/api/do_temp_ban"
            payload = {
                'player': player_name,
                'steam_id_64': player_id,
                'duration_hours': duration_hours,
                'reason': reason,
                'by': by
            }
        try:
            response = self.session.post(temp_ban_url, json=payload)
            print(f"do_temp_ban response: {response.status_code}, {response.text}")
            return response.ok
        except Exception as e:
            print(f"Fehler beim Aufrufen von do_temp_ban: {e}")
            return False

    def do_unban(self, player_id):
        if self.api_version.startswith("v10"):
            unban_url = f"{self.base_url}/api/unban"
            payload = {'player_id': player_id}
        else:
            unban_url = f"{self.base_url}/api/do_unban"
            payload = {'steam_id_64': player_id}
        try:
            response = self.session.post(unban_url, json=payload)
            return response.ok
        except Exception as e:
            print(f"Fehler beim Aufrufen von do_unban: {e}")
            return False

    def unblacklist_player(self, player_id):
        unblacklist_url = f"{self.base_url}/api/unblacklist_player"
        payload = {'player_id': player_id}
        try:
            response = self.session.post(unblacklist_url, json=payload)
            return response.ok
        except Exception as e:
            print(f"Fehler beim Aufrufen von unblacklist_player: {e}")
            return False

    def do_blacklist_player(self, player_id, player_name, reason, by):
        if self.api_version.startswith("v10"):
            blacklist_url = f"{self.base_url}/api/add_blacklist_record"
            payload = {
                'player_id': player_id,
                'reason': reason,
                'admin_name': by,
                'blacklist_id': 0,  # Default blacklist
                'sync': 'kick_only',
                'servers': None
            }
        else:
            blacklist_url = f"{self.base_url}/api/blacklist_player"
            payload = {
                'steam_id_64': player_id,
                'name': player_name,
                'reason': reason,
                'by': by
            }
        try:
            response = self.session.post(blacklist_url, json=payload)
            print(f"do_blacklist_player response: {response.status_code}, {response.text}")
            if response.status_code == 200:
                response_data = response.json()
                if not response_data.get("failed", False):
                    return True
                else:
                    logging.error(f"Fehler beim Blacklisting: {response_data}")
                    return False
            return False
        except Exception as e:
            print(f"Fehler beim Aufrufen von do_blacklist_player: {e}")
            logging.error(f"Fehler beim Aufrufen von do_blacklist_player: {e}")
            return False


    def do_watch_player(self, player_name, player_id, reason, by):
        if self.api_version.startswith("v10"):
            watchlist_url = f"{self.base_url}/api/watch_player"
            payload = {
                'player_id': player_id,
                'reason': reason,
                'by': by,
                'player_name': player_name  # Hinzufügen des player_name Feldes
            }
        else:
            watchlist_url = f"{self.base_url}/api/do_watch_player"
            payload = {
                'player': player_name,
                'steam_id_64': player_id,
                'reason': reason
            }
        try:
            response = self.session.post(watchlist_url, json=payload)
            print(f"do_watch_player response: {response.status_code}, {response.text}")
            return response.ok
        except Exception as e:
            print(f"Fehler beim Aufrufen von do_watch_player: {e}")
            return False

    def do_unwatch_player(self, player_name, player_id):
        if self.api_version.startswith("v10"):
            unwatch_url = f"{self.base_url}/api/unwatch_player"
            payload = {
                'player_id': player_id,
                'player_name': player_name  # Hinzufügen des player_name Feldes
            }
        else:
            unwatch_url = f"{self.base_url}/api/do_unwatch_player"
            payload = {
                'player': player_name,
                'steam_id_64': player_id
            }
        try:
            response = self.session.post(unwatch_url, json=payload)
            print(f"do_unwatch_player response: {response.status_code}, {response.text}")
            return response.ok
        except Exception as e:
            print(f"Fehler beim Aufrufen von do_unwatch_player: {e}")
            return False

    def post_player_comment(self, player_id, comment):
        if self.api_version.startswith("v10"):
            post_comment_url = f"{self.base_url}/api/post_player_comment"
            payload = {
                'player_id': player_id,
                'comment': comment
            }
        else:
            post_comment_url = f"{self.base_url}/api/post_player_comment"
            payload = {
                'steam_id_64': player_id,
                'comment': comment
            }

        try:
            response = self.session.post(post_comment_url, json=payload)
            print(f"post_player_comment response: {response.status_code}, {response.text}")
            if response.status_code == 200:
                response_data = response.json()
                if not response_data.get("failed", True):
                    return True
                else:
                    print(f"Fehler in der API-Antwort: {response_data}")
                    return False
            return False
        except Exception as e:
            print(f"Fehler beim Aufrufen von post_player_comment: {e}")
            return False


    async def report_api_version(client_id, version):
        url = "https://api.1bv.eu/update_client_version"  # Überprüfen Sie diese URL
        data = {
            'client_id': client_id,
            'api_version': version
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                response_text = await response.text()
                if response.status == 200:
                    logging.info(f"API-Version {version} erfolgreich gemeldet für Client {client_id}")
                else:
                    logging.error(f"Fehler beim Melden der API-Version {version} für Client {client_id}")
                    logging.error(f"Antwort vom Server: {response_text}")

