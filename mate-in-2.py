import io
import os
import re
import traceback

import feedparser
import requests
from PIL import Image
from atproto import Client
from atproto_client.exceptions import BadRequestError
from atproto_client.utils import TextBuilder


def get_profile_feed(client, bsky_id):
    cursor = None
    profile_feed_items = []
    while True:
        profile_feed = client.get_author_feed(actor=bsky_id, cursor=cursor)
        profile_feed_items = profile_feed_items + profile_feed.feed
        if not profile_feed.cursor:
            break
        else:
            cursor = profile_feed.cursor
    return profile_feed_items

def get_mate_in_2_posts():
    response = feedparser.parse(
        'https://nitter.privacydev.net/ImShahinyan/rss',
        request_headers={
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9,it;q=0.8',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        },
    )
    return response.entries

def post_item(client, post_id, image_id, text):
    image_data = get_image(image_id)
    tb = TextBuilder()
    tb.text('mate in 2 puzzle from ')
    tb.link(f"@ImShahinyan",
            f"https://x.com/ImShahinyan/status/{post_id}")
    tb.text(':\n')
    tb.text('"')
    tb.text(text)
    tb.text('"\n')
    tb.tag("#chess", "#chess")
    tb.text(" ")
    tb.tag("#puzzle", "#puzzle")
    response = client.send_image(text=tb,
                                 image=image_data,
                                 image_alt='chess board with a puzzle')
    # Print the URI of the created post
    print(f"Post created with URI: {response.uri}")
    return response.uri


def get_image(image_id):
    image_url = f"https://pbs.twimg.com/media/{image_id}?format=png&name=900x900"
    image_response = requests.get(image_url)
    if image_response.status_code == 200:
        image = Image.open(io.BytesIO(image_response.content))
        output = io.BytesIO()
        image.save(output, format='PNG', optimize=True, compress_level=9)
        return output.getvalue()
    else:
        raise Exception(f"Failed to fetch image from {image_url}")

def main():
    bsky_id = os.environ.get('BSKY_ID')
    bsky_password = os.environ.get('BSKY_PASSWORD')
    if not bsky_id or not bsky_password:
        raise ValueError("BSKY_ID/BSKY_PASSWORD environment variables should be set")

    client = Client()
    profile = client.login(bsky_id, bsky_password)
    print('Welcome,', profile.display_name)

    profile_feed_items = get_profile_feed(client, bsky_id)
    print(f"found {len(profile_feed_items)} posts in bsky profile feed")

    posts = get_mate_in_2_posts()
    print(f"found {len(posts)} posts in rss feed")
    for entry in posts:
        pattern = r'mate(s)? in 2'
        match = re.search(pattern, entry.title, re.IGNORECASE)
        if not match:
            continue

        post_id = None
        id_pattern = r'/status/(\d+)'
        match = re.search(id_pattern, entry.id)
        if match:
            post_id = match.group(1)

        image_id = None
        image_pattern = r'media%2F([^.]+)\.'
        match = re.search(image_pattern, entry.summary)
        if match:
            image_id = match.group(1)

        if not post_id or not image_id:
            print(f"skipping {entry.id} unable to parse")

        found = False
        for item in profile_feed_items:
            if post_id in str(item.post.record.facets):
                found = True
                break

        if not found:
            try:
                uri = post_item(client, post_id, image_id, entry.title)
                print(f"posted {entry.id} as {uri}")
            except BadRequestError:
                print(traceback.format_exc())
                print(f"unable to post {entry.id}")
        else:
            print(f"skipping {entry.id} already present")


main()
