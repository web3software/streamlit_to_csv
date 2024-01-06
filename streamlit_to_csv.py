import streamlit as st
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import pandas as pd
import os
import shutil
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
# from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options 
from selenium.webdriver.common.by import By

load_dotenv()
access_key = os.getenv('discord_authorization_key')
# access_key = st.secrets['discord_authorization_key']

@st.cache_resource(show_spinner=False)
def get_logpath():
    return os.path.join(os.getcwd(), 'selenium.log')


@st.cache_resource(show_spinner=False)
def get_chromedriver_path():
    return shutil.which('chromedriver')


@st.cache_resource(show_spinner=False)
def get_webdriver_options():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-features=NetworkService")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--disable-features=VizDisplayCompositor")
    return options


def get_webdriver_service():
    service = Service(
        executable_path=get_chromedriver_path()
    )
    return service


def delete_selenium_log(logpath):
    if os.path.exists(logpath):
        os.remove(logpath)


def show_selenium_log(logpath):
    if os.path.exists(logpath):
        with open(logpath) as f:
            content = f.read()
            st.code(body=content, language='log', line_numbers=True)
    else:
        st.warning('No log file found!')

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
    with st.spinner("Downloading data..."):
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

def scrape_article_info(url):

    with st.spinner("Scrapping data..."):
        driver = webdriver.Chrome(service=get_webdriver_service(logpath=logpath), options=get_webdriver_options())
        driver.get(url)  
        driver.implicitly_wait(5)

        # Extract article name
        article_name_element = driver.find_elements(By.TAG_NAME, 'h1')
        article_name = article_name_element[0].text.strip()

        # Extract article date
        time_element = driver.find_element(By.XPATH, "//time[@datetime]")
        article_date = time_element.text.strip()

        # Extract image URL
        div_element_image = driver.find_element(By.XPATH, "//div[contains(@class, 'gg-dark:p-1')]")
        img_element = div_element_image.find_element(By.TAG_NAME, 'img')
        img_url = img_element.get_attribute('src')

        # Extract article content
        div_element = driver.find_element(By.XPATH, "//div[contains(@class, 'grid grid-cols-1 md:grid-cols-8 unreset post-content md:pb-20')]")
        p_elements = div_element.find_elements(By.XPATH, ".//p[contains(@class, 'font-meta-serif-pro scene:font-noto-sans scene:text-base scene:md:text-lg font-normal text-lg md:text-xl md:leading-9 tracking-px text-body gg-dark:text-neutral-100')]")
        article_content = '\n'.join([p.text.strip() for p in p_elements])

        driver.quit()

        return article_name, article_date, img_url, article_content

# Function to run code for Tab 1
def run_tab1():
    st.subheader("Tab 1: Current Script")
    if st.button("Download Data"):
        df = download_data()
        st.write("Downloaded data:")
        st.write(df)

        # Save data to Excel
        excel_filename = "discord_data.xlsx"
        df.to_excel(excel_filename, index=False)
        st.success(f"Data saved to {excel_filename}")

# Function to run code for Tab 2
def run_tab2():
    st.title("Article Information")

    base_url = 'https://decrypt.co/news'
    response = requests.get(base_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    article_containers = soup.find_all('div', class_='mb-5 pb-5 last-of-type:mb-0')
    for container in article_containers:
        link = container.find('a', class_='linkbox__overlay')
        if link:
            href = link.get('href')
            full_url = f"https://decrypt.co/{href}" 

            article_name, article_date, img_url, article_content = scrape_article_info(full_url)

            # Display article information in a tabular form
            st.write(f"## {article_name}")
            st.write(f"**Date:** {article_date}")
            st.image(img_url, caption="Image", use_column_width=True)
            st.write("### Article Content:")
            st.write(article_content)

            st.markdown("---")  # Add a horizontal line between articles

# Function code for the second tab...
def run_tab3():
    st.subheader("Tab 3: Other Code")
    # Function code for the second tab...

# Main Streamlit UI
st.title("Discord Data Downloader")

# Create tabs using st.selectbox
selected_tab = st.selectbox("Select Tab", ["Discord", "News","YouTube"])

# Display content based on the selected tab
if selected_tab == "Discord":
    run_tab1()
elif selected_tab == "News":
    run_tab2()
elif selected_tab == "YouTube":
    run_tab3()