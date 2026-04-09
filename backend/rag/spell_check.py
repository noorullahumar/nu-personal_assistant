import re
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

COMMON_WORDS = {
    'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
    'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
    'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she',
    'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their',
    'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go',
    'me', 'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know',
    'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could', 'them',
    'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come', 'its', 'over',
    'think', 'also', 'back', 'after', 'use', 'two', 'how', 'our', 'work',
    'first', 'well', 'way', 'even', 'new', 'want', 'because', 'any', 'these',
    'give', 'day', 'most', 'us'
}

TECHNICAL_TERMS = {
    'ai': 'AI',
    'ml': 'ML',
    'api': 'API',
    'gpt': 'GPT',
    'rag': 'RAG',
    'llm': 'LLM',
    'nlp': 'NLP',
    'pdf': 'PDF',
    'csv': 'CSV',
    'json': 'JSON',
    'html': 'HTML',
    'css': 'CSS',
    'js': 'JS',
    'mongodb': 'MongoDB',
    'mysql': 'MySQL',
    'postgresql': 'PostgreSQL',
    'fastapi': 'FastAPI',
    'langchain': 'LangChain',
    'openai': 'OpenAI',
    'chatgpt': 'ChatGPT',
    'claude': 'Claude',
    'gemini': 'Gemini',
    'copilot': 'Copilot'
}

COMMON_MISTAKES = {
    'teh': 'the',
    'recieve': 'receive',
    'wether': 'whether',
    'alot': 'a lot',
    'thier': 'their',
    'definately': 'definitely',
    'seperate': 'separate',
    'occured': 'occurred',
    'occurance': 'occurrence',
    'accomodate': 'accommodate',
    'comittment': 'commitment',
    'goverment': 'government',
    'wich': 'which',
    'happend': 'happened',
    'begining': 'beginning',
    'realy': 'really',
    'beleive': 'believe',
    'adress': 'address',
    'aparent': 'apparent',
    'calender': 'calendar',
    'concious': 'conscious',
    'existance': 'existence',
    'freind': 'friend',
    'imediately': 'immediately',
    'independant': 'independent',
    'interupt': 'interrupt',
    'knowlege': 'knowledge',
    'liason': 'liaison',
    'misspel': 'misspell',
    'neccessary': 'necessary',
    'occassion': 'occasion',
    'priveledge': 'privilege',
    'recomend': 'recommend',
    'refered': 'referred',
    'refering': 'referring',
    'religous': 'religious',
    'remeber': 'remember',
    'repesent': 'represent',
    'sence': 'sense',
    'similiar': 'similar',
    'specfic': 'specific',
    'suprise': 'surprise',
    'tommorow': 'tomorrow',
    'truely': 'truly',
    'unfortunatly': 'unfortunately',
    'untill': 'until',
    'wheter': 'whether',
    'writen': 'written'
}

def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def find_closest_word(word, word_list, max_distance=2):
    word = word.lower()
    
    if word in word_list:
        return word
    
    if word in COMMON_MISTAKES:
        return COMMON_MISTAKES[word]
    
    best_match = None
    best_distance = float('inf')
    
    for candidate in word_list:
        distance = levenshtein_distance(word, candidate)
        if distance < best_distance and distance <= max_distance:
            best_distance = distance
            best_match = candidate
    
    return best_match if best_match else word

def correct_spelling(text):
    if not text:
        return text
    
    words = re.findall(r'\b\w+\b|[^\w\s]', text)
    corrected_words = []
    
    for word in words:
        if not word.isalpha():
            corrected_words.append(word)
            continue
        
        word_lower = word.lower()
        if word_lower in TECHNICAL_TERMS:
            corrected_words.append(TECHNICAL_TERMS[word_lower])
            continue
        
        if word_lower in COMMON_MISTAKES:
            corrected_words.append(COMMON_MISTAKES[word_lower])
            logger.info(f"Spell correction: '{word}' -> '{COMMON_MISTAKES[word_lower]}'")
            continue
        
        closest = find_closest_word(word_lower, COMMON_WORDS)
        if closest != word_lower:
            if word[0].isupper():
                closest = closest.capitalize()
            corrected_words.append(closest)
            logger.info(f"Spell correction: '{word}' -> '{closest}'")
        else:
            corrected_words.append(word)
    
    result = ''
    for i, word in enumerate(corrected_words):
        if i > 0 and not word in '.,!?;:':
            result += ' '
        result += word
    
    return result

def fuzzy_match_query(query, documents, threshold=0.6):
    from backend.database.mongodb import doc_collection
    
    cursor = doc_collection.find({})
    best_matches = []
    
    for doc in cursor:
        content = doc["page_content"].lower()
        ratio = SequenceMatcher(None, query.lower(), content).ratio()
        if ratio > threshold:
            best_matches.append({
                "content": doc["page_content"],
                "similarity": ratio,
                "metadata": doc["metadata"]
            })
    
    best_matches.sort(key=lambda x: x["similarity"], reverse=True)
    return best_matches[:3]

def expand_query_with_synonyms(query):
    synonyms = {
        'how': ['way', 'method', 'approach'],
        'what': ['which', 'define', 'explain'],
        'tell': ['explain', 'describe', 'inform'],
        'make': ['create', 'build', 'develop'],
        'get': ['obtain', 'retrieve', 'fetch'],
        'find': ['search', 'locate', 'discover'],
        'change': ['modify', 'update', 'alter'],
        'remove': ['delete', 'eliminate', 'erase'],
        'add': ['insert', 'include', 'append'],
        'show': ['display', 'view', 'present'],
        'help': ['assist', 'support', 'aid'],
        'problem': ['issue', 'error', 'bug'],
        'fix': ['repair', 'correct', 'resolve'],
        'use': ['utilize', 'employ', 'apply'],
        'need': ['require', 'want', 'desire'],
        'good': ['great', 'excellent', 'positive'],
        'bad': ['poor', 'terrible', 'negative'],
        'big': ['large', 'huge', 'massive'],
        'small': ['tiny', 'little', 'miniature'],
        'quick': ['fast', 'rapid', 'swift'],
        'slow': ['sluggish', 'gradual', 'leisurely']
    }
    
    words = query.lower().split()
    expanded_queries = [query]
    
    for i, word in enumerate(words):
        if word in synonyms:
            for synonym in synonyms[word]:
                new_words = words.copy()
                new_words[i] = synonym
                expanded_queries.append(' '.join(new_words))
    
    corrected = correct_spelling(query)
    if corrected != query:
        expanded_queries.append(corrected)
    
    return list(set(expanded_queries))

if __name__ == "__main__":
    test_queries = [
        "what is artifishal inteligence",
        "how too crete a new file",
        "teh quikc brown fox",
        "i want too lern about AI",
        "what is the wheather today"
    ]
    
    for query in test_queries:
        corrected = correct_spelling(query)
        print(f"Original: {query}")
        print(f"Corrected: {corrected}")
        print("-" * 50)