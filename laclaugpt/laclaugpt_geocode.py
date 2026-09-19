from laclaugpt.laclaugpt_mongo import insert_to_mongo, update_mongo, mongo_find_one, query_mongo, check_if_in_dashboard, insert_to_network, insert_to_dashboard, insert_to_map, insert_to_entities, insert_to_sentiments, insert_to_timeline, insert_to_topics
import geocoder
import logging
from logging.handlers import RotatingFileHandler
import os

MAPBOX_API_KEY = os.getenv("LACLAUGPT_MAPBOX_API_KEY") or os.getenv("MAPBOX_API_KEY")

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Only ERROR and above get logged
# Set up a rotating file handler
handler = RotatingFileHandler(
    filename='../data/logs/geocode.log',  # "virheet" means "errors" in Finnish
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

def get_geolocation(address):
   geo_string = ""
   lat = None
   lng = None
   try:
      geo = geocoder.mapbox(address,key=MAPBOX_API_KEY)
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


def geocode_events():
    messages = query_mongo(laclaugpt_preprocessed=True, laclaugpt_discoursed=True,  laclaugpt_multimodal=True, laclaugpt_postprocessed=True)
    event_lat, event_lng = None, None
    event_name, event_date, event_location, event_description = None, None, None, None
    for message in messages:
        try:
            source_url = message.get("source_url")
            channel_url = message.get("channel_url")
            source_date = message.get("source_date")
            source_text = message.get("source_text")
            source_language = message.get("source_language")
            translated_text = message.get("translated_text")
            spacy_entities = message.get("spacy_entities")
            whisper_transcript = message.get("whisper_transcript")
            whisper_language = message.get("whisper_language")
            whisper_translated = message.get("whisper_translated")
            ocr_text = message.get("ocr_text")
            multimodal_analysis = message.get("multimodal_analysis")
            laclaugpt_entities = message.get("laclaugpt_entities")
            laclaugpt_entities = laclaugpt_entities.split(",") if laclaugpt_entities else []
            laclaugpt_topics = message.get("laclaugpt_topics")
            # Transform to list if not already
            laclaugpt_topics = laclaugpt_topics.split(",") if laclaugpt_topics else []
            positive_sentiments = message.get("positive_sentiments")
            # Transform to list if not already
            positive_sentiments = positive_sentiments.split(",") if positive_sentiments else []
            neutral_sentiments = message.get("neutral_sentiments")
            # Transform to list if not already
            neutral_sentiments = neutral_sentiments.split(",") if neutral_sentiments else []
            negative_sentiments = message.get("negative_sentiments")
            # Transform to list if not already
            negative_sentiments = negative_sentiments.split(",") if negative_sentiments else []
            laclaugpt_events = message.get("laclaugpt_events")
            if not isinstance(laclaugpt_events, list):
                laclaugpt_events = eval(laclaugpt_events) if laclaugpt_events else []
            laclaugpt_network = message.get("laclaugpt_network")
            if not isinstance(laclaugpt_network, list):
                laclaugpt_network = eval(laclaugpt_network) if laclaugpt_network else []
            print(f"Processing message: {source_url}")
            logger.info(f"Processing message: {source_url}")
            # Check if in dashboard
            if check_if_in_dashboard(source_url):
                logger.info(f"Message {source_url} is already in the dashboard.")
                print(f"Message {source_url} is already in the dashboard.")
                continue
            for entity in laclaugpt_entities:
                logger.info(f"Entity: {entity}")
                print(f"Entity: {entity}")
                insert_to_entities(entity, source_url, source_date)
            for sentiment in positive_sentiments:
                logger.info(f"Positive Sentiment: {sentiment}")
                print(f"Positive Sentiment: {sentiment}")
                insert_to_sentiments(sentiment, "positive", source_url, source_date)
            for sentiment in neutral_sentiments:
                logger.info(f"Neutral Sentiment: {sentiment}")
                print(f"Neutral Sentiment: {sentiment}")
                insert_to_sentiments(sentiment, "neutral", source_url, source_date)
            for sentiment in negative_sentiments:
                logger.info(f"Negative Sentiment: {sentiment}")
                print(f"Negative Sentiment: {sentiment}")
                insert_to_sentiments(sentiment, "negative", source_url, source_date)
            for topic in laclaugpt_topics:
                logger.info(f"Topic: {topic}")
                print(f"Topic: {topic}")
                insert_to_topics(topic, source_url, source_date)
            laclaugpt_events = message.get("laclaugpt_events")
            if laclaugpt_events:
                for event in laclaugpt_events:
                    source_url = message.get("source_url")
                    event_name = event.get("event_name")
                    event_date = event.get("event_date")
                    event_location = event.get("event_location")
                    event_description = event.get("event_description")
                    event_lat, event_lng = get_geolocation(event_location)
                    logger.info(f"Event: {event_name}, Date: {event_date}, Location: {event_location}, Lat: {event_lat}, Lng: {event_lng}, Description: {event_description}")
                    print(f"Event: {event_name}, Date: {event_date}, Location: {event_location}, Lat: {event_lat}, Lng: {event_lng}, Description: {event_description}")
                    if event_lat and event_lng:
                        insert_to_map(source_url, event_name, event_date, event_location, event_description, event_lat, event_lng)
                    # Check if event_date is a valid date
                    if event_date and event_date != "N/A":
                        insert_to_timeline(source_url, event_name, event_date, event_location, event_description)
            laclaugpt_network = message.get("laclaugpt_network")
            if laclaugpt_network:
                for network in laclaugpt_network:
                    source_url = message.get("source_url")
                    source_date = message.get("source_date")
                    source_node = network.get("source_node")
                    target_node = network.get("target_node")
                    edge_description = network.get("edge_description")
                    logger.info(f"Network Edge: {source_node} -> {target_node}, Description: {edge_description}")
                    print(f"Network Edge: {source_node} -> {target_node}, Description: {edge_description}")
                    insert_to_network(source_url, source_date, source_node, target_node, edge_description)
            source_dict = {
                "source_url": source_url,
                "channel_url": channel_url,
                "source_date": source_date,
                "source_text": source_text,
                "source_language": source_language,
                "translated_text": translated_text,
                "spacy_entities": spacy_entities,
                "whisper_transcript": whisper_transcript,
                "whisper_language": whisper_language,
                "whisper_translated": whisper_translated,
                "ocr_text": ocr_text,
                "multimodal_analysis": multimodal_analysis,
                "laclaugpt_entities": laclaugpt_entities,
                "laclaugpt_topics": laclaugpt_topics,
                "positive_sentiments": positive_sentiments,
                "neutral_sentiments": neutral_sentiments,
                "negative_sentiments": negative_sentiments,
                "laclaugpt_events": laclaugpt_events,
                "laclaugpt_network": laclaugpt_network,
                "event_name": event_name,
                "event_date": event_date,
                "event_location": event_location,
                "event_description": event_description,
                "event_lat": event_lat,
                "event_lng": event_lng,
            }
            insert_to_dashboard(source_url, source_dict)
            logger.info(f"Inserted message {source_url} to dashboard.")
            print(f"Inserted message {source_url} to dashboard.")
        except Exception as e:
            logger.error(f"Error processing network for message {message.get('source_url')}: {e}")
            print(f"Error processing network for message {message.get('source_url')}: {e}")

