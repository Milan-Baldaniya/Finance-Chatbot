"""
Script to generate and save embeddings for all chunks that don't have one.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.db import get_db
from app.services.embeddings import generate_embeddings

def main():
    print("--- Starting Phase 4: Generating Embeddings ---")
    db = get_db()
    
    # Fetch chunks without embeddings
    response = db.table("document_chunks").select("id, content").is_("embedding", "null").execute()
    chunks = response.data
    
    if not chunks:
        print("✅ No chunks found without embeddings. Everything is up to date!")
        return
        
    print(f"Found {len(chunks)} chunks missing embeddings.")
    
    # Process in batches of 10 to avoid hitting HF API limits
    batch_size = 10
    updated_count = 0
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        texts = [c["content"] for c in batch]
        ids = [c["id"] for c in batch]
        
        print(f"  -> Generating embeddings for batch {i//batch_size + 1}...")
        vectors = generate_embeddings(texts)
        
        if not vectors or len(vectors) != len(batch):
            print("  Warning: Failed to generate proper embeddings for this batch. Stopping.")
            break
            
        # Update chunks in DB
        for chunk_id, vector in zip(ids, vectors):
            db.table("document_chunks").update({
                "embedding": vector
            }).eq("id", chunk_id).execute()
        
        updated_count += len(batch)
        print(f"  -> Saved {updated_count}/{len(chunks)} embeddings.")
        
    print("\n--- Embeddings Complete! ---")

if __name__ == "__main__":
    main()
