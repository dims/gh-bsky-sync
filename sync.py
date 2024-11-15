import argparse
import json
import os
import pathlib
import time
from datetime import datetime
from datetime import timezone

import chitose
import requests
import yaml

parser = argparse.ArgumentParser()
parser.add_argument(
    "-f",
    "--follow",
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
                    return profile["did"]
    elif response.status_code == 404:
        return None
    else:
        print(f"Error for user {username}: {response.status_code}")
        return None


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

    response = parse_json_from_bytes(agent.app.bsky.graph.get_list(list_uri))
    existing_members = response["items"]

    for member in sorted(all_members):
        bsky_id = get_bluesky_account(agent, member)
        if bsky_id:
            if args.follow:
                agent.follow(bsky_id)
                print(f"following {member} = {bsky_id}")
            found = False
            for item in existing_members:
                if item["subject"]["did"] == bsky_id:
                    found = True
                    break
            if found:
                print("Skipping already present : " + member + " = " + bsky_id)
            else:
                print("Adding : " + member + " = " + bsky_id)
                record = {
                    '$type': 'app.bsky.graph.listitem',
                    'subject': bsky_id,
                    'list': list_uri,
                    'createdAt': datetime.now(timezone.utc).isoformat(),
                }
                agent.com.atproto.repo.create_record(
                    repo=actor_did,
                    collection='app.bsky.graph.listitem',
                    record=record
                )
        time.sleep(.1)


main()
