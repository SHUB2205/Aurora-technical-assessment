import asyncio
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn


# Configuration
UPSTREAM_API = "https://november7-730026606190.europe-west1.run.app"
CACHE_TTL_SECONDS = 300  # 5 minutes cache
CACHE_REFRESH_INTERVAL = 60  # Refresh cache every minute
UPSTREAM_TIMEOUT = 30.0


# Models
class Message(BaseModel):
    id: str
    user_id: str
    user_name: str
    timestamp: str
    message: str


class SearchResponse(BaseModel):
    total: int
    items: List[Message]
    page: int = Field(description="Current page number (1-indexed)")
    page_size: int = Field(description="Number of items per page")
    total_pages: int = Field(description="Total number of pages")
    query: Optional[str] = Field(description="Search query used")
    response_time_ms: float = Field(description="Response time in milliseconds")


# In-memory cache
class MessageCache:
    def __init__(self):
        self.messages: List[Message] = []
        self.last_updated: Optional[datetime] = None
        self.is_loading = False
        self.total_count = 0
    
    def is_valid(self) -> bool:
        """Check if cache is still valid"""
        if not self.messages or not self.last_updated:
            return False
        return (datetime.now() - self.last_updated).seconds < CACHE_TTL_SECONDS
    
    def update(self, messages: List[Message], total: int):
        """Update cache with new data"""
        self.messages = messages
        self.total_count = total
        self.last_updated = datetime.now()
        self.is_loading = False


cache = MessageCache()
app = FastAPI(
    title="Fast Search Engine",
    description="High-performance search API with sub-100ms response times",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def fetch_all_messages() -> tuple[List[Message], int]:
    """Fetch all messages from upstream API with pagination"""
    all_messages = []
    skip = 0
    limit = 100
    total = 0
    
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        while True:
            try:
                response = await client.get(
                    f"{UPSTREAM_API}/messages/",
                    params={"skip": skip, "limit": limit}
                )
                response.raise_for_status()
                data = response.json()
                
                total = data.get("total", 0)
                items = data.get("items", [])
                
                if not items:
                    break
                
                all_messages.extend([Message(**item) for item in items])
                skip += limit
                
                # Stop if we've fetched all messages
                if skip >= total:
                    break
                    
            except Exception as e:
                print(f"Error fetching messages: {e}")
                break
    
    return all_messages, total


async def refresh_cache():
    """Background task to refresh cache periodically"""
    while True:
        try:
            if not cache.is_loading:
                cache.is_loading = True
                messages, total = await fetch_all_messages()
                cache.update(messages, total)
                print(f"Cache refreshed: {len(messages)} messages loaded")
        except Exception as e:
            print(f"Cache refresh error: {e}")
            cache.is_loading = False
        
        await asyncio.sleep(CACHE_REFRESH_INTERVAL)


@app.on_event("startup")
async def startup_event():
    """Initialize cache on startup"""
    print("Initializing cache...")
    messages, total = await fetch_all_messages()
    cache.update(messages, total)
    print(f"Cache initialized with {len(messages)} messages")
    
    # Start background refresh task
    asyncio.create_task(refresh_cache())


def search_messages(query: str, messages: List[Message]) -> List[Message]:
    """Search messages using case-insensitive substring matching"""
    if not query:
        return messages
    
    query_lower = query.lower()
    results = []
    
    for msg in messages:
        # Search in message content, user_name, and user_id
        if (query_lower in msg.message.lower() or 
            query_lower in msg.user_name.lower() or 
            query_lower in msg.user_id.lower()):
            results.append(msg)
    
    return results


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Fast Search Engine",
        "cache_status": "valid" if cache.is_valid() else "invalid",
        "cached_messages": len(cache.messages),
        "last_updated": cache.last_updated.isoformat() if cache.last_updated else None
    }


@app.get("/search", response_model=SearchResponse, tags=["Search"])
async def search(
    query: Optional[str] = Query(None, description="Search query to filter messages"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Number of results per page")
):
    
    start_time = time.perf_counter()
    
    # Check if cache is valid
    if not cache.is_valid():
        raise HTTPException(
            status_code=503,
            detail="Cache is being refreshed. Please try again in a moment."
        )
    
    # Perform search
    filtered_messages = search_messages(query or "", cache.messages)
    
    # Calculate pagination
    total_results = len(filtered_messages)
    total_pages = (total_results + page_size - 1) // page_size
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    # Get page results
    page_results = filtered_messages[start_idx:end_idx]
    
    # Calculate response time
    response_time_ms = (time.perf_counter() - start_time) * 1000
    
    return SearchResponse(
        total=total_results,
        items=page_results,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        query=query,
        response_time_ms=round(response_time_ms, 2)
    )


@app.get("/stats", tags=["Stats"])
async def get_stats():
    """Get statistics about the cached data"""
    if not cache.messages:
        return {"error": "No data in cache"}
    
    # Calculate some basic stats
    unique_users = len(set(msg.user_id for msg in cache.messages))
    
    return {
        "total_messages": len(cache.messages),
        "unique_users": unique_users,
        "cache_last_updated": cache.last_updated.isoformat() if cache.last_updated else None,
        "cache_age_seconds": (datetime.now() - cache.last_updated).seconds if cache.last_updated else None,
        "cache_valid": cache.is_valid()
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
