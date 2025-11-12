import os
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv
# Redis will be imported in startup_event

# Add project root to Python path
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from utils.response_formatter import success_response, error_response
from utils.cache import CacheManager, cached, invalidate_cache

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException, status, Header, Depends
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
CACHE_MANAGER: Optional[CacheManager] = None

# Environment Variables
NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL")
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "super-secret-dev-key")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

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

class UserCreate(BaseModel):
    """Request model for creating a new user."""
    email_address: str = Field(..., description="The user's primary email address.")
    phone_number: str = Field(..., description="The user's primary phone number (E.164 format recommended).")
    preferred_language: str = Field("en-US", description="The user's preferred language code (e.g., 'en-US').")
    preferences: UserPreferences = Field(..., description="A map of notification preferences.")

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


async def create_user_in_db(user_data: dict) -> dict:
    """
    Creates a new user in the database.
    
    Args:
        user_data: Dictionary containing user data (email_address, phone_number, 
                 preferred_language, preferences)
                  
    Returns:
        dict: The created user data with generated user_id
    """
    if IS_MOCK_MODE:
        # Generate a new user_id for mock mode
        user_id = str(uuid.uuid4())
        user = {
            "user_id": user_id,
            "email_address": user_data["email_address"],
            "phone_number": user_data["phone_number"],
            "preferred_language": user_data.get("preferred_language", "en-US"),
            "preferences": user_data["preferences"]
        }
        MOCK_USERS[user_id] = user
        
        # Invalidate cache for this user
        if CACHE_MANAGER:
            try:
                # Invalidate both user ID and email caches
                CACHE_MANAGER.delete(f"users:{user_id}")
                CACHE_MANAGER.delete(f"users:email:{user_data['email_address']}")
            except Exception as e:
                logger.warning(f"Cache invalidation failed: {str(e)}")
            
        return user
        
    if not HAS_DB_DRIVER or not DB_POOL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection not available"
        )
    
    try:
        async with DB_POOL.acquire() as conn:
            # Start a transaction
            async with conn.transaction():
                # Check if email already exists
                existing = await conn.fetchrow(
                    "SELECT user_id FROM users WHERE email_address = $1",
                    user_data["email_address"]
                )
                
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"User with email '{user_data['email_address']}' already exists"
                    )
                
                # Generate a new UUID for the user
                user_id = str(uuid.uuid4())
                
                # Insert the new user
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (
                        user_id,
                        email_address, 
                        phone_number, 
                        preferred_language, 
                        preferences
                    ) VALUES ($1, $2, $3, $4, $5)
                    RETURNING user_id, email_address, phone_number, 
                             preferred_language, preferences
                    """,
                    user_id,
                    user_data["email_address"],
                    user_data["phone_number"],
                    user_data.get("preferred_language", "en-US"),
                    json.dumps(user_data["preferences"].dict() if hasattr(user_data["preferences"], "dict") 
                              else user_data["preferences"])
                )
                
                # Convert the record to a dictionary and ensure preferences is a dict
                result = dict(row)
                if isinstance(result.get('preferences'), str):
                    try:
                        result['preferences'] = json.loads(result['preferences'])
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse preferences JSON for new user {user_id}")
                        result['preferences'] = {}
                        
                return result
                
    except asyncpg.UniqueViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email or phone number already exists"
        )
    except asyncpg.PostgresError as e:
        logger.error(f"Database error creating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user in database"
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
    Initialize database connection pool and cache on application startup.
    """
    global CACHE_MANAGER
    
    logger.info("User Service is starting up.")
    await initialize_db()
    
    # Initialize Redis cache
    try:
        from upstash_redis import Redis as UpstashRedis
        rest_url = os.getenv('UPSTASH_REDIS_REST_URL')
        token = os.getenv('UPSTASH_REDIS_REST_TOKEN')
        
        if rest_url and token:
            redis_client = UpstashRedis(url=rest_url, token=token)
            CACHE_MANAGER = CacheManager(redis_client, key_prefix="user_svc:")
            logger.info("Redis cache initialized successfully with Upstash")
        else:
            logger.warning("Upstash Redis credentials not found, cache disabled")
            CACHE_MANAGER = None
    except Exception as e:
        logger.error(f"Failed to initialize Redis cache: {str(e)}")
        CACHE_MANAGER = None

@app.on_event("shutdown")
async def shutdown_event():
    """
    Clean up resources on application shutdown.
    """
    global DB_POOL, CACHE_MANAGER
    
    try:
        # Close database connection pool
        if DB_POOL:
            logger.info("Closing Neon PostgreSQL connection pool.")
            await DB_POOL.close()
    except Exception as e:
        logger.error(f"Error closing database connection: {str(e)}")
    
    try:
        # Close Redis connection if using connection pooling
        if CACHE_MANAGER is not None and hasattr(CACHE_MANAGER, 'redis') and CACHE_MANAGER.redis is not None:
            if hasattr(CACHE_MANAGER.redis, 'close') and callable(CACHE_MANAGER.redis.close):
                logger.info("Closing Redis connection.")
                if asyncio.iscoroutinefunction(CACHE_MANAGER.redis.close):
                    await CACHE_MANAGER.redis.close()
                else:
                    CACHE_MANAGER.redis.close()
            elif hasattr(CACHE_MANAGER.redis, 'connection_pool') and CACHE_MANAGER.redis.connection_pool is not None:
                logger.info("Closing Redis connection pool.")
                if hasattr(CACHE_MANAGER.redis.connection_pool, 'disconnect') and \
                   callable(CACHE_MANAGER.redis.connection_pool.disconnect):
                    CACHE_MANAGER.redis.connection_pool.disconnect()
    except Exception as e:
        logger.error(f"Error closing Redis connection: {str(e)}")
    finally:
        # Ensure we clear the global variables
        DB_POOL = None
        CACHE_MANAGER = None

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

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint to verify the service is running."""
    return success_response(
        data={"service": "User Service"},
        message="User Service is running"
    )

@app.get(
    "/v1/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint"
)
async def health_check():
    """Health check endpoint to verify the service and its dependencies."""
    try:
        health_data = {
            "status": "healthy",
            "version": "1.0.0",
            "dependencies": {}
        }
        
        # Check database connection if database is enabled
        if HAS_DB_DRIVER and DB_POOL is not None:
            try:
                async with DB_POOL.acquire() as conn:
                    await conn.fetchval('SELECT 1')
                health_data["dependencies"]["database"] = "connected"
            except Exception as db_error:
                health_data["dependencies"]["database"] = f"error: {str(db_error)}"
                raise db_error
        else:
            health_data["dependencies"]["database"] = "disabled"
        
        return success_response(
            data=health_data,
            message="Service is healthy"
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return error_response(
            message="Service is unhealthy",
            error=f"Health check failed: {str(e)}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

@app.get(
    "/v1/users/{user_id}",
    response_model=UserContract,
    status_code=status.HTTP_200_OK,
    summary="Get user profile and preferences"
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
    
    Returns 401 if the secret is invalid.
    Returns 404 if the user ID is not found.
    """
    # Verify the internal secret
    if x_internal_secret != INTERNAL_API_SECRET:
        return error_response(
            message="Unauthorized",
            error="Invalid internal API secret",
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    # Try to get from cache first
    cache_key = f"users:{user_id}"
    if CACHE_MANAGER:
        cached_user = CACHE_MANAGER.get(cache_key)
        if cached_user:
            logger.info(f"Cache hit for user {user_id}")
            return success_response(
                data=cached_user,
                message="User profile retrieved successfully"
            )
    
    try:
        # Try to get user from database if available
        if HAS_DB_DRIVER and DB_POOL is not None:
            user_data = await fetch_user_from_db(user_id)
        else:
            # Fallback to mock data
            if user_id not in MOCK_USERS:
                return error_response(
                    message=f"User with ID '{user_id}' not found.",
                    status_code=status.HTTP_404_NOT_FOUND
                )
            user_data = MOCK_USERS[user_id]
        
        if not user_data:
            return error_response(
                message=f"User with ID '{user_id}' not found.",
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        # Cache the result
        if CACHE_MANAGER:
            CACHE_MANAGER.set(cache_key, user_data, ttl=3600)
            
        return success_response(
            data=user_data,
            message="User profile retrieved successfully"
        )
        
    except Exception as e:
        error_msg = f"Error fetching user {user_id}: {str(e)}"
        logger.error(error_msg)
        return error_response(
            message="Failed to retrieve user profile",
            error=error_msg,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

async def create_user_service(user_data: dict, cache: Optional[CacheManager] = None) -> dict:
    """
    Service function to create a new user.
    This can be called directly or from the API endpoint.
    
    Args:
        user_data: Dictionary containing user data
        cache: Optional cache manager instance
        
    Returns:
        dict: Response containing the created user or error details
    """
    try:
        # Create the user in the database
        created_user = await create_user_in_db(user_data)
        
        # Invalidate cache if cache is available
        if cache and 'email_address' in user_data:
            cache.delete(f"users:{user_data['email_address']}")
            
        return {
            "success": True,
            "data": created_user,
            "message": "User created successfully"
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        error_msg = f"Error creating user: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

@app.post(
    "/v1/users",
    status_code=status.HTTP_201_CREATED,
    response_model=UserContract,
    summary="Create a new user"
)
async def create_user_endpoint(
    user_data: UserCreate,
    x_internal_secret: str = Header(..., alias="X-Internal-Secret")
):
    """
    API endpoint to create a new user.
    
    This endpoint is internal and requires the 'X-Internal-Secret' header for access control,
    ensuring only the API Gateway can call it.
    
    Returns 201 with the created user data on success.
    Returns 400 for invalid input data.
    Returns 409 if a user with the email already exists.
    Returns 401 for invalid API secret.
    """
    # Verify the internal secret
    if x_internal_secret != INTERNAL_API_SECRET:
        return error_response(
            message="Unauthorized",
            error="Invalid internal API secret",
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Create the user in the database
        created_user = await create_user_in_db(user_data.dict())
        
        # Invalidate cache if cache is available
        if CACHE_MANAGER and user_data.email_address:
            CACHE_MANAGER.delete(f"users:email:{user_data.email_address}")
        
        return success_response(
            data=created_user,
            message="User created successfully",
            status_code=status.HTTP_201_CREATED
        )
    except HTTPException as he:
        return error_response(
            message=str(he.detail),
            status_code=he.status_code
        )
    except Exception as e:
        error_msg = f"Unexpected error in create_user_endpoint: {str(e)}"
        logger.error(error_msg)
        return error_response(
            message="Failed to create user",
            error=error_msg,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# --- How to run (Local Development) ---
# 1. Install dependencies: pip install fastapi uvicorn pydantic asyncpg
# 2. Run with your Neon URL and a secret:
# 3. Or run in mock mode (no DB required):
#    uvicorn user_service:app --reload