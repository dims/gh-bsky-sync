import json
import os
import time
import urllib.error

import chitose


def parse_json_from_bytes(json_bytes):
    try:
        # Decode bytes to string
        json_string = json_bytes.decode('utf-8')

        # Parse JSON string
        parsed_data = json.loads(json_string)

        return parsed_data
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")
        return None
    except UnicodeDecodeError as e:
        print(f"Unicode decoding error: {e}")
        return None


def unfollow(agent, bsky_id):
    cursor = ""
    followings = []
    while True:
        response = parse_json_from_bytes(agent.app.bsky.graph.get_follows(actor=bsky_id, cursor=cursor))
        if len(response["follows"]) == 0:
            break
        followings.extend(response["follows"])
        if "cursor" not in response:
            break
        cursor = response["cursor"]
    for following in followings:
        if "following" not in following["viewer"]:
            continue
        parts = following["viewer"]["following"].rsplit('/', 3)
        repo = parts[1]
        rkey = parts[3]
        response = parse_json_from_bytes(agent.app.bsky.actor.get_profiles(actors=following["handle"]))
        if (len(response["profiles"]) == 0 or
                response["profiles"][0]["postsCount"] < 5 or
                response["profiles"][0]["followersCount"] < 5 or
                response["profiles"][0]["followsCount"] < 5):
            print(f"Unfollowing {following['handle']} using repo {repo} and key {rkey}")
            try:
                response = parse_json_from_bytes(agent.com.atproto.repo.delete_record(
                    collection='app.bsky.graph.follow',
                    repo=repo,
                    rkey=rkey
                ))
                # print(response)
            except urllib.error.HTTPError as e:
                print(f"HTTP Error: {e.code}")
                print("snoozing....")
                time.sleep(5)
            except urllib.error.URLError as e:
                print(f"URL Error: {e.reason}")
                print("snoozing....")
                time.sleep(5)
            time.sleep(0.1)


def main():
    bsky_id = os.environ.get('BSKY_ID')
    bsky_password = os.environ.get('BSKY_PASSWORD')
    if not bsky_id or not bsky_password:
        raise ValueError("BSKY_ID/BSKY_PASSWORD environment variables should be set")

    agent = chitose.BskyAgent(service='https://bsky.social')
    agent.login(identifier=bsky_id, password=bsky_password)

    unfollow(agent, bsky_id)


main()
