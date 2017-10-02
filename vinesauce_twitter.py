import os, sys
import re
import praw
import yaml
import shutil
import tweepy
import requests
from urllib.parse import urlparse

# Custom logging stuff
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),"..")))
    from utils import log

except:
    import logging
    log = logging.getLogger(__name__)
    log.setLevel(logging.INFO)

    log.addHandler(logging.StreamHandler(sys.stdout))

# Get config
with open("config.yaml", 'r') as config:
    try:
        config = yaml.load(config)

        IMGUR_CLIENT_ID = config['IMGUR_CLIENT_ID']

        TWITTER_CONSUMER_TOKEN = config['TWITTER_CONSUMER_TOKEN']
        TWITTER_CONSUMER_SECRET = config['TWITTER_CONSUMER_SECRET']
        TWITTER_ACCESS_TOKEN = config['TWITTER_ACCESS_TOKEN']
        TWITTER_ACCESS_TOKEN_SECRET = config['TWITTER_ACCESS_TOKEN_SECRET']

    except yaml.YAMLError as exc:
        print('Error opening config file: '.config(exc))

# reddit
reddit = praw.Reddit('BonziBot', user_agent='VinesauceReddit Twitter bot /u/RenegadeAI')

# twitter
auth = tweepy.OAuthHandler(TWITTER_CONSUMER_TOKEN, TWITTER_CONSUMER_SECRET)
auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)
twitter = tweepy.API(auth)

def main():
    with open("posted") as fobj:
        posted = fobj.read().strip().split()

    # We only want to post once per iteration,
    # as to not spam twitter, so we get the
    # next post from reddit, tweet it, then break.

    for post in reddit.subreddit('vinesauce').hot(limit=5):
        meta = ' {} #vinesauce'.format(post.shortlink)

        if post.id not in posted:
            if post.link_flair_text == 'Weekly Post' or post.score >= 25:
                if post.is_self:
                    tweet(truncate_title(post.title, meta))

                elif any(s in post.url for s in ('imgur.com', 'i.redd.it', 'i.reddituploads.com')):
                    images = get_media(post.url)

                    files = save_media(images)

                    tweet(truncate_title(post.title, meta), files)

                    [os.remove(file) for file in files]

                elif any(s in post.url for s in ('clips.twitch.tv', 'youtube.com')):
                    tweet(truncate_title(post.title, '{0}\n{1}'.format(meta, post.url)))

                else:
                    tweet(truncate_title(post.title, meta))

                with open("posted", "a") as file:
                    file.write('{}\n'.format(post.id))

                break

def truncate_title(title, rest):
    remaining_len = 180 - len(rest) - 2

    return ((title[:remaining_len] + '..') if len(title) > remaining_len else title) + rest

def get_media(url):
    IMGUR_HEADERS = {'Authorization': 'Client-ID {}'.format(IMGUR_CLIENT_ID)}

    url = url.replace('http:', 'https:')

    # If its an imgur album
    match = re.match('(https?)\:\/\/(www\.)?(?:m\.)?imgur\.com/a/([a-zA-Z0-9]+)(#[0-9]+)?', url)
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
        return [ url if re.findall('/([^/]+\.(?:jpg|gif|png))', url) else '{}.jpg'.format(url) ]

def save_media(media):
    files = []

    for url in media:
        response = requests.get(url, stream=True, headers={'User-agent': 'Mozilla/5.0'})
        response.raw.decode_content = True

        filename = 'temp/{}'.format(os.path.basename(urlparse(url).path))

        with open(filename, 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)

        #Tweepy wont upload images over 3072kb for whatever reason
        if not os.path.getsize(filename) > (3072 * 1024):
            files.append(filename)

    return files

def tweet(status, media = None):
    log.info('Tweeted: {0}, media: {1}'.format(status, media))

    return twitter.update_status(status, media_ids=[twitter.media_upload(i).media_id_string for i in media] if media else None)

if __name__ == '__main__':
    main()