import os, sys
import io
import json
from PIL import Image
import requests

THUMB_SIZE = 38

team = requests.get('http://vinesauce.com/twitch/team-data.json').json()

logos = {}

for k, v in team.items():
    r = requests.get(v["channel"]["logo"], stream=True)
    if r.status_code == 200:
        buffer = bytes()

        for chunk in r.iter_content():
            buffer += chunk

        logos[k] = Image.open(io.BytesIO(buffer)).resize((THUMB_SIZE, THUMB_SIZE), Image.ANTIALIAS)

        print(f'Downloaded {k}')


sprite = Image.new('RGBA', (THUMB_SIZE, THUMB_SIZE * len(logos)))
styles = ""

i = 0
for k, logo in logos.items():
    sprite.paste(logo, box=(0, THUMB_SIZE * i))

    styles += f'a[href*="{k}"]:before {{ background-position: 0 -{THUMB_SIZE * i}px }}\n'

    i+=1

print(styles)
sprite.save('./sprite.png')
