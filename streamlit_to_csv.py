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
import psycopg2
from datetime import datetime, timedelta, timezone
import matplotlib.pyplot as plt
import plotly.graph_objs as go
from langchain.agents import create_sql_agent
from langchain.sql_database import SQLDatabase
from langchain_openai import ChatOpenAI
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak, Image
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from io import BytesIO
import datetime
import base64
from unidecode import unidecode
from fpdf import FPDF


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
    
def fetch_data_from_database(minutes):
    with st.spinner(f"Fetching data for the last {minutes} minutes from the database..."):
        # db_connection_string = os.getenv("DATABASE_URL")
        db_connection_string = st.secrets["DATABASE_URL"]
        sql_query = f"SELECT * FROM discord_data WHERE time_stamp > NOW() - INTERVAL '{minutes} minutes'"

        try:
            conn = psycopg2.connect(db_connection_string)

            df_database = pd.read_sql_query(sql_query, conn)

            return df_database

        except Exception as e:
            print(f"An error occurred: {e}")
            return pd.DataFrame()

        finally:
            if conn:
                conn.close()

    
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
        st.subheader("Transcript")
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

def connect_to_database():
    # DATABASE_URL = os.getenv("DATABASE_URL")
    DATABASE_URL = st.secrets["DATABASE_URL"]
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def get_tweets_last_day(conn):
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    query = f"SELECT * FROM twitter_data WHERE time_stamp >= '{yesterday_str}'"
    cur = conn.cursor()
    cur.execute(query)
    return cur.fetchall(), yesterday_str

def calculate_stats(tweets):
    stats = {}
    for tweet in tweets:
        channel = tweet[1]  # Assuming the channel is stored in the second column
        print(tweet[1])
        if channel in stats:
            stats[channel] += 1
        else:
            stats[channel] = 1
    return stats


# Function to run code for Tab 1

# def run_tab1():
#     st.subheader("Tab 1: Discord Data Scraper")
#     minutes = st.number_input("Enter the number of minutes to retrieve data:", value=30, min_value=1)
#     if st.button("Download Data"):
#         df = download_data(minutes)
#         st.write("Downloaded data:")
#         st.write(df)

#         # Save data to Excel
#         excel_filename = "discord_data.xlsx"
#         df.to_excel(excel_filename, index=False)
#         st.success(f"Data saved to {excel_filename}")

def fetch_data_coin(symbol):
    # conn_string = os.getenv("DATABASE_URL")
    conn_string = st.secrets["DATABASE_URL"]
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    query = f"SELECT timestamp, price, circulating_supply FROM coinmarket_historical_data WHERE symbol = '{symbol}'"
    cursor.execute(query)
    data = cursor.fetchall()
    columns = ["timestamp", "price", "circulating_supply"]
    df = pd.DataFrame(data, columns=columns)
    conn.close()
    return df 

def plot_line_graph(df, frequency):
    if frequency == 'Daily':
        df_resampled = df.set_index('timestamp').resample('D').mean().reset_index()
    elif frequency == 'Monthly':
        df_resampled = df.set_index('timestamp').resample('M').mean().reset_index()
    else:
        st.error("Invalid frequency selection!")
        return
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_resampled['timestamp'], y=df_resampled['price'].rolling(window=7, min_periods=1).mean(), mode='lines', name='Price'))
    # fig.add_trace(go.Scatter(x=df_resampled['timestamp'], y=df_resampled['circulating_supply'].rolling(window=7, min_periods=1).mean(), mode='lines', name='Circulating Supply'))
    fig.update_layout(title='Price Trend',
                      xaxis_title='Date',
                      yaxis_title='Value',
                      xaxis=dict(rangeslider=dict(visible=True), type="date"))
    fig.update_traces(hoverinfo='text+name', text=df_resampled['timestamp'].dt.strftime('%Y-%m-%d') + '<br>Price: ' + df_resampled['price'].astype(str))
    st.plotly_chart(fig)

    fig1 = go.Figure()
    # fig1.add_trace(go.Scatter(x=df_resampled['timestamp'], y=df_resampled['price'].rolling(window=7, min_periods=1).mean(), mode='lines', name='Price'))
    fig1.add_trace(go.Scatter(x=df_resampled['timestamp'], y=df_resampled['circulating_supply'].rolling(window=7, min_periods=1).mean(), mode='lines', name='Circulating Supply'))
    fig1.update_layout(title='Circulating Supply Trend',
                      xaxis_title='Date',
                      yaxis_title='Value',
                      xaxis=dict(rangeslider=dict(visible=True), type="date"))
    fig1.update_traces(hoverinfo='text+name', text=df_resampled['timestamp'].dt.strftime('%Y-%m-%d') +'<br>Circulating Supply: ' + df_resampled['circulating_supply'].astype(str))
    st.plotly_chart(fig1)

def generate_graphs(graph_input_symbol, timestamps, prices, circulating_supplies):
    # Plot price data
    plt.figure(figsize=(10, 6))
    plt.plot(timestamps, prices, marker='o', linestyle='-')
    plt.xlabel("Date")
    plt.ylabel("Price (USD)")
    plt.title(f"{graph_input_symbol.upper()} Price Trend")
    plt.xticks(rotation=45)
    plt.tight_layout()
    price_image_path = "price_trend.png"
    plt.savefig(price_image_path)

    # Plot circulating supply data
    plt.figure(figsize=(10, 6))
    plt.plot(timestamps, circulating_supplies, marker='o', linestyle='-')
    plt.xlabel("Date")
    plt.ylabel("Circulating Supply")
    plt.title(f"{graph_input_symbol.upper()} Circulating Supply Trend")
    plt.xticks(rotation=45)
    plt.tight_layout()
    supply_image_path = "supply_trend.png"
    plt.savefig(supply_image_path)

    return price_image_path, supply_image_path

def load_data():
    df = pd.read_excel('coin_keys.xlsx')
    return df

# Find coin name
def find_coin_name(df, symbol):
    symbol = symbol.lower()
    coin_keys = df.loc[df['Symbol'].str.lower() == symbol, 'Key'].values.tolist()
    return coin_keys if coin_keys else ["Ticker not found."]

def fetch_data_from_skynet(coin_id):
    # Define your Heroku PostgreSQL connection string
    # DATABASE_URL = os.getenv("DATABASE_URL")
    DATABASE_URL = st.secrets["DATABASE_URL"]

    # Connect to the PostgreSQL database
    conn = psycopg2.connect(DATABASE_URL)

    # Create a cursor object to execute SQL queries
    cur = conn.cursor()

    # Execute the SQL query to fetch data for the specified coin_id
    cur.execute("SELECT * FROM skynet_data WHERE coin_id = %s", (coin_id,))

    # Fetch all the rows
    data = cur.fetchone()

    colnames = [desc[0] for desc in cur.description]

    # Close the cursor and connection
    cur.close()
    conn.close()

    return colnames, data

def fetch_dataa(url):
    response = requests.get(url)
    data = response.json()
    return data


def fetch_price_data(coin_name):
    url = f"https://cryptorank.io/_next/data/XUG6L4yjy_WS2qN8tRUFJ/en/price/{coin_name}.json?coinKey={coin_name}"
    # st.write(url)
    data = fetch_dataa(url)
    if "notFound" in data and data["notFound"]:
        return None
    else:
        return data

def fetch_token_sale_data(coin_name):
    url = f"https://cryptorank.io/_next/data/XUG6L4yjy_WS2qN8tRUFJ/en/ico/{coin_name}.json?coinKey={coin_name}"
    # st.write(url)
    data = fetch_dataa(url)
    if "notFound" in data and data["notFound"]:
        return None
    else:
        return data

def fetch_market_data(coin_name):
    url = f"https://cryptorank.io/_next/data/XUG6L4yjy_WS2qN8tRUFJ/en/price/{coin_name}/exchanges.json?coinKey={coin_name}"
    # st.write(url)
    data = fetch_dataa(url)
    if "notFound" in data and data["notFound"]:
        return None

    else:
        return data

def fetch_vesting_data(coin_name):
    url = f"https://cryptorank.io/_next/data/XUG6L4yjy_WS2qN8tRUFJ/en/price/{coin_name}/vesting.json?coinKey={coin_name}"
    # st.write(url)
    data = fetch_dataa(url)
    if "notFound" in data and data["notFound"]:
        print(data)
    else:
        return data 
    
def fetch_historical_data(symbol):
    # Calculate the start and end dates for the last month
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=30)

    # Define the URL and parameters
    url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/historical"
    params = {
        "interval": "daily",
        "symbol": symbol.upper(),  # Convert the user input to uppercase
        "time_start": start_date.strftime("%Y-%m-%d"),
        "time_end": end_date.strftime("%Y-%m-%d")
    }
    headers = {
        "X-CMC_PRO_API_KEY": "8e24ed89-d78b-43ed-a2b5-b2e603bb2cc2"  # Add your API key here
    }

    # Send the request
    response = requests.get(url, params=params, headers=headers)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON response
        data = response.json()

        # Check if the symbol exists in the data
        if symbol.upper() not in data["data"]:
            return None, None, None  # Symbol not found, return None for all data arrays

        # Extract price and circulating supply data
        timestamps = []
        prices = []
        circulating_supplies = []
        coin_data = data["data"][symbol.upper()]  # Use uppercase symbol for consistency
        for entry in coin_data:
            for quote in entry["quotes"]:
                timestamp = quote["timestamp"]
                price = quote["quote"]["USD"]["price"]
                circulating_supply = quote["quote"]["USD"]["circulating_supply"]
                timestamps.append(timestamp)
                prices.append(price)
                circulating_supplies.append(circulating_supply)
        
        return timestamps, prices, circulating_supplies
    else:
        # Return None if the request was not successful
        return None, None, None

# Function to generate PDF using ReportLab
def generate_pdf(coin_name, price_data, token_sale_data, market_data, vesting_data,colnames,skynet_data, price_image_path, supply_image_path):
    pdf_content = b''
    # pdf_filename = "gameswifts_coin_data.pdf"
    # pdf = SimpleDocTemplate(pdf_filename, pagesize=letter)
    elements = []
    

    # Custom styles for headings
    heading1_style = ParagraphStyle(
        name='Heading1',
        fontSize=16,
        leading=20,
        fontWeight='Bold',
        alignment=1,
        spaceAfter=10
    )
    heading2_style = ParagraphStyle(
        name='Heading2',
        fontSize=14,
        leading=18,
        spaceAfter=8
    )

    # Title
    elements.append(Paragraph(f"{coin_name} Coin Data", heading1_style))

    # Price data
    if price_data:
        elements.append(Paragraph("Overview Data", heading1_style))
        price_info = []

        # Coin Name
        try:
            coin_name = price_data['pageProps']['coin']['name']
        except KeyError:
            coin_name = 'N/A'
        price_info.append(["Coin Name", coin_name])

        # Coin Price
        try:
            coin_price = price_data['pageProps']['coin']['price']['USD']
        except KeyError:
            coin_price = 'N/A'
        price_info.append(["Coin Price", coin_price])

        # High Price
        try:
            high_price = price_data['pageProps']['coin']['histData']['high']['24H']['USD']
        except KeyError:
            high_price = 'N/A'
        price_info.append(["High Price", high_price])

        # Low Price
        try:
            low_price = price_data['pageProps']['coin']['histData']['low']['24H']['USD']
        except KeyError:
            low_price = 'N/A'
        price_info.append(["Low Price", low_price])

        # Circulating Supply
        try:
            circulating_supply = price_data['pageProps']['priceStatistics']['availableSupply']
        except KeyError:
            circulating_supply = 'N/A'
        price_info.append(["Circulating Supply", circulating_supply])

        # Total Supply
        try:
            total_supply = price_data['pageProps']['coin']['totalSupply']
        except KeyError:
            total_supply = 'N/A'
        price_info.append(["Total Supply", total_supply])

        # Percentage of Max Supply
        try:
            max_supply_percent = price_data['pageProps']['priceStatistics']['availableSupplyPercent']
        except KeyError:
            max_supply_percent = 'N/A'
        price_info.append(["Percentage of Max Supply", max_supply_percent])

        # Trade Vol
        try:
            trade_volume = price_data['pageProps']['priceStatistics']['volume24h']
        except KeyError:
            trade_volume = 'N/A'
        price_info.append(["Trade Vol", trade_volume])

        # Vol 24h/ MCap
        try:
            volume_to_market_cap = price_data['pageProps']['priceStatistics']['volume24hRatio']
        except KeyError:
            volume_to_market_cap = 'N/A'
        price_info.append(["Vol 24h/ MCap", volume_to_market_cap])

        # All Time High
        try:
            all_time_high = price_data['pageProps']['priceStatistics']['athPrice']
        except KeyError:
            all_time_high = 'N/A'
        price_info.append(["All Time High", all_time_high])

        # All Time Low
        try:
            all_time_low = price_data['pageProps']['priceStatistics']['atlPrice']
        except KeyError:
            all_time_low = 'N/A'
        price_info.append(["All Time Low", all_time_low])

        # From ATH
        try:
            from_ath = price_data['pageProps']['priceStatistics']['fromAthPrice']
        except KeyError:
            from_ath = 'N/A'
        price_info.append(["From ATH", from_ath])

        # From ATL
        try:
            from_atl = price_data['pageProps']['priceStatistics']['fromAtlPrice']
        except KeyError:
            from_atl = 'N/A'
        price_info.append(["From ATL", from_atl])

        # IEO Price
        try:
            ieo_price = price_data['pageProps']['coin']['crowdsales'][0]['price']['USD']
        except (KeyError, IndexError):
            ieo_price = 'N/A'
        price_info.append(["IEO Price", ieo_price])

        # IEO Price Raise
        try:
            ieo_price_raise = price_data['pageProps']['coin']['crowdsales'][0]['raise']['USD']
        except (KeyError, IndexError):
            ieo_price_raise = 'N/A'
        price_info.append(["IEO Price Raise", ieo_price_raise])

        # ROI
        try:
            roi = price_data['pageProps']['coin']['crowdsales'][0]['roi']['value']
        except (KeyError, IndexError):
            roi = 'N/A'
        price_info.append(["ROI", roi])

        # ROI Percent Change
        try:
            roi_percent_change = price_data['pageProps']['coin']['crowdsales'][0]['roi']['percentChange']
        except (KeyError, IndexError):
            roi_percent_change = 'N/A'
        price_info.append(["ROI Percent Change", roi_percent_change])

       

        elements.append(Table(price_info, style=[('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(PageBreak())
    else:
        # If vesting data is missing, notify the user
        elements.append(Paragraph(f"Overview Data is missing in {coin_name} coin.", heading1_style))

    # Token sale data
    if token_sale_data:
        elements.append(Paragraph("Token Sale Data", heading1_style))
        token_sale_info = [
            ["Title", "Percent"]
        ]
        for item in token_sale_data['pageProps']['coin']['icoData']['allocationChart']:
            token_sale_info.append([item['title'], item['percent']])
        elements.append(Table(token_sale_info, style=[('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(Paragraph(" ", heading1_style))
        elements.append(Paragraph(" ", heading1_style))

        # Trending token sales
        elements.append(Paragraph("Trending Token Sales", heading1_style))
        trending_token_sales = [
            ["Key", "Name", "Symbol", "Category", "Start Date", "End Date"]
        ]
        for item in token_sale_data['pageProps']['fallbackDataTokenSales'][:4]:
            trending_token_sales.append([item['key'], item['name'], item['symbol'], item['category'], item['round']['startDate'], item['round']['endDate']])
        elements.append(Table(trending_token_sales, style=[('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(PageBreak())
    else:
        # If vesting data is missing, notify the user
        elements.append(Paragraph(f"Token Sale Data is missing in {coin_name} coin.", heading1_style))
 

    # market_data = fetch_market_data()
    if market_data:
        tickers = market_data['pageProps']['tickers']
        exchange_names = []
        coin_names = []
        highs = []
        lows = []
        open_prices = []
        close_prices = []
        bids = []
        asks = []
        base_volumes = []
        usd_volumes = []
        btc_volumes = []
        changes = []
        change_percents = []
        spreads = []
        exchange_percent_volumes = []

        for ticker in tickers:
            exchange_names.append(ticker['exchangeName'])
            coin_names.append(ticker['coinName'])
            highs.append(ticker['high'])
            lows.append(ticker['low'])
            open_prices.append(ticker['open'])
            close_prices.append(ticker['close'])
            bids.append(ticker['bid'])
            asks.append(ticker['ask'])
            base_volumes.append(ticker['baseVolume'])
            usd_volumes.append(ticker['usdVolume'])
            btc_volumes.append(ticker['btcVolume'])
            changes.append(ticker.get('change', 'N/A'))
            change_percents.append(ticker.get('changePercent', 'N/A'))
            spreads.append(ticker['spread'])
            exchange_percent_volumes.append(ticker['exchangePercentVolume'])
        
        # Splitting DataFrame into two DataFrames
        df = pd.DataFrame({
            'Exchange Name': exchange_names,
            'Coin Name': coin_names,
            'High': highs,
            'Low': lows,
            'Open': open_prices,
            'Close': close_prices,
            'Bid': bids,
            'Ask': asks,
            'Base Volume': base_volumes,
            'USD Volume': usd_volumes,
            'BTC Volume': btc_volumes,
            'Change': changes,
            'Change Percent': change_percents,
            'Spread': spreads,
            'Exchange Percent Volume': exchange_percent_volumes
        })
        
        df_1 = df.iloc[:, :6]  # First 8 columns
        df_2 = df.iloc[:, 0:1].join(df.iloc[:, 6:11])  # First column "Exchange Name" and the rest 7 columns
        df_3 = df.iloc[:, 0:1].join(df.iloc[:, 11:])
        # Convert DataFrames to list of lists
        table_data_1 = [df_1.columns.tolist()] + df_1.values.tolist()
        table_data_2 = [df_2.columns.tolist()] + df_2.values.tolist()
        table_data_3 = [df_3.columns.tolist()] + df_3.values.tolist()



        # Add two tables to the elements list
        elements.append(Paragraph("Market Data - Table 1", heading1_style))
        elements.append(Table(table_data_1, style=[('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(Paragraph(" ", heading1_style))
        elements.append(Paragraph(" ", heading1_style))

        elements.append(Paragraph("Market Data - Table 2", heading1_style))
        elements.append(Table(table_data_2, style=[('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(Paragraph(" ", heading1_style))
        elements.append(Paragraph(" ", heading1_style))

        elements.append(Paragraph("Market Data - Table 3", heading1_style))
        elements.append(Table(table_data_3, style=[('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(PageBreak())
    else:
        # If vesting data is missing, notify the user
        elements.append(Paragraph(f"Market Data is missing {coin_name} coin.", heading1_style))

    
    today_date = datetime.date.today()
    # Create vesting data table
    if vesting_data:
        vesting_table_data = []
        allocations = vesting_data['pageProps']['vestingInfo']['allocations']
        for allocation in allocations:
            name = allocation['name']
            token_percent = allocation['tokens_percent']
            token = allocation['tokens']
            batches = allocation.get('batches', [])
            for batch in batches:
                date = batch.get('date')
                unlock_percent = batch.get('unlock_percent')
                if date:
                    # Adjust the format string to include time information
                    date_obj = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ").date()
                    if date_obj >= today_date:
                        vesting_table_data.append([name, token_percent, token, date, unlock_percent])
        vesting_table_data.sort(key=lambda x: x[3] if x[3] else "")
        vesting_table_data.insert(0, ["Allocation Name", "Token Percent", "Tokens", "Batch Date", "Unlock Percent"])

        # Add vesting data table
        elements.append(Paragraph("Vesting Data", heading1_style))
        elements.append(Table(vesting_table_data, style=[('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(PageBreak())
    else:
        # If vesting data is missing, notify the user
        elements.append(Paragraph(f"Vesting Data is missing in {coin_name} coin.", heading1_style))
        elements.append(PageBreak())

    if skynet_data:
        # Define table data
        table_data = []
        # Add fetched data to the table
        for colname, value in zip(colnames, skynet_data):
            table_data.append([colname, str(value)])

        table_data = table_data[1:]

        # Create table
        table = Table(table_data)
        elements.append(Paragraph("Skynet and Certik Data", heading1_style))
        table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(table)
        elements.append(PageBreak())
    else:
        elements.append(Paragraph(f"Coin is not in Skynet.", heading1_style))
        

    elements.append(Paragraph("Price Trend Graph", heading1_style))
    elements.append(Image(price_image_path, width=500, height=300))
    elements.append(PageBreak())
    elements.append(Paragraph("Circulating Supply Trend Graph", heading1_style))
    elements.append(Image(supply_image_path, width=500, height=300))

    # Build PDF
    pdf_buffer = BytesIO()  # Create a BytesIO buffer to store the PDF content
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    pdf.build(elements)

    pdf_content = pdf_buffer.getvalue()
    pdf_buffer.close()
    return pdf_content

def fetch_coin_data_coinmarket(api_key, limit=5000):
    url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?limit={limit}"
    headers = {
        "X-CMC_PRO_API_KEY": api_key
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()['data']
    else:
        st.error("Failed to fetch coin data from the API.")
        return None


def run_tab1():
    st.subheader("Tab 1: Discord Data Scraper")

    # Button to download data from Discord channels
    minutes_download = st.number_input("Enter the number of minutes to retrieve data from Discord channels:", value=30, min_value=1)
    if st.button("Download Data from Discord Channels"):
        df_download = download_data(minutes_download)
        st.write("Downloaded data from Discord channels:")
        st.write(df_download)

        # Save data to Excel
        excel_filename_download = "discord_data_download.xlsx"
        df_download.to_excel(excel_filename_download, index=False)
        st.success(f"Data saved to {excel_filename_download}")

    # # Button to fetch data from the database
    # minutes_database = st.number_input("Enter the number of minutes to retrieve data from the database:", value=30, min_value=1)
    # if st.button("Fetch Data from Database"):
    #     df_database = fetch_data_from_database(minutes_database)
    #     st.write("Fetched data from the database:")
    #     st.write(df_database)

    #     # Save data to Excel
    #     excel_filename_db = "discord_data_database.xlsx"
    #     df_database.to_excel(excel_filename_db, index=False)
    #     st.success(f"Data fetched from the database and saved to {excel_filename_db}")
        
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
    os.remove(temp_key_file_path)

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
    #os.remove(temp_key_file_path)

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

def run_tab10():
    minutes_database = st.number_input("Enter the number of minutes to retrieve data from the database:", value=30, min_value=1)
    if st.button("Fetch Data from Discord"):
        df_database = fetch_data_from_database(minutes_database)
        st.write("Fetched data from the database:")
        st.write(df_database)

        excel_filename_db = "discord_data_database.xlsx"
        df_database.to_excel(excel_filename_db, index=False)
        st.success(f"Data fetched from the database and saved to {excel_filename_db}")

    database_url = st.secrets['DATABASE_URL']
    # database_url = os.getenv("DATABASE_URL")

    df_database = pd.DataFrame()

    if st.button("Fetch Data from News"):
        try:
            connection = psycopg2.connect(database_url, sslmode='require')

            query = "SELECT * FROM news_data WHERE data_source = 'News BTC' LIMIT 5"
            df_database = pd.read_sql(query, connection)

            connection.close()

            st.write("Fetched data from the database:")
            st.write(df_database)

            excel_filename_db = "news_data_database.xlsx"
            df_database.to_excel(excel_filename_db, index=False)
            st.success(f"Data fetched from the database and saved to {excel_filename_db}")

        except Exception as e:
            st.error(f"An error occurred: {e}")

    if st.button("Fetch Data from Youtube"):
        try:
            connection = psycopg2.connect(database_url, sslmode='require')

            query = "SELECT * FROM youtube_data LIMIT 5"
            df_database = pd.read_sql(query, connection)

            connection.close()

            st.write("Fetched data from the database:")
            st.write(df_database)

            excel_filename_db = "youtube_data_database.xlsx"
            df_database.to_excel(excel_filename_db, index=False)
            st.success(f"Data fetched from the database and saved to {excel_filename_db}")

        except Exception as e:
            st.error(f"An error occurred: {e}")

def run_tab11():
    st.title('Tweet Stats Per Channel')

    conn = connect_to_database()

    tweets, yesterday_str = get_tweets_last_day(conn)  

    stats = calculate_stats(tweets)

    st.write(f'**Stats for {yesterday_str}:**')
    for channel, count in stats.items():
        st.write(f"- {channel}: {count} tweets")

    fig, ax = plt.subplots()
    ax.bar(stats.keys(), stats.values())
    ax.set_xlabel('Channels')
    ax.set_ylabel('Number of Tweets')
    ax.set_title(f"Tweet Stats Per Channel {yesterday_str}")
    plt.xticks(rotation=45)
    st.pyplot(fig)

    if st.button("Fetch Data from Twitter"):
        df_tweets = pd.DataFrame(tweets, columns=['id', 'data_source', 'tweet_text', 'time_stamp'])

        # Display the DataFrame in Streamlit
        st.title(f"Data of Tweets for {yesterday_str}")
        st.dataframe(df_tweets)

    conn.close()

def fetch_data():
    # conn_string = os.getenv("DATABASE_URL")
    conn_string = st.secrets["DATABASE_URL"]
    conn = psycopg2.connect(conn_string)
    cur = conn.cursor()
    query = "SELECT * FROM coinmarket_historical_data"
    cur.execute(query)
    data = cur.fetchall()
    cur.close()
    conn.close()
    return data

def run_tab12():
    if st.button("Fetch Coin Market Cap Data"):
        with st.spinner("Fetching data..."):
            st.title("Historical Data")
            data = fetch_data()

            df = pd.DataFrame(data, columns=["id", "timestamp", "symbol", "percent_change_1h", "percent_change_24h", "percent_change_7d", "price", "volume_24h", "market_cap", "total_supply", "circulating_supply", "percent_change_30d"])

            st.dataframe(df)
    
def run_tab13():
    st.title('Cryptocurrency Price and Circulating Supply Visualization')
    symbol = st.selectbox("Select Symbol", ["IMX", "SAND"])
    frequency = st.radio("Select Frequency", ['Daily', 'Monthly'])
    df = fetch_data_coin(symbol)
    st.write(df)
    plot_line_graph(df, frequency)    

def fetch_data_fundraising():
    # conn_string = os.getenv("DATABASE_URL")
    conn_string = st.secrets["DATABASE_URL"]
    conn = psycopg2.connect(conn_string)
    cur = conn.cursor()
    query = "SELECT * FROM fundraising_data"
    cur.execute(query)
    data = cur.fetchall()
    cur.close()
    conn.close()
    return data

def run_tab14():
    if st.button("Fetch Crypto Fundraising Data"):
        with st.spinner("Fetching data..."):
            st.title("Crypto Fundraising Data")
            data = fetch_data_fundraising()

            df = pd.DataFrame(data, columns=["id", "project_name", "investor_names", "raised_date", "raised_amount"])

            st.dataframe(df)
    
def run_tab15():
    
    def create_db_from_uri():
        db_url = "postgresql+psycopg2://ucjaqskr8p8id6:p9721c6bd1d7d7d97cf608c68650475c54c27e9366893af0c017b705e29210072@ec2-54-197-133-119.compute-1.amazonaws.com/de2vvbr4bsnbvt"
        return SQLDatabase.from_uri(db_url)

    # Initialize Streamlit app
    st.title("Chat with Database")

    # Initialize session state
    if 'history' not in st.session_state:
        st.session_state.history = []

    # Create SQLDatabase instance
    db = create_db_from_uri()

    # openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_api_key = st.secrets["OPENAI_API_KEY"]


    # Create Langchain agent with OpenAI's GPT-3.5 model
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0, openai_api_key=openai_api_key)

    # Create agent executor
    agent_executor = create_sql_agent(llm, db=db, agent_type="openai-tools", verbose=True)

    # Define function to execute user queries
    def execute_query(query):
        # Invoke agent executor with user query
        response = agent_executor.invoke(query)
        st.session_state.history.append({"query": query, "response": response})
        return response

    # Render user input field and execute button
    user_query = st.text_input("Enter your query:")
    if st.button("Execute"):
        with st.spinner("Generating response..."):
            response = execute_query(user_query)
            st.write("Response:", response)

    # Render response history session
    st.subheader("Response History")
    for i, item in enumerate(st.session_state.history):
        st.write(f"{i + 1}. Query: {item['query']}")
        st.write(f"   Response: {item['response']}")

def run_tab16():
    st.header("Coin Data PDF's :books:")
    df = load_data()

    user_input = st.text_input("Enter the ticker name:")
    known_symbols = df['Symbol'].str.lower().tolist()

    # User input for selecting a coin symbol
    graph_input_symbol = user_input.strip().lower()

    if st.button("Search and Generate PDFs"):
        with st.spinner("Searching and Generating PDF..."):
            if user_input.strip() == "":
                return
    
            coin_names = find_coin_name(df, user_input)
            
            if not coin_names or "Ticker not found." in coin_names:
                st.error("Invalid Ticker! Please enter the correct Ticker/Symbol.")
                return

            for coin_name in coin_names:
                price_data = fetch_price_data(coin_name)
                token_sale_data = fetch_token_sale_data(coin_name)
                market_data = fetch_market_data(coin_name)
                vesting_data = fetch_vesting_data(coin_name)
                colnames, skynet_data = fetch_data_from_skynet(coin_name)

                pdf_generated = False

                if graph_input_symbol in known_symbols:
                    # Call fetch_historical_data function to get historical data
                    timestamps, prices, circulating_supplies = fetch_historical_data(graph_input_symbol)
                    if timestamps is not None and prices is not None and circulating_supplies is not None:
                        price_image_path, supply_image_path = generate_graphs(user_input, timestamps, prices, circulating_supplies)
                    else:
                        st.warning("Failed to fetch from coin market cap.")
                
                try:    
                    pdf_content = generate_pdf(coin_name, price_data, token_sale_data, market_data, vesting_data, colnames, skynet_data, price_image_path, supply_image_path)
                    pdf_generated = True
                except UnboundLocalError:
                    st.warning("This coin symbol is not in coin market cap.")
                if pdf_generated:
                    st.success("PDF Generated Successfully")
                    # Convert PDF content to base64
                    pdf_b64 = base64.b64encode(pdf_content).decode("utf-8")
                    # Generate download link using JavaScript
                    href = f'<a href="data:application/pdf;base64,{pdf_b64}" download="{coin_name}.pdf">Download {coin_name} PDF</a>'
                    st.markdown(href, unsafe_allow_html=True)

def fetch_coin_data(api_key, limit=5000):
    url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?limit={limit}"
    headers = {
        "X-CMC_PRO_API_KEY": api_key
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()['data']
    else:
        st.error("Failed to fetch coin data from the API.")
        return None

def filter_data(coins_data, x=None, y=None, z=None):
    filtered_coins = []

    if x is not None and y is not None and x > y:
        st.error("Invalid range: X must be less than or equal to Y.")
        return None
    
    for coin in coins_data:
        market_cap = coin['quote']['USD']['market_cap']
        volume_24h = coin['quote']['USD']['volume_24h']
        price = coin['quote']['USD']['price']
        name = coin['name']
        symbol = coin['symbol']

        if x is None:
            x = 0
        if y is None:
            y = float('inf')

        if x is None and y is None:
            st.error("Error: Either X or Y must have a value.")
            return None

        if z is not None and volume_24h < z:
            continue

        if market_cap >= x and market_cap <= y:
            # Calculate volume_24h_dollar
            volume_24h_dollar = volume_24h * price

            filtered_coins.append({
                'symbol': symbol,
                'coin_name': name,
                'marketcap': market_cap,
                'volume_24h': volume_24h,
                # 'price': price,
                'volume_24h_dollar': volume_24h_dollar  # Add new column
            })

    filtered_coins.sort(key=lambda x: x['marketcap'])
    return filtered_coins

def generate_pdf_filter(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Add table to PDF
    pdf.cell(200, 10, txt="Filtered Coins", ln=True, align="C")
    pdf.ln(10)
    col_width = 45
    row_height = 10
    for col in df.columns:
        pdf.cell(col_width, row_height, txt=unidecode(col), border=1)
    pdf.ln(row_height)
    for index, row in df.iterrows():
        for col in df.columns:
            pdf.cell(col_width, row_height, txt=unidecode(str(row[col])), border=1)
        pdf.ln(row_height)
    
    # Get PDF content buffer
    pdf_buffer = BytesIO()
    pdf_output = pdf.output(dest='S')
    pdf_buffer.write(pdf_output.encode('latin1'))
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    # Provide download button
    st.download_button(
        label="Download PDF",
        data=pdf_bytes,
        file_name="filtered_coins.pdf",
        mime="application/pdf"
    )


def run_tab17():
    st.title('Cryptocurrency Filter and Vesting Data')
    api_key = os.getenv("COIN_MARKET_API_KEY")
    api_key = st.secrets["COIN_MARKET_API_KEY"]
    coins_data = fetch_coin_data(api_key)
    if coins_data:
        x = st.number_input("Enter the minimum market cap (X)", value=None)
        y = st.number_input("Enter the maximum market cap (Y)", value=None)
        z = st.number_input("Enter the 24-hour volume $ (Z)", step=0.01, value=None)
        
        if st.button("Filter"):
            if x is None and y is None:
                st.error("Error: Either X or Y must have a value.")
            elif x is not None and y is not None and x > y:
                st.error("Invalid range: X must be less than or equal to Y.")
            else:
                filtered_coins = filter_data(coins_data, x, y, z)
                if filtered_coins is not None:
                    # Convert filtered data to DataFrame
                    df = pd.DataFrame(filtered_coins)
                    st.write(df)
                    # Generate PDF
                    buffer = BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=letter)
                    data = [df.columns.tolist()] + df.values.tolist()
                    table = Table(data, colWidths=[70, 120, 105, 100, 120])
                    style = TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                                        ('GRID', (0, 0), (-1, -1), 1, colors.black)])
                    table.setStyle(style)
                    elems = []
                    elems.append(table)
                    doc.build(elems)
                    pdf_data = buffer.getvalue()
                    buffer.close()

                    # Provide download button
                    st.download_button(
                        label="Download PDF",
                        data=pdf_data,
                        file_name="filtered_coins.pdf",
                        mime="application/pdf"
                   )
        if z is not None :
            show_vesting_data = st.selectbox("Do you want Vesting Data?", ('No', 'Yes'))
            if show_vesting_data == 'Yes':
                symbol = st.text_input('Enter the symbol of the coin:')
                if st.button('Get Vesting Data'):
                    df = load_data()
                    coin_names = find_coin_name(df, symbol)
                    print(coin_names)
                    for coin_name in coin_names:
                        vesting_data = fetch_vesting_data(coin_name)
                        if vesting_data:
                            today_date = datetime.date.today()
                            vesting_table_data = []
                            allocations = vesting_data['pageProps']['vestingInfo']['allocations']
                            for allocation in allocations:
                                name = allocation['name']
                                token_percent = allocation['tokens_percent']
                                token = allocation['tokens']
                                batches = allocation.get('batches', [])
                                for batch in batches:
                                    date = batch.get('date')
                                    unlock_percent = batch.get('unlock_percent')
                                    if date:
                                        date_obj = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ").date()
                                        if date_obj >= today_date:
                                            vesting_table_data.append([name, token_percent, token, date, unlock_percent])
                            vesting_table_data.sort(key=lambda x: x[3] if x[3] else "")
                            vesting_table_data.insert(0, ["Allocation Name", "Token Percent", "Tokens", "Batch Date", "Unlock Percent"])
                            st.write(f"Vesting Data for coin {coin_name}")
                            st.table(vesting_table_data)
                        else:
                            st.write(f"Vesting Data is missing in {coin_name} coin.")



def run_tab18():
    # connection_string = os.getenv("DATABASE_URL")
    connection_string = st.secrets["DATABASE_URL"]

    # Connect to PostgreSQL database
    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()

    # Function to calculate percentage change
    def calculate_percentage_change(current_price, old_price):
        return ((current_price - old_price) / old_price) * 100

    # Function to fetch historical price of a coin
    def fetch_historical_price(symbol, timestamp):
        six_months_ago = timestamp - timedelta(days=180)
        cursor.execute("SELECT price FROM coinmarket_historical_data WHERE symbol = %s AND timestamp >= %s ORDER BY timestamp ASC LIMIT 1", (symbol, six_months_ago))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            return None
        
    st.title("Filter by Price Action")
    price_change_desired = st.number_input("What is the price change desired in %", min_value=-100.0, max_value=100.0, step=0.01)

    if st.button("Filter"):
        st.subheader("List of coins with price change ({:.2f}% from 6 months ago)".format(price_change_desired))
        st.write("Symbol | Price Change % (+/-)")
        
        # Fetch all coins
        cursor.execute("SELECT DISTINCT symbol, price, timestamp FROM coinmarket_historical_data")
        coins = cursor.fetchall()
        
        # Filter coins based on price change
        for coin in coins:
            symbol, current_price, timestamp = coin
            historical_price = fetch_historical_price(symbol, timestamp)
            if historical_price is not None:
                percentage_change = calculate_percentage_change(current_price, historical_price)
                if percentage_change > price_change_desired:
                    st.write("{} | {:.2f}".format(symbol, percentage_change))
        

# Main Streamlit UI
st.title("DATA SCRAPPER")

# Create tabs using st.selectbox
selected_tab = st.selectbox("Select Tab", ["Discord", "Decrypt News","Coin Desk News","YouTube", "News BTC", "Crypto News", "Coin Desk Market", "Coin Desk Finance", "Coin Telegraph", "Data From Database", "Twitter Stats", "Coin Market Cap Data", "Coin Market Cap Graph", "Coin Fundraising Data", "Chat with Database", "PDF Research Report", "Coin Filtering Today", "Coin Filtering Historical"])

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
elif selected_tab == "Data From Database":
    run_tab10()
elif selected_tab == "Twitter Stats":
    run_tab11()
elif selected_tab == "Coin Market Cap Data":
    run_tab12()
elif selected_tab == "Coin Market Cap Graph":
    run_tab13()
elif selected_tab == "Coin Fundraising Data":
    run_tab14()
elif selected_tab == "Chat with Database":
    run_tab15()
elif selected_tab == "PDF Research Report":
    run_tab16()
elif selected_tab == "Coin Filtering Today":
    run_tab17()
elif selected_tab == "Coin Filtering Historical":
    run_tab18()