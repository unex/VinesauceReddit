import os
import re
import logging
import traceback

from io import BytesIO

import praw
import pymongo
import requests

import atproto
from atproto import client_utils

from PIL import Image


log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(levelname)s] %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)

MAX_LEN = 300

MONGO_URI = os.environ.get("MONGO_URI")

IMGUR_CLIENT_ID = os.environ.get("IMGUR_CLIENT_ID")

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN = os.environ.get("REDDIT_REFRESH_TOKEN")

BLUESKY_USERNAME = os.environ.get("BLUESKY_USERNAME")
BLUESKY_PASSWORD = os.environ.get("BLUESKY_PASSWORD")

SUBREDDIT = os.environ.get("SUBREDDIT")

reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    refresh_token=REDDIT_REFRESH_TOKEN,
    user_agent="Vinesauce BlueSky bot /u/RenegadeAI"
)

bluesky = atproto.Client()
bluesky.login(BLUESKY_USERNAME, BLUESKY_PASSWORD)

mongo = pymongo.MongoClient(MONGO_URI)
db = mongo.vinesauce.bluesky

def main():
    for submission in reversed(list(reddit.subreddit(SUBREDDIT).hot(limit=7))):
        if submission.link_flair_text == 'Weekly Post' or submission.score >= 80:

            if db.find_one({"id": submission.id}):
                log.debug(f"Skipping {submission.id}")
                continue

            try:
                send(submission)
            except:
                log.error(f"Error posting {submission.shortlink}\n{traceback.format_exc()}")
                continue

            db.insert_one({"id": submission.id})

            break

def get_media_urls(url):
    IMGUR_HEADERS = {'Authorization': 'Client-ID {}'.format(IMGUR_CLIENT_ID)}

    url = url.replace('http:', 'https:').replace('gallery', 'a')

    # If its an imgur album
    match = re.match(r'(https?)\:\/\/(www\.)?(?:m\.)?imgur\.com/a/([a-zA-Z0-9]+)(#[0-9]+)?', url)
    if match:
        album_id = match.group(3)

        response = requests.get('https://api.imgur.com/3/album/{}'.format(album_id), headers=IMGUR_HEADERS)

        return [s['link'] for s in response.json()['data']['images']]

    #if its an imgur image
    match = re.match(r"(?:https?\:\/\/)?(?:www\.)?(?:m\.)?(?:i\.)?imgur\.com\/([a-zA-Z0-9]+)", url)
    if match:
        image_id = match.group(1)

        response = requests.get('https://api.imgur.com/3/image/{}'.format(image_id), headers=IMGUR_HEADERS)

        return [response.json()['data']['link']]

    # if its a reddit hosted image
    if any(s in url for s in ('i.redd.it', 'i.reddituploads.com')):
        return [ url if re.findall(r'/([^/]+\.(?:jpg|jpeg|gif|png))', url) else '{}.jpg'.format(url) ]

def fetch_media(url: str) -> bytes:
    response = requests.get(url, stream=True, headers={'User-agent': 'Mozilla/5.0'})
    response.raw.decode_content = True

    if not response.headers.get('Content-Type').startswith('image'):
        return None

    return response.raw.data

def send(submission: praw.reddit.Submission):
    images = []
    embed = None

    builder = client_utils.TextBuilder()

    builder.text(f"{submission.title}\n")

    builder.link("view on reddit", submission.shortlink)
    builder.text(" • ")
    builder.tag("#vinesauce", "vinesauce")

    if any(s in submission.url for s in ('imgur.com', 'i.redd.it', 'i.reddituploads.com')):
        urls = get_media_urls(submission.url)

        for url in urls:
            if data := fetch_media(url):
                fp = BytesIO(data)
                im = Image.open(fp)

                MAX_DIM = 2000
                MAX_SIZE = 1E6

                while max(im.size) > MAX_DIM or len(data) > MAX_SIZE:
                    if max(im.size) > MAX_DIM:
                        ratio = MAX_DIM / max(im.size)
                    else:
                        ratio = 0.9

                    new_size = tuple(int(x * ratio) for x in im.size)

                    log.debug(f"Resizing image {im.size} -> {new_size}")

                    im = im.resize(new_size)

                    fp = BytesIO()
                    im.save(fp, format='JPEG')
                    fp.seek(0)

                    data = fp.read()

                images.append(data)


    elif m := submission.media:
        if oembed := m.get('oembed'):
            embed = atproto.models.AppBskyEmbedExternal.Main(
                external=atproto.models.AppBskyEmbedExternal.External(
                    title=oembed['title'],
                    description=f"{oembed['provider_name']} {oembed['type']} by {oembed['author_name']}",
                    uri=submission.url,
                    thumb=bluesky.upload_blob(fetch_media(oembed['thumbnail_url'])).blob,
                )
            )

    log.info(f'Posting: {submission.shortlink}')

    if images:
        bluesky.send_images(builder, images=images)
    else:
        bluesky.post(builder, embed=embed)


if __name__ == '__main__':
    main()
