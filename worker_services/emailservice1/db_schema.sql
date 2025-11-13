-- Email Notifications Log Table
-- Tracks all email notifications sent through the system for analytics and debugging

CREATE TABLE IF NOT EXISTS email_notifications_log (
    id SERIAL PRIMARY KEY,
    notification_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    recipient_email VARCHAR(255) NOT NULL,
    subject TEXT NOT NULL,
    template_key VARCHAR(100),
    status VARCHAR(50) NOT NULL, -- 'pending', 'sent', 'failed', 'retrying'
    sendgrid_message_id VARCHAR(255),
    sendgrid_status_code INTEGER,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB, -- Store additional data like language, template_key, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    failed_at TIMESTAMP
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_email_log_notification_id ON email_notifications_log(notification_id);
CREATE INDEX IF NOT EXISTS idx_email_log_user_id ON email_notifications_log(user_id);
CREATE INDEX IF NOT EXISTS idx_email_log_status ON email_notifications_log(status);
CREATE INDEX IF NOT EXISTS idx_email_log_created_at ON email_notifications_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_log_recipient ON email_notifications_log(recipient_email);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_email_log_updated_at ON email_notifications_log;
CREATE TRIGGER update_email_log_updated_at
    BEFORE UPDATE ON email_notifications_log
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- View for analytics: Email delivery statistics
CREATE OR REPLACE VIEW email_delivery_stats AS
SELECT 
    DATE(created_at) as date,
    status,
    COUNT(*) as count,
    COUNT(DISTINCT user_id) as unique_users,
    AVG(retry_count) as avg_retries
FROM email_notifications_log
GROUP BY DATE(created_at), status
ORDER BY date DESC, status;

-- View for failed emails analysis
CREATE OR REPLACE VIEW failed_emails_analysis AS
SELECT 
    recipient_email,
    template_key,
    error_message,
    COUNT(*) as failure_count,
    MAX(failed_at) as last_failure,
    AVG(retry_count) as avg_retries
FROM email_notifications_log
WHERE status = 'failed'
GROUP BY recipient_email, template_key, error_message
ORDER BY failure_count DESC;

COMMENT ON TABLE email_notifications_log IS 'Logs all email notifications for tracking, analytics, and debugging';
COMMENT ON COLUMN email_notifications_log.notification_id IS 'Unique identifier for the notification';
COMMENT ON COLUMN email_notifications_log.status IS 'Current status: pending, sent, failed, retrying';
COMMENT ON COLUMN email_notifications_log.metadata IS 'Additional data stored as JSON (language, custom fields, etc.)';
