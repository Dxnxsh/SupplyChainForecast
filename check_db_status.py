import sys
import os
from sqlalchemy import text
sys.path.append(os.getcwd())
from src.main import engine

def check_db():
    if not engine:
        print("Database engine not initialized.")
        return
    
    with engine.connect() as conn:
        try:
            # Check number of events
            res = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
            print(f"Total events in DB: {res}")
            
            # Check if temporal_info exists and is populated
            res = conn.execute(text("SELECT COUNT(*) FROM events WHERE temporal_info IS NOT NULL")).scalar()
            print(f"Events with temporal_info: {res}")
            
            # Check if ml_risk_label exists and is populated
            res = conn.execute(text("SELECT COUNT(*) FROM events WHERE ml_risk_label IS NOT NULL")).scalar()
            print(f"Events with ml_risk_label: {res}")
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
