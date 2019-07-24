import os
import re
import praw
import json
import requests
import twitch
from datetime import datetime as dt, timedelta
from derw import log

TWITCH_ID = os.environ.get("TWITCH_ID")
WIDGET_ID = os.environ.get("WIDGET_ID")

SUBREDDIT = "Vinesauce"
TEAM_URL = 'http://vinesauce.com/twitch/team-data.json'

team = None
ttv = twitch.Helix(TWITCH_ID, use_cache=True, cache_duration=timedelta(minutes=10))
reddit = praw.Reddit('BonziBot', user_agent='Vinesauce Twitch.tv monitor /u/RenegadeAI')
now = dt.utcnow()

log.debug('Logged in as {}'.format(reddit.user.me()))

class Stream(object):
    def __init__(self, user):
        self.id = user.id
        self.display_name = user.display_name
        self.login = user.login
        self.is_live = user.is_live
        # self.title = ""
        self.game = ""

        if user.is_live:
            self.type = user.stream.type
            # self.title = user.stream.title
            self.viewer_count = user.stream.viewer_count
            self.started_at = user.stream.started_at
            self.game = ttv.game(id=user.stream.game_id).name

        else:
            # This is still the only way to get hosts I guess
            r = requests.get(f'http://tmi.twitch.tv/hosts?client_id={TWITCH_ID}&include_logins=1&host={self.id}')
            if r.status_code == 200:
                host = r.json().get('hosts')[0]
                if host.get('target_id'):
                    self.type = 'hosting'
                    self.game = f'Hosting {host.get("target_display_name")}'
                    self.host_target = host.get("target_display_name")

                    return

            self.type = "offline"
            if user.login in team:
                # self.title = team[user.login]["channel"]["status"]
                self.game = team[user.login]["channel"]["game"]

    def render_sidebar(self):
        if self.type == "live":
            status = f'{self.display_name} playing {self.game}'
        elif self.type == "hosting":
            status = f'{self.display_name} is now hosting {self.host_target}'
        else:
            status = f'{self.display_name} last seen playing {self.game}'

        return f'>* [{status.upper()}](#{self.type})[](https://twitch.tv/{self.login})\n'

    def render_widget(self):
        status = f'{self.viewer_count}' if self.is_live else self.type

        return f'* [](#{self.type})[**~~{self.display_name}*{status}*~~{self.game.strip()}**](https://twitch.tv/{self.login})\n'

def get_team():
    log.debug('Checking for team updates...')

    try:
        req = requests.get(TEAM_URL)

        team = req.json()

        with open("./team.json", "w") as file:
            json.dump(team, file)

        return team

    except Exception as e:
        log.error('Error updating team: {}'.format(e))

        with open("./team.json") as file:
            return json.load(file)

def get_streams(team):
    log.debug('Fetching streams...')

    ids = [v["channel"]["_id"] for k, v in team.items()]
    streams = []

    for user in ttv.users(ids):
        stream = Stream(user)
        streams.append(stream)

    return streams


def update_widget(streams):
    widget = reddit.subreddit(SUBREDDIT).widgets.items[WIDGET_ID]
    content = ""

    for stream in streams:
        content += stream.render_widget()

    content += f'\n\n`LAST UPDATED @ {now.strftime("%X")} {now.strftime("%x")} UTC`'

    widget.mod.update(text=content, height=24 + len(streams)*50)

    log.debug('updated widget')

def update_sidebar(streams):
    any_live = False
    first_offline = True
    content = ""

    for stream in streams:
        if stream.type == "live": any_live = True
        if stream.type == "offline" and first_offline:
            content += ">* **[](#separator)**\n"
            first_offline = False

        content += stream.render_sidebar()

    content_header = "> ###CLICK A CHANNEL TO START WATCHING!\n" if any_live else "> ###TEAM IS OFFLINE\n"

    content = content_header + content

    content += f"* `LAST UPDATED\n@ {now.strftime('%X')}\n{now.strftime('%x')} UTC`\n"

    subreddit = reddit.subreddit(SUBREDDIT)
    settings = subreddit.mod.settings()
    sidebar = settings['description']

    # Remove text currently between the markers
    sidebar = re.sub(r'(\[\]\(#BOT_STREAMS\)).*(\[\]\(/BOT_STREAMS\))',
                    '\\1\\2',
                    sidebar,
                    flags=re.DOTALL)

    # Place new text between the markers
    opening_marker = "[](#BOT_STREAMS)"
    if content:
        try:
            marker_pos = sidebar.index(opening_marker) + len(opening_marker)
            sidebar = sidebar[:marker_pos] + f'\n\n{content}\n' + sidebar[marker_pos:]

            subreddit.mod.update(description=sidebar)

        except ValueError:
            # Substring not found
            log.critical(f'No streams marker found for /r/{SUBREDDIT}')

    log.debug('updated sidebar')

if __name__ == '__main__':
    team = get_team()

    streams = get_streams(team)

    sort = []
    for state in ["live", "hosting", "offline"]:
        for stream in streams:
            if stream.type == state:
                sort.append(stream)

    update_widget(sort)
    update_sidebar(sort)
