import chromadb
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core import StorageContext
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import Settings
from llama_index.readers.file import PandasCSVReader

parser = PandasCSVReader()
file_extractor = {".csv": parser}  # Add other CSV formats as needed
documents = SimpleDirectoryReader(
    "./csv", file_extractor=file_extractor
).load_data()

Settings.llm = Ollama(
    model="gemma3:4b",
    request_timeout=120.0,
    # Manually set the context window to limit memory usage
    context_window=8000,
)

# define embedding function
Settings.embed_model = OllamaEmbedding(
    model_name="nomic-embed-text:latest",
    base_url="http://localhost:11434",
    # Can optionally pass additional kwargs to ollama
    # ollama_additional_kwargs={"mirostat": 0},
)

# initialize client, setting path to save data
db = chromadb.PersistentClient(path="./chroma_db")

# create collection
chroma_collection = db.get_or_create_collection("vasama_osint")

# assign chroma as the vector_store to the context
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
storage_context = StorageContext.from_defaults(vector_store=vector_store)

# create your index
index = VectorStoreIndex.from_vector_store(
    vector_store, storage_context=storage_context, embed_model=Settings.embed_model
)

# create a query engine and query
query_engine = index.as_query_engine(llm=Settings.llm)
response = query_engine.query("Are Russian soldiers HIV-positive rapists?")
print(response)
