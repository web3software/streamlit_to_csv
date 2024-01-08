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
from selenium.webdriver.chrome.options import Options 
from selenium.webdriver.common.by import By
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi
import googleapiclient.discovery

load_dotenv()
access_key = os.getenv('discord_authorization_key')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'service_key.json'
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

    thirty_minutes_ago = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=180)

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
        driver = webdriver.Chrome(service=get_webdriver_service(), options=get_webdriver_options())
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

def get_channel_info(api_key, channel_id):
    api_service_name = "youtube"
    api_version = "v3"

    youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=api_key)

    request = youtube.channels().list(
        part="snippet,contentDetails,statistics",
        id=channel_id
    )

    try:
        response = request.execute()
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def get_latest_videos(api_key, channel_id, max_results=5):
    api_service_name = "youtube"
    api_version = "v3"

    youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=api_key)

    request = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        order="date",
        type="video",
        maxResults=max_results
    )

    try:
        response = request.execute()
        return response.get("items", [])
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def get_english_subtitles(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        return transcript
    except Exception as e:
        print(f"An error occurred while fetching English subtitles: {e}")
        return []

def get_youtuber_info(api_key, channel_id):
    channel_info = get_channel_info(api_key, channel_id)
    if channel_info:
        return {
            'id': channel_info['items'][0]['id'],
            'title': channel_info['items'][0]['snippet']['title'],
            'subscriber_count': channel_info['items'][0]['statistics']['subscriberCount']
        }
    else:
        return None

def fetch_video_details(video_url, developer_key, channel_id):
    try:
        yt = YouTube(video_url)
        subtitles = get_subtitles_string(yt.video_id)
        youtuber_info = get_youtuber_info(developer_key, channel_id)
        st.subheader("\nVideo Details:")
        st.write(f"Title: {yt.title}")
        st.write(f"YouTuber Name: {youtuber_info['title']}")
        st.write(f"Published At: {yt.publish_date}")
        st.write(f"Duration: {yt.length} seconds")
        st.write(f"Views: {yt.views}")
        st.subheader("Subtitles")
        st.write(subtitles)

    except Exception as e:
        print(f"An error occurred: {e}")

def get_subtitles_string(video_id):
    subtitles = get_english_subtitles(video_id)
    if subtitles:
        # Concatenate subtitles into a string
        return '\n'.join(entry['text'] for entry in subtitles)
    else:
        return "No English subtitles found."


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
    with st.spinner("Scrapping data..."):
        base_url = 'https://www.coindesk.com/tag/news/'
        response = requests.get(base_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        h6_tags = soup.find_all('h6', class_="typography__StyledTypography-sc-owin6q-0 diMXjy")

        for h6_tag in h6_tags:
            link = h6_tag.find('a', class_="card-title")

            if link:
                href = link.get('href')
                full_url = f'https://www.coindesk.com/{href}'
                response = requests.get(full_url)
                article_soup = BeautifulSoup(response.text, 'html.parser')

                article_name_element = article_soup.find('h1', class_="typography__StyledTypography-sc-owin6q-0 bSOJsQ")

                if article_name_element:
                    article_name = article_name_element.text.strip()
                    st.write(f'# Article Name: {article_name}')

                    date_time_div = article_soup.find('div', class_="at-created label-with-icon")
                    if date_time_div:
                        date_time_span = date_time_div.find('span', class_="typography__StyledTypography-sc-owin6q-0 hcIsFR")
                        date_time_text = date_time_span.text.strip()
                        st.write(f'Date and Time: {date_time_text}')
                    else:
                        alt_date_time_div = article_soup.find('div', class_="align-right")
                        alt_date_time_span = alt_date_time_div.find('span', class_="typography__StyledTypography-sc-owin6q-0 hcIsFR")
                        alt_date_time_text = alt_date_time_span.text.strip() if alt_date_time_span else 'Date and Time not found'
                        st.write(f'Date and Time (Alternative): {alt_date_time_text}')

                    main_div = article_soup.find('div', class_='featured-imagestyles__FeaturedImageWrapper-sc-ojmof1-0 jGviVP at-rail-aligner at-rail-aligner-fi')

                    if main_div:
                        picture_tag = main_div.find('picture', class_='responsive-picturestyles__ResponsivePictureWrapper-sc-1urqrom-0 iLCXlQ')

                        if picture_tag:
                            img_tag = picture_tag.find('img')
                            image_url = img_tag['src'] if img_tag else 'Image not found'
                            st.image(image_url, caption='Article Image', use_column_width=True)
                        else:
                            st.write('Image not found within main div.')
                    else:
                        main_div2 = article_soup.find('div', class_='featured-imagestyles__FeaturedImageWrapper-sc-ojmof1-0 jGviVP featured-media featured-media-fi')
                        if main_div2:
                            picture_tag2 = main_div2.find('picture', class_='responsive-picturestyles__ResponsivePictureWrapper-sc-1urqrom-0 iLCXlQ')

                            if picture_tag2:
                                img_tag2 = picture_tag2.find('img')
                                image_url2 = img_tag2['src'] if img_tag2 else 'Image not found'
                                st.image(image_url2, caption='Article Image', use_column_width=True)
                            else:
                                st.write('Image not found within picture tag.')
                        else:
                            st.write('Image not in article.')

                    divs = article_soup.find_all('div', class_=["common-textstyles__StyledWrapper-sc-18pd49k-0 eSbCkN"])
                    st.header('Article Content')
                    for div in divs:
                        p_tags = div.find_all('p')
                        for p_tag in p_tags:
                            p_text = p_tag.text.strip()
                            st.write(p_text)
                else:
                    st.write('Article Name not found. Moving to the next article.\n')

                # Add a separator between articles
                st.markdown("---")

# Function code for the second tab...
def run_tab4():
    st.subheader("Tab 4: Other Code")
    with st.spinner("Scrapping data..."):
        DEVELOPER_KEY = os.getenv('YOUTUBE_API_KEY')
        CHANNEL_IDS = ['UCfdrZpVbXl_HnmyYYo-N6Ig', 'UCk6jF6z-IZx4H00QTYlHwjw', 'UCMtJYS0PrtiUwlk6zjGDEMA', 'UCKQvGU-qtjEthINeViNbn6A', 'UCqK_GSMbpiV8spgD3ZGloSw', 'UCBCbEDO5tMP6saX9yNU_zYQ','UCN9Nj4tjXbVTLYWN0EKly_Q']

        for channel_id in CHANNEL_IDS:
            latest_videos = get_latest_videos(DEVELOPER_KEY, channel_id)
            if latest_videos:
                print(f"\nLatest Videos for Channel {channel_id}:")
                for video in latest_videos:
                    video_id = video['id']['videoId']
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    fetch_video_details(video_url, DEVELOPER_KEY, channel_id)
            else:
                print(f"No videos found for Channel {channel_id}.")

# Main Streamlit UI
st.title("DATA SCRAPPER")

# Create tabs using st.selectbox
selected_tab = st.selectbox("Select Tab", ["Discord", "Decrypt News","Coin Desk News","YouTube"])

# Display content based on the selected tab
if selected_tab == "Discord":
    run_tab1()
elif selected_tab == "Decrypt News":
    run_tab2()
elif selected_tab == "Coin Desk News":
    run_tab3()
elif selected_tab == "YouTube":
    run_tab4()