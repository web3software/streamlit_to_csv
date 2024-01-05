import streamlit as st
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import pandas as pd
import os
load_dotenv()
# access_key = os.getenv('discord_authorization_key')
access_key = st.secrets['discord_authorization_key']

def parse_timestamp(timestamp_str):
    try:
        dt = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S.%f%z')
    except ValueError:
        dt = datetime.fromisoformat(timestamp_str)

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt

def get_server_name(guild_id, headers):
    r_guild = requests.get(f'https://discord.com/api/v9/guilds/{guild_id}', headers=headers)
    if r_guild.status_code == 200:
        guild_data = r_guild.json()
        return guild_data.get('name', 'Unknown Server')
    else:
        print(f"Error retrieving guild information for ID {guild_id}. Status code: {r_guild.status_code}")
        return 'Unknown Server'

def retrieve_messages_from_channel(channel_id, server_name, channel_name, headers):
    messages = []
    oldest_message_id = None

    thirty_minutes_ago = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=30)

    url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
    params = {'limit': 100}

    r_channel = requests.get(url, headers=headers, params=params)

    if r_channel.status_code == 200:
        json_data_channel = r_channel.json()
        if not json_data_channel:
            print("No messages in the channel.")
            return messages

        sorted_messages = sorted(json_data_channel, key=lambda x: parse_timestamp(x['timestamp']), reverse=True)
        sorted_messages = [msg for msg in sorted_messages if parse_timestamp(msg['timestamp']) > thirty_minutes_ago]

        if not sorted_messages:
            print("No new messages within the last 30 minutes.")
            return messages

        messages.extend(sorted_messages)
        oldest_message_id = sorted_messages[-1]['id'] if sorted_messages else oldest_message_id

        # for message in sorted_messages:
        #     timestamp = parse_timestamp(message['timestamp'])
        #     author_name = message['author']['username']
        #     original_name = message.get('author', {}).get('member', {}).get('nick', author_name)
        #     content = (message['content'] if message['content'].strip() != "" 
        #                else (message['attachments'][0]['url'] if message['attachments'] else "<Empty Message>"))

            # data = {
            #     'server': server_name,
            #     'channel': channel_name,
            #     'author': author_name,
            #     'original_name': original_name,
            #     'message': content,
            #     'timestamp': timestamp
            # }
            # insert_message(data)  # Store data in the database (you can customize this function)

        return messages
    else:
        print(f"Error retrieving messages from channel {channel_id}. Status code: {r_channel.status_code}")
        return messages


def download_data():
    data = {'server': [], 'channel': [], 'author': [], 'original_name': [], 'message': [], 'timestamp': []}
    group_channels = [
    ('884204406189490176', ['894619517441957908', '895350107137011723', '1174476193165226004', '955488909436014722', '1168298193646276671']),
    ('905908516894670928', ['1014574494502891551', '1100410569892307095', '905962797656055919', '1014989330177077370']),
    ('1131672987502915704', ['1131672988023005206']),
    ('1189002289885749378', ['1189002290426806325'])
]
    headers = {
    'Authorization': access_key
    }
    for group_id, channel_ids in group_channels:
        server_name = get_server_name(group_id, headers)

        r_group = requests.get(f'https://discord.com/api/v9/guilds/{group_id}/channels', headers=headers)
        if r_group.status_code == 200:
            json_data_group = r_group.json()
            for channel_id in channel_ids:
                found_channel = next((channel for channel in json_data_group if channel['id'] == channel_id), None)
                if found_channel:
                    channel_name = found_channel['name']
                    
                    messages = retrieve_messages_from_channel(channel_id, server_name, channel_name, headers)
                    for message in messages:
                        content = (message['content'] if message['content'].strip() != "" 
                        else (message['attachments'][0]['url'] if message['attachments'] else "<Empty Message>"))
                        data['server'].append(server_name)
                        data['channel'].append(channel_name)
                        data['author'].append(message['author']['username'])
                        data['original_name'].append(message.get('author', {}).get('member', {}).get('nick', message['author']['username']))
                        data['message'].append(content)
                        data['timestamp'].append(message['timestamp'])
                else:
                    print(f"Channel with ID {channel_id} not found in the group {group_id}. Skipping...")

    df = pd.DataFrame(data)
    return df

# Streamlit UI
st.title("Discord Data Downloader")

if st.button("Download Data"):
    df = download_data()
    st.write("Downloaded data:")
    st.write(df)
    
    # Save data to Excel
    excel_filename = "discord_data.xlsx"
    df.to_excel(excel_filename, index=False)
    st.success(f"Data saved to {excel_filename}")
