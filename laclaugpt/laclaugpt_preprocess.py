# API ID: 29615549
# API HASH: 39dcacf684d9616a06da8086fe77c088
from laclaugpt_mongo import insert_to_mongo, update_mongo, mongo_find_one, query_mongo
from deep_translator import GoogleTranslator
import pymongo
import os
import redis
import json
import shutil
import requests
import random
from os import listdir
from os.path import isfile, join
import time
from telethon.sync import TelegramClient, events
import spacy
import geocoder
from langdetect import detect
import logging
import whisper
import easyocr
import cv2
from logging.handlers import RotatingFileHandler
# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)  # Only ERROR and above get logged
# Set up a rotating file handler
handler = RotatingFileHandler(
    filename='../data/logs/preprocess.log',  # "virheet" means "errors" in Finnish
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
en_nlp = spacy.load("en_core_web_sm")
vasama_channel_id = 2922944282
easyocr_reader = easyocr.Reader(['ru','uk','en']) 
# MMake it load to GPU-3
whisper_model = whisper.load_model('large', device="cuda:3")

def get_spacy_entities(text):
   try:
      doc = en_nlp(text)
      entities_list = []
      for ent in doc.ents:
         entities_list.append(f"{ent.text} ({ent.label_})")
         # If ent.label_ is FAC, GPE or LOC
   except Exception as e:
      logger.error(f"Error processing entity: {e}")
   return entities_list

def get_language(text):
   try:
      lang = detect(text)
      return lang
   except Exception as e:
      logger.error(f"Error detecting language for text: {e}")
      return "xx"

def save_keyframe(downloaded_file, channel_id, source_id):
   try:
      vidcap = cv2.VideoCapture(downloaded_file)
      milliseconds = 1000
      vidcap.set(cv2.CAP_PROP_POS_MSEC, milliseconds)
      (success, image) = vidcap.read()
      new_filename = f'{source_id}_{channel_id}_keyframe.jpg'
      if success:
         cv2.imwrite(new_filename, image)
         print(f"Keyframe saved for video {downloaded_file}")
         logger.debug(f'Keyframe saved for video {downloaded_file}')
         return new_filename
      else:
         print(f"Failed to extract keyframe for video {downloaded_file}")
         logger.warning(f"Failed to extract keyframe for video {downloaded_file}")
         return False
   except Exception as e:
      logger.error(f"Error saving keyframe for video {downloaded_file}: {e}")
      print(f"Error saving keyframe for video {downloaded_file}: {e}")
   return False


def get_transcript(video_filename):
   whisper_transcript = ''
   whisper_language = ''
   whisper_translated = ''
   try:
      result = whisper_model.transcribe(video_filename, temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
      whisper_transcript = str(result['text'])
      whisper_language = result['language']
      whisper_translated = GoogleTranslator(source='auto', target='en').translate(whisper_transcript[:3000])
      logger.debug(f"Whisper Transcript: {whisper_transcript}")
      logger.debug(f"Whisper Language: {whisper_language}")
      logger.debug(f"Whisper Translated: {whisper_translated}")
   except Exception as e:
      logger.error(f'Error transcribing video {video_filename}: {e}')
      print(f'Error transcribing video {video_filename}: {e}')
   return (whisper_transcript, whisper_language, whisper_translated)

def ocr_process(image_path):
   ocr_text = ''
   try:
      # Perform OCR on the image
      ocr_results = easyocr_reader.readtext(image_path)
      ocr_text = ''
      for ocr_result in ocr_results:
         ocr_text = ocr_text + ocr_result[1]
         ocr_text = ocr_text + '\n'
      logger.debug(f"OCR Result for {image_path}: {ocr_results}")
   except Exception as e:
      logger.error(f"Error performing OCR on {image_path}: {e}")
      ocr_text = ""
   return ocr_text


def laclaugpt_preprocess():
   try:
      mongo_messages = query_mongo(laclaugpt_preprocessed=False, laclaugpt_multimodal=False, laclaugpt_discourse=False, laclaugpt_postprocessed=False)
      for message in mongo_messages:
         print(message)
         source_id = message.get("source_id")
         channel_id = message.get("channel_id")
         channel_url = message.get("channel_url")
         source_url = message.get("source_url")
         source_date = message.get("source_date")
         source_text = message.get("source_text")
         local_media_file = message.get("local_media_file", "")
         source_raw_text = message.get("source_raw_text")
         logger.info(f"Processing message {source_id} from channel {channel_id} with text {source_text}.")
         print(f"Processing message {source_id} from channel {channel_id} with text {source_text}.")
         # Skip where source_text is empty
         if not source_text:
            logger.warning(f"Skipping message {source_url} due to lack of data.")
            print(f"Skipping message {source_url} due to lack of data.")
            continue
         source_language = message.get("source_language")
         translated_text = message.get("translated_text")
         laclaugpt_preprocessed = message.get("laclaugpt_preprocessed")
         laclaugpt_processed = message.get("laclaugpt_processed")
         laclaugpt_postprocessed = message.get("laclaugpt_postprocessed")
         spacy_entities = []
         spacy_entities_text = ""
         whisper_transcript = ""
         whisper_language = ""
         whisper_translated = ""
         local_multimodal_file = ""
         ocr_text = ""
         if translated_text:
            new_spacy_entities = get_spacy_entities(translated_text)
            if new_spacy_entities:
               spacy_entities.extend(new_spacy_entities)
               print(f"New spaCy entities for message {source_id}: {new_spacy_entities}")
               logger.info(f"New spaCy entities for message {source_id}: {new_spacy_entities}")
         if local_media_file:
            logger.info(f"Processing local media file for message {source_id}.")
            # If local_media_file ends with mp4
            if local_media_file.lower().endswith(".mp4"):
               # Check if file exists
               if os.path.exists(local_media_file):
                  try:
                     whisper_transcript, whisper_language, whisper_translated = get_transcript(local_media_file)
                     logger.info(f"Whisper processed for message {source_id}: {whisper_transcript}")
                     logger.info(f"Whisper language for message {source_id}: {whisper_language}")
                     logger.info(f"Whisper translated for message {source_id}: {whisper_translated}")
                     print(f"Whisper processed for message {source_id}: {whisper_transcript}")
                     print(f"Whisper language for message {source_id}: {whisper_language}")
                     print(f"Whisper translated for message {source_id}: {whisper_translated}")
                  except Exception as e:
                     logger.error(f"Error processing whisper for message {source_id}: {e}")
                  if whisper_translated:
                     new_spacy_entities = get_spacy_entities(whisper_translated)
                     if new_spacy_entities:
                        spacy_entities.extend(new_spacy_entities)
                        print(f"New spaCy entities for message {source_id}: {new_spacy_entities}")
                        logger.info(f"New spaCy entities for message {source_id}: {new_spacy_entities}")
                  try:
                     local_multimodal_file = save_keyframe(local_media_file, channel_id, source_id)
                     if local_multimodal_file:
                        print(f"Keyframe saved for video {local_media_file}")
                        logger.info(f"Keyframe saved for video {local_media_file}")
                        ocr_text = ocr_process(local_multimodal_file)
                        local_keyframes_path = f'data/keyframes/{channel_id}/{source_id}/'
                        os.makedirs(local_keyframes_path, exist_ok=True)
                        # Get filename of downloaded file
                        new_multimodal_filename = os.path.join(local_keyframes_path, local_multimodal_file)
                        # Move the file to the directory
                        shutil.move(local_multimodal_file, new_multimodal_filename)
                        local_multimodal_file = new_multimodal_filename
                     else:
                        print(f"Failed to extract keyframe for video {local_media_file}")
                        logger.warning(f"Failed to extract keyframe for video {local_media_file}")
                        local_multimodal_file = ""
                  except Exception as e:
                     print(f"Error saving keyframe for video {local_media_file}: {e}")
                     logger.error(f"Error saving keyframe for video {local_media_file}: {e}")
                     local_multimodal_file = ""
            elif local_media_file.lower().endswith(".jpg"):
               # Check if file exists
               local_multimodal_file = local_media_file
               try:
                  ocr_text = ocr_process(local_multimodal_file)
                  print(f"OCR processed for message {source_id}: {ocr_text}")
                  logger.info(f"OCR processed for message {source_id}: {ocr_text}")
               except Exception as e:
                  logger.error(f"Error processing OCR for message {source_id}: {e}")
                  ocr_text = ""
         else:
            logger.warning(f"No local media file found for message {source_id}.")
         laclaugpt_preprocessed = True
         # If length is greater than 0
         if len(spacy_entities) > 0:
            spacy_entities = list(set(spacy_entities))
            spacy_entities_text = ", ".join(spacy_entities)
         # Make message dict with updated entities
         source_dict = {
            "source_id": str(source_id),
            "channel_id": str(channel_id),
            "channel_url": str(channel_url),
            "source_url": str(source_url),
            "source_date": str(source_date),
            "source_text": str(source_text),
            "source_raw_text": str(source_raw_text),
            "source_language": str(source_language),
            "translated_text": str(translated_text),
            "laclaugpt_processed": laclaugpt_processed,
            "laclaugpt_preprocessed": laclaugpt_preprocessed,
            "laclaugpt_postprocessed": laclaugpt_postprocessed,
            "spacy_entities": str(spacy_entities_text),
            "ocr_text": str(ocr_text),
            "local_media_file": str(local_media_file),
            "local_multimodal_file": str(local_multimodal_file),
            "whisper_transcript": str(whisper_transcript),
            "whisper_language": str(whisper_language),
            "whisper_translated": str(whisper_translated),
         }
         update_success = update_mongo(source_url, source_dict)
         if update_success:
            print(f"Successfully updated MongoDB for message {source_id}.")
            logger.info(f"Successfully updated MongoDB for message {source_id}.")
         else:
            print(f"Failed to update MongoDB for message {source_id}.")
            logger.error(f"Failed to update MongoDB for message {source_id}.")
   except Exception as e:
      print(f"Error updating MongoDB for message {source_id}: {e}")
      logger.error(f"Error updating MongoDB for message {source_id}: {e}")
