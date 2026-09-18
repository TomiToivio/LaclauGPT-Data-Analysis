import logging
import os
import logging
from logging.handlers import RotatingFileHandler
from ollama import Client
import dotenv
dotenv.load_dotenv()
OLLAMA_HOST = dotenv.get_key(dotenv.find_dotenv(), "OLLAMA_HOST")
# Create data/logs directory if it doesn't exist
os.makedirs('../data/logs', exist_ok=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) 
# Set up a rotating file handler
handler = RotatingFileHandler(
    filename='../data/logs/ollama.log', 
    maxBytes=5 * 1024 * 1024,      
    backupCount=3,                 
    encoding='utf-8'
)
# Craft a formatter with Finnish-style datetime
formatter = logging.Formatter(
    fmt='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%d.%m.%Y %H:%M:%S'   
)
handler.setFormatter(formatter)
logger.addHandler(handler)

def get_ollama_model(model_type="multimodal"):
    client = Client(host=OLLAMA_HOST, headers={'x-some-header': 'some-value'})
    if model_type not in ["multimodal", "structured", "tools", "embedding", "cloud", "small"]:
        logger.error(f"Invalid model type: {model_type}. Must be one of 'multimodal', 'structured', 'tools', 'embedding', 'cloud', 'small'.")
        return False
    processes = ollama.ps()
    running_models = []
    number_of_models = len(processes["models"])
    if number_of_models == 4:
        logger.info("All 4 models are running.")
        print("All 4 models are running.")
        return False
    for process in processes["models"]:
        model = process["model"]
        print(f"Model: {model} running")
        logger.info(f"Model: {model} running")
        running_models.append(model)
    # This doesn't make so much sense as gemma4:12b can do everything?
    # Basically should test from largest model to smallest and then cloud if necessary.
    if model_type == "multimodal":
        models = ["gemma4:12b"]
    elif model_type == "structured":
        models = ["gemma4:12b"]
    elif model_type == "tools":
        models = ["gemma4:12b"]
    elif model_type == "embedding":
        models = ["embeddinggemma"]
    elif model_type == "cloud":
        models = ["gemma4:31b-cloud"]
    elif model_type == "small":
        models = ["gemma4:e2b"]
    else:
        logger.error(f"Invalid model type: {model_type}. Must be one of 'multimodal', 'structured', 'tools', 'embedding', 'cloud', 'small'.")
        return False
    return_model = False
    for model in models:
        if model not in running_models:
            logger.info(f"Offering model: {model}")
            print(f"Offering model: {model}")
            return_model = model
            return return_model
    logger.info(f"All models for type {model_type} are running.")
    print(f"All models for type {model_type} are running.")
    return return_model