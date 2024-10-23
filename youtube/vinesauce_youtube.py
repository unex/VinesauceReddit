import os
import sys
import logging
import datetime
import traceback

from typing import List, Optional
from collections import deque
from contextlib import suppress
from datetime import datetime as dt, timedelta
import praw
import prawcore
import pymongo

from apiclient.discovery import build
from apiclient.errors import HttpError
from pydantic import BaseModel

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
log.addHandler(ch)


DRY_RUN = '--dry-run' in sys.argv
POPULATE_SEEN = '--populate-seen' in sys.argv

MONGO_URI = os.environ.get("MONGO_URI")

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN = os.environ.get("REDDIT_REFRESH_TOKEN")

DEVELOPER_KEY = os.environ.get("DEVELOPER_KEY")
SUBREDDIT = os.environ.get("SUBREDDIT")
FLAIR_ID = os.environ.get("FLAIR_ID")

CHANNELS = [
    # {
    #     'id': 'UCzVu0rUV7xoerfGNx37SCjw',
    #     'name': 'Dire Boar',
    #     'title_sub': ['DireBoar -'],
    #     'title_reject': ['(Full Stream)', '(FULL STREAM)', 'DireVODs']
    # },
    # {
    #     'id': 'UC6CvZVuX2PP7IFxXI8bTIUA',
    #     'name': 'Limesalicious',
    #     'title_sub': ['Limes -']
    # },
    # {
    #     'id': 'UCcubzpdxucT9b3Va1H6L7LA',
    #     'name': 'Fredsauce',
    #     'title_sub': ['Fred -', 'Fredsauce: ']
    # },
    {
        'id': 'UCzORJV8l3FWY4cFO8ot-F2w',
        'name': 'Vinny',
        'title_sub': ['Vinny -']
    },
    # {
    #     'id': 'UC_qjBu445WM4dulK392K6ww',
    #     'name': 'Rev',
    #     'title_sub': ['- Rev']
    # },
    # {
    #     'id': 'UCllm3HivMERwu2x2Sjz5EIg',
    #     'name': 'Joel',
    #     'title_sub': ['Joel -']
    # },
    # {
    #     'id': 'UCb_y_5iILxmXRCffnq5oSUw',
    #     'name': 'VicariousPotato'
    # },
    # {
    #     'id': 'UCptltT9soFxW7FlyqfurfRQ',
    #     'name': 'MentalJen',
    #     'title_sub': ['Jen -']
    # },
    # {
    #     'id': 'UCxMbjeSHVFtV05rOrnc-hug',
    #     'name': 'Hootey'
    # },
    # {
    #     'id': 'UCcYvBu9t0Tsy0cwFUHwWJmA',
    #     'name': 'GeePM',
    #     'title_sub': ['- GeePM', 'GeePM -']
    # }
    # {
    #     'id': 'UC2_IYqb1Tc_8Azh7rByedPA',
    #     'name': 'Full Sauce'
    # },
    # {
    #     'id': 'UCRNCUBq676nUhXyy8AJzD5w',
    #     'name': 'Joel: Full Streams'
    # },
    # {
    #     'id': 'UCSNF0FG_I8NboKf0H7Xn1CQ',
    #     'name': 'Rev: After Hours'
    # }
]

mongo = pymongo.MongoClient(MONGO_URI)
db = mongo.vinesauce.youtube

class WatchedChannel(BaseModel):
    id: str
    name: str
    title_sub: Optional[List[str]] = []
    title_reject: Optional[List[str]] = []

class Video(BaseModel):
    id: str
    title: str
    channel_title: str

    @property
    def url(self):
        return f'https://www.youtube.com/watch?v={self.id}'

    @classmethod
    def from_api(cls, data):
        return cls(
            id = data["contentDetails"]["upload"]["videoId"],
            title = data["snippet"]["title"],
            channel_title = data["snippet"]["channelTitle"] if "channelTitle" in data["snippet"] else ""
        )


class SeenVideos(object):
    def __init__(self) -> None:
        pass

    def __contains__(self, _id) -> bool:
        return db.find_one({"id": _id}) is not None

    def add(self, _id) -> None:
        db.insert_one({"id": _id})


reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    refresh_token=REDDIT_REFRESH_TOKEN,
    user_agent='Vinesauce YouTube Bot - /u/RenegadeAI',
)
reddit.validate_on_submit = True
subreddit = reddit.subreddit(SUBREDDIT)
youtube = build('youtube', 'v3', developerKey = DEVELOPER_KEY)


def main():
    log.info(f'Logged into reddit as /u/{reddit.user.me()} on /r/{subreddit.display_name}')
    seen = SeenVideos()

    for c in CHANNELS:
        channel = WatchedChannel(**c)
        log.debug(f'Checking: {channel.name}')

        for video in get_videos(channel):
            log.debug(f"  - {video.title}")
            if video.id in seen:
                log.debug(f"    - SEEN")

                continue

            if not POPULATE_SEEN:
                post(video, channel)
            else:
                log.info(f'POPULATING SEEN - {video.id}')

            if not DRY_RUN:
                seen.add(video.id)

def get_videos(channel: WatchedChannel) -> List[Video]:
    try:
        yesterday = dt.now(datetime.UTC) - timedelta(hours = 24)
        r = youtube.activities().list(
                channelId = channel.id,
                publishedAfter = yesterday.isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                part = "snippet, contentDetails",
            ).execute()

        return [Video.from_api(x) for x in r.get("items") if x["snippet"]["type"] == 'upload']

    except HttpError as e:
        for err in e.error_details:
            if err.get('reason') == 'quotaExceeded':
                log.critical('YouTube API quota exceeded, exiting')
                sys.exit(1)

        log.error(e)

    except Exception as e:
        log.error(f'Error searching YouTube: {e}')
        traceback.print_exc()
        return []

def post(video, channel):
    for f in channel.title_reject:
        if f in video.title:
            return False

    sub = ['[Vinesauce]', '[VINESAUCE]']

    sub += channel.title_sub

    video_title = video.title

    for s in sub:
        video_title = video_title.replace(s, '')

    video_title = f'[{channel.name}] {video_title.strip()}'

    if DRY_RUN:
        log.info(f'DRY RUN - Post {video_title}')

        return

    while True:
        try:
            # Unsticky any bot posts
            for i in reversed(range(1, 7)):
                try:
                    s = subreddit.sticky(number=i)

                    if s.author == reddit.user.me():
                        s.mod.sticky(state=False)

                except prawcore.NotFound as e:
                    continue

            s = subreddit.submit(
                video_title,
                url = video.url,
                flair_id = FLAIR_ID,
                resubmit = True
            )

            s.mod.sticky(bottom=True, state=True)

            log.info(f'Posted: {video_title} {s.shortlink}')
            break

        except praw.exceptions.APIException as e:
            if(e.error_type == 'ALREADY_SUB'):
                log.warning(f'Already Posted: {video_title}')
                break

        except Exception as e:
            log.error(f'Error submitting: {video_title} {e}')

if __name__ == "__main__":
    main()
