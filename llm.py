# llm.py
"""LLM wrapper for Ollama Gemma models.
Streams responses and ensures citations are appended.
"""
import os
import json
from typing import List, Tuple
import ollama
from config import OS_MODEL

def format_passages(passages: List[Tuple[str, str, int, str]]) -> str:
    """Combine passages into a numbered list for prompt.
    Each passage includes content and source metadata.
    """
    formatted = []
    for i, (content, path, idx, section) in enumerate(passages, start=1):
        source = f"{os.path.basename(path)} - {section} (Chunk {idx})"
        formatted.append(f"[Passage {i}] {source}\n{content}\n")
    return "\n".join(formatted)


def build_prompt(question: str, passages: List[Tuple[str, str, int, str]], mode: str, language: str) -> str:
    """Create the final prompt for the model.
    The model is instructed to use ONLY the provided passages.
    """
    passage_text = format_passages(passages)
    instruction = (
        f"You are an offline study assistant. Answer the following question using ONLY the provided passages. "
        f"If the passages do not contain enough information, reply with 'I couldn't find this in your library.' "
        f"Provide the answer in {language}. Include citations after the answer, listing the passage numbers and their source files."
    )
    if mode != "Default":
        instruction += f" Apply the '{mode}' style to the answer."
    prompt = f"{instruction}\n\nPassages:\n{passage_text}\n\nQuestion: {question}\nAnswer:" 
    return prompt


def generate_answer(question: str, passages: List[Tuple[str, str, int, str]], mode: str = "Default", language: str = "English") -> str:
    """Send prompt to Ollama and stream the answer.
    If Ollama is unavailable, return a simple fallback answer using the first passage.
    Returns the answer string (including citations if possible).
    """
    prompt = build_prompt(question, passages, mode, language)
    try:
        response = ollama.generate(model=OS_MODEL, prompt=prompt, stream=True)
        answer_parts = []
        for chunk in response:
            if isinstance(chunk, dict) and "response" in chunk:
                answer_parts.append(chunk["response"])
        return "".join(answer_parts).strip()
    except Exception as e:
        # Fallback handling
        if passages:
            fallback = f"[Fallback answer] {passages[0][0]}"
        else:
            fallback = "No passages available to generate an answer."
        return fallback
