# Importing necessary libraries
import requests
import os
from dotenv import load_dotenv

class APIClient:
    def __init__(self, base_url, api_token):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Connection": "keep-alive",
            "Content-Type": "application/json"
        })

    def login(self, username, password):
        url = f'{self.base_url}/api/login'
        data = {'username': username, 'password': password}
        response = self.session.post(url, json=data)
        if response.status_code != 200:
            return False
        return True

    def is_logged_in(self):
        check_url = f"{self.base_url}/api/is_logged_in"
        response = self.session.get(check_url)
        return response.json().get('result', False)


    def do_perma_ban(self, player, steam_id_64, reason, by):
        ban_url = f"{self.base_url}/api/do_perma_ban"
        payload = {
            'player': player,
            'steam_id_64': steam_id_64,
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

    def do_temp_ban(self, player, steam_id_64, duration_hours, reason, by):
        temp_ban_url = f"{self.base_url}/api/do_temp_ban"
        payload = {
            'player': player,
            'steam_id_64': steam_id_64,
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



    def do_unban(self, steam_id):
        unban_url = f"{self.base_url}/api/do_unban"
        response = self.session.post(unban_url, json={'steam_id_64': steam_id})
        return response.ok
