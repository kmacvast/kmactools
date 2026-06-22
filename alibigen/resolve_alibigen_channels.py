#!/usr/bin/env python3
import os
import json
import time
import urllib.request
import urllib.parse

CONFIG_PATH = os.path.expanduser("~/.alibigen_cache/slack_channels.json")

def load_existing_credentials():
    """Attempts to pre-load credentials if the config file already exists."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
                token = config.get("slack_token", "")
                cookie = config.get("slack_d_cookie", "")
                existing_channels = config.get("channels", {})
                if token and cookie:
                    return token, cookie, existing_channels
        except Exception:
            pass
    return "", "", {}

def fetch_active_conversations(token, d_cookie):
    """Queries Slack to get channels, active 1-on-1 DMs, and group DMs."""
    channel_map = {}
    dm_list = []
    mpim_list = []
    
    url = "https://slack.com/api/users.conversations"
    params = {
        "types": "public_channel,private_channel,im,mpim",
        "limit": 1000
    }
    
    url_with_params = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url_with_params)
    req.add_header("Authorization", f"Bearer {token}")
    if d_cookie:
        req.add_header("Cookie", f"d={d_cookie}")

    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
            if not data.get("ok"):
                print(f"Error from Slack API: {data.get('error')}")
                return None, None, None
            
            for conv in data.get("channels", []):
                if conv.get("is_mpim"):
                    mpim_list.append(conv["id"])
                elif conv.get("is_im"):
                    dm_list.append({
                        "dm_id": conv["id"],
                        "user_id": conv["user"]
                    })
                else:
                    channel_map[conv["name"]] = conv["id"]
                    
            return channel_map, dm_list, mpim_list
    except Exception as e:
        print(f"Network error during conversation sync: {e}")
        return None, None, None

def get_user_name(token, d_cookie, user_id):
    """Looks up a single user's profile info to extract their name handles."""
    url = f"https://slack.com/api/users.info?user={user_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    if d_cookie:
        req.add_header("Cookie", f"d={d_cookie}")
        
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data.get("ok"):
                user_info = data.get("user", {})
                profile = user_info.get("profile", {})
                names = [
                    user_info.get("name", ""),
                    profile.get("display_name", ""),
                    profile.get("real_name", "")
                ]
                return [n.strip().lower() for n in names if n]
    except Exception:
        pass
    return []

def fetch_mpim_members(token, d_cookie, mpim_id):
    """Retrieves the list of user IDs belonging to a specific group DM."""
    url = f"https://slack.com/api/conversations.members?channel={mpim_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    if d_cookie:
        req.add_header("Cookie", f"d={d_cookie}")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data.get("ok"):
                return data.get("members", [])
    except Exception:
        pass
    return []

def print_pretty_table(channels_dict):
    """Prints out a neatly formatted, sorted ASCII table of currently tracked targets."""
    if not channels_dict:
        return
        
    print("\nCurrently Tracked Channels, People, and Groups:")
    max_name_len = max(max([len(name) for name in channels_dict.keys()]), 30)
    id_len = 15
    
    border = f"+{'-' * (max_name_len + 2)}+{'-' * (id_len + 2)}+"
    header = f"| {'Name / Handle':<{max_name_len}} | {'Slack ID':<{id_len}} |"
    
    print(border)
    print(header)
    print(border)
    
    for name in sorted(channels_dict.keys()):
        print(f"| {name:<{max_name_len}} | {channels_dict[name]:<{id_len}} |")
        
    print(border)

def main():
    print("--- AlibiGen Slack Target Resolver ---")
    
    token, cookie, existing_targets = load_existing_credentials()
    
    if token and cookie:
        print(f"Loaded active session credentials from {CONFIG_PATH}")
        print_pretty_table(existing_targets)
    else:
        print("No active session found. Please provide your browser session data.")
        token = input("Enter your xoxc token: ").strip()
        cookie = input("Enter your d cookie value: ").strip()

    if not token or not cookie:
        print("Error: Both token and cookie are required to authenticate.")
        return

    print("Synchronizing conversation streams...")
    channel_map, dm_list, mpim_list = fetch_active_conversations(token, cookie)
    if channel_map is None:
        print("Failed to look up conversations. Exiting.")
        return

    session_resolved = {}
    user_name_cache = {}
    
    print("\nSynchronization complete. Interactive resolver loop started.")
    print("Enter channel names, individual names, or group DMs.")
    print("Format Notes:")
    print("  - Use COMMAS to split separate lookups: channel_a, person_b")
    print("  - Use + or & to group people inside a group DM: Seb + Tommy Mac")
    print("Press Enter on an empty line or type 'done' to finish searching.")
    print("-" * 50)

    while True:
        raw_input = input("\nEnter target(s): ").strip()
        
        if not raw_input or raw_input.lower() == 'done':
            break
            
        # Split out distinct lookup requests via commas
        lookups = [t.strip() for t in raw_input.split(',') if t.strip()]
        
        for item in lookups:
            # Check if this item is a Group DM lookup (contains '+' or '&')
            if '+' in item or '&' in item:
                group_names = [n.strip().lower().lstrip('@') for n in item.replace('&', '+').split('+') if n.strip()]
                print(f"  Analyzing Group DM request for: {', '.join(group_names)}... ", end="", flush=True)
                
                target_user_ids = []
                for g_name in group_names:
                    found_uid = None
                    for dm in dm_list:
                        uid = dm["user_id"]
                        if uid not in user_name_cache:
                            user_name_cache[uid] = get_user_name(token, cookie, uid)
                            time.sleep(0.05)
                        if any(g_name in name for name in user_name_cache[uid]):
                            found_uid = uid
                            break
                    if found_uid:
                        target_user_ids.append(found_uid)
                
                if len(target_user_ids) != len(group_names):
                    print(f"\r  Not Found:     Could not resolve all individual names in the group '{item}'.")
                    continue
                
                # Scan through group DM list to find an exact membership match
                found_group = False
                for mpim_id in mpim_list:
                    members = fetch_mpim_members(token, cookie, mpim_id)
                    # Group DMs include you, so total members equals targeted users + 1
                    if len(members) == len(target_user_ids) + 1 and all(uid in members for uid in target_user_ids):
                        normalized_group_title = "_".join(group_names)
                        session_resolved[normalized_group_title] = mpim_id
                        print(f"\r  Found Group:   {normalized_group_title} -> {mpim_id}")
                        found_group = True
                        break
                        
                if not found_group:
                    print(f"\r  Not Found:     No active Group DM found matching exactly those members.")
            
            else:
                # Standard channel or individual person resolution path
                target = item.lower().lstrip('@')
                if target in channel_map:
                    cid = channel_map[target]
                    session_resolved[target] = cid
                    print(f"  Found Channel: {target} -> {cid}")
                    continue
                    
                print(f"  Searching open DMs for '{target}'... ", end="", flush=True)
                found_person = False
                for dm in dm_list:
                    uid = dm["user_id"]
                    if uid not in user_name_cache:
                        user_name_cache[uid] = get_user_name(token, cookie, uid)
                        time.sleep(0.05)
                    if any(target in name for name in user_name_cache[uid]):
                        cid = dm["dm_id"]
                        session_resolved[target] = cid
                        print(f"\r  Found Person:  {target} -> {cid}")
                        found_person = True
                        break
                        
                if not found_person:
                    print(f"\r  Not Found:     '{target}' matches no channels or active open DMs.")

    # 4. Save Block
    print("\n" + "-" * 50)
    if not session_resolved:
        print("No new targets were resolved during this session. Exiting without changes.")
        return

    print("Summary of targets resolved this session:")
    for name, cid in session_resolved.items():
        status = " (updates existing)" if name in existing_targets else ""
        print(f"  {name} -> {cid}{status}")

    print(f"\nDo you want to persist these {len(session_resolved)} lookups to {CONFIG_PATH}?")
    confirm = input("Save changes? (y/n): ").strip().lower()

    if confirm in ['y', 'yes']:
        existing_targets.update(session_resolved)
        config_data = {
            "slack_token": token,
            "slack_d_cookie": cookie,
            "channels": existing_targets
        }
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, 'w') as f:
                json.dump(config_data, f, indent=4)
            print(f"Success: Configuration safely updated. Total targets tracked: {len(existing_targets)}")
        except Exception as e:
            print(f"Failed to write configuration file to disk: {e}")
    else:
        print("Save canceled. Lookups discarded.")

if __name__ == "__main__":
    main()