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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
import json


load_dotenv()
service_key = {
  "type": st.secrets['type'],
  "project_id": st.secrets['project_id'],
  "private_key_id": st.secrets['private_key_id'],
  "private_key": st.secrets['private_key'],
  "client_email": st.secrets['client_email'],
  "client_id": st.secrets['client_id'],
  "auth_uri": st.secrets['auth_uri'],
  "token_uri": st.secrets['token_uri'],
  "auth_provider_x509_cert_url": st.secrets['auth_provider_x509_cert_url'],
  "client_x509_cert_url": st.secrets['client_x509_cert_url'],
  "universe_domain": st.secrets['universe_domain']
}

temp_key_file_path = "service_key.json"
with open(temp_key_file_path, "w") as key_file:
    json.dump(service_key, key_file)

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_key_file_path

access_key = st.secrets['discord_authorization_key']
# access_key = os.getenv('discord_authorization_key')
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

def retrieve_messages_from_channel(channel_id, server_name, channel_name, headers, minutes):
    messages = []
    oldest_message_id = None

    current_time_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    time_threshold = current_time_utc - timedelta(minutes=minutes)

    url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
    params = {'limit': 100}

    r_channel = requests.get(url, headers=headers, params=params)

    if r_channel.status_code == 200:
        json_data_channel = r_channel.json()
        if not json_data_channel:
            print("No messages in the channel.")
            return messages

        sorted_messages = sorted(json_data_channel, key=lambda x: parse_timestamp(x['timestamp']), reverse=True)
        sorted_messages = [msg for msg in sorted_messages if parse_timestamp(msg['timestamp']) > time_threshold]

        if not sorted_messages:
            print(f"No new messages within the last {minutes} minutes.")
            return messages

        messages.extend(sorted_messages)
        oldest_message_id = sorted_messages[-1]['id'] if sorted_messages else oldest_message_id

        return messages
    else:
        print(f"Error retrieving messages from channel {channel_id}. Status code: {r_channel.status_code}")
        return messages

def download_data(minutes):
    with st.spinner(f"Downloading data for the last {minutes} minutes..."):
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
                        
                        messages = retrieve_messages_from_channel(channel_id, server_name, channel_name, headers, minutes)
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

# def scrape_article_info(url):

#     with st.spinner("Scrapping data..."):
#         driver = webdriver.Chrome(service=get_webdriver_service(), options=get_webdriver_options())
#         driver.get(url)  
#         driver.implicitly_wait(5)

#         # Extract article name
#         article_name_element = driver.find_elements(By.TAG_NAME, 'h1')
#         article_name = article_name_element[0].text.strip()

#         # Extract article date
#         time_element = driver.find_element(By.XPATH, "//time[@datetime]")
#         article_date = time_element.text.strip()

#         # Extract image URL
#         div_element_image = driver.find_element(By.XPATH, "//div[contains(@class, 'gg-dark:p-1')]")
#         img_element = div_element_image.find_element(By.TAG_NAME, 'img')
#         img_url = img_element.get_attribute('src')

#         # Extract article content
#         div_element = driver.find_element(By.XPATH, "//div[contains(@class, 'grid grid-cols-1 md:grid-cols-8 unreset post-content md:pb-20')]")
#         p_elements = div_element.find_elements(By.XPATH, ".//p[contains(@class, 'font-meta-serif-pro scene:font-noto-sans scene:text-base scene:md:text-lg font-normal text-lg md:text-xl md:leading-9 tracking-px text-body gg-dark:text-neutral-100')]")
#         article_content = '\n'.join([p.text.strip() for p in p_elements])

#         driver.quit()

#         return article_name, article_date, img_url, article_content
    
def scrape_article_info(url):
    with st.spinner("Scraping data..."):
        driver = webdriver.Chrome(service=get_webdriver_service(), options=get_webdriver_options())
        driver.get(url)  
        driver.implicitly_wait(5)

        # Extract article name
        article_name_element = driver.find_elements(By.TAG_NAME, 'h1')
        article_name = article_name_element[0].text.strip()

        # Extract article date
        # time_element = driver.find_element(By.XPATH, "//time[@datetime]")
        wait = WebDriverWait(driver, 10)  # Adjust the timeout as needed
        time_element = wait.until(EC.presence_of_element_located((By.XPATH, "//time[@datetime]")))
        article_date = time_element.text.strip()

        # Extract image URL
        div_element_image = driver.find_element(By.XPATH, "//div[contains(@class, 'gg-dark:p-1')]")
        img_element = div_element_image.find_element(By.TAG_NAME, 'img')
        img_url = img_element.get_attribute('src')

        # Try the first XPath for article content
        try:
            div_element = driver.find_element(By.XPATH, "//div[contains(@class, 'grid grid-cols-1 md:grid-cols-8 unreset post-content md:pb-20')]")
            p_elements = div_element.find_elements(By.XPATH, ".//p[contains(@class, 'font-meta-serif-pro scene:font-noto-sans scene:text-base scene:md:text-lg font-normal text-lg md:text-xl md:leading-9 tracking-px text-body gg-dark:text-neutral-100')]")
            article_content = '\n'.join([p.text.strip() for p in p_elements])
        except NoSuchElementException:
            # If the first XPath fails, try the second XPath
            try:
                div_element = driver.find_element(By.XPATH, "//span[contains(text())]")
                p_elements = div_element.find_elements(By.XPATH, ".//p")
                article_content = '\n'.join([p.text.strip() for p in p_elements])
            except NoSuchElementException:
                article_content = "Unable to extract article content"

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

# def get_latest_videos(api_key, channel_id, max_results=5):
#     api_service_name = "youtube"
#     api_version = "v3"

#     youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=api_key)

#     request = youtube.search().list(
#         part="snippet",
#         channelId=channel_id,
#         order="date",
#         type="video",
#         maxResults=max_results
#     )

#     try:
#         response = request.execute()
#         return response.get("items", [])
#     except Exception as e:
#         print(f"An error occurred: {e}")
#         return []

def get_latest_videos(api_key, channel_id, max_results=5):
    api_service_name = "youtube"
    api_version = "v3"

    youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey=api_key)

    request = youtube.channels().list(
        part="contentDetails",
        id=channel_id
    )

    try:
        response = request.execute()
        uploads_playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=max_results
        )

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
        st.write(f"Video URL: {yt.watch_url}")
        st.write(f"Title: {yt.title}")
        st.write(f"YouTuber Name: {youtuber_info['title']}")
        st.write(f"Published At: {yt.publish_date}")
        st.write(f"Duration: {yt.length} seconds")
        st.write(f"Views: {yt.views}")
        st.subheader("Subtitles")
        # st.write(subtitles)
        if subtitles:
            st.write(subtitles[:200])
            st.write("...")
            st.write(subtitles[-200:])

    except Exception as e:
        print(f"An error occurred: {e}")

def get_subtitles_string(video_id):
    subtitles = get_english_subtitles(video_id)
    if subtitles:
        # Concatenate subtitles into a string
        return '\n'.join(entry['text'] for entry in subtitles)
    else:
        return "No English subtitles found."

def scrape_and_display_article(url):
    response = requests.get(url)
    article_soup = BeautifulSoup(response.text, 'html.parser')

    article_name_element = article_soup.find('h1', class_="typography__StyledTypography-sc-owin6q-0 bSOJsQ")
    if article_name_element:
        article_name = article_name_element.text.strip()
        st.write(f'# {article_name}')

        main_div = article_soup.find('div', class_='featured-imagestyles__FeaturedImageWrapper-sc-ojmof1-0 jGviVP at-rail-aligner at-rail-aligner-fi')
        if not main_div:
            main_div = article_soup.find('div', class_='featured-imagestyles__FeaturedImageWrapper-sc-ojmof1-0 jGviVP featured-media featured-media-fi')

        if main_div:
            picture_tag = main_div.find('picture', class_='responsive-picturestyles__ResponsivePictureWrapper-sc-1urqrom-0 iLCXlQ')
            if picture_tag:
                img_tag = picture_tag.find('img')
                if img_tag:
                    image_url = img_tag['src']
                    st.image(image_url, caption='Article Image', use_column_width=True)
                else:
                    st.write('Img tag not found within picture tag.')
            else:
                st.write('Picture tag not found within main div.')
        else:
            st.write('Image not in article.')

        date_time_div = article_soup.find('div', class_="at-created label-with-icon")
        if not date_time_div:
            date_time_div = article_soup.find('div', class_="align-right")

        if date_time_div:
            date_time_span = date_time_div.find('span', class_="typography__StyledTypography-sc-owin6q-0 hcIsFR")
            date_time_text = date_time_span.text.strip()
            st.write(f'## Date and Time\n{date_time_text}')
        else:
            st.write('Date and Time not found')

        divs = article_soup.find_all('div', class_=["common-textstyles__StyledWrapper-sc-18pd49k-0 eSbCkN"])
        for div in divs:
            p_tags = div.find_all('p')
            for p_tag in p_tags:
                p_text = p_tag.text.strip()
                st.markdown(f'{p_text}\n\n')
    else:
        st.write('Article Name not found. Moving to the next article.\n')

# Function to run code for Tab 1
# def run_tab1():
#     st.subheader("Tab 1: Current Script")
#     if st.button("Download Data"):
#         df = download_data()
#         st.write("Downloaded data:")
#         st.write(df)

#         # Save data to Excel
#         excel_filename = "discord_data.xlsx"
#         df.to_excel(excel_filename, index=False)
#         st.success(f"Data saved to {excel_filename}")
def run_tab1():
    st.subheader("Tab 1: Discord Data Scraper")
    minutes = st.number_input("Enter the number of minutes to retrieve data:", value=30, min_value=1)
    if st.button("Download Data"):
        df = download_data(minutes)
        st.write("Downloaded data:")
        st.write(df)

        # Save data to Excel
        excel_filename = "discord_data.xlsx"
        df.to_excel(excel_filename, index=False)
        st.success(f"Data saved to {excel_filename}")


# Function to run code for Tab 2
# def run_tab2():
    # st.title("Article Information")

    # base_url = 'https://decrypt.co/news'
    # response = requests.get(base_url)
    # soup = BeautifulSoup(response.text, 'html.parser')
    # article_containers = soup.find_all('div', class_='mb-5 pb-5 last-of-type:mb-0')
    # for container in article_containers:
    #     link = container.find('a', class_='linkbox__overlay')
    #     if link:
    #         href = link.get('href')
    #         full_url = f"https://decrypt.co/{href}" 

    #         article_name, article_date, img_url, article_content = scrape_article_info(full_url)

    #         # Display article information in a tabular form
    #         st.write(f"## {article_name}")
    #         st.write(f"**Date:** {article_date}")
    #         st.image(img_url, caption="Image", use_column_width=True)
    #         st.write("### Article Content:")
    #         st.write(article_content)

    #         st.markdown("---")  # Add a horizontal line between articles

# def run_tab2():
#     st.title("Article Information")
#     #num_articles = st.number_input("Enter the number of articles to retrieve:", value=1, min_value=1, step=1)

#     base_url = 'https://decrypt.co/news'
#     response = requests.get(base_url)
#     soup = BeautifulSoup(response.text, 'html.parser')
#     first_containers = soup.find_all('div', class_='mt-2 md:col-span-4 md:mt-0')
#     second_containers = soup.find_all('h3', class_="font-medium xl:font-normal mt-1 font-akzidenz-grotesk text-black gg-dark:text-neutral-100 gg-dark:font-poppins scene:font-itc-avant-garde-gothic-pro scene:font-medium scene:mt-2 degen-alley-dark:text-white text-base leading-4.5 xl:text-xl xl:leading-6")
#     third_containers = soup.find_all('h3', class_="font-medium mt-1 font-akzidenz-grotesk text-black gg-dark:text-neutral-100 gg-dark:font-poppins scene:font-itc-avant-garde-gothic-pro scene:font-medium scene:mt-2 degen-alley-dark:text-white text-base leading-4.5 xl:text-xl xl:leading-6")
#     article_containers = soup.find_all('div', class_='mb-5 pb-5 last-of-type:mb-0')

#     for fisrt in first_containers:
#         first_links = fisrt.find('a', class_='linkbox__overlay')
#         if first_links:
#             hrefs = first_links.get('href')
#             full_url = f"https://decrypt.co{hrefs}"

#             article_name, article_date, img_url, article_content = scrape_article_info(full_url)

#             # Display article information in a tabular form
#             st.write(f"##. {article_name}")
#             st.write(f"**Date:** {article_date}")
#             st.image(img_url, caption="Image", use_column_width=True)
#             st.write("### Article Content:")
#             st.write(article_content)

#             st.markdown("---") 

#     for second in second_containers:
#         second_links = second.find('a', class_="linkbox__overlay")
#         if second_links:
#             hrefs2 = second_links.get('href')
#             full_url = f"https://decrypt.co{hrefs2}"

#             article_name, article_date, img_url, article_content = scrape_article_info(full_url)

#             # Display article information in a tabular form
#             st.write(f"##. {article_name}")
#             st.write(f"**Date:** {article_date}")
#             st.image(img_url, caption="Image", use_column_width=True)
#             st.write("### Article Content:")
#             st.write(article_content)

#             st.markdown("---") 

#     for third in third_containers:
#         third_links = third.find('a', class_="linkbox__overlay")
#         if third_links:
#             hrefs3 = third_links.get('href')
#             full_url = f"https://decrypt.co{hrefs3}"

#             article_name, article_date, img_url, article_content = scrape_article_info(full_url)

#             # Display article information in a tabular form
#             st.write(f"##. {article_name}")
#             st.write(f"**Date:** {article_date}")
#             st.image(img_url, caption="Image", use_column_width=True)
#             st.write("### Article Content:")
#             st.write(article_content)

#             st.markdown("---") 


 
#     for container in article_containers:
#         link = container.find('a', class_='linkbox__overlay')
#         if link:
#             href = link.get('href')
#             full_url = f"https://decrypt.co/{href}"

#             article_name, article_date, img_url, article_content = scrape_article_info(full_url)

            

#             # Display article information in a tabular form
#             st.write(f"##. {article_name}")
#             st.write(f"**Date:** {article_date}")
#             st.image(img_url, caption="Image", use_column_width=True)
#             st.write("### Article Content:")
#             st.write(article_content)

#             st.markdown("---") 
        

def run_tab2():
    st.title("Article Information")
    num_articles = st.number_input("Enter the number of articles to retrieve:", value=1, min_value=1, step=1)

    base_url = 'https://decrypt.co/news'
    response = requests.get(base_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    first_containers = soup.find_all('div', class_='mt-2 md:col-span-4 md:mt-0')
    second_containers = soup.find_all('h3', class_="font-medium xl:font-normal mt-1 font-akzidenz-grotesk text-black gg-dark:text-neutral-100 gg-dark:font-poppins scene:font-itc-avant-garde-gothic-pro scene:font-medium scene:mt-2 degen-alley-dark:text-white text-base leading-4.5 xl:text-xl xl:leading-6")
    third_containers = soup.find_all('h3', class_="font-medium mt-1 font-akzidenz-grotesk text-black gg-dark:text-neutral-100 gg-dark:font-poppins scene:font-itc-avant-garde-gothic-pro scene:font-medium scene:mt-2 degen-alley-dark:text-white text-base leading-4.5 xl:text-xl xl:leading-6")
    article_containers = soup.find_all('div', class_='mb-5 pb-5 last-of-type:mb-0')

    total_articles_displayed = 0  # Track the total number of articles displayed

    for fisrt in first_containers:
        if total_articles_displayed >= num_articles:
            break

        first_links = fisrt.find('a', class_='linkbox__overlay')
        if first_links:
            hrefs = first_links.get('href')
            full_url = f"https://decrypt.co{hrefs}"

            article_name, article_date, img_url, article_content = scrape_article_info(full_url)

            # Display article information in a tabular form
            st.markdown(f"# {article_name}")
            st.write(f"**Date:** {article_date}")
            st.image(img_url, caption="Image", use_column_width=True)
            st.write("### Article Content:")
            st.write(article_content)

            st.markdown("---") 
            total_articles_displayed += 1

    for second in second_containers:
        if total_articles_displayed >= num_articles:
            break

        second_links = second.find('a', class_="linkbox__overlay")
        if second_links:
            hrefs2 = second_links.get('href')
            full_url = f"https://decrypt.co{hrefs2}"

            article_name, article_date, img_url, article_content = scrape_article_info(full_url)

            # Display article information in a tabular form
            st.markdown(f"# {article_name}")
            st.write(f"**Date:** {article_date}")
            st.image(img_url, caption="Image", use_column_width=True)
            st.write("### Article Content:")
            st.write(article_content)

            st.markdown("---") 
            total_articles_displayed += 1

    for third in third_containers:
        if total_articles_displayed >= num_articles:
            break

        third_links = third.find('a', class_="linkbox__overlay")
        if third_links:
            hrefs3 = third_links.get('href')
            full_url = f"https://decrypt.co{hrefs3}"

            article_name, article_date, img_url, article_content = scrape_article_info(full_url)

            # Display article information in a tabular form
            st.markdown(f"# {article_name}")
            st.write(f"**Date:** {article_date}")
            st.image(img_url, caption="Image", use_column_width=True)
            st.write("### Article Content:")
            st.write(article_content)

            st.markdown("---") 
            total_articles_displayed += 1

    for container in article_containers:
        if total_articles_displayed >= num_articles:
            break

        link = container.find('a', class_='linkbox__overlay')
        if link:
            href = link.get('href')
            full_url = f"https://decrypt.co/{href}"

            article_name, article_date, img_url, article_content = scrape_article_info(full_url)

            # Display article information in a tabular form
            st.markdown(f"# {article_name}")
            st.write(f"**Date:** {article_date}")
            st.image(img_url, caption="Image", use_column_width=True)
            st.write("### Article Content:")
            st.write(article_content)

            st.markdown("---") 
            total_articles_displayed += 1


# def run_tab3():
#     st.subheader("Tab 3: Other Code")
#     with st.spinner("Scrapping data..."):
#         base_url = 'https://www.coindesk.com/tag/news/'
#         response = requests.get(base_url)
#         soup = BeautifulSoup(response.text, 'html.parser')

#         h6_tags = soup.find_all('h6', class_="typography__StyledTypography-sc-owin6q-0 diMXjy")

#         for h6_tag in h6_tags:
#             link = h6_tag.find('a', class_="card-title")

#             if link:
#                 href = link.get('href')
#                 full_url = f'https://www.coindesk.com/{href}'
#                 response = requests.get(full_url)
#                 article_soup = BeautifulSoup(response.text, 'html.parser')

#                 article_name_element = article_soup.find('h1', class_="typography__StyledTypography-sc-owin6q-0 bSOJsQ")

#                 if article_name_element:
#                     article_name = article_name_element.text.strip()
#                     st.write(f'# Article Name: {article_name}')

#                     date_time_div = article_soup.find('div', class_="at-created label-with-icon")
#                     if date_time_div:
#                         date_time_span = date_time_div.find('span', class_="typography__StyledTypography-sc-owin6q-0 hcIsFR")
#                         date_time_text = date_time_span.text.strip()
#                         st.write(f'Date and Time: {date_time_text}')
#                     else:
#                         alt_date_time_div = article_soup.find('div', class_="align-right")
#                         alt_date_time_span = alt_date_time_div.find('span', class_="typography__StyledTypography-sc-owin6q-0 hcIsFR")
#                         alt_date_time_text = alt_date_time_span.text.strip() if alt_date_time_span else 'Date and Time not found'
#                         st.write(f'Date and Time (Alternative): {alt_date_time_text}')

#                     main_div = article_soup.find('div', class_='featured-imagestyles__FeaturedImageWrapper-sc-ojmof1-0 jGviVP at-rail-aligner at-rail-aligner-fi')

#                     if main_div:
#                         picture_tag = main_div.find('picture', class_='responsive-picturestyles__ResponsivePictureWrapper-sc-1urqrom-0 iLCXlQ')

#                         if picture_tag:
#                             img_tag = picture_tag.find('img')
#                             image_url = img_tag['src'] if img_tag else 'Image not found'
#                             st.image(image_url, caption='Article Image', use_column_width=True)
#                         else:
#                             st.write('Image not found within main div.')
#                     else:
#                         main_div2 = article_soup.find('div', class_='featured-imagestyles__FeaturedImageWrapper-sc-ojmof1-0 jGviVP featured-media featured-media-fi')
#                         if main_div2:
#                             picture_tag2 = main_div2.find('picture', class_='responsive-picturestyles__ResponsivePictureWrapper-sc-1urqrom-0 iLCXlQ')

#                             if picture_tag2:
#                                 img_tag2 = picture_tag2.find('img')
#                                 image_url2 = img_tag2['src'] if img_tag2 else 'Image not found'
#                                 st.image(image_url2, caption='Article Image', use_column_width=True)
#                             else:
#                                 st.write('Image not found within picture tag.')
#                         else:
#                             st.write('Image not in article.')

#                     divs = article_soup.find_all('div', class_=["common-textstyles__StyledWrapper-sc-18pd49k-0 eSbCkN"])
#                     st.header('Article Content')
#                     for div in divs:
#                         p_tags = div.find_all('p')
#                         for p_tag in p_tags:
#                             p_text = p_tag.text.strip()
#                             st.write(p_text)
#                 else:
#                     st.write('Article Name not found. Moving to the next article.\n')

#                 # Add a separator between articles
#                 st.markdown("---")

# Function code for the third tab...
def run_tab3():
    st.subheader("Tab 3: Coin Desk News")
    num_articles = st.number_input("Enter the number of articles to retrieve:", value=1, min_value=1, step=1)

    with st.spinner("Scraping data..."):
        base_url = 'https://www.coindesk.com/tag/news/'
        response = requests.get(base_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        h6_tags = soup.find_all('h6', class_="typography__StyledTypography-sc-owin6q-0 diMXjy")

        for i, h6_tag in enumerate(h6_tags[:num_articles]):
            link = h6_tag.find('a', class_="card-title")

            if link:
                href = link.get('href')
                full_url = f'https://www.coindesk.com/{href}'
                response = requests.get(full_url)
                article_soup = BeautifulSoup(response.text, 'html.parser')

                article_name_element = article_soup.find('h1', class_="typography__StyledTypography-sc-owin6q-0 bSOJsQ")

                if article_name_element:
                    article_name = article_name_element.text.strip()
                    st.write(f'# {i+1}. Article Name: {article_name}')

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
                    st.write(f'{i+1}. Article Name not found. Moving to the next article.\n')

                # Add a separator between articles
                st.markdown("---")

# Function code for the second tab...
def run_tab4():
    st.subheader("Tab 4: Youtube")
    with st.spinner("Scrapping data..."):
        # DEVELOPER_KEY = os.getenv('YOUTUBE_API_KEY')
        DEVELOPER_KEY = st.secrets['YOUTUBE_API_KEY']
        CHANNEL_IDS = ['UCfdrZpVbXl_HnmyYYo-N6Ig', 'UCk6jF6z-IZx4H00QTYlHwjw', 'UCMtJYS0PrtiUwlk6zjGDEMA', 'UCKQvGU-qtjEthINeViNbn6A', 'UCqK_GSMbpiV8spgD3ZGloSw', 'UCBCbEDO5tMP6saX9yNU_zYQ','UCN9Nj4tjXbVTLYWN0EKly_Q']
        num_videos = st.number_input('Enter the number of videos to display', min_value=1, max_value=5, value=5)
        for channel_id in CHANNEL_IDS:
            latest_videos = get_latest_videos(DEVELOPER_KEY, channel_id, max_results=num_videos)
            if latest_videos:
                print(f"\nLatest Videos for Channel {channel_id}:")
                for video in latest_videos:
                    video_id = video['snippet']['resourceId']['videoId']
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    fetch_video_details(video_url, DEVELOPER_KEY, channel_id)
            else:
                print(f"No videos found for Channel {channel_id}.")

        # for channel_id in CHANNEL_IDS:
        #     latest_videos = get_latest_videos(DEVELOPER_KEY, channel_id)
        #     if latest_videos:
        #         print(f"\nLatest Videos for Channel {channel_id}:")
        #         for video in latest_videos:
        #             video_id = video['id']['videoId']
        #             video_url = f"https://www.youtube.com/watch?v={video_id}"
        #             fetch_video_details(video_url, DEVELOPER_KEY, channel_id)
        #     else:
        #         print(f"No videos found for Channel {channel_id}.")
    os.remove(temp_key_file_path)

def run_tab5():
    st.subheader("Tab 5: News BTC News")
    num_articles = st.number_input("Enter the number of articles to retrieve:", value=1, min_value=1, step=1)
    total_articles_displayed = 0  # Track the total number of articles displayed

    with st.spinner("Scraping data..."):
        base_url = 'https://www.newsbtc.com/news/'
        response = requests.get(base_url)
        soup = BeautifulSoup(response.text, 'html.parser')

        first_container = soup.find_all('h2', class_='jeg_post_title')
        for fisrt in first_container:
            if total_articles_displayed >= num_articles:
                break

            link = fisrt.find('a')
            if link:
                url = link.get('href')
                response = requests.get(url)
                article_soup = BeautifulSoup(response.text, 'html.parser')

                article_name = article_soup.find('h1', class_='jeg_post_title').text.strip()
                st.markdown(f'# {article_name}')

                img_tag = article_soup.find('div', class_='single-post-hero-background').find('img')
                if img_tag:
                    img_src = img_tag.get('src')
                    st.image(img_src, caption='Article Image', use_column_width=True)

                date_div = article_soup.find('div', class_='jeg_meta_date')
                article_date = date_div.find('a').text.strip()
                st.write(f'**Article Date:** {article_date}')

                content_div = article_soup.find('div', class_='content-inner')
                paragraphs = content_div.find_all('p')
                for paragraph in paragraphs:
                    st.markdown(paragraph.text)

                st.markdown("---")
                total_articles_displayed += 1

        # Find all 'a' tags within the h3 elements
        anchor_tags = soup.find_all('h3', class_='jeg_post_title')

        for a_tag in anchor_tags:
            if total_articles_displayed >= num_articles:
                break

            link = a_tag.find('a')
            if link:
                url = link.get('href')
                # st.markdown(f"[{url}]({url})")

                response = requests.get(url)
                article_soup = BeautifulSoup(response.text, 'html.parser')

                article_name = article_soup.find('h1', class_='jeg_post_title').text.strip()
                st.markdown(f'# . {article_name}')

                img_tag = article_soup.find('div', class_='single-post-hero-background').find('img')
                if img_tag:
                    img_src = img_tag.get('src')
                    st.image(img_src, caption='Article Image', use_column_width=True)

                date_div = article_soup.find('div', class_='jeg_meta_date')
                article_date = date_div.find('a').text.strip()
                st.write(f'**Article Date:** {article_date}')

                content_div = article_soup.find('div', class_='content-inner')
                paragraphs = content_div.find_all('p')
                for paragraph in paragraphs:
                    st.markdown(paragraph.text)

                st.markdown("---")
                total_articles_displayed += 1

def run_tab6():
    st.subheader("Tab 6: Crypto News")
    num_articles = st.number_input("Enter the number of articles to retrieve:", value=1, min_value=1, step=1)
    with st.spinner("Scrapping data..."):
        base_url = 'https://crypto.news/news/'
        response = requests.get(base_url)

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all 'a' tags within the 'p' tags inside the post_loop_content_div
        all_links = soup.find_all('p', class_='post-loop__title')

        for i, all_links in enumerate(all_links[:num_articles]):
            link = all_links.find('a')
            if link:
                href = link.get('href')
                if href:
                    st.write(f"[{link.text}]({href})")
                    response = requests.get(href)

                    article_soup = BeautifulSoup(response.text, 'html.parser')

                    article_name = article_soup.find('h1', class_='post-detail__title').text.strip()
                    st.title(f'# {i+1}.Article Name: {article_name}')

                    date_time = article_soup.find('time', class_='post-detail__date').text.strip()
                    st.write(f'Date: {date_time}')

                    image_div = article_soup.find('div', class_='post-detail__media')

                    # Find the img tag within the post_detail_media_div
                    img_tag = image_div.find('img')

                    # Extract and print the src attribute
                    if img_tag:
                        img_url = img_tag.get('src')
                        if img_url:
                            st.image(img_url, caption='Image', use_column_width=True)

                    article_div = article_soup.find('div', class_='post-detail__content')

                    # Find all 'p' tags within the post_detail_content_div
                    all_paragraphs = article_div.find_all('p')

                    # Extract and print the text content of each 'p' tag
                    for paragraph in all_paragraphs:
                        st.write(paragraph.get_text(strip=True), unsafe_allow_html=True)

def run_tab7():
    with st.spinner("Scrapping data..."):
        st.subheader("Coindesk Market Scraper")
    
        num_articles = st.number_input("Enter the number of articles to retrieve:", value=1, min_value=1, step=1)
        driver = webdriver.Chrome(service=get_webdriver_service(), options=get_webdriver_options())
        base_url = 'https://www.coindesk.com/markets/'
        driver.get(base_url)

        wait = WebDriverWait(driver, 30)  # Increased timeout
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'h5.typography__StyledTypography-sc-owin6q-0.keiOrg')))

        page_source = driver.page_source

        soup = BeautifulSoup(page_source, 'html.parser')
        h5_tags = soup.find_all('h5', class_="typography__StyledTypography-sc-owin6q-0 keiOrg")
        for i, container in enumerate(h5_tags[:num_articles]):
            link = container.find('a', class_="card-title")
            if link:
                href = link.get('href')
                full_url = f'https://www.coindesk.com/{href}'
                st.write(full_url)
                scrape_and_display_article(full_url)

        driver.quit()

def run_tab8():
    with st.spinner("Scrapping data..."):
        st.subheader("Coindesk Finance Scraper")
    
        num_articles = st.number_input("Enter the number of articles to retrieve:", value=1, min_value=1, step=1)
        driver = webdriver.Chrome(service=get_webdriver_service(), options=get_webdriver_options())
        base_url = 'https://www.coindesk.com/business/'
        driver.get(base_url)

        wait = WebDriverWait(driver, 30)  # Increased timeout
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'h5.typography__StyledTypography-sc-owin6q-0.keiOrg')))

        page_source = driver.page_source

        soup = BeautifulSoup(page_source, 'html.parser')
        h5_tags = soup.find_all('h5', class_="typography__StyledTypography-sc-owin6q-0 keiOrg")
        for i, container in enumerate(h5_tags[:num_articles]):
            link = container.find('a', class_="card-title")
            if link:
                href = link.get('href')
                full_url = f'https://www.coindesk.com/{href}'
                st.write(full_url)
                scrape_and_display_article(full_url)

        driver.quit()


def run_tab9():
    st.subheader("Tab 9: Coin Telegraph")
    
    # Get the number of articles from the user
    num_articles = st.number_input("Enter the number of articles", value=5, min_value=1, max_value=20)

    url = 'https://cointelegraph.com/category/latest-news'

    chrome_options = webdriver.ChromeOptions()
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36'
    chrome_options.add_argument(f'user-agent={user_agent}')
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')  
    chrome_options.add_argument('--disable-dev-shm-usage')  

    # Use st.spinner to show a loading spinner while the content is being fetched
    with st.spinner("Fetching content..."):
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        driver.implicitly_wait(5)
        page_source = driver.page_source
        driver.quit()

    soup = BeautifulSoup(page_source, 'html.parser')

    allPage = soup.find('div', class_="category-page__content-col")
    MainDiv = allPage.find('div', class_="group category-page__posts inline")
    allList = MainDiv.find_all('li', class_="group-[.inline]:mb-8")

    # Loop through the specified number of articles
    for i, a_tag in enumerate(allList[:num_articles]):
        listRightDiv = a_tag.find('div', class_="post-card-inline__content")
        rightDivHeader = listRightDiv.find('div', class_="post-card-inline__header")
        all_links = rightDivHeader.find_all('a', class_='post-card-inline__title-link')

        for a in all_links:
            href_attribute = a.get('href')
            full_url = f'https://cointelegraph.com/{href_attribute}'
            st.write(full_url)
            date_time = rightDivHeader.find('time', class_='post-card-inline__date').text.strip()
            st.write(f'Article Date: {date_time}')

            # Show loading spinner for the article content
            with st.spinner("Fetching article content..."):
                driver = webdriver.Chrome(options=chrome_options)
                driver.get(full_url)
                driver.implicitly_wait(5)
                page_source = driver.page_source
                driver.quit()

            article_soup = BeautifulSoup(page_source, 'html.parser')
            first_div = article_soup.find('div', class_='post post-page__article')
            second_div = first_div.find('article', class_='post__article')
            article_name = second_div.find('h1', class_='post__title').text.strip()
            st.write(f'# Article Name: {article_name}')

            img_div = article_soup.find('div', class_='lazy-image post-cover__image lazy-image_loaded lazy-image_immediate')
            img_tag = img_div.find('img')
            image_url = img_tag['src']
            st.image(image_url, caption='Image', use_column_width=True)

            article_content = article_soup.find('div', class_='post-content relative')
            paragraphs = article_content.find_all('p')

            # Convert paragraphs to a markdown string
            article_markdown = "\n\n".join([para.text for para in paragraphs])
            st.markdown(article_markdown)
            st.markdown("---")

            # Break the loop if the specified number of articles is reached
            if i == num_articles - 1:
                break

# Main Streamlit UI
st.title("DATA SCRAPPER")

# Create tabs using st.selectbox
selected_tab = st.selectbox("Select Tab", ["Discord", "Decrypt News","Coin Desk News","YouTube", "News BTC", "Crypto News", "Coin Desk Market", "Coin Desk Finance", "Coin Telegraph"])

# Display content based on the selected tab
if selected_tab == "Discord":
    run_tab1()
elif selected_tab == "Decrypt News":
    run_tab2()
elif selected_tab == "Coin Desk News":
    run_tab3()
elif selected_tab == "YouTube":
    run_tab4()
elif selected_tab == "News BTC":
    run_tab5()
elif selected_tab == "Crypto News":
    run_tab6()
elif selected_tab == "Coin Desk Market":
    run_tab7()
elif selected_tab == "Coin Desk Finance":
    run_tab8()
elif selected_tab == "Coin Telegraph":
    run_tab9()