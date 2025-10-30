"""
Legacy prototype for Gemini routing and paper querying. Kept for reference.
The active implementation lives in my_agent.py.
"""

# api_key = "..."
# import os
# from google import genai
# import json, re

# # ---- your modules ----
# import my_chroma

# client = genai.Client(api_key=api_key)

# # ==========================
# # SYSTEM & CALL SPEC (RESEARCH ASSISTANT)
# # ==========================
# SYSTEM_V1 = """
# Role: AI research assistant that finds, organizes, and summarizes scholarly papers.
# Style: concise, structured; numbered steps for workflows; bullets for lists.
# Constraints:
# - If the user asks for paper recommendations, literature related to a topic, or “find papers,” route to query_papers.
# - If the user asks general conceptual questions (methods, math, background), answer directly with clear, sourced guidance.
# - Prefer actionable outputs: short summaries with key findings and why they matter.
# - Output plain text unless asked otherwise.
# - Do not give the semantic scholar url, give the paper url only.
# """

# CALL_SPEC = """
# You may either answer as text OR request a function call by returning ONLY this JSON:
# {"call":{"name":"<one of: query_papers>", "args":{...}}}

# If answering as text, return ONLY plain text (no JSON, no code fences).

# These are the ONLY ARGUMENTS FOR EACH CALL:

# def query_papers(query: str, top_k: int = 5):
#     # Fetch ~top_k most relevant papers for the user's query.
# """

# ROUTER_FEWSHOT = """
# User: find me 5 papers related to video games and how it can effect sleep
# {"call":{"name":"query_papers","args":{"query":"video games effect on sleep","top_k":5}}}

# User: What’s a quick way to explain the difference between RCTs and observational studies?
# Give a concise explanation with 3 bullets and a one-sentence caveat.
# """

# INTENT_CALL_SPEC_V2 = """
# You must return ONLY one line of JSON following this schema:

# {
#   "topic": "<short, clean topic phrase>",
#   "mode": "<one of: call | text>",
#   "n_results": <integer or null>,
#   "call": {
#     "name": "<one of: query_papers>",
#     "args": {
#       "query": "<query string>",
#       "top_k": <integer>
#     }
#   }
# }

# Rules:
# - Always fill "topic" with a concise phrase for the user's request (even for text mode).
# - If the user is asking for papers / literature search, set:
#     "mode": "call",
#     "call.name": "query_papers",
#     "call.args.query": a concise search string derived from the user's ask,
#     "call.args.top_k": an integer (default 5 if unspecified by user),
#     "n_results": same integer as top_k.
# - If the user is asking a conceptual/background question (not a paper search), set:
#     "mode": "text",
#     "call": null,
#     "n_results": null.
# - Return ONLY the JSON object. No prose, no code fences.

# Examples:

# User: find me 5 papers related to video games and how it can effect sleep
# {"topic":"video games and sleep","mode":"call","n_results":5,"call":{"name":"query_papers","args":{"query":"video games effect on sleep","top_k":5}}}

# User: What’s a quick way to explain the difference between RCTs and observational studies?
# {"topic":"RCTs vs observational studies","mode":"text","n_results":null,"call":null}
# """

# def build_router_prompt(user_text: str, query_texts: list[str]) -> str:
#     """
#     Build the router prompt, injecting my_chroma.get_query_texts() output
#     so the model can use those as hints for routing or answering.
#     """
#     qt_block = "\n".join(f"- {q}" for q in (query_texts or [])) or "- (none)"
#     return (
#         f"{CALL_SPEC}\n"
#         f"{ROUTER_FEWSHOT}\n"
#         f"Related search queries (from my_chroma.get_query_texts):\n{qt_block}\n\n"
#         f"User: {user_text}\n"
#     )

# # ==========================
# # CALL PARSER
# # ==========================
# def try_parse_call(text: str):
#     """If the model returns JSON like {"call":{...}}, parse it."""
#     text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())  # remove ```json fences
#     if "call" not in text or not text.strip().startswith("{"):
#         return None
#     try:
#         data = json.loads(text)
#         call = data.get("call")
#         if isinstance(call, dict) and "name" in call:
#             call.setdefault("args", {})
#             return call
#     except Exception:
#         pass
#     return None

# # ==========================
# # TOOL IMPLEMENTATIONS
# # ==========================
# def query_papers(query: str, top_k: int = 5):
#     """
#     Uses my_chroma.get_query_texts(topic) to expand the user's topic into
#     concrete search queries, runs those queries, deduplicates results,
#     and returns up to top_k normalized papers.

#     Returns:
#     {
#       "papers": [ {paperId,title,abstract,year,venue,url,authors}, ... ],
#       "used_queries": [ ... ],          # the queries returned by get_query_texts
#       "topic": "<original user topic>"
#     }
#     """
#     # 1) Expand the topic into concrete queries (this is REQUIRED by your design).
#     try:
#         qts = my_chroma.get_query_texts(query,n_results=top_k) 
#     except Exception as e:
#         qts = None

#     # Ensure we have a list of queries; fallback to the raw topic if needed.
#     if qts is None:
#         queries = [query]
#     elif isinstance(qts, (list, tuple)):
#         queries = [str(q).strip() for q in qts if q and str(q).strip()]
#         if not queries:
#             queries = [query]
#     else:
#         # single string
#         s = str(qts).strip()
#         queries = [s] if s else [query]

#     # 2) Execute searches for each query; stop when we have >= top_k unique papers.
#     raw_results = []
#     for q in queries:
#         try:
#             if hasattr(my_chroma, "query_papers"):
#                 # Preferred: your higher-level helper
#                 res = my_chroma.query_papers(q, top_k=top_k) or []
#             elif hasattr(my_chroma, "query"):
#                 # Fallback: a lower-level query(k=...)
#                 res = my_chroma.query(q, k=top_k) or []
#             else:
#                 res = []
#         except Exception:
#             res = []
#         if isinstance(res, dict) and "results" in res:
#             # handle cases where helper returns {"results":[...]}
#             res = res.get("results") or []
#         if isinstance(res, list):
#             raw_results.extend(res)
#         if len(raw_results) >= top_k * 2:  # small cap to avoid over-accumulating
#             break

#     # 3) Deduplicate (prefer paperId; else title+url fingerprint)
#     seen = set()
#     deduped = []
#     def _key(p):
#         pid = (p.get("paperId") or p.get("paper_id") or "").strip()
#         if pid:
#             return ("id", pid)
#         title = (p.get("title") or "").strip().lower()
#         url = (p.get("url") or ((p.get("openAccessPdf") or {}).get("url") or "")).strip().lower()
#         return ("tu", title, url)

#     for p in raw_results:
#         k = _key(p)
#         if k in seen:
#             continue
#         seen.add(k)
#         deduped.append(p)
#         if len(deduped) >= top_k:
#             break

#     # 4) Normalize schema for the formatter pass
#     normed = []
#     for p in deduped:
#         normed.append({
#             "paperId":  (str(p.get("paperId") or p.get("paper_id") or "").strip() or None),
#             "title":    ((p.get("title") or "").strip() or "(untitled)"),
#             "abstract": (p.get("abstract") or p.get("summary") or None),
#             "year":     p.get("year") if isinstance(p.get("year"), int) else None,
#             "venue":    (p.get("venue") or p.get("publicationVenue") or None),
#             "url":      ((p.get("openAccessPdf", {}) or {}).get("url") or p.get("url") or None),
#             "authors":  p.get("authors") or []
#         })

#     return {
#         "papers": normed[: max(1, int(top_k))],
#         "used_queries": queries,
#         "topic": query
#     }


# TOOL_REGISTRY = {
#     "query_papers": query_papers
# }

# # ==========================
# # RESPONDER
# # ==========================
# def respond(user_text: str) -> str:
#     # Step 0: Extract helpful query texts via my_chroma (for routing context)
#     try:
#         qts = my_chroma.get_query_texts(user_text)
#         if qts is None:
#             query_texts = []
#         elif isinstance(qts, (list, tuple)):
#             query_texts = [str(q) for q in qts if q is not None]
#         else:
#             query_texts = [str(qts)]
#     except Exception:
#         query_texts = []

#     # Step 1: Ask model to decide: answer or call query_papers
#     prompt = build_router_prompt(user_text, query_texts)
#     r = client.models.generate_content(
#         model="gemini-2.5-flash",
#         contents=prompt,
#         config={
#             "system_instruction": SYSTEM_V1,
#             "temperature": 0.2
#         }
#     )
#     reply = (r.text or "").strip()

#     # Step 2: Try to detect if it's a function call
#     call = try_parse_call(reply)
#     if not call:
#         # normal text answer
#         return reply

#     # Step 3: Execute tool
#     name, args = call["name"], call["args"]
#     tool = TOOL_REGISTRY.get(name)
#     if not tool:
#         return f"Sorry, I can’t perform '{name}' yet."

#     # Sensible defaults
#     if name == "query_papers":
#         if "query" not in args or not str(args["query"]).strip():
#             args["query"] = user_text
#         args["top_k"] = int(args.get("top_k") or 5)

#     result = tool(**args)

#     # Step 4: Ask model to format results into neat literature notes
#     followup_prompt = (
#         "You are formatting a short literature list for a researcher.\n"
#         "Return plain text only. For each paper, include:\n"
#         "1) Title (Year) — Venue (if any)\n"
#         "2) 2–3 sentence abstract gist (no fluff)\n"
#         "3) Main point / key finding (1 line)\n"
#         "4) Why this is relevant to the user’s query (1–2 bullets)\n"
#         "5) Link\n\n"
#         f"User query: {args.get('query')}\n"
#         f"Papers JSON: {json.dumps(result, ensure_ascii=False)}\n"
#         "If there are zero papers, say so and suggest 2 alternative queries."
#     )
#     r2 = client.models.generate_content(
#         model="gemini-2.5-flash",
#         contents=followup_prompt,
#         config={"system_instruction": SYSTEM_V1, "temperature": 0.3}
#     )
#     return (r2.text or "").strip()


# if __name__ == "__main__":
#     while True:
#         q = input("You: ")
#         if q.lower() in {"quit", "exit"}:
#             break
#         print("Bot:", respond(q))
#         print()
