# test_offline_scholar.py
"""Simple test script for OfflineScholar.
Indexes sample files, asks two questions, prints answers.
"""
import os
import json
from ingest import scan_library
from search import bm25_search
from llm import generate_answer

def main():
    # Ensure library is indexed
    print("Scanning library...")
    scan_library()
    # First question – should be found in sample1.txt (physics, mathematics)
    q1 = "What subjects are mentioned in sample1.txt?"
    passages = bm25_search(q1, top_k=4)
    ans1 = generate_answer(q1, passages, mode="Explain simply", language="English")
    print("\nQuestion 1:", q1)
    print("Answer 1:\n", ans1)
    # Second question – not in library
    q2 = "What is the capital of France?"
    passages = bm25_search(q2, top_k=4)
    ans2 = generate_answer(q2, passages, mode="Explain simply", language="English")
    print("\nQuestion 2:", q2)
    print("Answer 2:\n", ans2)

if __name__ == "__main__":
    main()
