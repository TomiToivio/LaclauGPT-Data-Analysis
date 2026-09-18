# collect RSS feeds as a sample
from laclaugpt_mongo import insert_to_mongo, update_mongo, mongo_find_one, query_mongo
from deep_translator import GoogleTranslator
import os
import json
import shutil
import requests
import random
from os import listdir
from os.path import isfile, join
import time
import datetime
from telethon.sync import TelegramClient, events
from langdetect import detect
import logging
from logging.handlers import RotatingFileHandler
# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)  # Only ERROR and above get logged
# Create data/logs directory if it doesn't exist
os.makedirs('../data/logs', exist_ok=True)
# Set up a rotating file handler
handler = RotatingFileHandler(
    filename='../data/logs/collect.log',  # "virheet" means "errors" in Finnish
    maxBytes=5 * 1024 * 1024,      # 5 MB per file
    backupCount=3,                 # Keep 3 rotated files
    encoding='utf-8'
)
# Craft a formatter with Finnish-style datetime
formatter = logging.Formatter(
    fmt='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%d.%m.%Y %H:%M:%S'   # Finnish format: day.month.year hour:minute:second
)
handler.setFormatter(formatter)
logger.addHandler(handler)
vasama_channel_id = 2922944282

def detect_language(text):
   try:
      lang = detect(text)
      return lang
   except Exception as e:
      logger.error(f"Error detecting language for text: {e}")
      return "xx"

def parse_message(message, channel_url):
   try:
      message_id = message.id
      message_id = str(message_id)
      channel_id = message.peer_id.channel_id if message.peer_id else None
      message_url = f"{channel_url}/{message_id}"
      # skip if message_id already in mongo collection
      if mongo_find_one(message_url):
         logger.info(f"Message {message_url} exists in MongoDB, skipping.")
         return None
      message_date = message.date
      message_text = str(message.text)
      logger.debug(f"Message Text: {message_text}")
      message_raw_text = str(message.raw_text)
      message_language = "xx"
      translated_text = ""
      if message_raw_text:
         translated_text = GoogleTranslator(source='auto', target='en').translate(message_raw_text[:3000])
         message_language = detect_language(message_raw_text)
         logger.debug(f"Translated Text: {translated_text}")
      message_date = message_date or datetime.datetime.now()
      # Format message_date in Finnish locale dd.mm.yyyy HH:MM:SS
      #message_date = message_date.strftime("%d.%m.%Y %H:%M:%S")
      # Convert message_date to iso format datetime
      message_date = message_date.strftime("%Y-%m-%d %H:%M:%S")
      local_media_file = ""
      laclaugpt_preprocessed = False
      laclaugpt_processed = False
      laclaugpt_postprocessed = False
      downloaded_file = message.download_media()
      print(f"Downloaded Media: {downloaded_file}")
      logger.debug(f"Downloaded Media: {downloaded_file}")
      if downloaded_file:
         # Create path if it doesn't exist
         local_media_path = f'data/downloads/telegram/{channel_id}/{message_id}/'
         os.makedirs(local_media_path, exist_ok=True)
         # Get filename of downloaded file
         local_media_file = os.path.join(local_media_path, downloaded_file)
         # Move the file to the directory
         shutil.move(downloaded_file, local_media_file)
         logger.info(f"Media file moved to: {local_media_file}")
         print(f"Media file moved to: {local_media_file}")
      # Parse to text
      message_dict = {
         "message_id": str(message_id),
         "channel_id": str(channel_id),
         "channel_url": str(channel_url),
         "message_url": str(message_url),
         "message_date": str(message_date),
         "message_text": str(message_text),
         "message_raw_text": str(message_raw_text),
         "message_language": str(message_language),
         "translated_text": str(translated_text),
         "local_media_file": str(local_media_file),
         "laclaugpt_preprocessed": laclaugpt_preprocessed,
         "laclaugpt_processed": laclaugpt_processed,
         "laclaugpt_postprocessed": laclaugpt_postprocessed,
      }
      insert_to_mongo(message_url, message_dict)
      logger.info(f"Parsed message {message_url} successfully.")
      return message_dict
   except Exception as e:
      logger.error(f"Error parsing message: {e}")
      return None


def laclaugpt_collect(channel_url, number=20):
   try:
      api_id = "29615549"
      api_hash = "39dcacf684d9616a06da8086fe77c088"
      api_username = get_username()
      telegram_client = TelegramClient(api_username, api_id, api_hash)
      telegram_client.start()
      logger.info("Telegram client started successfully.")
      messages = telegram_client.get_messages(channel_url, number)
      logger.info(f"Fetched {len(messages)} messages from {channel_url}")
      result_message = f"Fetched {len(messages)} messages from {channel_url}."
      for message in messages:
         message_text = str(message.text)
         # Skip where message_text is empty string
         if not message_text:
            logger.warning(f"Skipping message {message.id} due to lack of data.")
            print(f"Skipping message {message.id} due to lack of data.")
            continue
         parse_message(message, channel_url)
         logger.info(f"Processed message ID {message.id} from {channel_url}")
      telegram_client.disconnect()
      return result_message
   except Exception as e:
      logger.error(f"Error fetching messages from {channel_url}: {e}")
      result_message = f"Error fetching messages from {channel_url}: {e}"
      return result_message

