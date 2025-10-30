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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

