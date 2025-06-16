from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """Manages text embeddings for scraped content"""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        logger.info(f"Initialized embedding model: {model_name}")

    def create_embeddings(self, text: str, chunk_size: int = 512) -> List[Dict[str, Any]]:
        """Create embeddings for text, chunking if necessary"""
        try:
            # Split text into chunks if too long
            chunks = self._chunk_text(text, chunk_size)

            embeddings = []
            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 10:  # Skip very short chunks
                    continue

                # Generate embedding
                embedding_vector = self.model.encode(chunk)

                embeddings.append({
                    'model': self.model_name,
                    'vector': embedding_vector.tolist(),  # Convert numpy to list for JSON storage
                    'chunk_index': i,
                    'text': chunk,
                    'created_at': datetime.utcnow().isoformat()
                })

            logger.info(f"Created {len(embeddings)} embeddings for text of length {len(text)}")
            return embeddings

        except Exception as e:
            logger.error(f"Error creating embeddings: {e}")
            return []

    def _chunk_text(self, text: str, chunk_size: int) -> List[str]:
        """Split text into chunks of approximately chunk_size characters"""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        sentences = text.split('. ')

        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 2 <= chunk_size:  # +2 for '. '
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "

        # Add the last chunk
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def search_similar_text(self, query: str, candidate_texts: List[str],
                            top_k: int = 5) -> List[Dict[str, Any]]:
        """Find most similar texts to query"""
        try:
            query_embedding = self.model.encode(query)
            candidate_embeddings = self.model.encode(candidate_texts)

            # Calculate cosine similarities
            similarities = []
            for i, candidate_embedding in enumerate(candidate_embeddings):
                cosine_sim = np.dot(query_embedding, candidate_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(candidate_embedding)
                )

                similarities.append({
                    'index': i,
                    'text': candidate_texts[i],
                    'similarity': float(cosine_sim)
                })

            # Sort by similarity and return top_k
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            return similarities[:top_k]

        except Exception as e:
            logger.error(f"Error in similarity search: {e}")
            return []

    def embed_query(self, query: str) -> List[float]:
        """Create embedding for a single query"""
        try:
            embedding = self.model.encode(query)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error embedding query: {e}")
            return []
