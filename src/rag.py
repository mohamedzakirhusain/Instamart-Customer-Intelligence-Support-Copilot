"""Part D library (tasks 1-3): chunking, TF-IDF retrieval and grounded answering over the policy documents."""
import glob
import os
import sys

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, ".")
import mock_llm  # noqa: E402

POLICY_DIR = os.path.join("data", "policies")
CHUNK_WORDS, OVERLAP = 40, 10


def chunk_words(words, size=CHUNK_WORDS, overlap=OVERLAP):
    """Chunks of `size` words, each starting size-overlap words after the previous one.
    Stops after the first chunk whose end reaches or passes the last word."""
    step, start, out = size - overlap, 0, []
    while True:
        out.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
        start += step
    return out


def build_chunks(size=CHUNK_WORDS, overlap=OVERLAP):
    chunks = []
    for path in sorted(glob.glob(os.path.join(POLICY_DIR, "*.txt"))):
        with open(path, encoding="utf-8") as f:
            words = f.read().split()
        for text in chunk_words(words, size, overlap):
            chunks.append({"source": os.path.basename(path), "text": text})
    return chunks


class Index:
    """TF-IDF index over policy chunks."""

    def __init__(self, size=CHUNK_WORDS, overlap=OVERLAP):
        self.chunks = build_chunks(size, overlap)
        self.vectorizer = TfidfVectorizer()
        self.matrix = self.vectorizer.fit_transform([c["text"] for c in self.chunks])

    def retrieve(self, query, k=3):
        sims = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        top = sims.argsort()[::-1][:k]
        return [{"source": self.chunks[i]["source"], "score": round(float(sims[i]), 4),
                 "text": self.chunks[i]["text"]} for i in top]


INDEX = Index()


def retrieve(query, k=3):
    return INDEX.retrieve(query, k)


SYSTEM = ("You are a POLICY ASSISTANT for the support desk. Answer only from the supplied CONTEXT. "
          "If the answer is not in the context, say that you could not find the information in the policy documents.")


def answer(question, index=None):
    index = index or INDEX
    hits = index.retrieve(question, 3)
    context = "\n".join(f"[{h['source']}]\n{h['text']}" for h in hits)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"CONTEXT:\n{context}\nQUESTION:\n{question}"}]
    text = mock_llm.chat(messages).choices[0].message.content
    return text, [h["source"] for h in hits]
