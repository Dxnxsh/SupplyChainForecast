import os
import sys
from pathlib import Path
import modal
from dotenv import load_dotenv

# Load local environment variables at the module level
load_dotenv()
db_conn = os.getenv("DB_CONNECTION_STRING")
skip_nominatim = os.getenv("SKIP_NOMINATIM", "0")

# Define the Modal App
app = modal.App("supply-chain-ingest-pipeline")

# Create a container image with all local dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc")  # Required for compiling some postgres/psycopg2 drivers
    .pip_install(
        "numpy==1.26.4",
        "pandas==2.3.3",
        "scipy==1.16.2",
        "scikit-learn",
        "xgboost>=2.0.0",
        "torch==2.6.0",
        "transformers==4.57.0",
        "gliner2",
        "spacy==3.7.4",
        "psycopg2-binary==2.9.10",
        "SQLAlchemy==2.0.44",
        "geopy==2.4.1",
        "geonamescache==3.0.1",
        "tqdm==4.67.1",
        "python-dotenv==1.1.1",
        "langdetect",
        "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
    )
    .add_local_dir(
        local_path=str(Path(__file__).resolve().parent.parent),
        remote_path="/root/project",
        ignore=lambda p: any(x in str(p) for x in ["venv311", ".git", "__pycache__", ".pytest_cache"])
    )
)

@app.function(
    image=image,
    gpu="A100",      # Can be "A10G", "RTX4090", or "A100"
    secrets=[modal.Secret.from_dict({
        "DB_CONNECTION_STRING": db_conn or "",
        "SKIP_NOMINATIM": skip_nominatim
    })],
    env={
        "NER_BATCH_SIZE": "256",
        "FINBERT_BATCH_SIZE": "256"
    },
    timeout=86400    # Allow up to 24 hours execution
)
def run_modal_ingestion(directory: str, limit: int | None = None):
    # Set the working directory to the mounted project root
    os.chdir("/root/project")
    sys.path.insert(0, "/root/project")
    
    # Import and run the pipeline
    from src.json_ingest import run_json_ingest
    
    print("🚀 Starting serverless GPU pipeline on Modal...")
    
    # Define absolute paths inside the container mount
    legacy_model_path = "/root/project/model_training/classifier.pkl"
    disruption_model_path = "/root/project/model_training/disruption_classifier.pkl"
    impact_model_path = "/root/project/model_training/impact_regressor_v2.pkl"
    raw_dir = f"/root/project/{directory}"
    
    # Execute the pipeline on the Modal serverless container
    n = run_json_ingest(
        raw_dir,
        legacy_model_path=legacy_model_path,
        disruption_model_path=disruption_model_path,
        impact_model_path=impact_model_path,
        limit=limit,
        skip_db=False,
        skip_temporal=False,
        regenerate_forecasts=True,
        reprocess_all=False
    )
    
    print(f"✅ Ingestion complete. Processed {n} articles serverless.")

@app.local_entrypoint()
def main(directory: str = "data/raw/combined", limit: int = 500):
    if not db_conn:
        print("❌ Error: DB_CONNECTION_STRING is not set in your local .env file.")
        return
        
    # Treat 0 or negative values as no limit
    actual_limit = None if limit <= 0 else limit
    limit_str = "No Limit" if actual_limit is None else f"limit={actual_limit}"
    
    print(f"📡 Launching ingestion for '{directory}' ({limit_str}) on Modal...")
    run_modal_ingestion.remote(directory=directory, limit=actual_limit)
