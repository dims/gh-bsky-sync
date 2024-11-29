import os
from atproto import Client, client_utils
import feedparser
import json
import re
import requests
from atproto_client.utils import TextBuilder
import requests


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
        'https://nitter.poast.org/ImShahinyan/rss',
        request_headers={
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9,it;q=0.8',
            'cache-control': 'max-age=0',
            'cookie': 'res=69C35A40B4CE1ABFDDA1764EA815CCEB7F305C08129443',
            'dnt': '1',
            'priority': 'u=0, i',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'sec-gpc': '1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        },
    )
    return response.entries

def post_item(client, post_id, image_id, text):
    image_url = f"https://pbs.twimg.com/media/{image_id}?format=png&name=900x900"
    image_response = requests.get(image_url)
    if image_response.status_code == 200:
        image_data = image_response.content
    else:
        raise Exception(f"Failed to fetch image from {image_url}")
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

def main():
    bsky_id = os.environ.get('BSKY_ID')
    bsky_password = os.environ.get('BSKY_PASSWORD')
    if not bsky_id or not bsky_password:
        raise ValueError("BSKY_ID/BSKY_PASSWORD environment variables should be set")

    client = Client()
    profile = client.login(bsky_id, bsky_password)
    print('Welcome,', profile.display_name)

    profile_feed_items = get_profile_feed(client, bsky_id)

    for entry in get_mate_in_2_posts():
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
            uri = post_item(client, post_id, image_id, entry.title)
            print(f"posted {entry.id} as {uri}")
        else:
            print(f"skipping {entry.id} already present")


main()
