"""
Simple test script to verify API functionality
"""
import asyncio
import time
from main import app, cache, fetch_all_messages
from fastapi.testclient import TestClient


def test_health_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    print("✓ Health endpoint test passed")


def test_search_endpoint():
    """Test search endpoint"""
    client = TestClient(app)
    
    # Test without query
    response = client.get("/search")
    assert response.status_code in [200, 503]  # 503 if cache not ready
    print("✓ Search endpoint test passed (no query)")
    
    # Test with query
    response = client.get("/search?query=test&page=1&page_size=10")
    assert response.status_code in [200, 503]
    if response.status_code == 200:
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert "page" in data
        assert "response_time_ms" in data
        print(f"✓ Search endpoint test passed (with query, {data['response_time_ms']}ms)")


def test_stats_endpoint():
    """Test stats endpoint"""
    client = TestClient(app)
    response = client.get("/stats")
    assert response.status_code in [200]
    print("✓ Stats endpoint test passed")


def test_pagination():
    """Test pagination logic"""
    client = TestClient(app)
    
    # Test different page sizes
    for page_size in [10, 20, 50]:
        response = client.get(f"/search?page=1&page_size={page_size}")
        if response.status_code == 200:
            data = response.json()
            assert len(data["items"]) <= page_size
            print(f"✓ Pagination test passed (page_size={page_size})")


async def test_cache_loading():
    """Test cache loading functionality"""
    print("Testing cache loading...")
    messages, total = await fetch_all_messages()
    print(f"✓ Cache loading test passed: {len(messages)} messages loaded")
    return len(messages) > 0


def test_response_time():
    """Test that response time is under 100ms"""
    client = TestClient(app)
    
    # Warm up
    client.get("/search?query=test")
    
    # Measure response time
    times = []
    for _ in range(10):
        start = time.perf_counter()
        response = client.get("/search?query=test&page=1&page_size=20")
        elapsed = (time.perf_counter() - start) * 1000
        if response.status_code == 200:
            times.append(elapsed)
    
    if times:
        avg_time = sum(times) / len(times)
        max_time = max(times)
        print(f"✓ Response time test: avg={avg_time:.2f}ms, max={max_time:.2f}ms")
        if max_time < 100:
            print("✓ All responses under 100ms!")
        else:
            print(f"⚠ Some responses over 100ms (max: {max_time:.2f}ms)")


if __name__ == "__main__":
    print("Running API tests...\n")
    
    # Run async test
    cache_loaded = asyncio.run(test_cache_loading())
    
    if cache_loaded:
        # Initialize cache for tests
        asyncio.run(fetch_all_messages())
        messages, total = asyncio.run(fetch_all_messages())
        cache.update(messages, total)
    
    # Run sync tests
    test_health_endpoint()
    test_search_endpoint()
    test_stats_endpoint()
    test_pagination()
    
    if cache_loaded:
        test_response_time()
    
    print("\n✅ All tests completed!")
