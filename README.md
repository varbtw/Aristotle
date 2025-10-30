# Research Model - AI Research Assistant

An AI-powered research assistant that finds, indexes, and summarizes scholarly papers using ChromaDB vector search and the Semantic Scholar API.

## Features

- **Vector-based Paper Search**: Uses ChromaDB to store and query research papers
- **Automatic Indexing**: Automatically fetches and indexes papers from Semantic Scholar when needed
- **Smart Intent Routing**: Uses Gemini AI to determine whether to search papers or answer questions directly
- **Paper Summarization**: Automatically summarizes research findings related to user queries

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

Create a `.env` file in the project root with your API keys:

```env
GEMINI_API_KEY=your_gemini_api_key_here
SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_api_key_here
```

**Getting API Keys:**
- **Gemini API Key**: Get from [Google AI Studio](https://aistudio.google.com/)
- **Semantic Scholar API Key**: Get from [Semantic Scholar API](https://www.semanticscholar.org/product/api)

### 3. Run the Agent

```bash
python my_agent.py
```

Or use the agent programmatically:

```python
from my_agent import agent

result = agent("find me 5 papers about machine learning in healthcare")
print(result)
```

## Project Structure

- `my_agent.py` - Main agent with intent routing and paper query logic
- `my_chroma.py` - ChromaDB wrapper for paper indexing and retrieval
- `scholar_api.py` - Semantic Scholar API integration
- `gemini.py` - Legacy/commented version (not active)
- `chroma_db/` - Local ChromaDB database storage

## Usage Examples

### Search for Papers
```
User: find me 10 papers about climate change adaptation
```

### Ask Questions
```
User: What is the difference between RCTs and observational studies?
```

### Request Research Paper
### Fact-check a claim
```
/fact "Intermittent fasting lowers LDL" context=metabolic syndrome diet
```

### Fact-check a paper by id or title
```
/factpaper ca1bf071eda2bb5bcc0f87f84446bcd409da3890
/factpaper Reflection: Black Ghettoization and Marginalization – The Recent U.S. Experience
```
```
User: Write me a research paper about AI in healthcare
```

## How It Works

1. **User Query** → Intent Router (Gemini AI) decides: search papers or answer directly
2. **If Searching**:
   - Query ChromaDB vector database
   - Check result quality/quantity
   - If insufficient: Auto-fetch from Semantic Scholar → Index in ChromaDB
   - Summarize findings with Gemini AI
3. **If Direct Answer**: Gemini AI answers using general knowledge

## Notes

- The ChromaDB database persists locally in `./chroma_db/`
- Papers are indexed with embeddings for semantic search
- Distance threshold of 0.8 filters low-quality matches
- Automatic indexing triggers when less than `top_k/2` papers found or distance > 0.8


