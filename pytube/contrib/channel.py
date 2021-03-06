# -*- coding: utf-8 -*-
"""Module for interacting with a user's youtube channel."""
import json
import logging
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional
from typing import Tuple

from pytube import extract
from pytube import request
from pytube.continuation import Continuation
from pytube.helpers import cache
from pytube.helpers import uniqueify
from pytube.helpers import install_proxy

logger = logging.getLogger(__name__)


class Channel:
    def __init__(self, url: str, proxies: Optional[Dict[str, str]] = None):
        if proxies:
            install_proxy(proxies)

        self.channel_name = extract.channel_name(url)

        self.channel_url = (
            f"https://www.youtube.com/c/{self.channel_name}"
        )
        self.videos_url = self.channel_url + '/videos'
        self.playlists_url = self.channel_url + '/playlists_url'
        self.community_url = self.channel_url + '/community'
        self.featured_channels_url = self.channel_url + '/channels'
        self.about_url = self.channel_url + '/about'

        # Defer all of the html fetches until we need them
        self._videos_html = None

        # Possible future additions
        self._playlists_html = None
        self._community_html = None
        self._featured_channels_html = None
        self._about_html = None

        self.continuation_class = Continuation

    @property
    def videos_html(self):
        if self._videos_html:
            return self._videos_html
        else:
            self._videos_html = request.get(self.videos_url)
            return self._videos_html

    @property
    def playlists_html(self):
        if self._playlists_html:
            return self._playlists_html
        else:
            self._playlists_html = request.get(self.playlists_url)
            return self._playlists_html

    @property
    def community_html(self):
        if self._community_html:
            return self._community_html
        else:
            self._community_html = request.get(self.community_url)
            return self._community_html

    @property
    def featured_channels_html(self):
        if self._featured_channels_html:
            return self._featured_channels_html
        else:
            self._featured_channels_html = request.get(self.featured_channels_url)
            return self._featured_channels_html

    @property
    def about_html(self):
        if self._about_html:
            return self._about_html
        else:
            self._about_html = request.get(self.about_url)
            return self._about_html

    @property  # type: ignore
    @cache
    def video_urls(self) -> List[str]:
        """Complete links of all the videos in playlist

        :rtype: List[str]
        :returns: List of video URLs
        """
        # TODO: convert to an iterator, so a user can subscript how much they want
        # such as Channel.video_urls[:100]
        return [
            self._video_url(video)
            for page in list(self._paginate_videos())
            for video in page
        ]

    def _paginate_videos(
        self, until_watch_id: Optional[str] = None
    ) -> Iterable[List[str]]:
        """Parse the video links from the page source, yields the /watch?v=
        part from video link

        :param until_watch_id Optional[str]: YouTube Video watch id until
            which the playlist should be read.

        :rtype: Iterable[List[str]]
        :returns: Iterable of lists of YouTube watch ids
        """
        gen = self.continuation_class._paginate(self.videos_html)
        try:
            curr = next(gen)
        except StopIteration:
            return
        while True:
            # Trim the current page if necessary, else yield the whole thing
            try:
                trim_index = curr.index(f'/watch?v={until_watch_id}')
                yield curr[:trim_index]
                break
            except ValueError:
                yield curr

            # Try to get the next page
            try:
                curr = next(gen)
            except StopIteration:
                break

    @staticmethod
    def _extract_videos(raw_json: str) -> Tuple[List[str], Optional[str]]:
        """Extracts videos from a raw json page

        :param str raw_json: Input json extracted from the page or the last
            server response
        :rtype: Tuple[List[str], Optional[str]]
        :returns: Tuple containing a list of up to 100 video watch ids and
            a continuation token, if more videos are available
        """
        initial_data = json.loads(raw_json)
        # this is the json tree structure, if the json was extracted from
        # html
        try:
            videos = initial_data["contents"][
                "twoColumnBrowseResultsRenderer"][
                "tabs"][1]["tabRenderer"]["content"][
                "sectionListRenderer"]["contents"][0][
                "itemSectionRenderer"]["contents"][0][
                "gridRenderer"]["items"]
        except (KeyError, IndexError, TypeError):
            try:
                # this is the json tree structure, if the json was directly sent
                # by the server in a continuation response
                important_content = initial_data[1]['response']['onResponseReceivedActions'][
                    0
                ]['appendContinuationItemsAction']['continuationItems']
                videos = important_content
            except (KeyError, IndexError, TypeError) as p:
                print(p)
                return [], None

        try:
            continuation = videos[-1]['continuationItemRenderer'][
                'continuationEndpoint'
            ]['continuationCommand']['token']
            videos = videos[:-1]
        except (KeyError, IndexError):
            # if there is an error, no continuation is available
            continuation = None

        # remove duplicates
        return (
            uniqueify(
                list(
                    # only extract the video ids from the video data
                    map(
                        lambda x: (
                            f"/watch?v="
                            f"{x['gridVideoRenderer']['videoId']}"
                        ),
                        videos
                    )
                ),
            ),
            continuation,
        )

    @staticmethod
    def _video_url(watch_path: str):
        return f"https://www.youtube.com{watch_path}"
