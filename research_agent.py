"""
Research Agent - AI-Powered Research Paper Generator

Conducts comprehensive literature review, generates novel hypotheses,
develops simulations, and writes academic research papers.

Usage:
    python research_agent.py "quantum machine learning algorithms"
"""

import os
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
import my_chroma
import scholar_api as sch

# Load environment variables
load_dotenv()

# Configuration
MODEL = "gemini-2.0-flash-exp"
TEMPERATURE = 0.7  # Higher for creativity
MAX_PAPERS = 50
DEFAULT_HYPOTHESES = 3

# Initialize Gemini API client
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please set it in a .env file.")

client = genai.Client(api_key=api_key)


def conduct_literature_review(topic: str, paper_count: int = 30) -> dict:
    """
    Conduct comprehensive literature review on a given topic.
    
    Args:
        topic: Research topic to review
        paper_count: Number of papers to fetch and analyze
        
    Returns:
        Dictionary containing structured literature analysis
    """
    print(f"[INFO] Conducting literature review on: {topic}")
    
    # Fetch papers from ChromaDB or Semantic Scholar
    print(f"[INFO] Fetching {paper_count} papers...")
    my_chroma.papers_to_chroma([topic])
    
    # Query papers from ChromaDB
    res = my_chroma.get_query_texts(topic, n_results=min(paper_count, MAX_PAPERS))
    papers_json = json.dumps(res, default=str)
    
    # Use Gemini to analyze literature
    prompt = (
        "You are an expert academic researcher conducting a comprehensive literature review.\n\n"
        f"Topic: {topic}\n\n"
        "Below are {len_papers} research papers with titles, abstracts, and metadata.\n\n"
        "Please analyze these papers and provide:\n"
        "1. Key Themes: What are the main research themes in this field?\n"
        "2. Methodologies: What research methods are commonly used?\n"
        "3. Research Gaps: What questions or areas remain unanswered?\n"
        "4. Controversies: Are there conflicting findings or debates?\n"
        "5. Trends: What are emerging trends or future directions?\n"
        "6. Summary: A concise synthesis of the current state of research\n\n"
        "Format your response as structured analysis with clear sections."
    ).format(len_papers=len(res.get('metadatas', [[]])[0]))
    
    prompt = prompt + "\n\nPapers:\n" + papers_json
    
    print("[INFO] Analyzing literature with Gemini...")
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"temperature": TEMPERATURE}
    )
    
    analysis_text = (response.text or "").strip()
    
    # Extract metadata
    metas = res.get('metadatas', [[]])[0] if res.get('metadatas') else []
    papers_list = []
    for i, m in enumerate(metas[:paper_count], 1):
        papers_list.append({
            'id': i,
            'title': m.get('title', 'Unknown'),
            'year': m.get('year', ''),
            'authors': m.get('authors', ''),
            'url': m.get('url', ''),
            'abstract': m.get('abstract', '')[:500] if m.get('abstract') else ''
        })
    
    return {
        'topic': topic,
        'papers_analyzed': len(papers_list),
        'papers': papers_list,
        'analysis': analysis_text
    }


def generate_hypotheses(literature_analysis: dict) -> list[dict]:
    """
    Generate novel, testable hypotheses based on literature analysis.
    
    Args:
        literature_analysis: Output from conduct_literature_review()
        
    Returns:
        List of hypothesis dictionaries with full details
    """
    print("[INFO] Generating novel hypotheses...")
    
    prompt = (
        "You are an innovative researcher generating novel hypotheses.\n\n"
        "Based on the following literature review, propose 3-5 novel, testable hypotheses "
        "that extend beyond existing research.\n\n"
        "Literature Analysis:\n" + literature_analysis['analysis'] + "\n\n"
        "For each hypothesis, provide:\n"
        "1. Hypothesis Statement: A clear, testable claim\n"
        "2. Rationale: Why this hypothesis is novel and important\n"
        "3. Expected Outcomes: What you predict will be found\n"
        "4. Testability: How this could be experimentally tested\n"
        "5. Novelty: What makes this hypothesis different from existing research\n\n"
        "Format as:\n"
        "Hypothesis 1:\n"
        "Statement: [clear statement]\n"
        "Rationale: [explanation]\n"
        "Expected Outcomes: [predictions]\n"
        "Testability: [methods]\n"
        "Novelty: [uniqueness]\n\n"
        "Repeat for each hypothesis."
    )
    
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"temperature": TEMPERATURE}
    )
    
    hypotheses_text = (response.text or "").strip()
    
    # Parse hypotheses (handle both bold and plain text formats)
    hypotheses = []
    
    # Try splitting on different patterns
    sections = []
    import re
    if "**Hypothesis" in hypotheses_text:
        # Bold markdown format: **Hypothesis 1:**
        sections = re.split(r'\*\*Hypothesis\s+\d+:\*\*', hypotheses_text)
        sections = [s for s in sections if s.strip()][:DEFAULT_HYPOTHESES + 1]
    elif "Hypothesis 1:" in hypotheses_text or re.search(r'Hypothesis\s+\d+:', hypotheses_text):
        # Plain text format: Hypothesis 1: or with variations
        sections = re.split(r'Hypothesis\s+\d+:', hypotheses_text)
        sections = sections[1:DEFAULT_HYPOTHESES + 1] if len(sections) > 1 else []
    
    for section in sections[:DEFAULT_HYPOTHESES]:
        if not section.strip():
            continue
        
        lines = section.split('\n')
        hypothesis = {
            'statement': '',
            'rationale': '',
            'expected_outcomes': '',
            'testability': '',
            'novelty': ''
        }
        
        current_field = None
        current_text = []
        
        for line in lines:
            # Strip markdown bold markers and bullets
            line = line.strip().replace('**', '').lstrip('*').strip()
            if not line or line.startswith('--'):
                if current_field and current_text:
                    hypothesis[current_field] = ' '.join(current_text).strip()
                    current_text = []
                continue
            
            # Check for field headers (with or without bold)
            if line.startswith("Statement"):
                if current_field and current_text:
                    hypothesis[current_field] = ' '.join(current_text).strip()
                current_field = 'statement'
                current_text = [line.split(':', 1)[-1].strip()] if ':' in line else []
            elif line.startswith("Rationale"):
                if current_field and current_text:
                    hypothesis[current_field] = ' '.join(current_text).strip()
                current_field = 'rationale'
                current_text = [line.split(':', 1)[-1].strip()] if ':' in line else []
            elif line.startswith("Expected Outcomes"):
                if current_field and current_text:
                    hypothesis[current_field] = ' '.join(current_text).strip()
                current_field = 'expected_outcomes'
                current_text = [line.split(':', 1)[-1].strip()] if ':' in line else []
            elif line.startswith("Testability"):
                if current_field and current_text:
                    hypothesis[current_field] = ' '.join(current_text).strip()
                current_field = 'testability'
                current_text = [line.split(':', 1)[-1].strip()] if ':' in line else []
            elif line.startswith("Novelty"):
                if current_field and current_text:
                    hypothesis[current_field] = ' '.join(current_text).strip()
                current_field = 'novelty'
                current_text = [line.split(':', 1)[-1].strip()] if ':' in line else []
            elif current_field:
                current_text.append(line)
        
        if current_field and current_text:
            hypothesis[current_field] = ' '.join(current_text).strip()
        
        if hypothesis['statement']:
            hypotheses.append(hypothesis)
    
    print(f"[INFO] Generated {len(hypotheses)} hypotheses")
    return hypotheses


def design_simulation(hypothesis: dict, hypothesis_num: int) -> dict:
    """
    Design Python simulation code for testing a hypothesis.
    
    Args:
        hypothesis: Hypothesis dictionary from generate_hypotheses()
        hypothesis_num: Number of the hypothesis
        
    Returns:
        Dictionary containing simulation code, description, and expected outputs
    """
    print(f"[INFO] Designing simulation for Hypothesis {hypothesis_num}...")
    
    prompt = (
        "You are a computational researcher designing a Python simulation.\n\n"
        f"Hypothesis: {hypothesis['statement']}\n\n"
        "Design a Python simulation to test this hypothesis. Generate:\n\n"
        "1. Python Code: Complete, runnable simulation code\n"
        "   - Import necessary libraries (numpy, matplotlib, etc.)\n"
        "   - Generate synthetic data relevant to the hypothesis\n"
        "   - Perform statistical analysis\n"
        "   - Create visualizations\n"
        "   - Include comments explaining each step\n\n"
        "2. Description: Explain what the simulation does and how it tests the hypothesis\n\n"
        "3. Expected Outputs: Describe what results are expected\n\n"
        "Format as:\n"
        "CODE:\n"
        "```python\n"
        "[complete Python code here]\n"
        "```\n\n"
        "DESCRIPTION:\n"
        "[explanation]\n\n"
        "EXPECTED_OUTPUTS:\n"
        "[results description]"
    )
    
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"temperature": TEMPERATURE}
    )
    
    result_text = (response.text or "").strip()
    
    # Parse simulation components
    simulation = {
        'code': '',
        'description': '',
        'expected_outputs': '',
        'hypothesis': hypothesis['statement']
    }
    
    # Extract code from markdown code block
    code_match = result_text.find("```python")
    if code_match != -1:
        code_start = code_match + len("```python")
        code_end = result_text.find("```", code_start)
        if code_end != -1:
            simulation['code'] = result_text[code_start:code_end].strip()
    
    # Extract description
    desc_match = result_text.find("DESCRIPTION:")
    if desc_match != -1:
        desc_start = desc_match + len("DESCRIPTION:")
        exp_match = result_text.find("EXPECTED_OUTPUTS:")
        if exp_match != -1:
            simulation['description'] = result_text[desc_start:exp_match].strip()
    
    # Extract expected outputs
    exp_match = result_text.find("EXPECTED_OUTPUTS:")
    if exp_match != -1:
        simulation['expected_outputs'] = result_text[exp_match + len("EXPECTED_OUTPUTS:"):].strip()
    
    return simulation


def write_research_paper(topic: str, literature: dict, hypotheses: list, simulations: list) -> str:
    """
    Write comprehensive academic research paper.
    
    Args:
        topic: Research topic
        literature: Literature analysis from conduct_literature_review()
        hypotheses: List of hypotheses from generate_hypotheses()
        simulations: List of simulation designs from design_simulation()
        
    Returns:
        Full research paper as markdown text
    """
    print("[INFO] Writing research paper...")
    
    # Prepare citations
    citations = "\n".join([
        f"{i}. {p['title']} ({p['year']}). {p['authors']}. {p['url']}"
        for i, p in enumerate(literature['papers'][:30], 1)
    ])
    
    # Prepare hypotheses section
    hypotheses_text = ""
    for i, hyp in enumerate(hypotheses, 1):
        hypotheses_text += f"\n\n{i}. {hyp['statement']}\n"
        hypotheses_text += f"   Rationale: {hyp['rationale']}\n"
        hypotheses_text += f"   Expected Outcomes: {hyp['expected_outcomes']}\n"
    
    # Prepare simulations section
    simulations_text = ""
    for i, sim in enumerate(simulations, 1):
        simulations_text += f"\n\n{i}. {sim['description']}\n"
        simulations_text += f"   Expected Outputs: {sim['expected_outputs']}\n"
    
    prompt = (
        "You are an expert academic researcher writing a comprehensive research paper.\n\n"
        f"Research Topic: {topic}\n\n"
        "Write a complete academic research paper in markdown format with the following structure:\n\n"
        "1. Title: Create an academic title for this research\n"
        "2. Abstract (200-250 words): Summary of the research\n"
        "3. Introduction (2 pages): Background, motivation, objectives\n"
        "4. Literature Review (3 pages): Synthesis of existing research\n"
        "5. Hypotheses (1 page): Your novel hypotheses\n"
        "6. Methodology (2 pages): How you would test the hypotheses\n"
        "7. Simulation Design (2 pages): Description of computational approaches\n"
        "8. Expected Results (2 pages): What outcomes are predicted\n"
        "9. Discussion (2 pages): Implications and significance\n"
        "10. Conclusion (1 page): Summary and future work\n"
        "11. References: Cite the papers provided\n\n"
        f"Literature Analysis:\n{literature['analysis']}\n\n"
        f"Hypotheses:\n{hypotheses_text}\n\n"
        f"Simulations:\n{simulations_text}\n\n"
        "Write at least 8-15 pages equivalent (comprehensive depth).\n"
        "Use proper academic language and formatting.\n"
        "Include citations in the format: [1], [2], etc.\n"
        "Format as markdown with clear section headers."
    )
    
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"temperature": TEMPERATURE}
    )
    
    paper_text = (response.text or "").strip()
    
    # Add references section
    paper_text += "\n\n## References\n\n" + citations
    
    return paper_text


def run_research_agent(topic: str, output_dir: str = "./research_output") -> str:
    """
    Run the complete research agent pipeline.
    
    Args:
        topic: Research topic to investigate
        output_dir: Directory to save outputs
        
    Returns:
        Path to generated research paper
    """
    print(f"\n{'='*80}")
    print(f"RESEARCH AGENT: {topic}")
    print(f"{'='*80}\n")
    
    # Create output directory
    safe_topic = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in topic)
    safe_topic = safe_topic.strip().replace(' ', '_')[:100]
    
    output_path = Path(output_dir) / safe_topic
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "simulations").mkdir(exist_ok=True)
    
    # Step 1: Literature Review
    literature = conduct_literature_review(topic, paper_count=30)
    
    # Save literature analysis
    with open(output_path / "literature_analysis.json", 'w') as f:
        json.dump(literature, f, indent=2)
    
    # Step 2: Generate Hypotheses
    hypotheses = generate_hypotheses(literature)
    
    # Save hypotheses
    with open(output_path / "hypotheses.json", 'w') as f:
        json.dump(hypotheses, f, indent=2)
    
    # Step 3: Design Simulations
    simulations = []
    for i, hypothesis in enumerate(hypotheses, 1):
        sim = design_simulation(hypothesis, i)
        simulations.append(sim)
        
        # Save simulation code
        sim_path = output_path / "simulations" / f"simulation_{i}.py"
        with open(sim_path, 'w') as f:
            f.write(sim['code'])
        print(f"[INFO] Saved simulation code: {sim_path}")
    
    # Save simulations metadata
    with open(output_path / "simulations.json", 'w') as f:
        json.dump(simulations, f, indent=2)
    
    # Step 4: Write Paper
    paper = write_research_paper(topic, literature, hypotheses, simulations)
    
    # Save paper
    paper_path = output_path / "paper.md"
    with open(paper_path, 'w') as f:
        f.write(paper)
    
    # Save metadata
    metadata = {
        'topic': topic,
        'papers_analyzed': len(literature['papers']),
        'hypotheses_generated': len(hypotheses),
        'simulations_created': len(simulations),
        'output_path': str(output_path)
    }
    with open(output_path / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n{'='*80}")
    print("RESEARCH COMPLETE")
    print(f"{'='*80}")
    print(f"Paper: {paper_path}")
    print(f"Literature: {len(literature['papers'])} papers")
    print(f"Hypotheses: {len(hypotheses)}")
    print(f"Simulations: {len(simulations)}")
    print(f"{'='*80}\n")
    
    return str(paper_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python research_agent.py <topic>")
        print("Example: python research_agent.py \"quantum machine learning algorithms\"")
        sys.exit(1)
    
    topic = " ".join(sys.argv[1:])
    output_path = run_research_agent(topic)
    print(f"Research paper generated: {output_path}")

