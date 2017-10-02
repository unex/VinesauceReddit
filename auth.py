import yaml
import tweepy

with open("config.yaml", 'r') as config:
    try:
        config = yaml.load(config)

        TWITTER_CONSUMER_TOKEN = config['TWITTER_CONSUMER_TOKEN']
        TWITTER_CONSUMER_SECRET = config['TWITTER_CONSUMER_SECRET']

    except yaml.YAMLError as exc:
        print('Error opening config file: '.config(exc))

auth = tweepy.OAuthHandler(TWITTER_CONSUMER_TOKEN, TWITTER_CONSUMER_SECRET, 'http://localhost')

print(auth.get_authorization_url())

verifier = input('Verifier:')

try:
    auth.get_access_token(verifier)
except tweepy.TweepError as e:
    print('Error! Failed to get access token: {}'.format(e))

print('TWITTER_ACCESS_TOKEN: {0.access_token}\nTWITTER_ACCESS_TOKEN_SECRET: {0.access_token_secret}'.format(auth))