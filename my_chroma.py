"""
ChromaDB wrapper: persistent collection, indexing helpers, queries, and
maintenance utilities (auditing, rehydrating abstracts).
"""

import chromadb
from chromadb.config import Settings
import scholar_api as sch
from itertools import islice
import numpy as np
import json

# Persistent client
try:
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="scholarCollection_local")
    print("Connected to Collection : ", collection.name)
except Exception as e:
    print(f"[ERROR] Failed to initialize ChromaDB: {e}")
    raise

def _batched(iterable, n=100):
    it = iter(iterable)
    while True:
        batch = list(islice(it, n))
        if not batch:
            return
        yield batch


def _normalize_paper_to_doc_meta(p: dict, topic: str | None = None):
    title = (p.get("title") or "").strip()
    url = (p.get("url") or "").strip()
    abstract = (p.get("abstract") or "").strip()
    year = p.get("year")
    venue_field = p.get("publicationVenue") or p.get("venue") or ""
    if isinstance(venue_field, dict):
        venue = (venue_field.get("name") or venue_field.get("displayName") or "").strip()
    else:
        venue = str(venue_field or "").strip()
    ref_count = p.get("referenceCount")
    cit_count = p.get("citationCount")

    authors_field = p.get("authors") or []
    author_names = []
    if isinstance(authors_field, list):
        for a in authors_field:
            if isinstance(a, dict) and a.get("name"):
                author_names.append((a["name"] or "").strip())
            elif isinstance(a, str):
                author_names.append(a.strip())
    authors_str = ", ".join(author_names)

    doc_parts = [title]
    if abstract:
        doc_parts.append(abstract)
    if url:
        doc_parts.append(url)
    doc = "\n\n".join(doc_parts) if doc_parts else title

    meta = {
        "paperId": (p.get("paperId") or p.get("paper_id") or "").strip(),
        "title": title,
        "url": url,
        "abstract": abstract,
        "authors": authors_str,
        "year": year,
        "venue": venue,
        "referenceCount": ref_count,
        "citationCount": cit_count,
        "topic": topic or "",
        "source": "Semantic Scholar",
    }
    meta = {k: v for k, v in meta.items() if (v is not None and (not isinstance(v, str) or v))}
    return doc, meta


def upsert_papers(papers: list[dict], topic: str | None = None, batch_size: int = 100):
    writer = collection.upsert if hasattr(collection, "upsert") else collection.add
    for batch in _batched(papers, batch_size):
        ids, documents, metadatas = [], [], []
        for p in batch:
            if not isinstance(p, dict):
                continue
            pid = (p.get("paperId") or p.get("paper_id") or "").strip()
            if not pid:
                continue
            doc, meta = _normalize_paper_to_doc_meta(p, topic)
            ids.append(pid)
            documents.append(doc)
            metadatas.append(meta)
        if ids:
            writer(ids=ids, documents=documents, metadatas=metadatas)


def papers_to_chroma(topics, batch_size=100):
    """
    For each topic in `topics`, call sch.find_basis_paper(topic)
    and insert the resulting Semantic Scholar papers into Chroma.

    Each paper can include: paperId, title, url, abstract, authors.
    """
    if not topics:
        print("[WARNING] No topics provided to papers_to_chroma")
        return
    
    for topic in topics:
        try:
            papers = sch.find_basis_paper(topic, result_limit="100")
            if not papers:
                continue
        except Exception as e:
            print(f"[ERROR] Failed to fetch papers for '{topic}': {e}")
            continue
        upsert_papers(papers, topic=topic, batch_size=batch_size)

def print_chroma_titles(query_result):
    """
    Print all paper titles from a Chroma query() result.
    Expects a dict like the one returned by collection.query().
    """
    if not query_result or "metadatas" not in query_result:
        print("No results found.")
        return

    all_titles = []
    for group in query_result["metadatas"]:  # one group per query_text
        for meta in group:
            title = meta.get("title")
            if title:
                all_titles.append(title)

    if not all_titles:
        print("No titles found in metadata.")
        return

    print(f"Found {len(all_titles)} titles:\n")
    for i, t in enumerate(all_titles, 1):
        print(f"{i}. {t}")

def get_query_texts(query, n_results=5):
    """
    Query ChromaDB for papers related to the given query.
    
    Args:
        query: Search query string
        n_results: Number of results to return (default: 5)
        
    Returns:
        Dictionary with keys: ids, distances, metadatas, documents
    """
    if not query or not query.strip():
        return {'ids': [[]], 'distances': [[]], 'metadatas': [[]], 'documents': [[]]}
    
    try:
        return collection.query(query_texts=[query], n_results=max(1, int(n_results)))
    except Exception as e:
        print(f"[ERROR] Failed to query ChromaDB: {e}")
        return {'ids': [[]], 'distances': [[]], 'metadatas': [[]], 'documents': [[]]}


def get_by_ids(ids: list[str]):
    if not ids:
        return {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}
    try:
        return collection.get(ids=ids, include=["metadatas", "documents"])
    except Exception as e:
        print(f"[ERROR] Failed to get by ids: {e}")
        return {"ids": [[]], "metadatas": [[]], "documents": [[]]}


def ensure_indexed(topics_or_ids):
    """
    No-op placeholder to avoid external indexing. Assumes papers are already in Chroma.
    """
    return


def audit_abstracts(sample_missing: int = 20):
    """
    Scan the collection and report how many items have a non-empty abstract
    in metadata or in the stored document. Returns a dict with counts and
    a small sample list of paperIds missing abstracts.
    """
    try:
        total = collection.count()
        if total == 0:
            return {"total": 0, "with_abstract": 0, "without_abstract": 0, "missing_ids": []}
        data = collection.get(
            ids=None,
            where=None,
            where_document=None,
            limit=total,
            offset=0,
            include=["metadatas", "documents"],
        )
        ids = data.get("ids") or []
        metas_groups = data.get("metadatas") or []
        docs = data.get("documents") or []
        with_abs = 0
        missing_ids = []
        for idx, pid in enumerate(ids):
            meta = metas_groups[idx] if idx < len(metas_groups) else {}
            doc = docs[idx] if idx < len(docs) else ""
            abstract_str = (meta.get("abstract") or "").strip() if isinstance(meta, dict) else ""
            has_in_doc = False
            if isinstance(doc, str):
                # Document is built as: title [+ abstract] [+ url]
                parts = [p.strip() for p in doc.split("\n\n") if p and p.strip()]
                def is_url(s: str) -> bool:
                    return s.startswith("http://") or s.startswith("https://")
                if len(parts) >= 3 and is_url(parts[-1]):
                    # title, abstract, url
                    has_in_doc = True
                elif len(parts) >= 2 and not is_url(parts[1]):
                    # title, abstract (no url)
                    has_in_doc = True
            if abstract_str or has_in_doc:
                with_abs += 1
            else:
                if len(missing_ids) < max(0, int(sample_missing)):
                    missing_ids.append(pid)
        return {
            "total": total,
            "with_abstract": with_abs,
            "without_abstract": max(0, total - with_abs),
            "missing_ids": missing_ids,
        }
    except Exception as e:
        print(f"[ERROR] audit_abstracts failed: {e}")
        return {"total": 0, "with_abstract": 0, "without_abstract": 0, "missing_ids": []}


def find_missing_abstract_ids(max_ids: int = 1000) -> list[str]:
    """
    Return up to max_ids paperIds that are missing abstracts in metadata and
    do not have an abstract segment in the stored document.
    """
    try:
        total = collection.count()
        if total == 0:
            return []
        data = collection.get(
            ids=None,
            where=None,
            where_document=None,
            limit=total,
            offset=0,
            include=["metadatas", "documents"],
        )
        ids = data.get("ids") or []
        metas_groups = data.get("metadatas") or []
        docs = data.get("documents") or []
        out = []
        for idx, pid in enumerate(ids):
            if len(out) >= max(1, int(max_ids)):
                break
            meta = metas_groups[idx] if idx < len(metas_groups) else {}
            doc = docs[idx] if idx < len(docs) else ""
            abstract_str = (meta.get("abstract") or "").strip() if isinstance(meta, dict) else ""
            has_in_doc = False
            if isinstance(doc, str):
                parts = [p.strip() for p in doc.split("\n\n") if p and p.strip()]
                def is_url(s: str) -> bool:
                    return s.startswith("http://") or s.startswith("https://")
                if len(parts) >= 3 and is_url(parts[-1]):
                    has_in_doc = True
                elif len(parts) >= 2 and not is_url(parts[1]):
                    has_in_doc = True
            if not (abstract_str or has_in_doc):
                out.append(pid)
        return out
    except Exception as e:
        print(f"[ERROR] find_missing_abstract_ids failed: {e}")
        return []


def rehydrate_papers_by_ids(paper_ids: list[str]) -> dict:
    """
    Fetch papers by id from Semantic Scholar and upsert any with abstracts
    into Chroma. Returns summary counts.
    """
    import scholar_api as sch  # local import to avoid cycles on module load
    fetched = 0
    updated = 0
    batch: list[dict] = []
    for pid in paper_ids:
        if not pid:
            continue
        p = sch.get_paper(pid)
        if p:
            fetched += 1
            if (p.get("abstract") or "").strip():
                batch.append(p)
        if len(batch) >= 50:
            upsert_papers(batch, topic=None, batch_size=50)
            updated += len(batch)
            batch = []
    if batch:
        upsert_papers(batch, topic=None, batch_size=50)
        updated += len(batch)
    return {"requested": len(paper_ids), "fetched": fetched, "updated": updated}


def rehydrate_missing_abstracts(max_ids: int = 200) -> dict:
    """
    Find up to max_ids papers missing abstracts and attempt to backfill
    abstracts from Semantic Scholar, then upsert into Chroma.
    """
    ids = find_missing_abstract_ids(max_ids=max_ids)
    if not ids:
        return {"requested": 0, "fetched": 0, "updated": 0}
    return rehydrate_papers_by_ids(ids)

# Example topic lists for bulk indexing (comment out when not needed)
# These are kept for reference but not executed automatically
_EXAMPLE_TOPICS = [
    'The effects of video gaming on sleep quality and cognitive performance',
    'How social media use influences adolescent mental health',
    'The relationship between sleep deprivation and academic achievement',
    'Artificial intelligence and its impact on the modern workforce',
    'Climate change adaptation strategies in coastal communities',
    'The ethics of genetic modification in agriculture',
    'How exercise affects mental health in college students',
    'The role of nutrition in preventing chronic diseases',
    'Renewable energy adoption in developing countries',
    'Cybersecurity challenges in small businesses',
    'Machine learning applications in medical diagnostics',
    'How childhood trauma affects adult relationships',
    'Online education and student engagement in higher learning',
    'The psychological effects of social isolation in youth',
    'Sustainable urban planning and green architecture',
    'The influence of advertising on consumer behavior',
    'How sleep impacts emotional regulation and decision-making',
    'Water scarcity and conflict in the Middle East',
    'The role of media bias in shaping public opinion',
    'Blockchain technology and financial transparency',
    'Gender representation in STEM fields',
    'How climate change affects agricultural productivity',
    'The future of electric vehicles and infrastructure',
    'Impact of remote work on employee productivity',
    'The role of biodiversity in ecosystem resilience',
    'How poverty influences access to healthcare',
    'Cultural identity and assimilation in immigrant communities',
    'Data privacy and the ethics of digital surveillance',
    'Psychological resilience and coping strategies after trauma',
    'The effects of music on concentration and creativity',
    'Global supply chain disruptions and economic recovery',
    'Renewable energy policy implementation barriers',
    'AI-driven automation and job displacement',
    'Mindfulness-based stress reduction in workplace settings',
    'The connection between diet and mental health',
    'How plastic pollution affects marine biodiversity',
    'Public trust in science and misinformation online',
    'The influence of parental involvement on academic success',
    'E-sports as a growing professional industry',
    'Economic inequality and political polarization',
    'Smart cities and the future of sustainable infrastructure',
    'Effects of smartphone use on sleep and circadian rhythm',
    'Artificial intelligence in criminal justice systems',
    'The role of education in reducing gender inequality',
    'Digital marketing strategies in the post-pandemic economy',
    'How renewable energy investments affect local economies',
    'Neural mechanisms of decision-making under stress',
    'Consumer attitudes toward sustainable fashion',
    'Ethical implications of human cloning technologies',
    'Wildlife conservation and eco-tourism impacts',
    'How ocean acidification affects coral reef ecosystems',
    'Mental health stigma and access to therapy services',
    'Cross-cultural communication in global business',
    'How leadership style influences team performance',
    'Political misinformation on social media platforms',
    'Renewable agriculture and soil restoration methods',
    'The role of genetics in addiction vulnerability',
    'AI in education: personalized learning and ethical concerns',
    'How video games enhance problem-solving skills',
    'Psychological impacts of long-term social media exposure',
    'Food insecurity and sustainable agricultural practices',
    'Neuroscience of motivation and goal pursuit',
    'How climate migration affects global demographics',
    'Gender roles in media representation and advertising',
    'The future of cryptocurrency in global finance',
    'Air pollution and respiratory disease prevalence',
    'Cultural influences on moral decision-making',
    'The impact of early childhood education on lifelong learning',
    'Privacy concerns in wearable health technology',
    'Green innovation in corporate sustainability practices',
    'Artificial intelligence and creativity in the arts',
    'Global trade policies and environmental sustainability',
    'How diet diversity affects gut microbiome health',
    'Digital addiction and attention span in adolescents',
    'The role of forests in carbon sequestration and climate mitigation',
    'AI ethics and accountability in decision-making systems',
    'Urbanization and the loss of natural habitats',
    'Social determinants of health in urban populations',
    'Economic incentives for renewable energy transition',
    'Cognitive effects of prolonged screen exposure',
    'How peer influence affects adolescent risk-taking',
    'Biotechnology solutions to world hunger',
    'AI-based healthcare diagnostics and patient privacy',
    'Psychological impacts of natural disasters on survivors',
    'Ethical consumerism and brand loyalty trends',
    'Machine learning for predicting climate events',
    'Effects of global tourism on cultural heritage sites',
    'Social media algorithms and political polarization',
    'Virtual reality in education and skill development',
    'How leadership ethics shape organizational culture',
    'Economic effects of climate-related disasters',
    'Digital divide and inequality in developing countries',
    'AI-driven misinformation detection systems',
    'Behavioral economics and decision-making biases',
    'How chronic stress impacts immune system function',
    'Sustainable fisheries and marine resource management',
    'Mental health effects of competitive online gaming',
    'Gender-based violence and global policy responses',
    'The use of drones in environmental monitoring',
    'Corporate responsibility in climate action',
    'Technological innovation and ethical boundaries in healthcare'
]
_EXAMPLE_TOPICS2 = [
    'video game addiction',
    'sleep and performance',
    'mental health awareness',
    'artificial intelligence ethics',
    'climate change adaptation',
    'renewable energy technology',
    'nutrition and wellness',
    'digital privacy',
    'social media influence',
    'youth development',
    'exercise and motivation',
    'stress management',
    'cognitive development',
    'public health systems',
    'genetic engineering',
    'education reform',
    'urban sustainability',
    'globalization effects',
    'environmental conservation',
    'biodiversity loss',
    'renewable resources',
    'political polarization',
    'gender equality',
    'economic inequality',
    'leadership behavior',
    'cybersecurity threats',
    'internet culture',
    'cultural identity',
    'workplace psychology',
    'technology innovation',
    'renewable energy policy',
    'social inequality',
    'consumer behavior',
    'AI in healthcare',
    'mental resilience',
    'youth and technology',
    'climate policy',
    'ocean pollution',
    'agricultural sustainability',
    'forest management',
    'global economics',
    'population growth',
    'migration patterns',
    'renewable transportation',
    'AI in education',
    'digital communication',
    'emotional intelligence',
    'environmental justice',
    'cultural diversity',
    'ecological restoration',
    'renewable agriculture',
    'human behavior',
    'decision making',
    'climate activism',
    'energy storage',
    'gender roles',
    'political communication',
    'wildlife protection',
    'urban development',
    'technological dependence',
    'digital ethics',
    'economic sustainability',
    'renewable investment',
    'ocean ecosystems',
    'water management',
    'mental fatigue',
    'learning technology',
    'public opinion',
    'renewable innovation',
    'social psychology',
    'sleep disorders',
    'addictive behaviors',
    'digital learning',
    'neuroscience research',
    'AI governance',
    'educational inequality',
    'environmental health',
    'waste management',
    'food security',
    'global trade',
    'renewable economy',
    'psychological well-being',
    'virtual reality use',
    'sustainable fashion',
    'renewable materials',
    'economic resilience',
    'mental performance',
    'ethical technology',
    'youth culture',
    'sustainable design',
    'climate education',
    'information systems',
    'AI creativity',
    'media literacy',
    'digital addiction',
    'public policy',
    'environmental ethics',
    'corporate responsibility',
    'renewable industries',
    'health equity',
    'artificial consciousness',
    'biodiversity protection',
    'psychological adaptation',
    'AI sustainability'
]
_EXAMPLE_TOPICS3 = [
    'quantum computing applications',
    'microplastic pollution in oceans',
    'gene editing and CRISPR ethics',
    'renewable hydrogen energy',
    'climate-induced migration patterns',
    'blockchain in supply chain management',
    'mental health in remote work environments',
    'electric aviation technology',
    'carbon capture and storage innovation',
    'biodegradable materials in packaging',
    'AI-driven climate modeling',
    'future of nuclear fusion energy',
    'cyber-physical systems in manufacturing',
    'impact of automation on global labor markets',
    'digital twin technology in smart cities',
    'psychological effects of virtual reality immersion',
    'ecofeminism and environmental justice',
    'social robotics and human empathy',
    'cognitive neuroscience of creativity',
    'AI-assisted medical diagnosis reliability',
    'autonomous vehicles and traffic safety',
    'circular economy in urban infrastructure',
    'deepfake technology and misinformation',
    'biodiversity restoration through rewilding',
    'nanotechnology in drug delivery',
    'ethics of brain-computer interfaces',
    'renewable desalination technologies',
    'psychology of online radicalization',
    'climate finance and green investment',
    'digital surveillance and human rights',
    'genetic diversity and food security',
    'smart agriculture and precision farming',
    'AI transparency and algorithmic bias',
    'socioeconomic impact of longevity research',
    'biomimicry in architectural design',
    'data sovereignty and cloud computing',
    'space debris management and sustainability',
    'AI in disaster prediction and response',
    'cross-cultural leadership in global organizations',
    'neural networks and consciousness theories',
    'environmental taxation and policy design',
    'biophilic design in modern architecture',
    'neuroethics and cognitive enhancement',
    'impact of wearable technology on privacy',
    'quantum encryption and cybersecurity',
    'sustainable fisheries and aquaculture',
    'artificial general intelligence safety',
    'eco-tourism and local community development',
    'plastic recycling and circular materials',
    'geothermal energy potential worldwide',
    'neuroscience of learning and memory retention',
    'AI fairness in criminal justice systems',
    'ocean thermal energy conversion',
    'pharmaceutical waste and water pollution',
    'psychological effects of social media algorithms',
    'bioinformatics and personalized medicine',
    'smart grids and energy optimization',
    'digital identity and authentication systems',
    'automation ethics and employment equity',
    'urban biodiversity and green corridors',
    'AI regulation and global governance',
    'renewable infrastructure financing models',
    'sustainable textile production',
    'internet of things security risks',
    'ethical implications of predictive policing',
    'forest carbon offset markets',
    'machine learning in environmental monitoring',
    'AI in creative industries and art generation',
    'climate anxiety and youth activism',
    'human-robot collaboration in workplaces',
    'mental health impacts of digital overstimulation',
    'data privacy in healthcare systems',
    'sustainable mining practices',
    'autonomous drones in environmental research',
    'eco-innovation in corporate strategy',
    'quantum sensors and environmental measurement',
    'agroforestry and carbon sequestration',
    'AI-enhanced education systems',
    'epigenetics and environmental exposure',
    'climate-smart agriculture',
    'biofuels and sustainable transportation',
    'renewable microgrids in rural communities',
    'AI for biodiversity mapping',
    'genetic data privacy and ownership',
    'neuroplasticity and rehabilitation science',
    'sustainable ocean governance',
    'inclusive technology design',
    'psychology of decision-making under uncertainty',
    'energy equity and global development',
    'ethics of synthetic biology',
    'marine conservation and coral reef protection',
    'AI in cultural heritage preservation',
    'hydrogen fuel infrastructure challenges',
    'biotechnology in waste management',
    'psychological well-being and environmental connection',
    'global cooperation on climate technology transfer',
    'digital divide in healthcare access',
    'environmental economics and carbon pricing',
    'AI-powered public health surveillance',
    'geoengineering and climate intervention ethics'
]


# papers_to_chroma(collection,topics3)
# papers_to_chroma(collection, ["how is ml used in finance", "machine learning in finance","machine learning + finance","finanace using machine learning","finance","machine learning"])
# print_chroma_titles(collection.query(query_texts=['how is ml used in finance'], n_results=5))


def find_empty_space(vectors, tol=None):
    """
    Find an orthonormal basis for the 'empty space' (Null(A^T))
    where your input is simply an array or list of vectors in R^384.

    Parameters
    ----------
    vectors : array-like, shape (n_vectors, 384)
        Each row is one vector in R^384.
    tol : float or None
        Optional numerical tolerance for rank estimation.

    Returns
    -------
    empty_basis : np.ndarray, shape (384, k)
        Columns form an orthonormal basis for the empty space.
        k = 384 - rank(A).
    """
    # Convert to numpy array
    A = np.array(vectors, dtype=float)
    if A.ndim != 2 or A.shape[1] != 384:
        raise ValueError(f"Expected shape (n_vectors, 384), got {A.shape}")

    # Transpose so columns are the vectors
    A = A.T  # shape (384, n_vectors)

    # Perform SVD
    U, s, Vt = np.linalg.svd(A, full_matrices=True)

    # Compute numerical rank
    if tol is None:
        tol = np.finfo(s.dtype).eps * max(A.shape) * s[0] if s.size > 0 else 0.0
    rank = int(np.sum(s > tol))

    # Null(A^T) basis = columns of U corresponding to zero singular values
    empty_basis = U[:, rank:]
    return empty_basis
# count = (collection.count())
# all_data = collection.get(
#         ids=None,  # Retrieve all IDs
#         where=None, # No metadata filtering
#         where_document=None, # No document content filtering
#         limit=count, # No limit, retrieve all records
#         offset=0, # Start from the beginning
#         include=['embeddings', 'documents', 'metadatas'] # Specify what to include
#     )

#     # The embeddings will be in all_data['embeddings']
# vectors = all_data['embeddings']
# print(len(vectors))

# empty_space = find_empty_space(vectors)
# print("Empty-space dimension:", empty_space.shape[1])

# v1 = empty_space[:, 0]   # first null-space vector (shape (384,))
# v2 = empty_space[:, 1]   # second null-space vector (shape (384,))
# A = np.array(vectors).T  # shape (384, n_vectors)
# print(np.allclose(A.T @ v1, 0))
# print(np.allclose(A.T @ v2, 0))

# z = (collection.query(query_embeddings=[v1.tolist(),v2.tolist()], n_results=2))

# print(get_query_texts("how pets reduce stress",n_results=5))