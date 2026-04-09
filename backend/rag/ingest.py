import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from backend.database.mongodb import doc_collection

async def process_pdf_to_mongodb(pdf_path, document_id=None):
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=200
    )
    split_docs = splitter.split_documents(docs)

    new_entries = [
        {
            "page_content": doc.page_content,
            "metadata": {
                "source": os.path.basename(doc.metadata.get("source", "")),
                "page": doc.metadata.get("page", None),
                "document_id": document_id
            }
        }
        for doc in split_docs
    ]

    if new_entries:
        await doc_collection.insert_many(new_entries)
    
    return len(new_entries)