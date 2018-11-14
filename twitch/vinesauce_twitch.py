import os, sys
import re
import praw
import time
import json
import requests
from dotenv import load_dotenv
from string import Template

try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),"../../utils")))
    from log import log

except:
    print('Could not load custom logging')
    import logging
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)

    log.addHandler(logging.StreamHandler(sys.stdout))

DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(DIR, '.env'))

TWITCH_ID = os.environ.get("TWITCH_ID")

SUBREDDITS = ['Vinesauce']
IGNORED_MEMBERS = ['kingky', 'hootey']
TEAM_URL = 'http://vinesauce.com/twitch/team-data.json'

USER_URL = "https://api.twitch.tv/kraken/channels/%s?client_id={}".format(TWITCH_ID)
STREAM_URL = "https://api.twitch.tv/kraken/streams/%s?client_id={}".format(TWITCH_ID)
HOST_URL = "http://tmi.twitch.tv/hosts?client_id={}&include_logins=1&host=%s".format(TWITCH_ID)

#Streamer template
TEMPLATE = '>* [$statustext](#$status)[](https://twitch.tv/$name)\n'

reddit = praw.Reddit('BonziBot', user_agent='Vinesauce Twitch.tv monitor /u/RenegadeAI')

class objdict(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        else:
            raise AttributeError("No such attribute: " + name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        if name in self:
            del self[name]
        else:
            raise AttributeError("No such attribute: " + name)

# log.debug('Logged in as {}'.format(reddit.user.me()))

def get_team():
    log.debug('Checking for team updates...')

    try:
        req = requests.get(TEAM_URL)

        team = req.json()

        with open(DIR + "team.json", "w") as file:
            json.dump(team, file)

        return team

    except Exception as e:
        log.error('Error updating team: {}'.format(e))

        with open(DIR + "team.json") as file:
            return json.load(file)

def decode_str(s): return bytes(s, "utf-8").decode("unicode_escape")

def render(team):
    template = Template(decode_str(TEMPLATE))

    STREAMING = ''
    HOSTING = ''
    OFFLINE = ''

    for name, member in team.items():
        if not name in IGNORED_MEMBERS:
            for i in range(3):
                try:
                    res = requests.get(STREAM_URL % member.get('channel').get('name'))
                    res.raise_for_status()

                    stream = res.json().get('stream')
                    if stream:
                        log.debug('{} is streaming'.format(member.get('channel').get('name')))
                        STREAMING += template.safe_substitute({
                                    "name": member.get('channel').get('name'),
                                    "status": "streaming",
                                    "statustext": "{0} playing {1}".format(stream.get('channel').get('name'), stream.get('channel').get('game')).upper()
                                })

                        break

                    else:
                        res = requests.get(HOST_URL % member.get('channel').get('_id'))
                        res.raise_for_status()

                        host = res.json().get('hosts')[0].get('target_login')
                        if host:
                            log.debug('{} is hosting'.format(member.get('channel').get('name')))
                            HOSTING += template.safe_substitute({
                                    "name": member.get('channel').get('name'),
                                    "status": "hosting",
                                    "statustext": "{0} is now hosting {1}".format(member.get('channel').get('name'), host).upper()
                                })

                            break

                        else:
                            log.debug('{} is offline'.format(member.get('channel').get('name')))
                            OFFLINE += template.safe_substitute({
                                    "name": member.get('channel').get('name'),
                                    "status": "offline",
                                    "statustext": "{0[name]} last seen playing {0[game]}".format(member.get('channel')).upper()
                                })

                            break

                except requests.RequestException as e:
                    log.error("There was an error checking status for {0}, waiting before trying again: {1}".format(name, e))
                    time.sleep(10)

    if (STREAMING or HOSTING) and OFFLINE:
        OFFLINE = ">* **[](#separator)**\n" + OFFLINE

    title = "> ###CLICK A CHANNEL TO START WATCHING!\n" if STREAMING else "> ###TEAM IS OFFLINE\n"

    return "\n\n{0}{1}\n".format(title, STREAMING + HOSTING + OFFLINE)

def update_sidebar(content):
    for sub in SUBREDDITS:
        subreddit = reddit.subreddit(sub)
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
                sidebar = sidebar[:marker_pos] + content + sidebar[marker_pos:]

                subreddit.mod.update(description=sidebar)

            except ValueError:
                # Substring not found
                log.critical("No streams marker found for /r/{}".format(sub))

        log.debug("Updated /r/{}".format(sub))

if __name__ == '__main__':
    team = get_team()

    content = render(team)

    try:
        update_sidebar(content)

    except Exception as e:
        log.error('Error updating sidebar: {}'.format(e))