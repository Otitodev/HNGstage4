import os
import logging
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from fastapi import FastAPI, HTTPException, status, Header
from pydantic import BaseModel, Field
from redis_client import get_redis_client
from utils.response_formatter import success_response, error_response

# --- PYTHON-DOTENV IMPORT AND LOAD ---
try:
    # Requires: pip install python-dotenv
    from dotenv import load_dotenv
    # Load environment variables from .env file (if it exists)
    load_dotenv()
    print("INFO: .env file loaded successfully.")
except ImportError:
    print("WARNING: 'python-dotenv' not installed. Environment variables will only be sourced from the OS environment.")
# --- END DOTENV ---

# Conditional import for the asynchronous PostgreSQL driver
try:
    # Requires: pip install asyncpg
    import asyncpg
    HAS_DB_DRIVER = True
except ImportError:
    HAS_DB_DRIVER = False
    print("WARNING: 'asyncpg' not installed. Running in mock mode only.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

import asyncio
from contextlib import asynccontextmanager

# --- Global State & Configuration ---
DB_POOL: Optional[asyncpg.Pool] = None
DB_INIT_LOCK = asyncio.Lock()

# Environment Variables (now sourced from .env first, then OS environment)
NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL", "postgresql://user:pass@host/db")
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "super-secret-dev-key")

# Flag to determine if we run in mock mode
IS_MOCK_MODE = not HAS_DB_DRIVER or "postgresql://user:pass@host/db" in NEON_DATABASE_URL or "test" in os.environ.get("PYTEST_CURRENT_TEST", "")

# Mock templates storage (for testing and when DB is not available)
MOCK_TEMPLATES: Dict[str, Dict[str, str]] = {}


# --- 1. Define the Template Contracts using Pydantic Models ---

class TemplateContent(BaseModel):
    """
    The base contract for raw template content (used internally by the service).
    """
    subject: str = Field(..., description="The template string for the notification subject.")
    body: str = Field(..., description="The plain text template string for the notification body.")
    html_body: str = Field(..., description="The HTML template string for the rich email body.")

class TemplateCreate(BaseModel):
    """
    The input contract for creating a new template.
    """
    template_key: str = Field(..., description="The unique key for the new template (e.g., 'NEW_PROMO').")
    subject: str = Field(..., description="The template string for the notification subject.")
    body: str = Field(..., description="The plain text template string for the notification body.")
    html_body: str = Field(..., description="The HTML template string for the rich email body.")

class RenderRequest(BaseModel):
    """
    The input contract for the rendering endpoint.
    """
    template_key: str = Field(..., description="The unique key of the template to be rendered.")
    message_data: Dict[str, Any] = Field(..., description="Key-value pairs containing data to substitute into the template placeholders.")

class RenderedContract(BaseModel):
    """
    The response contract for the rendered output (final content ready for delivery).
    """
    subject: str = Field(..., description="The final, interpolated subject line.")
    body: str = Field(..., description="The final, interpolated plain text body.")
    html_body: str = Field(..., description="The final, interpolated HTML body.")


# --- 2. Mock Template Storage (10 Common Templates for DB Population) ---

# This dictionary is used to populate the database on first run or serve as the mock data source.
MOCK_TEMPLATES: Dict[str, Dict[str, str]] = {
    "ORDER_CONFIRMATION": {
        "subject": "Your Order {order_id} is Confirmed!",
        "body": "Hi {customer_name},\n\nThanks for your purchase. Order {order_id} is confirmed and on its way. Track it here: {tracking_link}",
        "html_body": "<html><body><h1>Order Confirmed!</h1><p>Hi <b>{customer_name}</b>, your order <code>{order_id}</code> is confirmed.</p><p><a href='{tracking_link}'>Track your package</a></p></body></html>"
    },
    "PASSWORD_RESET": {
        "subject": "Reset Your Password for {app_name}",
        "body": "Hello {customer_name},\n\nClick this link: {reset_link} to securely reset your password.",
        "html_body": "<html><body><p>Hello {customer_name},</p><p>Please click the button below to reset your password:</p><p><a href='{reset_link}' style='padding: 10px; background-color: #4A90E2; color: white; text-decoration: none;'>Reset Password</a></p></body></html>"
    },
    "SHIPPING_UPDATE": {
        "subject": "📦 Your package for Order {order_id} is out for delivery!",
        "body": "Your item is scheduled for delivery today. Carrier: {carrier}, Tracking: {tracking_number}. View details: {tracking_link}",
        "html_body": "<html><body><h2>Out for Delivery!</h2><p>Your item is scheduled for delivery today. Track it: <a href='{tracking_link}'>{tracking_number}</a></p></body></html>"
    },
    "INVOICE_PAID": {
        "subject": "Thank you! Invoice {invoice_id} has been paid.",
        "body": "This confirms we have received your payment of {amount}. Receipt: {receipt_link}",
        "html_body": "<html><body><h2>Payment Received</h2><p>Your invoice {invoice_id} has been successfully paid. Amount: <b>{amount}</b>.</p><p><a href='{receipt_link}'>Download Receipt</a></p></body></html>"
    },
    "WELCOME_NEW_USER": {
        "subject": "Welcome to {app_name}!",
        "body": "Thank you for signing up, {customer_name}! Complete your profile here: {profile_link}",
        "html_body": "<html><body><h2>Welcome, {customer_name}!</h2><p>Your journey starts now. Complete your profile to get started: <a href='{profile_link}'>Profile Setup</a></p></body></html>"
    },
    "WEEKLY_DIGEST": {
        "subject": "Your Weekly {app_name} Digest: {new_updates} new items!",
        "body": "Check out your latest activity and updates for this week. See summary: {digest_link}",
        "html_body": "<html><body><h3>Weekly Summary</h3><p>You have {new_updates} new items this week. <a href='{digest_link}'>View Digest</a></p></body></html>"
    },
    "ACCOUNT_LOCKED": {
        "subject": "⚠️ Urgent: Your {app_name} account is temporarily locked.",
        "body": "For security, we've locked your account due to {reason}. Contact support immediately: {support_number}",
        "html_body": "<html><body><h2 style='color: red;'>Account Locked</h2><p>Your account has been locked. Please call support at {support_number} immediately.</p></body></html>"
    },
    "PROMOTION_FLASH_SALE": {
        "subject": "⚡ FLASH SALE! Get {discount_percent} Off Today Only!",
        "body": "Don't miss our limited time offer! Use code {promo_code} at checkout. Shop now: {sale_link}",
        "html_body": "<html><body><h1 style='color: orange;'>Flash Sale!</h1><p>Use code <b>{promo_code}</b> for {discount_percent} off.</p><a href='{sale_link}'>Shop Now</a></body></html>"
    },
    "SUPPORT_TICKET_UPDATE": {
        "subject": "Update on your support ticket #{ticket_id}",
        "body": "Hello {customer_name}, Ticket #{ticket_id} has been updated. Status: {status}. View details: {ticket_link}",
        "html_body": "<html><body><p>Ticket #{ticket_id} updated. Status: <b>{status}</b>.</p><p><a href='{ticket_link}'>View Ticket</a></p></body></html>"
    },
    "LOW_STOCK_ALERT": {
        "subject": "Low Stock Alert for {product_name}!",
        "body": "The item you viewed, {product_name}, is running low on stock ({stock_count} remaining). Purchase soon: {product_link}",
        "html_body": "<html><body><p>Only <b>{stock_count}</b> left of {product_name}!</p><p><a href='{product_link}'>Buy Now</a></p></body></html>"
    }
}


# --- Database Initialization and Operations ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global DB_POOL
    if HAS_DB_DRIVER and not IS_MOCK_MODE:
        DB_POOL = await asyncpg.create_pool(NEON_DATABASE_URL)
        logger.info("Database connection pool initialized.")
    
    yield
    
    # Shutdown
    if DB_POOL:
        await DB_POOL.close()
        DB_POOL = None
        logger.info("Database connection pool closed.")

async def fetch_template_from_db(template_key: str) -> Dict[str, str]:
    """
    Fetches raw template content from Redis cache, Neon database, or mock data.
    Implements a cache-aside pattern with Redis.
    Raises HTTPException 404 if template is not found.
    """
    # Check Redis cache first
    redis = get_redis_client()
    cache_key = f"template:{template_key}"
    
    try:
        # Try to get from cache
        cached_template = await redis.get(cache_key)
        if cached_template:
            logger.info(f"Cache hit for template: {template_key}")
            return json.loads(cached_template)
    except Exception as e:
        logger.warning(f"Redis cache error (will continue to DB): {e}")
    
    # Check mock data if in mock mode or if we have mock data available
    if IS_MOCK_MODE or template_key in MOCK_TEMPLATES:
        logger.info(f"Using mock data for template key: {template_key}")
        if template_key in MOCK_TEMPLATES:
            template = MOCK_TEMPLATES[template_key]
            # Cache the template for future use (1 hour TTL)
            try:
                await redis.set(cache_key, json.dumps(template), ex=3600)
            except Exception as e:
                logger.warning(f"Failed to cache template {template_key}: {e}")
            return template
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_key}' not found."
        )

    # Real DB Logic
    select_query = """
        SELECT subject, body, html_body
        FROM templates 
        WHERE template_key = $1;
    """
    
    try:
        pool = await get_db_pool()
        if not pool:
            # If we can't get a pool, check mock data one more time
            if template_key in MOCK_TEMPLATES:
                return MOCK_TEMPLATES[template_key]
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{template_key}' not found."
            )

        async with pool.acquire() as conn:
            record = await conn.fetchrow(select_query, template_key)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Template '{template_key}' not found."
                )
            
            template = dict(record)
            # Cache the template for future use (1 hour TTL)
            try:
                await redis.set(cache_key, json.dumps(template), ex=3600)
            except Exception as e:
                logger.warning(f"Failed to cache template {template_key}: {e}")
                
            return template
            
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions (like 404)
        raise http_exc
    except asyncpg.exceptions.PostgresError as e:
        logger.error(f"PostgreSQL query failed for template {template_key}: {e}")
        # In case of database error, check mock data one more time
        if template_key in MOCK_TEMPLATES:
            logger.warning(f"Falling back to mock data for {template_key} due to database error")
            return MOCK_TEMPLATES[template_key]
            
        # If we get here, the template doesn't exist in mock data either
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_key}' not found."
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred during DB fetch: {e}")
        # Last chance to check mock data
        if template_key in MOCK_TEMPLATES:
            logger.warning(f"Falling back to mock data for {template_key} due to error: {e}")
            return MOCK_TEMPLATES[template_key]
            
        # If we get here, the template doesn't exist in mock data either
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_key}' not found."
        )


async def add_template_to_db(template_key: str, data: Dict[str, str]):
    """
    Adds a new template to the database or mock storage.
    Invalidates the Redis cache for this template.
    Raises HTTPException 409 if the key already exists.
    """
    # Invalidate cache for this template
    redis = get_redis_client()
    cache_key = f"template:{template_key}"
    try:
        await redis.delete(cache_key)
    except Exception as e:
        logger.warning(f"Failed to invalidate cache for {template_key}: {e}")
    if IS_MOCK_MODE:
        if template_key in MOCK_TEMPLATES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Template key '{template_key}' already exists in mock storage."
            )
        MOCK_TEMPLATES[template_key] = data
        logger.info(f"Added new template '{template_key}' to mock storage.")
        return

    # Real DB Logic
    insert_query = """
        INSERT INTO templates 
        (template_key, subject, body, html_body) 
        VALUES ($1, $2, $3, $4) 
        ON CONFLICT (template_key) 
        DO NOTHING 
        RETURNING template_key; 
    """
    
    try:
        pool = await get_db_pool()
        if not pool:
            raise Exception("Database pool is not available.")

        async with pool.acquire() as conn:
            # If result is None, the ON CONFLICT DO NOTHING clause was triggered (key existed).
            result = await conn.fetchrow(
                insert_query, 
                template_key, 
                data['subject'], 
                data['body'], 
                data['html_body']
            )

            if result is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Template key '{template_key}' already exists."
                )
                
        logger.info(f"Added new template '{template_key}' to the database.")

    except asyncpg.exceptions.UniqueViolationError:
        # Handle race condition where template was just added
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template key '{template_key}' already exists."
        )
    except asyncpg.exceptions.PostgresError as e:
        logger.error(f"PostgreSQL insert failed for template {template_key}: {e}")
        # Fall back to mock storage if DB insert fails
        MOCK_TEMPLATES[template_key] = data
        logger.warning(f"Falling back to mock storage for template {template_key} due to database error")
    except HTTPException:
        # Re-raise HTTP exceptions (like 409 Conflict)
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during DB insert: {e}")
        # Fall back to mock storage on unexpected errors
        MOCK_TEMPLATES[template_key] = data
        logger.warning(f"Falling back to mock storage for template {template_key} due to error: {e}")


# --- Helper Function for Template Interpolation ---

def render_content(template: str, data: Dict[str, Any]) -> str:
    """
    Safely interpolates template placeholders using string.format().
    """
    try:
        return template.format(**data)
    except KeyError as e:
        logger.error(f"Missing data key {e} required for template rendering.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing data key {e} required to render template."
        )


# --- 3. FastAPI Application Setup ---

app = FastAPI(
    title="Template Service",
    description="Microservice for managing and rendering notification templates.",
    version="1.0.0",
    lifespan=lifespan
)

# For backward compatibility with tests
async def get_db_pool() -> asyncpg.Pool:
    """Get or create a database pool"""
    global DB_POOL
    
    if IS_MOCK_MODE:
        return None
        
    if DB_POOL is None:
        async with DB_INIT_LOCK:
            if DB_POOL is None:  # Double-checked locking pattern
                try:
                    DB_POOL = await asyncpg.create_pool(
                        dsn=NEON_DATABASE_URL,
                        min_size=1,
                        max_size=10,
                        command_timeout=60
                    )
                    logger.info("Database connection pool created")
                except Exception as e:
                    logger.error(f"Failed to create database pool: {e}")
                    raise
    return DB_POOL

async def initialize_db():
    """Initialize the database (for testing)"""
    if IS_MOCK_MODE:
        return
        
    try:
        pool = await get_db_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS templates (
                        template_key TEXT PRIMARY KEY,
                        subject TEXT NOT NULL,
                        body TEXT NOT NULL,
                        html_body TEXT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
                logger.info("Database tables verified/created")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def shutdown_event():
    """Shutdown the database (for testing)"""
    global DB_POOL
    if DB_POOL:
        try:
            await DB_POOL.close()
            logger.info("Database connection pool closed")
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")
        finally:
            DB_POOL = None



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
                    conn = await pool.acquire()
                    try:
                        # Execute a simple query to verify database connection
                        result = await conn.fetchval("SELECT 1")
                        if result != 1:
                            raise ValueError("Unexpected database response")
                        health_status["services"]["postgresql"] = "connected"
                    finally:
                        await pool.release(conn)
                else:
                    health_status["services"]["postgresql"] = "disconnected"
                    health_status["status"] = "degraded"
            except Exception as db_error:
                logger.error(f"Database health check failed: {str(db_error)}")
                health_status["services"]["postgresql"] = "unavailable"
                health_status["status"] = "degraded"
        else:
            health_status["services"]["postgresql"] = "mock_mode"
            
        # Check Redis connection
        try:
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
            return error_response(
                message="Service unavailable",
                error="One or more dependencies are unavailable",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
            
        return success_response(
            data=health_status,
            message="Service is running and all dependencies are accessible"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return error_response(
            message="Failed to perform health check",
            error=str(e),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.post(
    "/v1/templates/render", 
    response_model=RenderedContract,
    status_code=status.HTTP_200_OK,
    summary="Render a Notification Template with Payload (Internal Auth Required)"
)
async def render_template_with_payload(
    request: RenderRequest,
    x_internal_secret: str = Header(..., alias="X-Internal-Secret") 
):
    """
    Retrieves the template from the cache or database, renders the final 
    subject, body, and HTML body, and returns the finished content.
    """
    # Verify service-to-service authentication
    if x_internal_secret != INTERNAL_API_SECRET:
        return error_response(
            message="Unauthorized",
            error="Invalid or missing internal API secret",
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    # Get the template (will raise 404 if not found)
    # The fetch_template_from_db function now includes Redis caching
    try:
        template = await fetch_template_from_db(request.template_key)
        
        # Render each part of the template with the provided data
        rendered_subject = render_content(template["subject"], request.message_data)
        rendered_body = render_content(template["body"], request.message_data)
        rendered_html = render_content(template["html_body"], request.message_data)
        
        rendered_content = {
            "subject": rendered_subject,
            "body": rendered_body,
            "html_body": rendered_html
        }
        
        return success_response(
            data=rendered_content,
            message="Template rendered successfully"
        )
        
    except HTTPException as he:
        # Re-raise HTTP exceptions (like 404) with our standard format
        return error_response(
            message=he.detail,
            status_code=he.status_code
        )
    except Exception as e:
        error_msg = f"Error rendering template {request.template_key}: {str(e)}"
        logger.error(error_msg)
        return error_response(
            message="Failed to render template",
            error=error_msg,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@app.post(
    "/v1/templates", 
    status_code=status.HTTP_201_CREATED,
    summary="Create a New Notification Template (Internal Auth Required)"
)
async def create_template(
    request: TemplateCreate,
    x_internal_secret: str = Header(..., alias="X-Internal-Secret") 
):
    """
    Adds a brand new notification template (subject, body, html_body) 
    to the system's content management database. 
    Requires service-to-service authorization.
    
    Raises 409 Conflict if the template_key already exists.
    """
    # Verify service-to-service authentication
    if x_internal_secret != INTERNAL_API_SECRET:
        return error_response(
            message="Unauthorized",
            error="Invalid or missing internal API secret",
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Convert the Pydantic model to a dict for storage
        template_data = {
            "subject": request.subject,
            "body": request.body,
            "html_body": request.html_body
        }
        
        # Check if template already exists
        try:
            existing = await fetch_template_from_db(request.template_key)
            if existing:
                return error_response(
                    message="Template already exists",
                    error=f"Template with key '{request.template_key}' already exists.",
                    status_code=status.HTTP_409_CONFLICT
                )
        except HTTPException as e:
            if e.status_code != status.HTTP_404_NOT_FOUND:
                return error_response(
                    message=e.detail,
                    status_code=e.status_code
                )
        
        # Add to database or mock storage
        await add_template_to_db(request.template_key, template_data)
        
        # Invalidate cache for this template
        redis = get_redis_client()
        cache_key = f"template:{request.template_key}"
        try:
            await redis.delete(cache_key)
        except Exception as e:
            logger.warning(f"Failed to invalidate cache for {request.template_key}: {e}")
        
        return success_response(
            data={"template_key": request.template_key},
            message=f"Template '{request.template_key}' created successfully.",
            status_code=status.HTTP_201_CREATED
        )
        
    except HTTPException as he:
        # Convert HTTP exceptions to our standard format
        return error_response(
            message=he.detail,
            status_code=he.status_code
        )
    except Exception as e:
        error_msg = f"Error creating template {request.template_key}: {str(e)}"
        logger.error(error_msg)
        return error_response(
            message="Failed to create template",
            error=error_msg,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    await add_template_to_db(request.template_key, template_data)
    
    return {"message": f"Template '{request.template_key}' created successfully."}