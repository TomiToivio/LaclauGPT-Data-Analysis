from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.readers.file import (
    DocxReader,
    HWPReader,
    PDFReader,
    EpubReader,
    FlatReader,
    HTMLTagReader,
    ImageCaptionReader,
    ImageReader,
    ImageVisionLLMReader,
    IPYNBReader,
    MarkdownReader,
    MboxReader,
    PptxReader,
    PandasCSVReader,
    VideoAudioReader,
    UnstructuredReader,
    PyMuPDFReader,
    ImageTabularChartReader,
    XMLReader,
    PagedCSVReader,
    CSVReader,
    RTFReader,
)
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from IPython.display import Markdown, display
import chromadb
from llama_index.core import Settings


Settings.llm = Ollama(
    model="gemma3:4b",
    request_timeout=120.0,
    # Manually set the context window to limit memory usage
    context_window=8000,
)

db = chromadb.PersistentClient(path="./chroma_db")
chroma_collection = db.get_or_create_collection("vasama_osint")

# define embedding function
Settings.embed_model = OllamaEmbedding(
    model_name="nomic-embed-text:latest",
    base_url="http://localhost:11434",
    # Can optionally pass additional kwargs to ollama
    # ollama_additional_kwargs={"mirostat": 0},
)

# load documents
# Pandas CSV Reader example
parser = PandasCSVReader()
file_extractor = {".csv": parser}  # Add other CSV formats as needed
documents = SimpleDirectoryReader(
    "./csv", file_extractor=file_extractor
).load_data()

# set up ChromaVectorStore and load in data
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

storage_context = StorageContext.from_defaults(vector_store=vector_store, persist_dir="./storage")

index = VectorStoreIndex.from_documents(
    documents, 
    storage_context=storage_context, 
    embed_model=Settings.embed_model
)

# Query Data
query_engine = index.as_query_engine(llm=Settings.llm)
response = query_engine.query("Has Russia committed war crimes?")
print(response)

index.storage_context.persist("./storage")
