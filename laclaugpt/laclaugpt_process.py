# API ID: 29615549
# API HASH: 39dcacf684d9616a06da8086fe77c088
from laclaugpt_ollama import get_ollama_model
from laclaugpt_mongo import insert_to_mongo, update_mongo, mongo_find_one, query_mongo
import ollama
from deep_translator import GoogleTranslator
import pymongo
import cv2
import os
import json
import shutil
import requests
import random
from os import listdir
from os.path import isfile, join
import time
import logging
from logging.handlers import RotatingFileHandler
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)  # Only ERROR and above get logged
# Set up a rotating file handler
handler = RotatingFileHandler(
    filename='data/logs/process.log',  # "virheet" means "errors" in Finnish
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

system_prompt = """### System Prompt

You are an advanced OSINT analysis model.  
Your task is to analyze **multimodal Telegram messages** related to the **War in Ukraine** and **Russian geopolitics**.  

Messages may originate from **Russian, Ukrainian, or Western sources**. Consider potential **biases, propaganda, and disinformation techniques**, especially in the context of Russian hybrid warfare (deception, cyber, proxies, narrative warfare).  

You must extract and analyze **all available data** (text, images, video transcripts, metadata). Provide structured, concise, and objective outputs.

---

### Input Data

You may receive:
* **Message text and translation**
* **Metadata** (channel name, timestamp, etc.)
* **Images** (photos or frames from videos) 
* **Video transcripts and translations** (Whisper output, if available)

Use **all provided data** in your analysis.

---

### Tasks

#### 1. Multimodal Summary  
* Provide an **objective, concise summary** of the content.  
* If images: describe uniforms, insignia, weapons, vehicles, symbols, visible text, location clues, and activities.  
* If videos: integrate transcript/translation context.  
* Limit to **512 tokens max**, Markdown formatting allowed.  

#### 2. OSINT Analysis  
* Extract militarily relevant details:
  * Units, personnel, equipment, tactics, locations, events.  
  * Evidence of hybrid warfare: propaganda, cyber, sabotage.  
  * Any mention of war crimes or human rights violations.  
* Keep concise and factual, **≤512 tokens**, Markdown formatting allowed.  

#### 3. Political Analysis  
* Examine expressed **political sentiments**:
  * Inside Russia: nationalism, pro-/anti-Putin narratives, dissent.  
  * War in Ukraine: support for invasion, escalation, peace, anti-NATO/Ukraine propaganda.  
  * Global geopolitics: Russia’s relations with China, Iran, North Korea, and rivalry with the West.  
* Identify **disinformation or propaganda techniques**.  
* Limit to **512 tokens**, objective and clear.  

#### 4. Topic Modeling  
* Extract the **main topics** of the post (e.g., “drone warfare”, “frontline battle”, “propaganda”).  
* Provide a **list** of topics, each with a short description in plain language.  

#### 5. Named Entities  
* Extract **militarily and geopolitically relevant entities**:  
  * Units, personnel, organizations, places, events, dates, weapons.  
* For each entity, provide:  
  * **Name**  
  * **Type** (e.g., unit, weapon, person, organization, location, date, event)  
  * **Relevance** (why it matters to the conflict)  
* Present as a **formatted list**.  

#### 6. Sentiment Analysis  
* Identify **sentiments and their targets**:  
  * Political/geopolitical attitudes toward countries, leaders, armies, alliances.  
* For each sentiment, provide:  
  * **Target entity**  
  * **Sentiment classification** (positive, negative, neutral)  
  * **Description** of the sentiment.  
* Present as a **structured list**.  

#### 7. Event Map & Timeline  
* Extract the **most important verifiable event** mentioned. Only include if relevant to Ukraine war or Russian geopolitics.  
* Provide:  
  * **Event Name** (3-5 words)  
  * **Date** (ISO 8601 format, YYYY-MM-DD; approximate if necessary, round to first of month/year if exact unknown)  
  * **Location** (city, region, country; must be geocodable)  
  * **Short Description** (1-2 sentences)  
* If no major event is present, output: `"No major events mentioned."`  
* Extract **only one event per message** — the most significant one.  

---
"""


def ollama_multimodal_analysis(user_prompt, system_prompt, model, frame_file=None):
   multimodal_analysis = None
   logger.debug(f"OSINT Analysis - User Prompt: {user_prompt}")
   images = []
   # If frame_file is not None
   if frame_file is not None:
      logger.debug(f'Processing image: {frame_file}')
      images = [frame_file]
   options={"repeat_last_n": 64,
            "repeat_penalty": 1.1,
            "num_ctx": 8192,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.0,
            "temperature": 0.0,
            "num_predict": 4096}
   try:
      multimodal_analysis = ollama.chat(model=model, messages=[
                                 {'role': 'system', 'content': system_prompt}, 
                                 {'role': 'user', 'content': user_prompt, 'images': images},
                                 ], options=options)
      multimodal_analysis = multimodal_analysis['message']
      multimodal_analysis = multimodal_analysis['content']
      logger.debug(f'Frame description: {multimodal_analysis}')
   except Exception as e:
      logger.error(f'Error processing image: {e}')
   return multimodal_analysis

def laclaugpt_process():
   model = get_ollama_model("multimodal")
   if not model:
      logger.error("No model available for OSINT processing.")
      return False
   # Get all with nlp_processed = False
   try:
      # Loop through messages
      # Get all laclaugpt_preprocessed = True from mongo collection
      # Order so that latest messages are first
      mongo_messages = query_mongo(laclaugpt_preprocessed=True, laclaugpt_processed=False, laclaugpt_postprocessed=False)
      for message in mongo_messages:
         print(message)
         source_id = message.get("source_id")
         channel_id = message.get("channel_id")
         channel_url = message.get("channel_url")
         source_url = message.get("source_url")
         source_date = message.get("source_date")
         source_text = message.get("source_text")
         source_raw_text = message.get("source_raw_text")
         logger.info(f"Processing message {source_id} from channel {channel_id} with text {source_text}.")
         print(f"Processing message {source_id} from channel {channel_id} with text {source_text}.")
         source_language = message.get("source_language")
         translated_text = message.get("translated_text")
         laclaugpt_preprocessed = message.get("laclaugpt_preprocessed")
         laclaugpt_processed = message.get("laclaugpt_processed")
         laclaugpt_postprocessed = message.get("laclaugpt_postprocessed")
         laclaugpt_discourse = message.get("laclaugpt_discourse")
         spacy_entities = message.get("spacy_entities")
         # Skip if whisper_transcript and source_text are both empty
         if not source_text:
            logger.warning(f"Skipping message {source_url} due to lack of data.")
            print(f"Skipping message {source_url} due to lack of data.")
            continue
         user_prompt = f'''### **User Prompt**:

         Analyze the provided data from Telegram message {source_url} from channel {channel_url} published on {source_date}. If an image file is available, please include it in your analysis. It can be a photo attached to the message or a frame extracted from a video.

         **Data for Analysis**:

         1. **Message Text**:
         ```
         {source_text}
         ```

         2. **Message Translated**:
         ```
         {translated_text}
         ```

         '''
         # if whisper_transcript is available, add it to the user_prompt
         whisper_transcript = message.get("whisper_transcript", "")
         whisper_language = message.get("whisper_language", "")
         whisper_translated = message.get("whisper_translated", "")
         if whisper_transcript:
            user_prompt += f'''3. **Video Transcript**:
            ```
            {whisper_transcript}
            ```

            4. **Video Transcript Translated**:
            ```
            {whisper_translated}
            ```
            '''
         # if ocr_text is available, add it to the user_prompt
         ocr_text = message.get("ocr_text", "")
         if ocr_text:
            user_prompt += f'''5. **Image OCR Text**:
            ```
            {ocr_text}
            ```
            '''
         frame_file = None
         local_media_file = message.get("local_media_file", "")
         # If local_multimodal_file is available, use it as frame_file
         local_multimodal_file = message.get("local_multimodal_file", "")
         if local_multimodal_file and os.path.exists(local_multimodal_file):
            frame_file = local_multimodal_file
            logger.info(f"Using local multimodal file {local_multimodal_file} for analysis.")
            print(f"Using local multimodal file {local_multimodal_file} for analysis.")
         logger.info(f"System Prompt: {system_prompt}")
         print(f"System Prompt: {system_prompt}")
         logger.info(f"User Prompt: {user_prompt}")
         print(f"User Prompt: {user_prompt}")
         multimodal_analysis = ollama_multimodal_analysis(user_prompt, system_prompt, model, frame_file=frame_file)
         # If multimodal analysis is empty, skip
         if not multimodal_analysis:
            logger.warning(f"Skipping message {source_url} due to empty analysis.")
            print(f"Skipping message {source_url} due to empty analysis.")
            continue
         logger.info(f"Multimodal Analysis: {multimodal_analysis}")
         print(f"Multimodal Analysis: {multimodal_analysis}")
         laclaugpt_processed = True
         multimodal_analysis = str(multimodal_analysis)
         # Create new source_dict
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
            "laclaugpt_preprocessed": laclaugpt_preprocessed,
            "laclaugpt_processed": laclaugpt_processed,
            "laclaugpt_postprocessed": laclaugpt_postprocessed,
            "laclaugpt_discourse": laclaugpt_discourse,
            "laclaugpt_topics": laclaugpt_topics,
            "laclaugpt_entities": laclaugpt_entities,
            "positive_sentiments": positive_sentiments,
            "negative_sentiments": negative_sentiments,
            "spacy_entities": str(spacy_entities),
            "multimodal_analysis": str(multimodal_analysis),
            "whisper_transcript": str(whisper_transcript),
            "whisper_language": str(whisper_language),
            "whisper_translated": str(whisper_translated),
            "ocr_text": str(ocr_text),
            "local_multimodal_file": str(local_multimodal_file),
            "local_media_file": str(local_media_file),
         }
         update_mongo(source_url, source_dict)
         print(f"Updated MongoDB for message {source_id}.")
         logger.info(f"Updated MongoDB for message {source_id}.")
         # write to latest analysis .md
         with open("latest-analysis.md", "w", encoding="utf-8") as f:
            f.write(multimodal_analysis)
   except Exception as e:
      print(f"Error updating MongoDB for message {source_id}: {e}")
      logger.error(f"Error updating MongoDB for message {source_id}: {e}")
