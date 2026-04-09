import os
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_classic.chains import RetrievalQA
from backend.database.mongodb import doc_collection
from backend.rag.spell_check import correct_spelling, fuzzy_match_query, expand_query_with_synonyms
import logging
import hashlib
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VECTOR_PATH = "vector_store"

embeddings = OpenAIEmbeddings()

vectorstore = None

llm = ChatOpenAI(
    temperature=0,
    model="gpt-4o-mini",
    request_timeout=30,  # Add timeout
    max_retries=2
)

async def build_vector_store():
    global vectorstore
    logger.info("Building vector store...")

    docs = []
    cursor = doc_collection.find({})

    async for doc in cursor:
        docs.append(
            Document(
                page_content=doc["page_content"],
                metadata=doc["metadata"]
            )
        )

    logger.info(f"Found {len(docs)} documents in MongoDB")

    if not docs:
        logger.warning("No documents found in MongoDB")
        vectorstore = None
        return None

    try:
        vectorstore = FAISS.from_documents(docs, embeddings)
        logger.info("FAISS vector store created successfully")

        os.makedirs(VECTOR_PATH, exist_ok=True)
        
        vectorstore.save_local(VECTOR_PATH)
        logger.info(f"Vector store saved to {VECTOR_PATH}")

    except Exception as e:
        logger.error(f"Error building vector store: {str(e)}")
        vectorstore = None
        return None

    return vectorstore


def verify_vector_store_integrity():
    hash_file = f"{VECTOR_PATH}/hash.txt"

    if os.path.exists(hash_file):
        with open(hash_file, 'r') as f:
            expected_hash = f.read().strip()

        # Compute current hash of index file (you can adjust file name if needed)
        index_file = f"{VECTOR_PATH}/index.faiss"
        if not os.path.exists(index_file):
            logger.error("Index file missing for integrity check")
            return False

        hasher = hashlib.sha256()
        with open(index_file, 'rb') as f:
            hasher.update(f.read())

        current_hash = hasher.hexdigest()

        if current_hash != expected_hash:
            logger.error("Vector store integrity check failed! Hash mismatch.")
            return False

        logger.info("Vector store integrity verified successfully")
        return True

    else:
        logger.warning("No hash file found. Skipping integrity check.")
        return True


def load_vector_store():
    global vectorstore
    logger.info("Loading vector store from disk...")

    if vectorstore is None:
        if os.path.exists(VECTOR_PATH):
            try:
                # ✅ Verify integrity BEFORE loading
                if not verify_vector_store_integrity():
                    logger.error("Aborting load due to failed integrity check.")
                    return None

                vectorstore = FAISS.load_local(
                    VECTOR_PATH,
                    embeddings,
                    allow_dangerous_deserialization=True
                )
                logger.info("Vector store loaded successfully from disk")

            except Exception as e:
                logger.error(f"Error loading vector store: {str(e)}")
                vectorstore = None
        else:
            logger.info(f"No vector store found at {VECTOR_PATH}")

    return vectorstore

async def get_qa_chain():
    logger.info("Getting QA chain...")
    store = load_vector_store()

    if not store:
        logger.info("No vector store found, building new one...")
        store = await build_vector_store()

    if not store:
        logger.warning("No vector store available")
        return None

    try:
        llm = ChatOpenAI(
            temperature=0,
            model="gpt-4o-mini",
            request_timeout=60
        )
        logger.info("LLM initialized")

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=store.as_retriever(search_kwargs={"k": 5}),
            return_source_documents=True
        )
        logger.info("QA chain created successfully")
        return qa_chain

    except Exception as e:
        logger.error(f"Error creating QA chain: {str(e)}")
        return None


async def enhanced_query_processing(query):
    logger.info(f"Original query: {query}")
    
    corrected_query = correct_spelling(query)
    if corrected_query != query:
        logger.info(f"Spell-corrected query: {corrected_query}")
    
    expanded_queries = expand_query_with_synonyms(corrected_query)
    logger.info(f"Generated {len(expanded_queries)} query variations")
    
    return corrected_query, expanded_queries


async def role_based_query(qa_chain, query):
    if qa_chain is None:
        logger.warning("QA chain is None")
        return {
            "result": "No documents found. Admin needs to upload files first.",
            "source_documents": []
        }

    corrected_query, expanded_queries = await enhanced_query_processing(query)
    
    prompt = f"""
You are my personal assistant. Answer the question using the knowledge base.

If the user has spelling mistakes, understand what they meant and answer accordingly.

Question: {corrected_query}

Note: The original query was: "{query}"
"""

    try:
        logger.info(f"Processing query with correction: {corrected_query[:50]}...")
        response = await qa_chain.ainvoke({"query": prompt})
        
        if "I don't know" in response["result"] or "I'm not sure" in response["result"]:
            for exp_query in expanded_queries[1:]:
                logger.info(f"Trying expanded query: {exp_query[:50]}...")
                alt_prompt = f"""
You are my personal assistant. Answer the question using the knowledge base.

The user might have meant: "{exp_query}"
Original question was: "{query}"

Please try to answer based on what they likely meant.
"""
                alt_response = await qa_chain.ainvoke({"query": alt_prompt})
                if "I don't know" not in alt_response["result"]:
                    response = alt_response
                    break
        
        logger.info("Query processed successfully")
        return response
    except Exception as e:
        logger.error(f"Error in role_based_query: {str(e)}")
        return {
            "result": f"Error processing query: {str(e)}",
            "source_documents": []
        }