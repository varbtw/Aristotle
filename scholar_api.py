"""
Semantic Scholar API integration: search, get paper, get references.
Includes simple retry/backoff and in-memory caches to reduce 429s.
"""

import requests
import re
import json
import gzip
import os
from dotenv import load_dotenv
import time

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
if not api_key:
    print("[WARNING] SEMANTIC_SCHOLAR_API_KEY not found in environment variables. Some functionality may be limited.")
    print("Please set SEMANTIC_SCHOLAR_API_KEY in a .env file.")

result_limit = 10


def find_basis_paper(topic, result_limit="10"):
    """
    Search for papers on a given topic using Semantic Scholar API.
    
    Args:
        topic: Search topic/query string
        result_limit: Maximum number of papers to return (default: "10")
        
    Returns:
        List of paper dictionaries with metadata
    """
    if not topic:
        raise ValueError("Please provide a topic to search for.")

    if not api_key:
        raise ValueError("Semantic Scholar API key not configured. Please set SEMANTIC_SCHOLAR_API_KEY in your .env file.")

    try:
        headers = {"X-API-KEY": api_key} if api_key else {}
        fields = (
            "title,url,abstract,authors,year,publicationVenue,paperId,externalIds,"
            "referenceCount,citationCount"
        )
        rsp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            headers=headers,
            params={"query": topic, "limit": result_limit, "fields": fields},
            timeout=30
        )
        rsp.raise_for_status()

        results = rsp.json()
        total = results.get("total", 0)
        if total == 0:
            print(f"No papers found for topic: {topic}")
            return []

        return results.get("data", [])
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to fetch papers from Semantic Scholar: {e}")
        return []


# In-memory caches to reduce API calls and handle rate limiting
_paper_cache: dict[str, dict] = {}  # Cache for fetched papers
_refs_cache: dict[str, list] = {}   # Cache for paper references


def _request_with_backoff(url: str, headers: dict, params: dict, max_retries: int = 3):
    """
    Make HTTP request with exponential backoff retry logic.
    Handles rate limiting (429) and server errors (5xx).
    
    Args:
        url: Request URL
        headers: HTTP headers
        params: Query parameters
        max_retries: Maximum number of retry attempts
        
    Returns:
        Response object or None if all retries fail
    """
    delay = 0.5
    for attempt in range(max_retries):
        try:
            rsp = requests.get(url, headers=headers, params=params, timeout=30)
            if rsp.status_code == 429:
                # Too many requests – back off and retry with exponential backoff
                time.sleep(delay)
                delay = min(delay * 2, 4.0)
                continue
            rsp.raise_for_status()
            return rsp
        except requests.exceptions.HTTPError as e:
            # Retry on 5xx server errors as well
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            if status is not None and 500 <= status < 600 and attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 4.0)
                continue
            raise
    return None


def get_paper(paper_id: str):
    """
    Fetch a single paper with references and basic metadata from Semantic Scholar.
    Uses in-memory cache to avoid duplicate API calls.
    
    Args:
        paper_id: Semantic Scholar paper ID
        
    Returns:
        Paper data dictionary or None if fetch fails
    """
    if not api_key:
        raise ValueError("Semantic Scholar API key not configured. Please set SEMANTIC_SCHOLAR_API_KEY in your .env file.")
    # Check in-memory cache first
    if paper_id in _paper_cache:
        return _paper_cache[paper_id]
    try:
        headers = {"X-API-KEY": api_key}
        fields = (
            "title,url,abstract,authors,year,publicationVenue,paperId,externalIds,"
            "referenceCount,citationCount,references.paperId,references.title,references.url,"
            "references.year"
        )
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
        rsp = _request_with_backoff(url, headers, {"fields": fields})
        if rsp is None:
            return None
        data = rsp.json()
        _paper_cache[paper_id] = data
        return data
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to fetch paper {paper_id}: {e}")
        return None


def get_references(paper_id: str, limit: int = 100):
    """
    Get references for a paper from Semantic Scholar.
    Uses cached data if available to reduce API calls.
    
    Args:
        paper_id: Semantic Scholar paper ID
        limit: Maximum number of references to return (default: 100)
        
    Returns:
        List of reference dictionaries with paperId, title, url, and year
    """
    # Check cache first
    if paper_id in _refs_cache:
        return _refs_cache[paper_id][: max(1, int(limit))]
    data = get_paper(paper_id)
    if not data:
        return []
    refs = data.get("references") or []
    out = []
    for r in refs[: max(1, int(limit))]:
        if not isinstance(r, dict):
            continue
        pid = (r.get("paperId") or "").strip()
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        year = r.get("year")
        out.append({"paperId": pid, "title": title, "url": url, "year": year})
    _refs_cache[paper_id] = out
    return out


def print_papers(papers):
    """
    Print papers from find_basis_paper function in a readable format.
    
    Args:
        papers: List of paper dictionaries
    """
    for idx, paper in enumerate(papers):
        print(f"{idx}  {paper['title']} {paper['url']}")


def get_dataset(dataset_name: str = "abstracts",
                api_key: str | None = None,
                release_id: str = "latest",
                timeout: int = 30):
    """
    Fetch metadata for a Semantic Scholar dataset from a given release
    (default: 'latest'). Requires an API key with Datasets access.

    Args:
        dataset_name: e.g. 'abstracts', 'papers', 'authors', 'citations', etc.
        api_key:      pass explicitly or set env var S2_API_KEY
        release_id:   'latest' or a specific date like '2023-03-28'
        timeout:      request timeout in seconds

    Returns:
        dict with { name, description, README, files: [S3 URLs...] } or None on error.
    """
    api_key = api_key or os.getenv("S2_API_KEY")
    url = f"https://api.semanticscholar.org/datasets/v1/release/{release_id}/dataset/{dataset_name}"
    headers = {"x-api-key": api_key} if api_key else {}

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        # brief summary
        files = data.get("files", []) or []
        print(f"✅ Dataset: {data.get('name','?')}  |  Files: {len(files)}  |  Release: {release_id}")
        for f in files[:3]:
            print("   🔗", f)
        return data

    except requests.HTTPError:
        status = resp.status_code
        if status == 401:
            print("❌ 401 Unauthorized: missing/invalid API key or key lacks Datasets access.")
            print("   - Set env var S2_API_KEY or pass api_key=... to get_dataset()")
        elif status == 404:
            print(f"❌ 404 Not Found: check dataset_name='{dataset_name}' and release_id='{release_id}'.")
        else:
            preview = resp.text[:200].replace("\n", " ")
            print(f"❌ HTTP {status}: {preview}")
        return None
    except requests.RequestException as e:
        print(f"❌ Request error: {e}")

def preview_dataset_file(url: str, n: int = 100):
    """
    Stream and preview the first n records from a .jsonl.gz dataset file.
    """
    print(f"🔗 Streaming preview from: {url}")
    resp = requests.get(url, stream=True)
    resp.raise_for_status()

    count = 0
    with gzip.open(resp.raw, "rt", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            print(f"\n{count+1}. {record.get('title')}")
            print(record.get('abstract', '')[:250], "...")
            count += 1
            if count >= n:
                break

    print(f"\n✅ Previewed {count} papers.")
