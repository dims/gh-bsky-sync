import argparse
import json
import os
import pathlib
import time
from datetime import datetime
from datetime import timezone

import chitose
import requests
import urllib.error
import yaml
from chitose.app.bsky.feed.post import Post

parser = argparse.ArgumentParser()
parser.add_argument(
    "-f",
    "--follow",
    action="store_true",
)
parser.add_argument(
    "-s",
    "--skip-list",
    action="store_true",
)
args = parser.parse_args()


def extract_members(data):
    members = set()

    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'members' or key == 'admins':
                members.update(value)
            elif isinstance(value, (dict, list)):
                members.update(extract_members(value))
    elif isinstance(data, list):
        for item in data:
            members.update(extract_members(item))

    return members


def find_and_parse_org_yaml(root_dir):
    all_members = set()

    urls = [
        "https://raw.githubusercontent.com/kubernetes/org/refs/heads/main/config/kubernetes-sigs/org.yaml",
        "https://raw.githubusercontent.com/kubernetes/org/refs/heads/main/onfig/kubernetes-incubator/org.yaml",
        "https://raw.githubusercontent.com/kubernetes/org/refs/heads/main/config/kubernetes-retired/org.yaml",
        "https://raw.githubusercontent.com/kubernetes/org/refs/heads/main/config/etcd-io/org.yaml",
        "https://raw.githubusercontent.com/kubernetes/org/refs/heads/main/org/config/kubernetes-nightly/org.yaml",
        "https://raw.githubusercontent.com/kubernetes/org/refs/heads/main/config/kubernetes-client/org.yaml",
        "https://raw.githubusercontent.com/kubernetes/org/refs/heads/main/config/kubernetes-csi/org.yaml",
        "https://raw.githubusercontent.com/kubernetes/org/refs/heads/main/config/kubernetes/org.yaml"
    ]
    for url in urls:
        print(f"Processing: {url}")
        try:
            parsed_data = yaml.safe_load(requests.get(url).text)
            members = extract_members(parsed_data)
            all_members.update(members)
        except yaml.YAMLError as e:
            print(f"Error parsing YAML file {url}: {e}")
        except IOError as e:
            print(f"Error reading file {url}: {e}")

    return all_members


github_token = os.environ.get('GH_TOKEN')


def get_bluesky_account(agent, username):
    if not github_token:
        raise ValueError("GH_TOKEN environment variable is not set")

    url = f"https://api.github.com/users/{username}/social_accounts"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        accounts = response.json()
        for account in accounts:
            if account['provider'] == 'bluesky':
                actor = account['url'].split('/')[-1]
                response = parse_json_from_bytes(agent.app.bsky.actor.get_profiles(actors=actor))
                for profile in response["profiles"]:
                    return profile["handle"], profile["did"]
    elif response.status_code == 404:
        return None, None
    else:
        print(f"Error for user {username}: {response.status_code}")
    return None, None


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


def main():
    # Specify the root directory to start the search
    root_directory = str(pathlib.Path.home()) + '/go/src/k8s.io/org'

    # Find and parse all org.yaml files
    all_members = find_and_parse_org_yaml(root_directory)

    bsky_id = os.environ.get('BSKY_ID')
    bsky_password = os.environ.get('BSKY_PASSWORD')
    if not bsky_id or not bsky_password:
        raise ValueError("BSKY_ID/BSKY_PASSWORD environment variables should be set")

    agent = chitose.BskyAgent(service='https://bsky.social')
    agent.login(identifier=bsky_id, password=bsky_password)

    handle = "dims.dev"
    response = parse_json_from_bytes(agent.app.bsky.actor.get_profile(handle))
    actor_did = response["did"]
    print(handle + " = " + actor_did)

    list_name = "Kubernetes Community/GitHub org members"
    list_uri = ""
    response = parse_json_from_bytes(agent.app.bsky.graph.get_lists(handle))
    for list in response["lists"]:
        if list["name"] == list_name:
            list_uri = list["uri"]
    print(list_name + " = " + list_uri)

    # Print the results
    print(f"\nTotal number of unique members across all org.yaml files: {len(all_members)}")
    print("All members:")

    existing_members = get_existing_members(agent, list_uri)
    map_handle_did = {}

    existing_followings = get_followings(agent, bsky_id)

    for member in sorted(all_members):
        bsky_handle, bsky_did = get_bluesky_account(agent, member)
        if bsky_handle and bsky_did:
            if args.follow:
                is_following = any(follow["did"] == bsky_did or follow["handle"] == bsky_handle for follow in existing_followings)
                if not is_following:
                    agent.follow(bsky_did)
                    print(f"following {member} / {bsky_handle} = {bsky_did}")
                else:
                    print(f"Skipping already following : {member}  / {bsky_handle} = {bsky_did}")
            if not args.skip_list:
                found = False
                for item in existing_members:
                    if item["subject"]["did"] == bsky_did:
                        found = True
                        break
                if found:
                    print(f"Skipping already present : {member}  / {bsky_handle} = {bsky_did}")
                else:
                    print(f"Adding : {member}  / {bsky_handle} = {bsky_did}")
                    map_handle_did[bsky_handle] = bsky_did
                    record = {
                        '$type': 'app.bsky.graph.listitem',
                        'subject': bsky_did,
                        'list': list_uri,
                        'createdAt': datetime.now(timezone.utc).isoformat(),
                    }
                    try:
                        agent.com.atproto.repo.create_record(
                            repo=actor_did,
                            collection='app.bsky.graph.listitem',
                            record=record
                        )
                    except urllib.error.HTTPError as err:
                        print(f">>>> HTTPError - Unable to add {member}: {err.msg}")
        time.sleep(.1)

    if len(map_handle_did) > 0:
        post_message(agent, map_handle_did)


def get_followings(agent, bsky_id):
    cursor = ""
    existing_followings = []
    while True:
        response = parse_json_from_bytes(agent.app.bsky.graph.get_follows(actor=bsky_id, cursor=cursor))
        if len(response["follows"]) == 0:
            break
        existing_followings.extend(response["follows"])
        if "cursor" not in response:
            break
        cursor = response["cursor"]
    return existing_followings


def find_byte_array(haystack: bytes, needle: bytes) -> tuple[int, int]:
    start = haystack.find(needle)
    if start != -1:
        end = start + len(needle)
        return start, end
    return -1, -1


def get_index(haystack, needle):
    start, end = find_byte_array(bytes(haystack, "utf-8"), bytes(needle, "utf-8"))
    return {
        'byteEnd': end, 'byteStart': start
    }


def post_message(agent, map_handle_did):
    embed = {
        '$type': 'app.bsky.embed.record',
        'record':
            {
                'cid': 'bafyreidsidmzftmp3g736d3zargqrvoibhy7dlgkpnkileyuqm7wd7ge7m',
                'uri': 'at://did:plc:kfztyuziv2i44b5kpecth77y/app.bsky.graph.list/3lau2wjkn3g2s'
            }
    }

    text = "Hi! "
    for key, value in map_handle_did.items():
        text += f"@{key} "
    text += " - added you to go.k8s.io/bsky (list for k8s GitHub org members)."
    text += "\n\n@kubernetes.dev #kubernetes"

    facets = [
        {
            'features': [
                {
                    '$type': 'app.bsky.richtext.facet#link',
                    'uri': 'https://bsky.app/profile/did:plc:kfztyuziv2i44b5kpecth77y/lists/3lau2wjkn3g2s'
                }
            ],
            'index': get_index(text, "go.k8s.io/bsky")
        },
        {
            'features': [
                {
                    '$type': 'app.bsky.richtext.facet#tag', 'tag': 'kubernetes'
                }
            ],
            'index': get_index(text, "#kubernetes")
        },
        {
            '$type': 'app.bsky.richtext.facet',
            'features': [
                {
                    '$type': 'app.bsky.richtext.facet#mention',
                    'did': 'did:plc:v6ps63hssmxoznrgwbyxmqcx'
                }
            ],
            'index': get_index(text, "@kubernetes.dev")
        },
    ]

    for key, value in map_handle_did.items():
        facets += [{
            '$type': 'app.bsky.richtext.facet',
            'features': [
                {
                    '$type': 'app.bsky.richtext.facet#mention',
                    'did': f'{value}'
                }
            ],
            'index': get_index(text, f"@{key}")
        }]

    record = Post(text=text,
                  embed=embed,
                  facets=facets,
                  created_at=datetime.now(timezone.utc).isoformat())
    agent.com.atproto.repo.create_record(
        repo=agent.session['did'], collection='app.bsky.feed.post', record=record)
    print(f"Posted message : {text}")


def get_existing_members(agent, list_uri):
    cursor = ""
    members = []
    while True:
        response = parse_json_from_bytes(agent.app.bsky.graph.get_list(list_uri, cursor=cursor))
        if len(response["items"]) == 0:
            break
        members.extend(response["items"])
        if "cursor" not in response:
            break
        cursor = response["cursor"]

    return members


main()
