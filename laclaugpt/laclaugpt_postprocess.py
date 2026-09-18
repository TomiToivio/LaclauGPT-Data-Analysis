from laclaugpt_ollama import get_ollama_model
from laclaugpt_mongo import insert_to_mongo, update_mongo, mongo_find_one, query_mongo, insert_to_map, insert_to_timeline, insert_to_network, insert_to_entities, insert_to_sentiments, insert_to_topics, check_if_in_dashboard, insert_to_dashboard
import ollama
import pymongo
import geocoder
import cv2
import os
import redis
import json
import shutil
import requests
from pydantic import BaseModel
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
    filename='data/logs/postprocess.log',  # "virheet" means "errors" in Finnish
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

class EDGE(BaseModel):
   source_node: str
   target_node: str
   edge_description: str

class EVENT(BaseModel):
   event_name: str
   event_date: str
   event_location: str
   event_description: str

class OSINT(BaseModel):
   laclaugpt_topics: list[str]
   laclaugpt_entities: list[str]
   positive_sentiments: list[str]
   neutral_sentiments: list[str]
   negative_sentiments: list[str]
   laclaugpt_events: list[EVENT]
   laclaugpt_network: list[EDGE]


system_prompt = """
### **System Prompt**

Your task is to convert analysis results into structured OSINT (Open Source Intelligence) data.
You will receive a previously generated multimodal LLM analysis of a Telegram message.
The messages are related to the Russia-Ukraine war and you need to extract militarily relevant information and political analysis from them.
Use the provided multimodal analysis as the basis of your work. Y
You must answer **strictly in JSON format**, following the provided **Pydantic model**:

```python
class EDGE(BaseModel):
   source_node: str
   target_node: str
   edge_description: str

class EVENT(BaseModel):
   event_name: str
   event_date: str
   event_location: str
   event_description: str

class OSINT(BaseModel):
   laclaugpt_topics: list[str]
   laclaugpt_entities: list[str]
   positive_sentiments: list[str]
   neutral_sentiments: list[str]
   negative_sentiments: list[str]
   laclaugpt_events: list[EVENT]
   laclaugpt_network: list[EDGE]
```

You will receive a previously generated multimodal LLM analysis of the message.
Use this multimodal analysis as the basis of your work.
All outputs must strictly match the JSON schema above.

---

### **Input Data**

You will receive:

* **Multimodal Analysis** (from a Mistal LLM)

---

### **Tasks**

#### 1. Topic Modeling → `laclaugpt_topics`

* Extract the main topics from the analysis (e.g., `"drone warfare"`, `"frontline battle"`, `"propaganda"`).
* Write the names of topics in English.
* Provide a **JSON list of topic names only**.
* Store the list in `laclaugpt_topics`.
* If none are found, return an empty list.

#### 2. Named Entities → `laclaugpt_entities`

* Extract named entities from the analysis.
* Units, personnel, organizations, places, events, dates, and weapons.
* Write the names of entities in English.
* Provide a **JSON list of entity names only**.
* Store the list in `laclaugpt_entities`.
* If none are found, return an empty list.

#### 3. Sentiment Analysis → `positive_sentiments`, `neutral_sentiments`, `negative_sentiments`

* Extract sentiment targets from the analysis.
* Write the targets in English.
* List the targets under three categories:
  * `positive_sentiments` → targets with positive tone.
  * `neutral_sentiments` → targets with neutral tone.
  * `negative_sentiments` → targets with negative tone.
* Provide **JSON lists of targets only** (no explanations).
* If none are found for a classification, return an empty list.

#### 4. Event Extraction → `laclaugpt_events`

* Extract militarily or geopolitically relevant events mentioned in the analysis.
* Usually there should be only 0-1 events per message.
* For each event, provide:
* `event_name` → name of the event (e.g., `"drone strike"`, `"artillery attack"`, `"troop movement"`).
* `event_date` → date of the event (e.g., `"2023-10-05"`). If no date is mentioned, use the message date. This should be in ISO 8601 format (YYYY-MM-DD). It will be used to create an event timeline.
* `event_location` → location of the event (e.g., `"Bakhmut", `"Donetsk region"`). If no location is mentioned, use `"unknown"`. This should be a geocodable location. It will used to plot the event on a map.
* `event_description` → brief description of the event (1-2 sentences).
* Provide the event details in English.
* Provide a **JSON list of event objects**.
* Store the list in `laclaugpt_events`.
* If no events are found, return an empty list.

### 5. Network Extraction → `laclaugpt_network`

* Extract relationships between entities mentioned in the analysis.
* If you cannot determine relationships, return an empty list.
* Named entities are the source and target nodes of the relationship.
* Create edges between entities when you can identify a relationship. 
* For each edge relationship, provide:
* `source_node` → the source entity in the relationship (e.g., `"Unit A"`).
* `target_node` → the target entity in the relationship (e.g., `"Location X"`).
* `edge_description` → brief description of the relationship (e.g., `"deployed to"`, `"attacked"`).
* Provide the relationship details in English.
* Provide a **JSON list of edge objects**.
* Store the list in `laclaugpt_network`.
* If no relationships are found, return an empty list.

---
"""


def ollama_laclaugpt_analysis(user_prompt, system_prompt, model):
   # mistral-small3.2:24b or gemma3:27b
   laclaugpt_analysis = None
   logger.debug(f"OSINT Analysis - User Prompt: {user_prompt}")
   options={"repeat_last_n": 64,
            "repeat_penalty": 1.1,
            "num_ctx": 8192,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.0,
            "temperature": 0.0,
            "num_predict": 2048}
   try:
      laclaugpt_analysis = ollama.chat(model=model, messages=[
                                 {'role': 'system', 'content': system_prompt}, 
                                 {'role': 'user', 'content': user_prompt},
                                 ], options=options,  format=OSINT.model_json_schema())
      laclaugpt_analysis = OSINT.model_validate_json(laclaugpt_analysis.message.content)
      print(f'OSINT Analysis: {laclaugpt_analysis}')
      logger.debug(f'OSINT Analysis: {laclaugpt_analysis}')
   except Exception as e:
      logger.error(f'Error processing analysis: {e}')
      print(f'Error processing analysis: {e}')
   return laclaugpt_analysis

def get_geolocation(address):
   geo_string = ""
   lat = None
   lng = None
   try:
      geo = geocoder.mapbox(address,key='pk.eyJ1Ijoia3liZXJwdW5ra2FyaSIsImEiOiJjbWVsNTVqMXMwOWhmMmpxenE3NmV0YjVqIn0.IKrUarc0rWuYvL_dKsdUvQ')
      geojson = geo.json
      json_address = geojson["address"]
      lat = geojson["lat"]
      lng = geojson["lng"]
      geo_string = f"{json_address} ({lat}, {lng})"
      print(f"Geolocation for {address}: {geo_string}")
      logger.info(f"Geolocation for {address}: {geo_string}")
   except Exception as e:
      logger.error(f"Error getting geolocation for {address}: {e}")
      print(f"Error getting geolocation for {address}: {e}")
   return lat, lng

def laclaugpt_postprocess():
   model = get_ollama_model("structured")
   if not model:
      logger.error("No model available for OSINT postprocessing.")
      return False
   try:
      logger.info("Starting OSINT postprocessing...")
      mongo_messages = query_mongo(laclaugpt_preprocessed=True, laclaugpt_processed=True, laclaugpt_postprocessed=False)
      logger.info(f"Found {len(mongo_messages)} messages to process.")
      print(f"Found {len(mongo_messages)} messages to process.")
      for message in mongo_messages:
         print(message)
         message_id = message.get("message_id")
         channel_id = message.get("channel_id")
         channel_url = message.get("channel_url")
         message_url = message.get("message_url")
         message_date = message.get("message_date")
         message_text = message.get("message_text")
         # Get if available else empty string
         local_multimodal_file = message.get("local_multimodal_file", "")
         local_media_file = message.get("local_media_file", "")
         whisper_transcript = message.get("whisper_transcript", "")
         whisper_language = message.get("whisper_language", "")
         whisper_translated = message.get("whisper_translated", "")
         ocr_text = message.get("ocr_text", "")
         local_multimodal_file = message.get("local_multimodal_file", "")
         local_media_file = message.get("local_media_file", "")
         message_raw_text = message.get("message_raw_text", "")
         logger.info(f"Processing message {message_id} from channel {channel_id} with text {message_text}.")
         print(f"Processing message {message_id} from channel {channel_id} with text {message_text}.")
         message_language = message.get("message_language")
         translated_text = message.get("translated_text")
         laclaugpt_processed = message.get("laclaugpt_processed")
         laclaugpt_preprocessed = message.get("laclaugpt_preprocessed")
         laclaugpt_postprocessed = message.get("laclaugpt_postprocessed")
         spacy_entities = message.get("spacy_entities")
         multimodal_analysis = message.get("multimodal_analysis")
         if not message_text:
            logger.warning(f"Skipping message {message_url} due to lack of data.")
            print(f"Skipping message {message_url} due to lack of data.")
            continue
         user_prompt = f'''### **User Prompt**:

         Analyze the provided multimodal analysis of Telegram message {message_url} from channel {channel_url} published on {message_date}. 

         **Data for Analysis**:

         1. **Multimodal Analysis**:
         ```
         {multimodal_analysis}
         ```

         '''
         logger.info(f"System Prompt: {system_prompt}")
         print(f"System Prompt: {system_prompt}")
         logger.info(f"User Prompt: {user_prompt}")
         print(f"User Prompt: {user_prompt}")
         laclaugpt_results = ollama_laclaugpt_analysis(user_prompt, system_prompt, model)
         # If laclaugpt_results is None, skip
         if not laclaugpt_results:
            logger.warning(f"Skipping message {message_url} due to empty OSINT results.")
            print(f"Skipping message {message_url} due to empty OSINT results.")
            continue
         laclaugpt_postprocessed = True
         # Get OSINT results
         laclaugpt_entities = laclaugpt_results.laclaugpt_entities
         laclaugpt_topics = laclaugpt_results.laclaugpt_topics
         positive_sentiments = laclaugpt_results.positive_sentiments
         neutral_sentiments = laclaugpt_results.neutral_sentiments
         negative_sentiments = laclaugpt_results.negative_sentiments
         laclaugpt_events = laclaugpt_results.laclaugpt_events
         laclaugpt_network = laclaugpt_results.laclaugpt_network
         event_name = ""
         event_date = ""
         event_location = ""
         event_description = "" 
         event_lat = ""
         event_lng = ""
         edge_list = []
         event_list = []
         if laclaugpt_network:
            for edge in laclaugpt_network:
               source_node = edge.source_node
               target_node = edge.target_node
               edge_description = edge.edge_description
               logger.info(f"Edge - Source: {source_node}, Target: {target_node}, Description: {edge_description}")
               print(f"Edge - Source: {source_node}, Target: {target_node}, Description: {edge_description}")
               edge_list.append({
                  "source_node": source_node,
                  "target_node": target_node,
                  "edge_description": edge_description
               })
         if laclaugpt_events:
            for event in laclaugpt_events:
               event_name = event.event_name
               event_date = event.event_date
               event_location = event.event_location
               event_description = event.event_description
               logger.info(f"Event - Name: {event_name}, Date: {event_date}, Location: {event_location}, Description: {event_description}")
               print(f"Event - Name: {event_name}, Date: {event_date}, Location: {event_location}, Description: {event_description}")
               event_lat, event_lng = get_geolocation(event_location)
               event_list.append({
                  "event_name": event_name,
                  "event_date": event_date,
                  "event_location": event_location,
                  "event_description": event_description,
                  "event_lat": event_lat,
                  "event_lng": event_lng,
               })
               logger.info(f"Event: {event_name}, Date: {event_date}, Location: {event_location}, Lat: {event_lat}, Lng: {event_lng}, Description: {event_description}")
               print(f"Event: {event_name}, Date: {event_date}, Location: {event_location}, Lat: {event_lat}, Lng: {event_lng}, Description: {event_description}")
               if event_lat and event_lng:
                  insert_to_map(message_url, event_name, event_date, event_location, event_description, event_lat, event_lng)
               # Check if event_date is a valid date
               if event_date and event_date != "N/A":
                  insert_to_timeline(message_url, event_name, event_date, event_location, event_description)
         if laclaugpt_network:
            for edge in laclaugpt_network:
               source_node = edge.source_node
               target_node = edge.target_node
               edge_description = edge.edge_description
               logger.info(f"Network Edge: {source_node} -> {target_node}, Description: {edge_description}")
               print(f"Network Edge: {source_node} -> {target_node}, Description: {edge_description}")
               insert_to_network(message_url, message_date, source_node, target_node, edge_description)
         for entity in laclaugpt_entities:
            logger.info(f"Entity: {entity}")
            print(f"Entity: {entity}")
            insert_to_entities(entity, message_url, message_date)
         for sentiment in positive_sentiments:
            logger.info(f"Positive Sentiment: {sentiment}")
            print(f"Positive Sentiment: {sentiment}")
            insert_to_sentiments(sentiment, "positive", message_url, message_date)
         for sentiment in neutral_sentiments:
            logger.info(f"Neutral Sentiment: {sentiment}")
            print(f"Neutral Sentiment: {sentiment}")
            insert_to_sentiments(sentiment, "neutral", message_url, message_date)
         for sentiment in negative_sentiments:
            logger.info(f"Negative Sentiment: {sentiment}")
            print(f"Negative Sentiment: {sentiment}")
            insert_to_sentiments(sentiment, "negative", message_url, message_date)
         for topic in laclaugpt_topics:
            logger.info(f"Topic: {topic}")
            print(f"Topic: {topic}")
            insert_to_topics(topic, message_url, message_date)
            # Convert laclaugpt_topics to string
         laclaugpt_topics = ", ".join(laclaugpt_topics)
         # Convert other lists to strings
         laclaugpt_entities = ", ".join(laclaugpt_entities)
         positive_sentiments = ", ".join(positive_sentiments)
         neutral_sentiments = ", ".join(neutral_sentiments)
         negative_sentiments = ", ".join(negative_sentiments)
         print(f"OSINT Entities: {laclaugpt_entities}")
         logger.info(f"OSINT Entities: {laclaugpt_entities}")
         print(f"OSINT Topics: {laclaugpt_topics}")
         logger.info(f"OSINT Topics: {laclaugpt_topics}")
         print(f"Positive Sentiments: {positive_sentiments}")
         logger.info(f"Positive Sentiments: {positive_sentiments}")
         print(f"Neutral Sentiments: {neutral_sentiments}")
         logger.info(f"Neutral Sentiments: {neutral_sentiments}")
         print(f"Negative Sentiments: {negative_sentiments}")
         logger.info(f"Negative Sentiments: {negative_sentiments}")
         # Create new message_dict
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
            "laclaugpt_processed": laclaugpt_processed,
            "laclaugpt_preprocessed": laclaugpt_preprocessed,
            "laclaugpt_postprocessed": laclaugpt_postprocessed,
            "spacy_entities": str(spacy_entities),
            "multimodal_analysis": str(multimodal_analysis),
            "whisper_transcript": str(whisper_transcript),
            "whisper_language": str(whisper_language),
            "whisper_translated": str(whisper_translated),
            "ocr_text": str(ocr_text),
            "local_multimodal_file": str(local_multimodal_file),
            "local_media_file": str(local_media_file),
            "laclaugpt_entities": str(laclaugpt_entities),
            "laclaugpt_topics": str(laclaugpt_topics),
            "positive_sentiments": str(positive_sentiments),
            "neutral_sentiments": str(neutral_sentiments),
            "negative_sentiments": str(negative_sentiments),
            "laclaugpt_events": event_list,
            "laclaugpt_network": edge_list,
            "event_name": event_name,
            "event_date": event_date,
            "event_location": event_location,
            "event_description": event_description,
            "event_lat": event_lat,
            "event_lng": event_lng,
         }
         update_mongo(message_url, message_dict)
         print(f"Updated MongoDB for message {message_id}.")
         logger.info(f"Updated MongoDB for message {message_id}.")
         insert_to_dashboard(message_url, message_dict)
         logger.info(f"Inserted message {message_url} to dashboard.")
         print(f"Inserted message {message_url} to dashboard.")
   except Exception as e:
      print(f"Error updating MongoDB for message {message_id}: {e}")
      logger.error(f"Error updating MongoDB for message {message_id}: {e}")
