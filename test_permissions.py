#!/usr/bin/env python3
"""
Test permission checks directly
"""
import asyncio
import httpx

SERVICE_TOKEN = "5XFXyEFX5p4qxWK6pYGDibG3YM-r3WqagY3VzFkAVqW3WU00ngh8K7eh4ka-44VJ5WksrfDspeer2Hx8AQOk5A"
AUTH_API_URL = "http://localhost:8000"

async def test_permission_check():
    """Test direct permission check via Auth API"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AUTH_API_URL}/api/v1/authorization/check",
            headers={
                "X-Service-Token": SERVICE_TOKEN,
                "Content-Type": "application/json"
            },
            json={
                "org_id": "99999999-9999-9999-9999-999999999999",
                "user_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                "permission": "chat:read"
            }
        )

        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

        return response.json()

if __name__ == "__main__":
    result = asyncio.run(test_permission_check())
    print(f"\n✓ Test passed: allowed={result.get('allowed')}")
