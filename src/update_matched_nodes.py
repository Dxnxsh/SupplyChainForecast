# src/update_matched_nodes.py
"""
This script updates existing events in the database with their matched_node values.
"""

import json
import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# --- Configuration ---
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING", "postgresql://postgres:your_password@localhost:5432/supply_chain_db")

def get_db_engine():
    """Establishes and returns a database engine."""
    try:
        engine = create_engine(DB_CONNECTION_STRING)
        with engine.connect() as connection:
            print("✅ Database connection successful.")
        return engine
    except SQLAlchemyError as e:
        print(f"❌ Error connecting to the database: {e}")
        return None

def load_matched_events(filepath="data/processed/matched_events.jsonl"):
    """Load matched events from JSONL file."""
    if not os.path.exists(filepath):
        print(f"❌ Error: Matched events file not found at {filepath}")
        return []
    
    print(f"Loading matched events from {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        events = [json.loads(line) for line in f]
    print(f"✅ Loaded {len(events)} matched events")
    return events

def update_matched_nodes(engine, events):
    """Update the matched_node field for existing events in the database."""
    print(f"\n🔄 Updating matched_node field for {len(events)} events...")
    
    with engine.connect() as connection:
        update_count = 0
        error_count = 0
        
        for i, event in enumerate(events):
            if i % 100 == 0:
                print(f"  Processing event {i+1}/{len(events)}...")
            
            article_url = event.get('article_url')
            matched_node = event.get('matched_node')
            
            if not article_url:
                error_count += 1
                continue
            
            try:
                stmt = text("""
                    UPDATE events 
                    SET matched_node = :matched_node 
                    WHERE article_url = :article_url
                """)
                result = connection.execute(stmt, {
                    "matched_node": matched_node,
                    "article_url": article_url
                })
                
                if result.rowcount > 0:
                    update_count += 1
                    
            except SQLAlchemyError as e:
                print(f"⚠️ Warning: Could not update event {article_url}. Error: {e}")
                error_count += 1
        
        connection.commit()
        print(f"\n✅ Update complete!")
        print(f"  📝 Updated: {update_count} events")
        print(f"  ❌ Errors: {error_count} events")
        
        # Verify the update
        print(f"\n🔍 Verifying update...")
        verify_stmt = text("""
            SELECT 
                matched_node,
                COUNT(*) as count
            FROM events
            GROUP BY matched_node
            ORDER BY count DESC
        """)
        result = connection.execute(verify_stmt)
        
        print(f"\n📊 Events by matched_node in database:")
        for row in result:
            node_name = row[0] if row[0] else "NULL (unmatched)"
            count = row[1]
            print(f"  {node_name}: {count} events")

def main():
    """Main function."""
    engine = get_db_engine()
    if not engine:
        print("Failed to connect to database.")
        return
    
    events = load_matched_events()
    if not events:
        print("No events to process.")
        return
    
    update_matched_nodes(engine, events)

if __name__ == "__main__":
    main()
