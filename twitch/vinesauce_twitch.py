import os
import re
import sys
import json
import yaml
import math
import asyncio
import logging

from PIL import Image
from io import BytesIO
from enum import IntEnum
from typing import Set, Dict, List, Optional
from datetime import datetime as dt, timezone

import sass
import aiohttp
import asyncpraw

from twitchAPI.twitch import Twitch
from pydantic import BaseModel, constr
from aiopath import AsyncPath


TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET")

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN = os.environ.get("REDDIT_REFRESH_TOKEN")

SUBREDDIT = os.environ.get("SUBREDDIT")
WIDGET_ID = os.environ.get("WIDGET_ID")

CACHE_DIR = AsyncPath('.cache')

STREAMER_CACHE = CACHE_DIR.joinpath("streamers.json")  # AsyncPath("streamers.json")

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
log.addHandler(ch)


class Config(BaseModel):
    friends: Set[constr(to_lower=True)]

class StreamerStatus(IntEnum):
    OFFLINE = 0
    LIVE    = 1

    def __str__(self):
        return self.name;

class Streamer(BaseModel):
    id: str
    login: str
    display_name: str
    profile_image_url: str
    status: StreamerStatus
    game_name: Optional[str] = "sample text"
    title: Optional[str] = ""
    viewer_count: Optional[int] = 0

    def render_sidebar(self):
        if self.status == StreamerStatus.LIVE:
            s = f'{self.display_name} playing {self.game_name}'
        else:
            s = f'{self.display_name} last seen playing {self.game_name}'

        return f'>* [{s.upper()}](#{self.status})[](https://twitch.tv/{self.login})\n'

    def render_widget(self):
        if self.status == StreamerStatus.LIVE:
            game = self.game_name
            s = f'{self.viewer_count:,}'

        else:
            game = f"Last seen playing {self.game_name}"
            s = self.status

        return f'* [](#{str(self.status).lower()})[~~pic~~ >!**{self.display_name}** *{s}* **{game.strip()}**!<](https://twitch.tv/{self.login})\n'


class VinesauceTwitch():
    MAIN_CHANNEL = "vinesauce"

    logins: list
    config: Config = None
    streamers: List[Streamer] = []
    subreddit: asyncpraw.reddit.Subreddit
    widget: asyncpraw.reddit.models.CustomWidget

    def __init__(self) -> None:
        pass

    def __await__(self):
        yield from asyncio.create_task(self.prepare())
        return self

    async def prepare(self):
        # init reddit
        self.reddit = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            refresh_token=REDDIT_REFRESH_TOKEN,
            user_agent="Vinesauce Twitch.tv monitor /u/RenegadeAI"
        )  # scopes:

        # init target subreddit
        self.subreddit = await self.reddit.subreddit(SUBREDDIT, fetch=True)
        log.info(f"Using /r/{self.subreddit.display_name}")

        # find target widget
        try:
            widgets = await self.subreddit.widgets.items()
            self.widget = widgets[WIDGET_ID]

        except KeyError:
            log.critical(f'Could not find widget "{WIDGET_ID}"')

            log.critical('Avaliable widgets:')
            for w in self.subreddit.widgets.sidebar:
                log.critical(f'    {w.id} - {w.kind}')

            sys.exit(0)

        # init twitch
        self.twitch = await Twitch(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)

        # load config
        await self.load_config()

        # load streamers from cache
        if await STREAMER_CACHE.exists():
            for s in json.loads(await STREAMER_CACHE.read_text()):
                streamer = Streamer(**s)

                if streamer.login in self.logins:
                    self.streamers.append(streamer)

    @property
    def logins(self):
        # create logins
        logins = list(map(lambda x: x.lower(), self.config.friends))
        logins.insert(0, self.MAIN_CHANNEL)

        return logins

    async def _fetch_config(self) -> Config:
        log.debug(f"Fetching config for {self.subreddit.display_name}")
        page = await self.subreddit.wiki.get_page("bots/twitch")
        return Config(**yaml.safe_load(page.content_md))

    async def load_config(self, force_fetch=False) -> None:
        config_file = CACHE_DIR.joinpath("config.yaml")

        try:
            self.config = Config(**yaml.safe_load(await config_file.read_text()))
            log.debug(f"Loaded config for {self.subreddit.display_name}")

        except Exception as e:
            log.error(f"Failed to load config from file: {e}")

        if not self.config or force_fetch:
            self.config = await self._fetch_config()

            await config_file.write_text(yaml.dump(self.config.model_dump()))

        log.debug(self.config)

    async def update_streamers(self) -> None:
        data: Dict[str, dict] = {}

        # fetch user data
        async for u in self.twitch.get_users(logins=self.logins):
            data[u.login] = {}
            data[u.login]["status"] = StreamerStatus.OFFLINE

            for s in ["id", "login", "display_name", "profile_image_url"]:
                data[u.login][s] = getattr(u, s)

        # fetch stream data
        async for u in self.twitch.get_streams(user_login=self.logins):
            data[u.user_login]["status"] = StreamerStatus.LIVE

            for s in ["game_name", "title", "viewer_count"]:
                data[u.user_login][s] = getattr(u, s)

        # update existing streamers
        for s in self.streamers:
            if not s.login in data:
                continue

            for k, v in data[s.login].items():
                if k == "login":
                    continue

                setattr(s, k, v)

            del data[s.login]

            log.debug(f"Updated {s.display_name} {s.status}")

        # add new streamers
        for login, d in data.items():
            s = Streamer(**d)

            self.streamers.append(s)

            log.debug(f"Added {s.display_name} {s.status}")

        self.streamers.sort(key=lambda x: x.status == StreamerStatus.LIVE, reverse=True) # sort live to top

        await STREAMER_CACHE.write_text(json.dumps([s.model_dump() for s in self.streamers]))

    def _build_css(self, img_styles: str) -> str:
        with open("widget.scss") as fp:
            scss = fp.read()

            scss += img_styles

            css = f"// Compiled at {dt.utcnow()}\n"
            css += sass.compile(string=scss, output_style='compressed')

            return css

    async def build_widget(self, update_sprite=False, update_css=False, update_height=False) -> None:
        THUMB_SIZE = 42

        streamers = sorted(self.streamers, key=lambda x: int(x.id))

        try:
            current_sprite = next(x for x in self.widget.imageData if x.name == "sprite")
        except StopIteration:
            current_sprite = None #asyncpraw.reddit.models.ImageData(self.reddit, {"height": -1})

        to_update = {}

        if not current_sprite or current_sprite.height != len(streamers) * THUMB_SIZE:
            update_sprite = True
            update_css = True
            update_height = True


        if update_sprite:
            log.debug(f"Updating sprite")

            sprite = Image.new("RGBA", (THUMB_SIZE, len(self.streamers) * THUMB_SIZE))

            async with aiohttp.ClientSession() as s:
                for i, stream in enumerate(streamers):
                    async with s.get(stream.profile_image_url) as r:
                        fp = BytesIO()

                        async for chunk in r.content.iter_chunked(2 * 1024):
                            fp.write(chunk)

                        fp.seek(0)

                        im = Image.open(fp).resize((THUMB_SIZE, THUMB_SIZE))

                        pos = i * THUMB_SIZE

                        sprite.paste(im, (0, pos))


            # upload the image directly, asyncpraw doesnt directly support this
            # https://github.com/praw-dev/asyncpraw/blob/7bc8c10dd2c18229c14d1858bb1221ed806a4c00/asyncpraw/models/reddit/widgets.py#L1863
            image = BytesIO()
            sprite.save(image, format="PNG")
            image.seek(0)

            img_data = {
                "filepath": "sprite.png",
                "mimetype": "image/png",
                "file": image,
            }

            url = asyncpraw.const.API_PATH["widget_lease"].format(subreddit=self.widget.subreddit)
            response = await self.reddit.post(url, data=img_data)
            upload_lease = response["s3UploadLease"]
            upload_data = {item["name"]: item["value"] for item in upload_lease["fields"]}
            upload_url = f"https:{upload_lease['action']}"

            upload_data["file"] = image
            response = await self.reddit._core._requestor._http.post(
                upload_url, data=upload_data
            )

            response.raise_for_status()

            image_url = f"{upload_url}/{upload_data['key']}"

            if current_sprite and sprite.height == current_sprite.height:
                # if the images are the same height, and I dont clear the widget first, uploading a new sprite will 404 for some reason
                log.debug(" - clearing sprite")

                to_update["css"] = self.widget.css
                self.widget = await self.widget.mod.update(imageData=[], css='{}')

                await asyncio.sleep(1)

            image_data = self.widget.imageData

            try:
                image_data.remove(current_sprite)
            except:
                pass

            # update the widget
            image_data.append({
                'name': "sprite",
                'width': sprite.width,
                'height': sprite.height,
                'url': image_url,
            })

            to_update["imageData"] = image_data


        if update_css:
            log.debug("Updating CSS")

            img_styles = "li {\n"

            for i, stream in enumerate(streamers):
                pos = i * THUMB_SIZE

                img_styles += f'a[href*="{stream.login}"] del:before {{ background-position: 0 -{pos}px }}\n'

            img_styles += "}\n"

            loop = asyncio.get_running_loop()
            to_update["css"] = await loop.run_in_executor(None, self._build_css, img_styles)


        if update_height:
            log.debug("Updating height")

            top_height = 184
            row_height = 78

            max_height = top_height + row_height * 3 + 31

            height = top_height + math.ceil(len(self.streamers) / 4) * row_height

            if height > max_height:
                height = max_height

            to_update["height"] = height


        if to_update:
            self.widget = await self.widget.mod.update(**to_update)

            log.info("built widget")

        else:
            log.info("widget build skipped")


    async def update_widget(self) -> None:
        content = ""

        streamers = self.streamers

        # main streamer
        ms = next((x for x in streamers if x.login == self.MAIN_CHANNEL), None)

        content += f"#### CURRENTLY {ms.status}\n\n"

        content += ms.render_widget()

        content += "\n\n"
        content += "#### VINNY'S FRIENDS\n\n"

        # the rest
        streamers = filter(lambda x: x.login != self.MAIN_CHANNEL, streamers) # remove main streamer from the rest

        for stream in streamers:
            content += stream.render_widget()

        now = dt.now(tz=timezone.utc)

        content += f'\n\n`LAST UPDATED @ {now.strftime("%X")} {now.strftime("%x")} UTC`'

        self.widget = await self.widget.mod.update(text=content)

        log.info('updated widget')

    async def run(self) -> None:
        await self.update_streamers()

        await self.subreddit.load()

        await self.update_widget()

    async def close(self) -> None:
        await self.reddit.close()


async def main():
    await CACHE_DIR.mkdir(exist_ok=True)

    bot = await VinesauceTwitch()

    mode = sys.argv[1]

    try:
        if mode == "update":
            await bot.build_widget()
            await bot.run()

        elif mode == "config":
            await bot.load_config(force_fetch=True)
            await bot.update_streamers()
            await bot.build_widget()

        elif mode == "sprite":
            await bot.build_widget(update_sprite=True)

    except KeyboardInterrupt:
        pass

    finally:
        await bot.close()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
