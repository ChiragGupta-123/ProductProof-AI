from dotenv import load_dotenv
load_dotenv()
from app.services.rag import ingest_documents
print("Ingested",ingest_documents(),"knowledge chunks")
