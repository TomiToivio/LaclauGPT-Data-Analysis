import dotenv
import pandas as pd
import hashlib
import pymongo
import json
from os import listdir
from os.path import isfile, join
import time
import logging
from datetime import datetime
from datetime import timedelta
from logging.handlers import RotatingFileHandler
import os 
import dotenv
dotenv.load_dotenv()
# Load MONGO_URI, MONGO_DB_NAME, and other environment variables if needed
LACLAUGPT_MONGODB_URI = dotenv.get_key(dotenv.find_dotenv(), "MONGO_URI")
LACLAUGPT_MONGODB_DATABASE = dotenv.get_key(dotenv.find_dotenv(), "MONGO_DB_NAME")
LACLAUGPT_PROJECT_ID = dotenv.get_key(dotenv.find_dotenv(), "LACLAUGPT_PROJECT_ID")

# Make dir logs if not exists
if not os.path.exists('../data/logs'):
    os.makedirs('../data/logs')
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)  # Only ERROR and above get logged

# Set up a rotating file handler
handler = RotatingFileHandler(
    filename='../data/logs/mongo.log',  # "virheet" means "errors" in Finnish
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

mongo_client = pymongo.MongoClient(LACLAUGPT_MONGODB_URI)   
mongo_database = mongo_client[LACLAUGPT_MONGODB_DATABASE]

laclaugpt_mongo_prefix = f"laclaugpt2_{LACLAUGPT_PROJECT_ID}_"
scraper_collection = mongo_database[f"{laclaugpt_mongo_prefix}scraper_collection"]
map_collection = mongo_database[f"{laclaugpt_mongo_prefix}map_collection"]
network_collection = mongo_database[f"{laclaugpt_mongo_prefix}network_collection"]
dashboard_collection = mongo_database[f"{laclaugpt_mongo_prefix}dashboard_collection"]
sentiment_collection = mongo_database[f"{laclaugpt_mongo_prefix}sentiments_collection"]
entity_collection = mongo_database[f"{laclaugpt_mongo_prefix}entities_collection"]
timeline_collection = mongo_database[f"{laclaugpt_mongo_prefix}timeline_collection"]
topics_collection = mongo_database[f"{laclaugpt_mongo_prefix}topics_collection"]
report_collection = mongo_database[f"{laclaugpt_mongo_prefix}reports_collection"]
discourse_collection = mongo_database[f"{laclaugpt_mongo_prefix}discourse_collection"]

def insert_to_topics(topic, source_url, source_date):
   try:
      topic_string = f"{topic},{source_url},{source_date}"
      topic_hash = create_string_hash(topic_string)
      existing_topic = topics_collection.find_one({"topic_hash": topic_hash})
      if existing_topic:
         logger.info(f"Topic {topic} already exists, skipping insertion.")
         return True
      else:
         logger.info(f"Inserting topic {topic}.")
         topics_collection.insert_one({"topic": topic, "source_url": source_url, "source_date": source_date, "topic_hash": topic_hash})
         return True
   except Exception as e:
      logger.error(f"Failed to insert topic {topic} for message {source_url}: {e}")
      return False

def insert_to_sentiments(target, sentiment, source_url, source_date):
   try:
      hash_string = f"{target}_{sentiment}"
      sentiment_hash = create_string_hash(hash_string)
      sentiment_dict = {"target": target, "sentiment": sentiment, "source_url": source_url, "source_date": source_date, "sentiment_hash": sentiment_hash}
      existing_sentiment = sentiment_collection.find_one({"sentiment_hash": sentiment_hash})
      if existing_sentiment:
         logger.info(f"Sentiment for target {target} with sentiment {sentiment} for message {source_url} already exists, skipping insertion.")
         return True
      else:
         logger.info(f"Inserting sentiment with hash {sentiment_hash}.")
         sentiment_collection.insert_one(sentiment_dict)
         return True
   except Exception as e:
      logger.error(f"Failed to insert sentiment for target {target} with sentiment {sentiment} for message {source_url}: {e}")
      return False

def insert_to_entities(entity, source_url, source_date):
   # Check if entity already exists
   try:
      entity_string = f"{entity},{source_url},{source_date}"
      entity_hash = create_string_hash(entity_string)
      existing_entity = entity_collection.find_one({"entity_hash": entity_hash})
      if existing_entity:
         logger.info(f"Entity {entity} already exists, skipping insertion.")
         return True
      else:
         logger.info(f"Inserting entity {entity}.")
         entity_collection.insert_one({"entity": entity, "source_url": source_url, "source_date": source_date, "entity_hash": entity_hash})
         return True
   except Exception as e:
      logger.error(f"Failed to insert entity {entity} for message {source_url}: {e}")
      return False

def create_string_hash(hash_string):
   hash_result = hashlib.md5(hash_string.encode())
   hex_result = hash_result.hexdigest()
   return hex_result

def insert_to_timeline(source_url, event_name, event_date, event_location, event_description):
   hash_string = f"{source_url}_{event_name}_{event_date}_{event_location}_{event_description}"
   timeline_hash = create_string_hash(hash_string)
   timeline_dict = {
      "source_url": source_url,
      "event_name": event_name,
      "event_date": event_date,
      "event_location": event_location,
      "event_description": event_description,
      "timeline_hash": timeline_hash
   }
   try:
      existing_event = timeline_collection.find_one({"timeline_hash": timeline_hash})
      if existing_event:
         logger.info(f"Timeline event {event_name} for message {source_url} already exists, skipping insertion.")
         return True
      else:
         logger.info(f"Inserting timeline event {event_name} with hash {timeline_hash}.")
         timeline_collection.insert_one(timeline_dict)
         return True
   except Exception as e:
      logger.error(f"Failed to insert timeline event {event_name} for message {source_url}: {e}")
      return False

def insert_to_map(source_url, event_name, event_date, event_location, event_description, event_lat, event_lng):
   hash_string = f"{source_url}_{event_name}_{event_date}_{event_location}_{event_description}_{event_lat}_{event_lng}"
   event_hash = create_string_hash(hash_string)
   event_dict = {
      "source_url": source_url,
      "event_name": event_name,
      "event_date": event_date,
      "event_location": event_location,
      "event_description": event_description,
      "event_lat": event_lat,
      "event_lng": event_lng,
      "event_hash": event_hash
   }
   try:
      existing_event = map_collection.find_one({"event_hash": event_hash})
      if existing_event:
         logger.info(f"Event {event_name} for message {source_url} already exists, skipping insertion.")
         return True
      else:
         logger.info(f"Inserting event {event_name} with hash {event_hash}.")
         map_collection.insert_one(event_dict)
         return True
   except Exception as e:
      logger.error(f"Failed to insert event {event_name} for message {source_url}: {e}")
      return False

def insert_to_network(source_url, source_date, source_node, target_node, edge_description):
   try:
      hash_string = f"{source_node}_{target_node}_{edge_description}"
      edge_hash = create_string_hash(hash_string)
      edge_dict = {"source_url": source_url, "source_date": source_date, "source_node": source_node, "target_node": target_node, "edge_description": edge_description, "edge_hash": edge_hash}
      existing_edge = network_collection.find_one({"edge_hash": edge_hash})
      if existing_edge:
         logger.info(f"Network edge from {source_node} to {target_node} for message {source_url} already exists, skipping insertion.")
         return True
      else:
         logger.info(f"Inserting network edge with hash {edge_hash}.")
         network_collection.insert_one(edge_dict)
         return True
   except Exception as e:
      logger.error(f"Failed to insert network edge from {source_node} to {target_node} for message {source_url}: {e}")
      return False

def insert_to_dashboard(source_url, source_dict):
   # upsert to dashboard collection
   try:
      logger.info(f"Upserting message {source_url} into Dashboard MongoDB.")
      # add vector_processed = False to source_dict if not exists
      if "vector_processed" not in source_dict:
         source_dict["vector_processed"] = False
      # add graph_processed = False to source_dict if not exists
      if "graph_processed" not in source_dict:
         source_dict["graph_processed"] = False
      dashboard_collection.update_one({"source_url": source_url}, {"$set": source_dict}, upsert=True)
   except Exception as e:
      logger.error(f"Failed to upsert message {source_url} into Dashboard MongoDB: {e}")
      return False

def check_if_in_dashboard(source_url):
   try:
      message = dashboard_collection.find_one({"source_url": source_url})
      if message:
         logger.info(f"Found message {source_url} in Dashboard MongoDB.")
         return True
      else:
         logger.info(f"Message {source_url} not found in Dashboard MongoDB.")
         return False
   except Exception as e:
      logger.error(f"Failed to find message {source_url} in Dashboard MongoDB: {e}")
      return False

def insert_to_mongo(source_url, source_dict):
   if source_url.find_one({"source_url": source_url}) is not None:
      logger.info(f"Message {source_url} already exists in MongoDB, skipping insertion.")
      return True
   try:
      logger.info(f"Inserting message {source_url} into MongoDB.")
      # Use the source_url as the unique identifier
      # Insert into mongo
      source_url.insert_one({"source_url": source_url, **source_dict})
   except Exception as e:
      logger.error(f"Failed to insert message {source_url} into MongoDB: {e}")
      return False
   return True

def update_mongo(source_url, source_dict):
   try:
      logger.info(f"Updating message {source_url} in MongoDB.")
      source_url.update_one({"source_url": source_url}, {"$set": source_dict})
   except Exception as e:
      logger.error(f"Failed to update message {source_url} in MongoDB: {e}")
      return False
   return True

def mongo_find_one(source_url):
   try:
      message = source_url.find_one({"source_url": source_url})
      if message:
         logger.info(f"Found message {source_url} in MongoDB.")
         return message
      else:
         logger.info(f"Message {source_url} not found in MongoDB.")
         return None
   except Exception as e:
      logger.error(f"Failed to find message {source_url} in MongoDB: {e}")
      return None

def get_daily_messages():
   # covert date_string to datetime   
   # Get yesterday's date in iso format YYYY-MM-DD 
   today = datetime.now()
   yesterday = today - timedelta(days=1)
   start_time = yesterday.strftime("%Y-%m-%d %H:%M:%S")
   end_time = today.strftime("%Y-%m-%d %H:%M:%S")
   # Get messages where source_date between day_start and day_end
   # Get messages where message date is between start_time and end_time
   query = {
      "$and": [
         {"source_date": {"$gte": start_time}},
         {"source_date": {"$lte": end_time}},
      ]
   }
   try:
      messages = []
      for message in (
         dashboard_collection.find(query).sort("source_date", pymongo.DESCENDING).batch_size(8)):
         logger.info(f"Found message: {message.get('source_url')}")
         #print(f"Found message: {message.get('source_url')}")
         messages.append(message)
      logger.info(f"Total messages found: {len(messages)}")
      #print(f"Total messages found: {len(messages)}")
      return messages
   except Exception as e:
      logger.error(f"Failed to get yesterday's messages from MongoDB: {e}")
      #print(f"Failed to get yesterday's messages from MongoDB: {e}")
      return []

# Processing stages for basic LaclauGPT: preprocessing, multimodal, discourse, postprocessed
def query_mongo(laclaugpt_preprocessed=False, laclaugpt_multimodal=False, laclaugpt_discourse=False, laclaugpt_postprocessed=False):
   try:
      query = {
         "$and": [
            {"laclaugpt_preprocessed": laclaugpt_preprocessed},
            {"laclaugpt_multimodal": laclaugpt_multimodal},
            {"laclaugpt_discourse": laclaugpt_discourse},
            {"laclaugpt_postprocessed": laclaugpt_postprocessed},
         ]
      }
      logger.info(f"Querying MongoDB with: {query}")
      #print(f"Querying MongoDB with: {query}")
      messages = []
      for message in (
         scraper_collection.find(query).sort("source_date", pymongo.DESCENDING).batch_size(1000)
      ):
         logger.info(f"Found message: {message.get('source_url')}")
         #print(f"Found message: {message.get('source_url')}")
         messages.append(message)
      logger.info(f"Total messages found: {len(messages)}")
      #print(f"Total messages found: {len(messages)}")
      return messages
   except Exception as e:
      logger.error(f"Failed to query MongoDB: {e}")
      #print(f"Failed to query MongoDB: {e}")
      return []

def insert_report(report_date, report_dict):
   try:
      logger.info(f"Upserting report for date {report_date} into Reports MongoDB.")
      report_date = pd.to_datetime(report_date, errors='coerce')
      report_date = report_date.strftime("%Y-%m-%d %H:%M:%S")
      report_dict["report_date"] = report_date
      report_collection.update_one({"report_date": report_date}, {"$set": report_dict}, upsert=True)
      return True
   except Exception as e:
      logger.error(f"Failed to upsert report for date {report_date} into Reports MongoDB: {e}")
      return False

def report_collection_to_csv():
   try:
      df = pd.DataFrame(list(report_collection.find().sort("report_date", pymongo.DESCENDING).batch_size(100)))
      # Remove column _id
      if '_id' in df.columns:
         df = df.drop(columns=['_id'])
      # Convert report_date to iso format datetime
      df["report_date"] = pd.to_datetime(df["report_date"], errors='coerce')
      df["report_date"] = df["report_date"].dt.strftime("%Y-%m-%d %H:%M:%S")
      # Order dataframe by report_date descending
      df = df.sort_values(by='report_date', ascending=False)
      df.to_csv("report_collection.csv", index=False)
      logger.info("Exported report collection to report_collection.csv")
      return True
   except Exception as e:
      logger.error(f"Failed to export report collection to CSV: {e}")
      return False


def dataframe_collection_to_csv():
   try:
      df = pd.DataFrame(list(dashboard_collection.find().sort("source_date", pymongo.DESCENDING).batch_size(10000)))
      # Remove column _id
      if '_id' in df.columns:
         df = df.drop(columns=['_id'])
      # Order dataframe by source_date descending
      df = df.sort_values(by='source_date', ascending=False)
      # Loop through each row
      for index, row in df.iterrows():
         laclaugpt_entities = row["laclaugpt_entities"]
         laclaugpt_topics = row["laclaugpt_topics"]
         positive_sentiments = row["positive_sentiments"]
         negative_sentiments = row["negative_sentiments"]
         neutral_sentiments = row["neutral_sentiments"]
         #print(f"Row {index}: {laclaugpt_entities}, {laclaugpt_topics}, {positive_sentiments}, {negative_sentiments}, {neutral_sentiments}")
         if isinstance(laclaugpt_entities, list):
            entity_text = ""
            for entity in laclaugpt_entities:
               # strip leading and trailing whitespace and newlines
               entity = entity.strip()
               entity_text += entity + ","
            entity_text = entity_text.rstrip(",")  # remove trailing comma
            df.at[index, "laclaugpt_entities"] = str(entity_text)
         if isinstance(laclaugpt_topics, list):
            topic_text = ""
            for topic in laclaugpt_topics:
               topic = topic.strip()
               topic_text += topic + ","
            topic_text = topic_text.rstrip(",")
            df.at[index, "laclaugpt_topics"] = str(topic_text)
         if isinstance(positive_sentiments, list):
            positive_text = ""
            for sentiment in positive_sentiments:
               sentiment = sentiment.strip()
               positive_text += sentiment + ","
            positive_text = positive_text.rstrip(",")
            df.at[index, "positive_sentiments"] = str(positive_text)
         if isinstance(negative_sentiments, list):
            negative_text = ""
            for sentiment in negative_sentiments:
               sentiment = sentiment.strip()
               negative_text += sentiment + ","
            negative_text = negative_text.rstrip(",")
            df.at[index, "negative_sentiments"] = str(negative_text)
         if isinstance(neutral_sentiments, list):
            neutral_text = ""
            for sentiment in neutral_sentiments:
               sentiment = sentiment.strip()
               neutral_text += sentiment + ","
            neutral_text = neutral_text.rstrip(",")
            df.at[index, "neutral_sentiments"] = str(neutral_text)
      # Convert source_date to iso format datetime
      df["source_date"] = pd.to_datetime(df["source_date"], errors='coerce')
      df["source_date"] = df["source_date"].dt.strftime("%Y-%m-%d %H:%M:%S")
      df.to_csv("dataframe.csv", index=False)
      logger.info("Exported dataframe collection to dataframe.csv")
      return True
   except Exception as e:
      logger.error(f"Failed to export dataframe collection to CSV: {e}")
      return False