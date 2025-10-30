"""
FastAPI backend for Aristotle UI.
Provides REST API endpoints to connect the web interface with the agent.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging

# Import the agent module
from my_agent import agent
import research_agent
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Aristotle API",
    description="API for Aristotle AI Research Assistant",
    version="1.0.0"
)

# Configure CORS to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class QueryRequest(BaseModel):
    """Request model for search queries"""
    query: str
    command: Optional[str] = None


class QueryResponse(BaseModel):
    """Response model for search queries"""
    response: str
    query: str
    command: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    message: str


class ResearchRequest(BaseModel):
    """Request model for research generation"""
    topic: str


@app.get("/", response_model=HealthResponse)
async def root():
    """
    Root endpoint for health check.
    
    Returns:
        Health status of the API
    """
    return HealthResponse(status="healthy", message="Aristotle API is running")


@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Process a user query through the Aristotle agent.
    
    Args:
        request: QueryRequest containing the user's query
        
    Returns:
        QueryResponse with the agent's response
        
    Raises:
        HTTPException: If the agent fails to process the query
    """
    try:
        logger.info(f"Processing query: {request.query}")
        
        # Call the agent to process the query
        response = agent(request.query)
        
        logger.info(f"Successfully processed query")
        
        return QueryResponse(
            response=response,
            query=request.query,
            command=request.command
        )
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process query: {str(e)}"
        )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
        Health status
    """
    return HealthResponse(status="healthy", message="Aristotle API is operational")


@app.post("/research")
async def generate_research(request: ResearchRequest):
    """
    Generate a complete research paper with live progress updates.
    
    Args:
        request: ResearchRequest containing the research topic
        
    Returns:
        Server-sent events stream with progress updates and final results
    """
    from fastapi.responses import StreamingResponse
    import json
    import asyncio
    
    async def generate():
        topic = request.topic
        
        try:
            # Emit initial stage
            yield f"data: {json.dumps({'type': 'stage', 'message': f'Starting research on: {topic}', 'percent': 5})}\n\n"
            
            # Run research agent
            result = {'output_path': '', 'papers_analyzed': 0, 'hypotheses_generated': 0, 'simulations_created': 0}
            
            def run_agent():
                try:
                    # Monkey-patch print to capture output
                    import sys
                    from io import StringIO
                    old_print = print
                    
                    output_buffer = []
                    
                    def capture_print(*args, **kwargs):
                        msg = ' '.join(str(arg) for arg in args)
                        output_buffer.append(msg)
                        old_print(*args, **kwargs)  # Still print to console
                    
                    # Temporarily replace print
                    import builtins
                    builtins.print = capture_print
                    
                    try:
                        output_path = research_agent.run_research_agent(topic)
                        result['output_path'] = output_path
                        
                        # Read metadata
                        import json
                        from pathlib import Path
                        parts = output_path.split('/')
                        topic_folder = parts[-2] if len(parts) > 1 else ''
                        metadata_path = Path(f"./research_output/{topic_folder}/metadata.json")
                        
                        if metadata_path.exists():
                            with open(metadata_path, 'r') as f:
                                metadata = json.load(f)
                                result['papers_analyzed'] = metadata.get('papers_analyzed', 0)
                                result['hypotheses_generated'] = metadata.get('hypotheses_generated', 0)
                                result['simulations_created'] = metadata.get('simulations_created', 0)
                    finally:
                        # Restore original print
                        builtins.print = old_print
                
                except Exception as e:
                    logger.error(f"Research agent error: {str(e)}")
                    result['error'] = str(e)
            
            # Run in thread
            thread = threading.Thread(target=run_agent)
            thread.start()
            
            # Simulate progress with reasonable timing
            progress_updates = [
                (15, 'Fetching papers from Semantic Scholar...'),
                (30, 'Analyzing literature with Gemini AI...'),
                (50, 'Generating novel hypotheses...'),
                (65, 'Creating simulation for Hypothesis 1...'),
                (75, 'Creating simulation for Hypothesis 2...'),
                (85, 'Writing comprehensive research paper...'),
                (95, 'Finalizing output files...'),
            ]
            
            for percent, message in progress_updates:
                await asyncio.sleep(2)  # Wait 2 seconds between updates
                if thread.is_alive():
                    yield f"data: {json.dumps({'type': 'stage', 'message': message, 'percent': percent})}\n\n"
            
            # Wait for completion
            thread.join()
            
            # Final result
            if 'error' in result:
                yield f"data: {json.dumps({'type': 'error', 'message': result['error']})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'complete', 'result': result})}\n\n"
        
        except Exception as e:
            logger.error(f"Error in research generation: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

