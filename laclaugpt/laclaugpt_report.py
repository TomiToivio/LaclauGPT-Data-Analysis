# API ID: 29615549
# API HASH: 39dcacf684d9616a06da8086fe77c088
from osint_ollama import get_ollama_model
from osint_mongo import insert_to_mongo, update_mongo, mongo_find_one, query_mongo, get_daily_messages, insert_report
import ollama
import pymongo
import pandas as pd
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
import datetime
from datetime import date
from datetime import datetime
from datetime import timedelta
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Only ERROR and above get logged
# Make dit logs if not exist
if not os.path.exists('../data/logs'):
    os.makedirs('../data/logs')
# Set up a rotating file handler
handler = RotatingFileHandler(
    filename='../data/logs/report.log',  # "virheet" means "errors" in Finnish
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
Your task is to create a daily report of previously analyzed multimodal Telegram messages related to the War in Ukraine and Russian geopolitics.

You will receive OSINT analysis results of Telegram messages published yesterday. Create a structured daily OSINT report based on the provided analyses.

---

### Input Data

You may receive:
* **Analysis Results**: Textual OSINT analysis of Telegram messages, including images and videos.

Use **all provided data** in your analysis.

---

### Tasks

#### 1. OSINT Analysis  
* Extract and summarize militarily relevant details from the analyses:
  * Units, personnel, equipment, tactics, locations, events.  
  * Evidence of hybrid warfare: propaganda, cyber, sabotage.  
  * Any mention of war crimes or human rights violations.
* Provide a **concise summary** of key findings of the most important militarily relevant details for yesterday. 
* Keep concise and factual, limit to **1024 tokens**, Markdown formatting allowed.  

#### 2. Political Analysis  
* Summarize the findings related to political sentiments and narratives:
  * Inside Russia: nationalism, pro-/anti-Putin narratives, dissent.  
  * War in Ukraine: support for invasion, escalation, peace, anti-NATO/Ukraine propaganda.  
  * Global geopolitics: Russia’s relations with China, Iran, North Korea, and rivalry with the West.  
* Provide a **concise summary** of key political narratives and sentiments for yesterday. 
* Limit to **1024 tokens**, objective and clear, Markdown formatting allowed.

---
"""

def ollama_daily_report(user_prompt, system_prompt, model):
   osint_report = None
   logger.debug(f"OSINT Analysis - User Prompt: {user_prompt}")
   options={"repeat_last_n": 64,
            "repeat_penalty": 1.1,
            "num_ctx": 10240,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.0,
            "temperature": 0.0,
            "num_predict": 4096}
   try:
      osint_report = ollama.chat(model=model, messages=[
                                 {'role': 'system', 'content': system_prompt}, 
                                 {'role': 'user', 'content': user_prompt},
                                 ], options=options)
      logger.debug(f'Full ollama response: {osint_report}')
      print(osint_report)
      osint_report = osint_report['message']
      logger.debug(f'Ollama message: {osint_report}')
      print(osint_report)
      osint_report = osint_report['content']
      print(osint_report)
      logger.debug(f'Ollama Content: {osint_report}')
   except Exception as e:
      logger.error(f'Error report: {e}')
   return osint_report

def osint_report():
   # Get yesterday's date in iso format
   # Get yesterday's date in iso format
   today = datetime.now()
   yesterday = today - timedelta(days=1)
   start_time = yesterday.strftime("%Y-%m-%d %H:%M:%S")
   end_time = today.strftime("%Y-%m-%d %H:%M:%S")
   # convert date_string to format YYYY-MM-DD
   model = get_ollama_model("tools")
   logger.info(f"Using model: {model}")
   print(f"Using model: {model}")
   if not model:
      logger.error("No model available for OSINT processing.")
      return False
   # Get all with nlp_processed = False
   try:
      # Loop through messages
      # Get all osint_preprocessed = True from mongo collection
      # Order so that latest messages are first
      mongo_messages = get_daily_messages()
      message_number = 1 
      user_prompt = f'''### User Prompt

      Create a daily report of the multimodal analysis results of the following Telegram messages from {start_time} to {end_time}. The messages are related to the War in Ukraine and Russian geopolitics. Provide structured daily OSINT report as per the tasks outlined in the system prompt. 
      
      '''
      for message in mongo_messages:
         print(message)
         message_url = message.get("message_url")
         message_date = message.get("message_date")
         multimodal_analysis = message.get("multimodal_analysis")
         # Skip if multimodal_analysis and message_text are both empty
         if not multimodal_analysis:
            logger.warning(f"Skipping message {message_url} due to lack of data.")
            print(f"Skipping message {message_url} due to lack of data.")
            continue
         # Take only 8 multimodal analysis results
         if message_number > 8:
            logger.info("Reached maximum of 8 messages for the report.")
            print("Reached maximum of 8 messages for the report.")
            break
         user_prompt += f'''

         ### OSINT Analysis result {message_number} of message from url {message_url} published on {message_date}

         ```
         {multimodal_analysis}
         ```

         '''
         message_number += 1
      logger.info(f"System Prompt: {system_prompt}")
      print(f"System Prompt: {system_prompt}")
      logger.info(f"User Prompt: {user_prompt}")
      print(f"User Prompt: {user_prompt}")
      daily_report = ollama_daily_report(user_prompt, system_prompt, model)
      logger.info(f"Daily Report: {daily_report}")
      print(f"Daily Report: {daily_report}")
      daily_report = str(daily_report)
      # Create new report_dict
      report_dict = {
         "report_date": end_time,
         "report_text": daily_report,
      }
      insert_report(end_time, report_dict)
      print(f"Updated MongoDB for report {end_time}.")
      logger.info(f"Updated MongoDB for report {end_time}.")
      # Write to latest-report.md
      with open("latest-report.md", "w", encoding="utf-8") as f:
         f.write(daily_report)
   except Exception as e:
      print(f"Error: {e}")
      logger.error(f"Error: {e}")
