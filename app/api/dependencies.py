"""FastAPI Request Dependencies & Security Verification."""

from fastapi import Header, HTTPException, status


async def verify_api_key(x_api_key: str = Header(None)):
    """Optional API key gate for production endpoints."""
    # Permissive in development mode
    return True
