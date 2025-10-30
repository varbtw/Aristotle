"""
Terminal-first research assistant with search, summarization, fact-checking,
abstract auditing and backfilling. Loads GEMINI_API_KEY from .env.
"""

import os
from google import genai
import json
import re
from dotenv import load_dotenv
# ---- local modules ----
import my_chroma
import scholar_api as sch

# Load environment variables
load_dotenv()

# Get API key from environment variable
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please set it in a .env file.")

client = genai.Client(api_key=api_key)


SYSTEM_V1 = """
Role: AI research assistant that finds, organizes, and summarizes scholarly papers.
Style: concise, structured; numbered steps for workflows; bullets for lists.
Constraints:
- If the user asks for paper recommendations, literature related to a topic, or “find papers,” route to query_papers.
- If the user asks general conceptual questions (methods, math, background), answer directly with clear, sourced guidance.
- Prefer actionable outputs: short summaries with key findings and why they matter.
- If the user asks for a paper, you can write reasearch papers as well. Just write them a reaearch paper.
- Output plain text unless asked otherwise.
- NEVER GIVE THE SEMANTIC SCHOLAR LINK YOU MUST GIVE THE PAPER URL.
- If the question is more casual, no need to talk about each paper, just awnser the question using the papers as a source.
- If the question is asking to find papers, then you can summarize each paper and provide an overall insight.
"""

CALL_SPEC = """
You may either answer as text OR request a function call by returning ONLY this JSON:
{"call":{"name":"<one of: query_papers>", "args":{...}}}

If answering as text, return ONLY plain text (no JSON, no code fences).

These are the ONLY ARGUMENTS FOR EACH CALL:

def query_papers(query: str, top_k: int = 5):
    # Fetch ~top_k most relevant papers for the user's query.

"""

ROUTER_FEWSHOT = """
User: find me 5 papers related to video games and how it can effect sleep
{"call":{"name":"query_papers","args":{"query":"video games effect on sleep","top_k":5}}}

User: What’s a quick way to explain the difference between RCTs and observational studies?
Give a concise explanation with 3 bullets and a one-sentence caveat.

User: What is prime Fortnite?
Prime Fortnite refers to the early era of Fortnite Battle Royale, often remembered for its original map, simpler weapons, and nostalgic events.

User: How does climate change affect coral reefs?
Explain briefly without calling any function.
"""


# class response(BaseModel):
#     call:str
    

#this is the intent router which takes in the users raw question and figures out what functions to call and what to do with it
def intent_router(user_text: str):
    prompt = (
        CALL_SPEC
        + "\n\nYou are the intent router. "
          "Given the user message, decide whether to call a function or answer directly. "
          "If a function should be called, respond ONLY with valid JSON.\n\n"
        + ROUTER_FEWSHOT
        + "\n\nUser: " + user_text
    )

    try:
        # Log model input
        print("\n=== MODEL INPUT (intent_router) ===\n")
        print(prompt)
        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config={
                "system_instruction": SYSTEM_V1,
                "temperature": 0.2,
                "response_mime_type": "application/json",
            }
        )
        try:
            parsed = json.loads(resp.text)
            if isinstance(parsed, dict):
                return parsed
            else:
                return {"text": str(parsed)}
        except json.JSONDecodeError:
            # Try to extract JSON from text if it's wrapped
            text = resp.text.strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {"text": text}
            except json.JSONDecodeError:
                return {"text": text}
    except Exception as e:
        return {"error": f"Failed to process intent: {str(e)}", "text": user_text}

#this function queries chroma for papers related to the users query
def query_papers_chroma(query: str, top_k: int = 5):
    try:
        results = my_chroma.get_query_texts(query, top_k)
        if not results or 'ids' not in results or not results['ids'] or not results['ids'][0]:
            return {'ids': [[]], 'distances': [[]], 'metadatas': [[]], 'documents': [[]]}
        return results
    except Exception as e:
        print(f"[ERROR] Failed to query ChromaDB: {e}")
        return {'ids': [[]], 'distances': [[]], 'metadatas': [[]], 'documents': [[]]}


#this is the function that calls the query papers function and then summarizes the results for the user
def call_query_papers(call_args, user_text):
    try:
        # Validate call_args
        query = call_args.get('query', user_text)
        top_k = max(1, int(call_args.get('top_k', 5)))  # Ensure at least 1
        
        # grabs papers from chroma
        papers = query_papers_chroma(query, top_k)
        
        # Safely count papers found
        n_papers = len(papers.get('ids', [[]])[0]) if papers.get('ids') and papers['ids'] else 0
        
        # Check if we need to index more papers
        needs_more = False
        if n_papers < (top_k / 2):
            needs_more = True
        elif papers.get('distances') and papers['distances'] and len(papers['distances'][0]) > 0:
            if papers['distances'][0][0] > 0.8:
                needs_more = True

        if needs_more:
            try:
                my_chroma.papers_to_chroma([query])
                papers = query_papers_chroma(query, top_k)
                n_papers = len(papers.get('ids', [[]])[0]) if papers.get('ids') and papers['ids'] else 0
            except Exception as e:
                print(f"[WARNING] Failed to index new papers: {e}")
                # Continue with existing papers

        # Prepare papers for summarization
        papers_json = json.dumps(papers, default=str)  # default=str handles non-serializable types
        
    # prompts the model to summarize the papers found
        prompt = (
            "You are given a set of papers where each item includes title, abstract, and URL.\n"
            "Prioritize the abstract as the primary evidence; use title/URL only to resolve ambiguity.\n"
            + papers_json +
            "\n\nUser Question: " + user_text +
            "\n\nProvide a concise summary of the key findings from these papers in relation to the user's question."
        )
        
        try:
            resp = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_V1,
                    "temperature": 0.2,
                }
            )
            return resp.text if resp.text else "No response generated."
        except Exception as e:
            return f"Failed to generate summary: {str(e)}"
    except Exception as e:
        return f"Error in call_query_papers: {str(e)}"


def _parse_command(text: str):
    if not text or not text.strip():
        return ("default", text)
    if not text.startswith("/"):
        return ("default", text)
    parts = text.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]
    return (cmd, args)


def _cmd_search(args: list[str]):
    if not args:
        return "Usage: /search <query> [k]"
    query = " ".join(a for a in args if not a.isdigit())
    k_vals = [int(a) for a in args if a.isdigit()]
    top_k = k_vals[0] if k_vals else 5
    res = my_chroma.get_query_texts(query, n_results=top_k)
    n = len(res.get('ids', [[]])[0]) if res.get('ids') and res['ids'] else 0
    if n < max(1, top_k // 2):
        my_chroma.papers_to_chroma([query])
        res = my_chroma.get_query_texts(query, n_results=top_k)
        n = len(res.get('ids', [[]])[0]) if res.get('ids') and res['ids'] else 0
    lines = []
    metas = res.get('metadatas', [[]])[0] if res.get('metadatas') else []
    for i, m in enumerate(metas, 1):
        title = m.get('title') or '(untitled)'
        url = m.get('url') or ''
        year = m.get('year')
        if year:
            lines.append(f"{i}. {title} ({year})\n   {url}")
        else:
            lines.append(f"{i}. {title}\n   {url}")
    if not lines:
        return "No results. Try a more specific query."
    return "\n".join(lines)


def _cmd_sum(args: list[str]):
    if not args:
        return "Usage: /sum <query or paperId> [k]"
    # If first arg looks like a paperId (no spaces), fetch that, else treat as query
    if len(args) == 1 and " " not in args[0]:
        pid = args[0]
        my_chroma.ensure_indexed([pid])
        got = my_chroma.get_by_ids([pid])
        docs = got.get('documents') or [[]]
        papers_json = json.dumps(got, default=str)
        prompt = (
            "You are given a paper where the document contains title, abstract, and URL.\n"
            "Use the abstract as the main source for your summary.\n" +
            papers_json +
            "\n\nSummarize the key findings of the above paper in 5-7 bullets."
        )
    else:
        query = " ".join(a for a in args if not a.isdigit())
        k_vals = [int(a) for a in args if a.isdigit()]
        top_k = k_vals[0] if k_vals else 5
        res = my_chroma.get_query_texts(query, n_results=top_k)
        papers_json = json.dumps(res, default=str)
        prompt = (
            "You are given a set of papers where each item includes title, abstract, and URL.\n"
            "Prioritize the abstract as the primary evidence; use title/URL only to resolve ambiguity.\n" +
            papers_json +
            f"\n\nUser query: {query}\nSummarize the key insights across these papers in concise bullets."
        )
    r = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt,
        config={"system_instruction": SYSTEM_V1, "temperature": 0.2}
    )
    return (r.text or "").strip() or "No summary generated."


def _cmd_audit(args: list[str]):
    """
    /audit                -> show totals and sample of missing abstracts
    /audit <paperId>      -> show stored record (metadata + document) for that id
    /audit <N>            -> totals with a sample size of N
    """
    if args:
        a0 = args[0]
        # If numeric, treat as sample size for totals
        if a0.isdigit():
            try:
                sample = int(a0)
            except Exception:
                sample = 20
            report = my_chroma.audit_abstracts(sample_missing=sample)
            return (
                f"Total: {report.get('total', 0)}\n"
                f"With abstracts: {report.get('with_abstract', 0)}\n"
                f"Without abstracts: {report.get('without_abstract', 0)}\n"
                f"Sample missing IDs: {', '.join(report.get('missing_ids', []))}"
            )
        # Otherwise, assume a paperId
        pid = a0.strip()
        got = my_chroma.get_by_ids([pid])
        ids = got.get('ids') or []
        if not ids:
            return f"PaperId not found in Chroma: {pid}"
        # Format a concise view
        metas_list = got.get('metadatas') or []
        docs_list = got.get('documents') or []
        m = metas_list[0] if len(metas_list) > 0 else {}
        d = docs_list[0] if len(docs_list) > 0 else ""
        lines = [
            f"paperId: {pid}",
            f"title: {m.get('title','')}",
            f"year: {m.get('year','')}",
            f"url: {m.get('url','')}",
            f"has_abstract_in_meta: {bool((m.get('abstract') or '').strip())}",
            f"document_snippet: {(d[:240] + '…') if isinstance(d, str) and len(d) > 240 else (d or '')}",
        ]
        return "\n".join(lines)
    # No args: totals with default sample size
    report = my_chroma.audit_abstracts(sample_missing=20)
    return (
        f"Total: {report.get('total', 0)}\n"
        f"With abstracts: {report.get('with_abstract', 0)}\n"
        f"Without abstracts: {report.get('without_abstract', 0)}\n"
        f"Sample missing IDs: {', '.join(report.get('missing_ids', []))}"
    )


def _collect_evidence_from_references(primary_ids: list[str], max_refs: int = 100):
    seen = set()
    evidence_ids = []
    # Apply conservative caps to avoid API rate limiting
    hop1_cap = max(5, min(20, max_refs))
    hop2_cap_total = max(5, min(20, max_refs // 2))
    hop2_per_seed = max(3, min(10, hop2_cap_total))

    # 1-hop: references of primary papers (capped)
    for pid in primary_ids[:5]:
        refs = sch.get_references(pid, limit=hop1_cap) or []
        for r in refs[:hop1_cap]:
            rid = (r.get('paperId') or '').strip()
            if rid and rid not in seen:
                seen.add(rid)
                evidence_ids.append(rid)
    # 2nd hop: references of references (capped)
    added2 = 0
    for rid in list(evidence_ids)[:hop1_cap]:
        if added2 >= hop2_cap_total:
            break
        refs2 = sch.get_references(rid, limit=hop2_per_seed) or []
        for r2 in refs2[:hop2_per_seed]:
            if added2 >= hop2_cap_total:
                break
            rid2 = (r2.get('paperId') or '').strip()
            if rid2 and rid2 not in seen:
                seen.add(rid2)
                evidence_ids.append(rid2)
                added2 += 1
    # Ensure indexed in Chroma
    my_chroma.ensure_indexed(evidence_ids)
    return evidence_ids


def _rank_evidence(claim: str, evidence_ids: list[str], k: int = 10):
    # Use Chroma semantic search against claim
    # We rely on documents already stored; query by text to rank
    res = my_chroma.get_query_texts(claim, n_results=k)
    return res


def _format_factcheck_verdict(claim: str, evidence_json: dict):
    prompt = (
        "You are a rigorous research fact-checker.\n"
        "Given the user's claim and a set of candidate papers (with titles/abstracts/urls),\n"
        "use ABSTRACTS as the primary evidence. Do NOT paste the input JSON back.\n"
        "Only cite papers that include a non-empty Title and a valid URL from the provided data.\n"
        "Output EXACTLY this format:\n"
        "Verdict: <Supported | Contradicted | Insufficient>\n"
        "Confidence: <0-100>%\n"
        "Rationale: <2-3 concise sentences using abstract evidence>\n"
        "Citations:\n"
        "1) <Title> (<Year>) — <URL>\n"
        "2) <Title> (<Year>) — <URL>\n"
        "3) <Title> (<Year>) — <URL>\n\n"
        f"Claim: {claim}\n"
        f"Papers JSON: {json.dumps(evidence_json, ensure_ascii=False)}\n"
    )
    r = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt,
        config={"system_instruction": SYSTEM_V1, "temperature": 0.1}
    )
    return (r.text or "").strip() or "No verdict generated."


def _cmd_fact(args: list[str]):
    if not args:
        return "Usage: /fact <claim> [context=<query or paperId>]"
    # Parse optional context
    text = " ".join(args)
    context = None
    if "context=" in text:
        parts = text.split("context=", 1)
        claim = parts[0].strip()
        context = parts[1].strip()
    else:
        claim = text.strip()

    primary_ids = []
    if context:
        if " " not in context:  # likely a paperId
            primary_ids = [context]
            my_chroma.ensure_indexed(primary_ids)
        else:
            res = my_chroma.get_query_texts(context, n_results=5)
            primary_ids = [pid for pid in (res.get('ids') or [[]])[0]]
    else:
        # If no context, search by the claim text to find seed papers
        res = my_chroma.get_query_texts(claim, n_results=5)
        primary_ids = [pid for pid in (res.get('ids') or [[]])[0]]

    primary_ids = [pid for pid in primary_ids if pid]
    if not primary_ids:
        return "No seed papers found to fact-check this claim. Try adding context=."

    evidence_ids = _collect_evidence_from_references(primary_ids)
    ranked = _rank_evidence(claim, evidence_ids, k=10)
    return _format_factcheck_verdict(claim, ranked)


def _resolve_paper_id(identifier_or_title: str) -> str | None:
    """
    Resolve a paperId from either a direct id (no spaces) or a title query.
    Returns the first matching id or None if not found.
    """
    s = (identifier_or_title or "").strip()
    if not s:
        return None
    if " " not in s:
        return s  # assume it's already a paperId
    res = my_chroma.get_query_texts(s, n_results=1)
    ids = (res.get('ids') or [[]])[0]
    return ids[0] if ids else None


def _extract_claims_from_paper(paper_json: dict, max_claims: int = 3) -> list[str]:
    """
    Use the paper's title/abstract (from metadata/document) to extract concise claims.
    Returns a list of short claim strings.
    """
    prompt = (
        "You are given a single paper entry with title and abstract.\n"
        "Extract up to " + str(max_claims) + " core factual claims stated in the abstract.\n"
        "Return a plain list with one short claim per line (no numbering).\n\n"
        + json.dumps(paper_json, ensure_ascii=False)
    )
    r = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt,
        config={"system_instruction": SYSTEM_V1, "temperature": 0.2}
    )
    text = (r.text or "").strip()
    lines = [ln.strip(" -\t") for ln in text.splitlines() if ln.strip()]
    return lines[:max_claims]


def _extract_intent_from_paper(paper_json: dict) -> str:
    """
    Return a one-sentence statement of the paper's main intent based on title/abstract.
    """
    prompt = (
        "You are given a single paper entry with title and abstract.\n"
        "Write ONE sentence describing the paper's main intent/purpose in plain English.\n"
        "Return only the sentence.\n\n"
        + json.dumps(paper_json, ensure_ascii=False)
    )
    r = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt,
        config={"system_instruction": SYSTEM_V1, "temperature": 0.2}
    )
    return (r.text or "").strip()


def _cmd_factpaper(args: list[str]):
    """
    /factpaper <paperId or title>  -> extract a few claims and fact-check each
    """
    if not args:
        return "Usage: /factpaper <paperId or title>"
    target = " ".join(args).strip()
    pid = _resolve_paper_id(target)
    if not pid:
        return "Paper not found in Chroma. Try a more specific title."
    got = my_chroma.get_by_ids([pid])
    if not (got.get('ids') or []):
        return "Paper not found in Chroma."
    # Build a minimal paper JSON shape for claim extraction
    paper_json = {
        "ids": got.get('ids'),
        "metadatas": got.get('metadatas'),
        "documents": got.get('documents')
    }
    claims = _extract_claims_from_paper(paper_json, max_claims=3)
    intent = _extract_intent_from_paper(paper_json)
    if not claims:
        return "No extractable claims from the paper's abstract."
    # Build evidence universe from this paper's references (two-hop capped)
    evidence_ids = _collect_evidence_from_references([pid])
    outputs = []
    # Header with paper info and intent
    m0 = (got.get('metadatas') or [{}])[0] if got.get('metadatas') else {}
    title = m0.get('title') or '(untitled)'
    year = m0.get('year')
    url = m0.get('url') or ''
    header = []
    header.append(f"Paper: {title}{' (' + str(year) + ')' if year else ''}")
    if url:
        header.append(f"Link: {url}")
    if intent:
        header.append(f"Intent: {intent}")
    if claims:
        header.append("Claims:")
        for i, c in enumerate(claims, 1):
            header.append(f"{i}. {c}")
    outputs.append("\n".join(header))

    for c in claims:
        ranked = _rank_evidence(c, evidence_ids, k=10)
        verdict = _format_factcheck_verdict(c, ranked)
        outputs.append(verdict)
    return "\n\n".join(outputs)

def agent(user_text: str):
    """
    Main agent function that processes user queries.
    
    Args:
        user_text: The user's query string
        
    Returns:
        str: Response text from the agent
    """
    try:
        intent = intent_router(user_text)
        
        # Handle error responses
        if isinstance(intent, dict) and 'error' in intent:
            return intent.get('text', 'An error occurred processing your query.')
        
        # Handle direct text responses
        if isinstance(intent, dict) and 'text' in intent and 'call' not in intent:
            return intent['text']
        
        # Handle function calls
        if isinstance(intent, dict) and 'call' in intent:
            call_name = intent['call'].get('name')
            call_args = intent['call'].get('args', {})
            
            if call_name == 'query_papers':
                return call_query_papers(call_args, user_text)
            else:
                return f"Unknown function call: {call_name}"
        
        # Fallback for unexpected response format
        return str(intent)
    except Exception as e:
        return f"Error in agent: {str(e)}"


# Only run if this file is executed directly, not when imported
if __name__ == "__main__":
    print("Research Agent CLI. Type 'exit' or 'quit' to end.\n")
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue
        cmd, args = _parse_command(user_input)
        if cmd == "/search":
            print(_cmd_search(args))
            continue
        if cmd == "/sum":
            print(_cmd_sum(args))
            continue
        if cmd == "/fact":
            print(_cmd_fact(args))
            continue
        if cmd == "/factpaper":
            print(_cmd_factpaper(args))
            continue
        if cmd == "/audit":
            print(_cmd_audit(args))
            continue
        if cmd == "/rehydrate":
            # Usage: /rehydrate [N] | /rehydrate <paperId> | /rehydrate query=<text>
            if not args:
                summary = my_chroma.rehydrate_missing_abstracts(max_ids=200)
                print(f"Backfill: requested={summary['requested']} fetched={summary['fetched']} updated={summary['updated']}")
                continue
            a0 = args[0]
            if a0.isdigit():
                n = int(a0)
                summary = my_chroma.rehydrate_missing_abstracts(max_ids=n)
                print(f"Backfill: requested={summary['requested']} fetched={summary['fetched']} updated={summary['updated']}")
                continue
            if a0.startswith("query="):
                q = a0.split("=", 1)[1]
                res = my_chroma.get_query_texts(q, n_results=50)
                ids = [pid for pid in (res.get('ids') or [[]])[0] if pid]
                summary = my_chroma.rehydrate_papers_by_ids(ids)
                print(f"Backfill: requested={summary['requested']} fetched={summary['fetched']} updated={summary['updated']}")
                continue
            # treat as paperId list
            ids = [a.strip() for a in args if a.strip()]
            summary = my_chroma.rehydrate_papers_by_ids(ids)
            print(f"Backfill: requested={summary['requested']} fetched={summary['fetched']} updated={summary['updated']}")
            continue
        # default agent behavior
        response = agent(user_input)
        print(response)