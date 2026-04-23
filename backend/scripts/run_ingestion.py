"""
CLI script to trigger PDF ingestion manually.
Run from backend folder: python scripts/run_ingestion.py
"""

import sys
import os
import glob

# Add the 'backend' dir to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models.document import register_document, save_chunks
from app.services.ingestion import ingest_pdf
from pypdf import PdfReader
from app.services.embeddings import generate_embeddings

def main():
    print("--- Starting Bulk PDF Ingestion ---")
    
    # Create docs folder if it doesn't exist
    docs_dir = os.path.join(os.path.dirname(__file__), '..', 'docs')
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)
        print(f"Created '{docs_dir}' directory. Please place PDFs here and re-run.")
        return

    # Find all PDFs in the docs folder
    pdf_files = glob.glob(os.path.join(docs_dir, '*.pdf'))
    if not pdf_files:
        print(f"No PDFs found in the 'backend/docs' directory. Add some PDFs and run again.")
        return
    
    from app.core.db import get_db
    db = get_db()
    
    for path in pdf_files:
        filename = os.path.basename(path)
        title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")
        
        # Check if already ingested
        existing = db.table("documents").select("id").eq("filename", filename).limit(1).execute()
        if existing.data:
            print(f"\nSkipping '{title}': Already in database.")
            continue
            
        print(f"\nProcessing '{title}'...")
        
        # Get page count
        try:
            reader = PdfReader(path)
            page_count = len(reader.pages)
        except Exception as e:
            print(f"  -> Error reading PDF: {e}")
            continue
            
        # 1. Register Document
        doc_id = register_document(title=title, filename=filename, page_count=page_count)
        
        # 2. Extract and Chunk
        chunks = ingest_pdf(path, doc_id)
        print(f"  -> Extracted {len(chunks)} chunks.")
        
        # 3. Generate Embeddings for chunks
        texts = [chunk["content"] for chunk in chunks if chunk.get("content")]
        embeddings = generate_embeddings(texts)
        if embeddings and len(embeddings) == len(texts):
            for chunk, embedding in zip(chunks, embeddings):
                chunk["embedding"] = embedding
            # 4. Save Chunks
            save_chunks(doc_id, chunks)
            print(f"  -> Successfully embedded and saved {len(chunks)} chunks.")
        else:
            print("  -> Failed to generate embeddings.")
            # Rollback
            db.table("documents").delete().eq("id", doc_id).execute()

    print("\n--- Bulk Ingestion Complete! ---")

if __name__ == "__main__":
    main()
