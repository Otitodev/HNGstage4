"""
Initialize the database schema for email notifications logging
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def init_database():
    """Create the email_notifications_log table and related objects"""
    
    db_url = os.getenv('NEON_DATABASE_URL')
    
    if not db_url:
        print("❌ NEON_DATABASE_URL not found in environment variables")
        return False
    
    try:
        # Connect to database
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        print("✓ Connected to database")
        
        # Read and execute schema
        schema_path = os.path.join(os.path.dirname(__file__), 'db_schema.sql')
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        cursor.execute(schema_sql)
        conn.commit()
        
        print("✓ Database schema created successfully")
        
        # Verify table was created
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_name = 'email_notifications_log'
        """)
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            print("✓ email_notifications_log table verified")
            
            # Show table structure
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'email_notifications_log'
                ORDER BY ordinal_position
            """)
            
            print("\n📋 Table Structure:")
            for row in cursor.fetchall():
                print(f"  - {row[0]}: {row[1]}")
        
        cursor.close()
        conn.close()
        
        print("\n✅ Database initialization complete!")
        return True
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Email Notifications Database Initialization")
    print("=" * 60)
    print()
    
    init_database()
