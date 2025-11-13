# Template Service - Available Templates & Variables

This document provides a comprehensive reference for all notification templates available in the Template Service, including their variables and usage examples.

---

## Template Overview

The Template Service currently supports **10 pre-configured templates** for common notification scenarios. Each template includes:
- **Subject**: Email/notification subject line
- **Body**: Plain text message body
- **HTML Body**: Rich HTML formatted message body

---

## Available Templates

### 1. ORDER_CONFIRMATION

**Purpose**: Confirm customer orders and provide tracking information

**Template Key**: `ORDER_CONFIRMATION`

**Variables**:
- `{customer_name}` - Customer's name
- `{order_id}` - Unique order identifier
- `{tracking_link}` - URL to track the package

**Example Usage**:
```json
{
  "template_key": "ORDER_CONFIRMATION",
  "message_data": {
    "customer_name": "John Doe",
    "order_id": "ORD-12345",
    "tracking_link": "https://example.com/track/ORD-12345"
  }
}
```

**Rendered Output**:
- Subject: `Your Order ORD-12345 is Confirmed!`
- Body: `Hi John Doe, Thanks for your purchase. Order ORD-12345 is confirmed and on its way. Track it here: https://example.com/track/ORD-12345`

---

### 2. PASSWORD_RESET

**Purpose**: Send password reset instructions to users

**Template Key**: `PASSWORD_RESET`

**Variables**:
- `{customer_name}` - User's name
- `{app_name}` - Application/service name
- `{reset_link}` - Secure password reset URL

**Example Usage**:
```json
{
  "template_key": "PASSWORD_RESET",
  "message_data": {
    "customer_name": "Jane Smith",
    "app_name": "MyApp",
    "reset_link": "https://example.com/reset/token123"
  }
}
```

**Rendered Output**:
- Subject: `Reset Your Password for MyApp`
- Body: `Hello Jane Smith, Click this link: https://example.com/reset/token123 to securely reset your password.`

---

### 3. SHIPPING_UPDATE

**Purpose**: Notify customers about package delivery status

**Template Key**: `SHIPPING_UPDATE`

**Variables**:
- `{order_id}` - Order identifier
- `{carrier}` - Shipping carrier name
- `{tracking_number}` - Carrier tracking number
- `{tracking_link}` - URL to track the package

**Example Usage**:
```json
{
  "template_key": "SHIPPING_UPDATE",
  "message_data": {
    "order_id": "ORD-67890",
    "carrier": "FedEx",
    "tracking_number": "1234567890",
    "tracking_link": "https://fedex.com/track/1234567890"
  }
}
```

**Rendered Output**:
- Subject: `📦 Your package for Order ORD-67890 is out for delivery!`
- Body: `Your item is scheduled for delivery today. Carrier: FedEx, Tracking: 1234567890. View details: https://fedex.com/track/1234567890`

---

### 4. INVOICE_PAID

**Purpose**: Confirm payment receipt and provide receipt access

**Template Key**: `INVOICE_PAID`

**Variables**:
- `{invoice_id}` - Invoice identifier
- `{amount}` - Payment amount (e.g., "$99.99")
- `{receipt_link}` - URL to download receipt

**Example Usage**:
```json
{
  "template_key": "INVOICE_PAID",
  "message_data": {
    "invoice_id": "INV-2024-001",
    "amount": "$149.99",
    "receipt_link": "https://example.com/receipts/INV-2024-001"
  }
}
```

**Rendered Output**:
- Subject: `Thank you! Invoice INV-2024-001 has been paid.`
- Body: `This confirms we have received your payment of $149.99. Receipt: https://example.com/receipts/INV-2024-001`

---

### 5. WELCOME_NEW_USER

**Purpose**: Welcome new users and guide them to complete their profile

**Template Key**: `WELCOME_NEW_USER`

**Variables**:
- `{customer_name}` - New user's name
- `{app_name}` - Application/service name
- `{profile_link}` - URL to complete profile setup

**Example Usage**:
```json
{
  "template_key": "WELCOME_NEW_USER",
  "message_data": {
    "customer_name": "Alex Johnson",
    "app_name": "MyPlatform",
    "profile_link": "https://example.com/profile/setup"
  }
}
```

**Rendered Output**:
- Subject: `Welcome to MyPlatform!`
- Body: `Thank you for signing up, Alex Johnson! Complete your profile here: https://example.com/profile/setup`

---

### 6. WEEKLY_DIGEST

**Purpose**: Send weekly activity summaries to users

**Template Key**: `WEEKLY_DIGEST`

**Variables**:
- `{app_name}` - Application/service name
- `{new_updates}` - Number of new items/updates
- `{digest_link}` - URL to view full digest

**Example Usage**:
```json
{
  "template_key": "WEEKLY_DIGEST",
  "message_data": {
    "app_name": "MyApp",
    "new_updates": "15",
    "digest_link": "https://example.com/digest/week-45"
  }
}
```

**Rendered Output**:
- Subject: `Your Weekly MyApp Digest: 15 new items!`
- Body: `Check out your latest activity and updates for this week. See summary: https://example.com/digest/week-45`

---

### 7. ACCOUNT_LOCKED

**Purpose**: Alert users about account security issues

**Template Key**: `ACCOUNT_LOCKED`

**Variables**:
- `{app_name}` - Application/service name
- `{reason}` - Reason for account lock (e.g., "suspicious activity")
- `{support_number}` - Support contact number

**Example Usage**:
```json
{
  "template_key": "ACCOUNT_LOCKED",
  "message_data": {
    "app_name": "SecureApp",
    "reason": "multiple failed login attempts",
    "support_number": "1-800-SUPPORT"
  }
}
```

**Rendered Output**:
- Subject: `⚠️ Urgent: Your SecureApp account is temporarily locked.`
- Body: `For security, we've locked your account due to multiple failed login attempts. Contact support immediately: 1-800-SUPPORT`

---

### 8. PROMOTION_FLASH_SALE

**Purpose**: Announce limited-time promotional offers

**Template Key**: `PROMOTION_FLASH_SALE`

**Variables**:
- `{discount_percent}` - Discount percentage (e.g., "50%")
- `{promo_code}` - Promotional code to use at checkout
- `{sale_link}` - URL to shop the sale

**Example Usage**:
```json
{
  "template_key": "PROMOTION_FLASH_SALE",
  "message_data": {
    "discount_percent": "30%",
    "promo_code": "FLASH30",
    "sale_link": "https://example.com/sale"
  }
}
```

**Rendered Output**:
- Subject: `⚡ FLASH SALE! Get 30% Off Today Only!`
- Body: `Don't miss our limited time offer! Use code FLASH30 at checkout. Shop now: https://example.com/sale`

---

### 9. SUPPORT_TICKET_UPDATE

**Purpose**: Notify users about support ticket status changes

**Template Key**: `SUPPORT_TICKET_UPDATE`

**Variables**:
- `{customer_name}` - Customer's name
- `{ticket_id}` - Support ticket identifier
- `{status}` - Current ticket status (e.g., "In Progress", "Resolved")
- `{ticket_link}` - URL to view ticket details

**Example Usage**:
```json
{
  "template_key": "SUPPORT_TICKET_UPDATE",
  "message_data": {
    "customer_name": "Sarah Williams",
    "ticket_id": "TKT-9876",
    "status": "Resolved",
    "ticket_link": "https://example.com/support/TKT-9876"
  }
}
```

**Rendered Output**:
- Subject: `Update on your support ticket #TKT-9876`
- Body: `Hello Sarah Williams, Ticket #TKT-9876 has been updated. Status: Resolved. View details: https://example.com/support/TKT-9876`

---

### 10. LOW_STOCK_ALERT

**Purpose**: Alert customers about low inventory on items they're interested in

**Template Key**: `LOW_STOCK_ALERT`

**Variables**:
- `{product_name}` - Name of the product
- `{stock_count}` - Remaining inventory count
- `{product_link}` - URL to purchase the product

**Example Usage**:
```json
{
  "template_key": "LOW_STOCK_ALERT",
  "message_data": {
    "product_name": "Wireless Headphones Pro",
    "stock_count": "3",
    "product_link": "https://example.com/products/headphones-pro"
  }
}
```

**Rendered Output**:
- Subject: `Low Stock Alert for Wireless Headphones Pro!`
- Body: `The item you viewed, Wireless Headphones Pro, is running low on stock (3 remaining). Purchase soon: https://example.com/products/headphones-pro`

---

## API Usage

### Rendering a Template

**Endpoint**: `POST /v1/templates/render`

**Headers**:
```
X-Internal-Secret: <your-internal-api-secret>
Content-Type: application/json
```

**Request Body**:
```json
{
  "template_key": "ORDER_CONFIRMATION",
  "message_data": {
    "customer_name": "John Doe",
    "order_id": "ORD-12345",
    "tracking_link": "https://example.com/track/ORD-12345"
  }
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Template rendered successfully",
  "data": {
    "subject": "Your Order ORD-12345 is Confirmed!",
    "body": "Hi John Doe,\n\nThanks for your purchase. Order ORD-12345 is confirmed and on its way. Track it here: https://example.com/track/ORD-12345",
    "html_body": "<html><body><h1>Order Confirmed!</h1><p>Hi <b>John Doe</b>, your order <code>ORD-12345</code> is confirmed.</p><p><a href='https://example.com/track/ORD-12345'>Track your package</a></p></body></html>"
  }
}
```

### Creating a New Template

**Endpoint**: `POST /v1/templates`

**Headers**:
```
X-Internal-Secret: <your-internal-api-secret>
Content-Type: application/json
```

**Request Body**:
```json
{
  "template_key": "CUSTOM_TEMPLATE",
  "subject": "Custom Subject with {variable}",
  "body": "Custom body text with {variable}",
  "html_body": "<html><body><p>Custom HTML with {variable}</p></body></html>"
}
```

**Response** (201 Created):
```json
{
  "success": true,
  "message": "Template 'CUSTOM_TEMPLATE' created successfully.",
  "data": {
    "template_key": "CUSTOM_TEMPLATE"
  }
}
```

---

## Variable Naming Conventions

When creating custom templates or using existing ones:

1. **Use descriptive names**: `{customer_name}` instead of `{name}`
2. **Use snake_case**: `{order_id}` instead of `{orderId}`
3. **Be specific**: `{tracking_link}` instead of `{link}`
4. **Include units when relevant**: `{discount_percent}` should include the "%" symbol in the data

---

## Error Handling

### Missing Variables

If a required variable is not provided in `message_data`, the API will return:

```json
{
  "success": false,
  "message": "Failed to render template",
  "error": "Missing data key 'customer_name' required to render template."
}
```

### Template Not Found

If the specified `template_key` doesn't exist:

```json
{
  "success": false,
  "message": "Template 'INVALID_KEY' not found.",
  "error": null
}
```

---

## Caching

Templates are cached in Redis with a 1-hour TTL (Time To Live) to improve performance. The cache is automatically invalidated when:
- A new template is created
- A template is updated (future feature)

---

## Best Practices

1. **Always provide all required variables** - Check the template documentation before rendering
2. **Format data appropriately** - Include currency symbols, percentages, etc. in your data
3. **Use meaningful URLs** - Ensure all links are valid and properly formatted
4. **Test templates** - Render templates with sample data before using in production
5. **Keep HTML simple** - Use basic HTML tags for maximum email client compatibility

---

## Support

For questions or issues with templates, contact the platform team or refer to the main [Template Service Documentation](TEMPLATE_SERVICE.md).
