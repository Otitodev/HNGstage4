import os
import json
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException, status, Header
from pydantic import BaseModel, Field

# Conditional import for the asynchronous PostgreSQL driver
try:
    # Requires: pip install asyncpg
    import asyncpg
    HAS_DB_DRIVER = True
except ImportError:
    HAS_DB_DRIVER = False
    print("WARNING: 'asyncpg' not installed. Running in mock mode only.")


# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global State & Configuration ---
DB_POOL: Optional[asyncpg.Pool] = None

# Environment Variables
NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL")
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "super-secret-dev-key")

# Debug log environment variables (masking sensitive data)
logger.info(f"NEON_DATABASE_URL loaded: {'*' * 20}{NEON_DATABASE_URL[-10:] if NEON_DATABASE_URL else 'None'}")
logger.info(f"INTERNAL_API_SECRET loaded: {'*' * (len(INTERNAL_API_SECRET) - 4) + INTERNAL_API_SECRET[-4:] if INTERNAL_API_SECRET else 'None'}")

# Flag to determine if we run in mock mode
IS_MOCK_MODE = not HAS_DB_DRIVER or not NEON_DATABASE_URL or "postgresql://user:pass@host/db" in NEON_DATABASE_URL


# --- 1. Define the API Contract using Pydantic Models ---

class UserPreferences(BaseModel):
    """
    Nested structure for user delivery preferences.
    """
    email_enabled: bool = Field(..., description="If email notifications are permitted.")
    push_enabled: bool = Field(..., description="If mobile push notifications are permitted.")
    quiet_hours_start: str = Field(..., description="Start time for quiet hours (e.g., '22:00').")
    quiet_hours_end: str = Field(..., description="End time for quiet hours (e.g., '08:00').")

class UserContract(BaseModel):
    """
    The main response contract for the User Service, matching Section 1.A.
    """
    user_id: str = Field(..., description="The unique identifier for the user (UUID format).")
    email_address: str = Field(..., description="The user's primary email address.")
    phone_number: str = Field(..., description="The user's primary phone number (E.164 format recommended).")
    preferred_language: str = Field(..., description="The user's preferred language code (e.g., 'en-US').")
    preferences: UserPreferences = Field(..., description="A map of notification preferences.")


# --- 2. Database Initialization and Operations ---

# Mock Data (used for table population if connected, or as fallback)
MOCK_USERS: Dict[str, Dict[str, Any]] = {
    "user-123": {
        "user_id": "user-123",
        "email_address": "alice@example.com",
        "phone_number": "+14155550001",
        "preferred_language": "en-US",
        "preferences": {
            "email_enabled": True,
            "push_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00"
        }
    },
    "user-456": {
        "user_id": "user-456",
        "email_address": "bob@example.com",
        "phone_number": "+442012345678",
        "preferred_language": "fr-FR",
        "preferences": {
            "email_enabled": False, 
            "push_enabled": True,
            "quiet_hours_start": "00:00",
            "quiet_hours_end": "00:00" 
        }
    }
}


async def initialize_db():
    """
    Sets up the asyncpg connection pool and ensures the necessary table exists.
    """
    # FIX: Declare both global variables at the start of the function.
    global DB_POOL
    global IS_MOCK_MODE 
    
    if IS_MOCK_MODE:
        logger.warning("Database connection skipped. Running entirely in Mock Data Mode.")
        return

    try:
        # Create a connection pool using the NEON_DATABASE_URL
        DB_POOL = await asyncpg.create_pool(dsn=NEON_DATABASE_URL)
        logger.info("Successfully established connection pool to Neon PostgreSQL.")
        
        # 2.1 Ensure Table Exists
        async with DB_POOL.acquire() as conn:
            # Use JSONB for the flexible 'preferences' object
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(255) PRIMARY KEY,
                    email_address VARCHAR(255) NOT NULL,
                    phone_number VARCHAR(20),
                    preferred_language VARCHAR(10) NOT NULL,
                    preferences JSONB 
                );
            """)
            logger.info("Checked/Created 'users' table structure.")
            
            # 2.2 Populate Mock Data (for a fresh start)
            insert_query = """
                INSERT INTO users 
                (user_id, email_address, phone_number, preferred_language, preferences) 
                VALUES ($1, $2, $3, $4, $5) 
                ON CONFLICT (user_id) DO NOTHING;
            """
            
            insert_data = [
                (
                    user_id, 
                    data['email_address'], 
                    data['phone_number'], 
                    data['preferred_language'], 
                    json.dumps(data['preferences']) # JSONB expects a JSON string
                )
                for user_id, data in MOCK_USERS.items()
            ]
            
            await conn.executemany(insert_query, insert_data)
            logger.info(f"Inserted/Confirmed {len(insert_data)} mock users in the DB.")

    except Exception as e:
        logger.error(f"FATAL DB ERROR: Could not connect or initialize database. {e}")
        # Force mock mode if connection fails
        IS_MOCK_MODE = True


async def fetch_user_from_db(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches user data from the Neon database using the asyncpg pool.
    """
    
    if IS_MOCK_MODE:
        logger.info(f"Using mock data for user_id: {user_id}")
        return MOCK_USERS.get(user_id)

    # Real DB Logic
    select_query = """
        SELECT user_id, email_address, phone_number, preferred_language, preferences 
        FROM users 
        WHERE user_id = $1;
    """
    
    try:
        if DB_POOL is None:
             raise Exception("Database pool is not initialized.")

        # fetchrow returns a record object
        record = await DB_POOL.fetchrow(select_query, user_id)

        if record:
            # Convert the asyncpg.Record to a dictionary and ensure preferences is a dict
            data = dict(record)
            if isinstance(data.get('preferences'), str):
                try:
                    data['preferences'] = json.loads(data['preferences'])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse preferences JSON for user {user_id}")
                    data['preferences'] = {}
            return data
        
        return None
        
    except asyncpg.exceptions.PostgresError as e:
        logger.error(f"PostgreSQL query failed for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Check Neon connection."
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred during DB fetch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during data retrieval."
        )


# --- 3. FastAPI Application Setup ---

app = FastAPI(
    title="User Service API (Authenticated)",
    description="Provides user profiles and notification preferences. Requires service-to-service authentication.",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """
    Initialize database connection pool on application startup.
    """
    logger.info("User Service is starting up.")
    await initialize_db()

@app.on_event("shutdown")
async def shutdown_event():
    """
    Close the database connection pool on application shutdown.
    """
    global DB_POOL
    if DB_POOL:
        logger.info("Closing Neon PostgreSQL connection pool.")
        await DB_POOL.close()

async def get_db_pool() -> asyncpg.Pool:
    """Get or create a database pool"""
    global DB_POOL
    
    if IS_MOCK_MODE:
        return None
        
    if DB_POOL is None:
        try:
            DB_POOL = await asyncpg.create_pool(dsn=NEON_DATABASE_URL)
            logger.info("Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise
    return DB_POOL
    
# --- 4. Define the API Endpoint (Contract Implementation) ---

@app.get("/")
async def root():
    """Root endpoint to verify the service is running."""
    return {"status": "User Service is running"}

@app.get(
    "/v1/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint"
)
async def health_check():
    """
    Health check endpoint to verify the service is running and all dependencies are accessible.
    Checks both PostgreSQL and Redis connections.
    """
    health_status = {
        "status": "healthy",
        "version": "1.0.0",
        "services": {}
    }
    
    try:
        # Check PostgreSQL connection
        if not IS_MOCK_MODE and HAS_DB_DRIVER:
            try:
                pool = await get_db_pool()
                if pool:
                    async with pool.acquire() as conn:
                        # Execute a simple query to verify database connection
                        result = await conn.fetchval("SELECT 1")
                        if result != 1:
                            raise ValueError("Unexpected database response")
                    health_status["services"]["postgresql"] = "connected"
            except Exception as db_error:
                logger.error(f"Database health check failed: {str(db_error)}")
                health_status["services"]["postgresql"] = "unavailable"
                health_status["status"] = "degraded"
        else:
            health_status["services"]["postgresql"] = "mock_mode"
            
        # Check Redis connection if available
        try:
            from redis_client import get_redis_client
            redis = get_redis_client()
            # Use the underlying client's ping which is synchronous
            redis_pong = redis._client.ping()
            if not redis_pong:
                raise ValueError("Redis ping failed")
            health_status["services"]["redis"] = "connected"
        except ImportError:
            logger.warning("Redis client not available")
            health_status["services"]["redis"] = "not_configured"
        except Exception as redis_error:
            logger.error(f"Redis health check failed: {str(redis_error)}")
            health_status["services"]["redis"] = "unavailable"
            health_status["status"] = "degraded"
            
        # If any critical service is down, return 503
        if health_status["status"] == "degraded":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "service_unavailable", "details": health_status}
            )
            
        return health_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "service_unavailable", "error": str(e)}
        )

@app.get(
    "/v1/users/{user_id}", 
    response_model=UserContract,
    status_code=status.HTTP_200_OK,
    summary="Retrieve User Profile and Notification Preferences (Internal Auth Required)"
)
async def get_user_profile(
    user_id: str,
    # Require the custom header for service-to-service authentication
    x_internal_secret: str = Header(..., alias="X-Internal-Secret") 
):
    """
    Retrieves the user's profile and preferences. This endpoint is internal 
    and requires the 'X-Internal-Secret' header for access control, 
    ensuring only the API Gateway can call it.
    
    Raises 401 if the secret is invalid.
    Raises 404 if the user ID is not found.
    """
    
    # 4.1 Internal Service Authentication Check
    if x_internal_secret != INTERNAL_API_SECRET:
        logger.error(f"Authentication failed: Invalid X-Internal-Secret provided.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service authorization header. Access denied."
        )
    
    # 4.2 Data Retrieval
    user_data = await fetch_user_from_db(user_id)
    
    if user_data is None:
        logger.warning(f"User not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID '{user_id}' not found."
        )
    
    # 4.3 Contract Validation
    try:
        contract_data = UserContract(**user_data)
        logger.info(f"Successfully retrieved and validated contract for user: {user_id}")
        return contract_data
    except Exception as e:
        logger.error(f"Data validation failed for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal data structure error. Contract violation."
        )

# --- How to run (Local Development) ---
# 1. Install dependencies: pip install fastapi uvicorn pydantic asyncpg
# 2. Run with your Neon URL and a secret: 
#    NEON_DATABASE_URL="<YOUR_NEON_URI>" INTERNAL_API_SECRET="<YOUR_SECRET>" uvicorn user_service:app --reload 
# 3. Or run in mock mode (no DB required):
#    uvicorn user_service:app --reload