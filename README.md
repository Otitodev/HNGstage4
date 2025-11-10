# Template Service

A FastAPI-based microservice for managing and rendering notification templates with support for both plain text and HTML content.

## Features

- Create and manage email/notification templates
- Render templates with dynamic data
- Support for both plain text and HTML content
- Built-in mock mode for development and testing
- PostgreSQL database integration with connection pooling
- Comprehensive error handling and validation

## Prerequisites

- Python 3.8+
- PostgreSQL (optional, mock mode available)
- pip (Python package manager)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd template-service
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file in the root directory with the following variables:
   ```
   INTERNAL_API_SECRET=your-secret-key
   NEON_DATABASE_URL=postgresql://user:password@localhost:5432/yourdb
   ```

## Running the Service

### Development Mode (with Mock Database)
```bash
uvicorn template_service:app --reload
```

### Production Mode
```bash
uvicorn template_service:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### 1. Create a New Template

**Endpoint:** `POST /v1/templates`

**Headers:**
- `X-Internal-Secret`: Your secret key

**Request Body:**
```json
{
    "template_key": "TEMPLATE_KEY",
    "subject": "Your subject with {variable}",
    "body": "Hello {name}, this is a plain text template.",
    "html_body": "<h1>Hello {name}</h1><p>This is an HTML template.</p>"
}
```

**Response:**
```json
{
    "message": "Template 'TEMPLATE_KEY' created successfully."
}
```

### 2. Render a Template

**Endpoint:** `POST /v1/templates/render`

**Headers:**
- `X-Internal-Secret`: Your secret key

**Request Body:**
```json
{
    "template_key": "TEMPLATE_KEY",
    "message_data": {
        "name": "John",
        "variable": "value"
    }
}
```

**Response:**
```json
{
    "subject": "Your subject with value",
    "body": "Hello John, this is a plain text template.",
    "html_body": "<h1>Hello John</h1><p>This is an HTML template.</p>"
}
```

## Available Templates

The service comes with the following pre-defined templates:

### 1. Order Confirmation
- **Key:** `ORDER_CONFIRMATION`
- **Description:** Sent when a customer places an order
- **Variables:**
  - `{order_id}` - The order ID
  - `{customer_name}` - Customer's name
  - `{tracking_link}` - Link to track the order

### 2. Password Reset
- **Key:** `PASSWORD_RESET`
- **Description:** Sent when a user requests a password reset
- **Variables:**
  - `{app_name}` - Your application name
  - `{customer_name}` - Customer's name
  - `{reset_link}` - Password reset link

### 3. Shipping Update
- **Key:** `SHIPPING_UPDATE`
- **Description:** Sent when there's an update to an order's shipping status
- **Variables:**
  - `{order_id}` - The order ID
  - `{carrier}` - Shipping carrier name
  - `{tracking_number}` - Tracking number
  - `{tracking_link}` - Link to track the package

### 4. Invoice Paid
- **Key:** `INVOICE_PAID`
- **Description:** Sent when an invoice is paid
- **Variables:**
  - `{invoice_id}` - The invoice ID
  - `{amount}` - Amount paid
  - `{receipt_link}` - Link to download the receipt

### 5. Welcome New User
- **Key:** `WELCOME_NEW_USER`
- **Description:** Sent to new users after signup
- **Variables:**
  - `{app_name}` - Your application name
  - `{customer_name}` - New user's name
  - `{profile_link}` - Link to complete profile

### 6. Weekly Digest
- **Key:** `WEEKLY_DIGEST`
- **Description:** Weekly summary of user activity
- **Variables:**
  - `{app_name}` - Your application name
  - `{new_updates}` - Number of new updates
  - `{digest_link}` - Link to view full digest

### 7. Account Locked
- **Key:** `ACCOUNT_LOCKED`
- **Description:** Sent when an account is locked for security reasons
- **Variables:**
  - `{app_name}` - Your application name
  - `{reason}` - Reason for account lock
  - `{support_number}` - Support contact number

### 8. Promotion - Flash Sale
- **Key:** `PROMOTION_FLASH_SALE`
- **Description:** Promotional email for flash sales
- **Variables:**
  - `{discount_percent}` - Discount percentage
  - `{promo_code}` - Promo code to use
  - `{sale_link}` - Link to the sale

### 9. Support Ticket Update
- **Key:** `SUPPORT_TICKET_UPDATE`
- **Description:** Notification about support ticket updates
- **Variables:**
  - `{ticket_id}` - Support ticket ID
  - `{customer_name}` - Customer's name
  - `{status}` - Current status of the ticket
  - `{ticket_link}` - Link to view the ticket

### 10. Low Stock Alert
- **Key:** `LOW_STOCK_ALERT`
- **Description:** Notification about low stock levels
- **Variables:**
  - `{product_name}` - Name of the product
  - `{stock_count}` - Remaining stock count
  - `{product_link}` - Link to the product page

## Error Handling

The API returns appropriate HTTP status codes along with JSON error messages:

- `200 OK`: Request was successful
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid API key
- `404 Not Found`: Template not found
- `409 Conflict`: Template with the same key already exists
- `500 Internal Server Error`: Server error

## Testing

Run the test suite with:

```bash
pytest test_template_service.py -v
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
