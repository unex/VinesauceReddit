#pip install google-api-python-client

import os, sys
import yaml
from apiclient.discovery import build
from apiclient.errors import HttpError
from googleapiclient.discovery_cache.base import Cache
import praw
import time
from datetime import datetime as dt
import requests
from derw import log

DEVELOPER_KEY = os.environ.get("DEVELOPER_KEY")

SUBREDDIT = 'Vinesauce'
CHANNELS = [
    {
        'id': 'UCzVu0rUV7xoerfGNx37SCjw',
        'name': 'Dire Boar',
        'title_sub': ['DireBoar -'],
        'title_reject': ['(Full Stream)', '(FULL STREAM)', 'DireVODs']
    },
    {
        'id': 'UC6CvZVuX2PP7IFxXI8bTIUA',
        'name': 'Limesalicious',
        'title_sub': ['Limes -']
    },
    {
        'id': 'UCcubzpdxucT9b3Va1H6L7LA',
        'name': 'Fredsauce',
        'title_sub': ['Fred -', 'Fredsauce: ']
    },
    {
        'id': 'UCzORJV8l3FWY4cFO8ot-F2w',
        'name': 'Vinny',
        'title_sub': ['Vinny -']
    },
    {
        'id': 'UC_qjBu445WM4dulK392K6ww',
        'name': 'Rev',
        'title_sub': ['- Rev']
    },
    {
        'id': 'UCllm3HivMERwu2x2Sjz5EIg',
        'name': 'Joel',
        'title_sub': ['Joel -']
    },
    {
        'id': 'UCb_y_5iILxmXRCffnq5oSUw',
        'name': 'VicariousPotato'
    },
    {
        'id': 'UCptltT9soFxW7FlyqfurfRQ',
        'name': 'MentalJen',
        'title_sub': ['Jen -']
    },
    # {
    #     'id': 'UCxMbjeSHVFtV05rOrnc-hug',
    #     'name': 'Hootey'
    # },
    # {
    #     'id': 'UCcYvBu9t0Tsy0cwFUHwWJmA',
    #     'name': 'GeePM',
    #     'title_sub': ['- GeePM', 'GeePM -']
    # }
    {
        'id': 'UC2_IYqb1Tc_8Azh7rByedPA',
        'name': 'Full Sauce'
    },
    # {
    #     'id': 'UCRNCUBq676nUhXyy8AJzD5w',
    #     'name': 'Joel: Full Streams'
    # },
    # {
    #     'id': 'UCSNF0FG_I8NboKf0H7Xn1CQ',
    #     'name': 'Rev: After Hours'
    # }
]

try:
    with open(os.path.dirname(os.path.realpath(__file__)) + '/last_checked') as f:
        LAST_CHECKED = dt.fromtimestamp(float(f.read()))

except Exception as e:
    log.error('{}'.format(e))

reddit = praw.Reddit('BonziBot', user_agent='Vinesauce Youtube Poster by /u/RenegadeAI')

class MemoryCache(Cache):
        _CACHE = {}

        def get(self, url):
            return MemoryCache._CACHE.get(url)

        def set(self, url, content):
            MemoryCache._CACHE[url] = content

youtube = build('youtube', 'v3', developerKey = DEVELOPER_KEY, cache=MemoryCache())

def main():
    log.debug("Last checked at {}".format(LAST_CHECKED.time().strftime("%H:%M:%S")))

    current_time = dt.utcnow()

    for channel in CHANNELS:
        log.debug('Checking: {}'.format(channel['name']))
        videos = get_videos(channel)
        if videos:
            for video in videos:
                post(video, channel)

    with open(os.path.dirname(os.path.realpath(__file__)) + '/last_checked', 'w') as f:
        f.write(str(current_time.timestamp()))

def get_videos(channel):
    try:
        search_response = youtube.search().list(
                            channelId = channel['id'],
                            publishedAfter = LAST_CHECKED.isoformat('T') + 'Z',
                            order = 'date',
                            part = "id, snippet",
                            maxResults = 50, # Change if you want to search more videos at a time.
                            type = 'video').execute()

    except Exception as e:
        log.error('Error searching YouTube: {}'.format(e))
        return []

    videos = []

    for search_result in search_response.get("items", []):
        if(search_result['snippet']['liveBroadcastContent'] != 'live'):
            videos.append([search_result['snippet']['title'],
                           search_result['snippet']['channelTitle'],
                           search_result['id']['videoId'],
                           search_result['snippet']['channelId']])

        return videos

def post(video, channel):
    video_title = video[0]

    if 'title_reject' in channel:
        for filter in channel['title_reject']:
            if filter in video_title:
                return False

    sub = ['[Vinesauce]', '[Vinesauce]', '[VINESAUCE]']

    if 'title_sub' in channel:
        sub += channel['title_sub']

    for str_ in sub:
        video_title = video_title.replace(str_, '')

    # video_title = '[' + channel['name'] + '] ' + video_title.strip()
    video_title = '[{0}] {1}'.format(channel['name'], video_title.strip())

    video_id = video[2]
    link = 'https://www.youtube.com/watch?v={}'.format(video_id)

    while True:
        try:
            reddit.subreddit(SUBREDDIT).submit(video_title, url=link, flair_id="ac140ae8-f369-11e8-8489-0e4499b53a5a", resubmit=True)

            log.info('Posted: ' + video_title)
            break

        except praw.exceptions.APIException as e:
            if(e.error_type == 'ALREADY_SUB'):
                log.warning('Already Posted: {}'.format(video_title))
                break

        except Exception as e:
            log.error('Error submitting: {}'.format(e))

if __name__ == "__main__":
    main()
