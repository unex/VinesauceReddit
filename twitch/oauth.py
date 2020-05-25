import requests

from typing import List, Text

class TwitchOAuth:
    def __init__(self, client_id: Text, client_secret: Text, scope: List[Text]):
        req = requests.post('https://id.twitch.tv/oauth2/token', data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'client_credentials',
            'scope': ' '.join(scope)
        })

        self.access_token = req.json()['access_token']
