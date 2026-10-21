"""Short replies from a small Hugging Face model.

The weights stay unloaded until a summary or a question is requested. The
default is a 4-bit Qwen 1.5B instruct model from Hugging Face (MLX), which
stays near a gigabyte on disk and runs on Apple silicon. Install it with
``uv sync --extra summarize``. Override the model with GLIMPSE_SUMMARY_MODEL.

A summary is kept only when it stays inside the wording of the result. An
answer is kept only when every number in it already appears in the result or
the question, and it does not give medical advice.
"""
import os
import re
import threading

MODEL_ID = os.environ.get(
    "GLIMPSE_SUMMARY_MODEL", "mlx-community/Qwen2.5-1.5B-Instruct-4bit")
_MAX_NEW = 80
_MAX_ANSWER = 120
_SYSTEM = (
    "Copy two sentences from the result exactly, including the chance "
    "and any smallest change. Do not change any words or numbers."
)
_ASK = (
    "Answer in one or two short sentences, quoting the result. "
    "If the result does not say, answer exactly: The result does not say. "
    "Do not give a diagnosis, treatment, or medical advice. Do not invent numbers."
)
_REFUSAL = "That can’t be answered from the numbers on this page."
_ADVICE = (
    "medication", "medicine", "insulin", "prescribe", "prescription",
    "treatment", "diagnose", "diagnosis", "doctor", "physician",
)
_WORDS = re.compile(r"[a-z0-9%]+")
_NUMS = re.compile(r"\d+(?:\.\d+)?")
_STOP = {
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "with", "from",
    "that", "this", "these", "those", "is", "are", "was", "be", "by", "as", "at",
    "it", "its", "you", "your", "they", "their", "than", "then", "into", "over",
    "also", "both", "same", "not", "no", "so", "if", "but", "about", "would",
}
_lock = threading.RLock()
_bundle = None


def summarize(text, question=""):
    """Return ``{"summary", "model"}``. ``model`` is null when the draft was dropped.

    With no question, copy a short summary of ``text``. With a question, answer
    it from ``text``.
    """
    text = " ".join(str(text).split())
    if len(text) > 1800:
        text = text[:1800].rsplit(" ", 1)[0]
    question = " ".join(str(question or "").split())
    draft = _two_sentences(_generate(text, question))
    if question:
        if not _answer_ok(draft, text, question):
            return {"summary": _REFUSAL, "model": None}
        return {"summary": draft, "model": MODEL_ID}
    if not _usable(draft, text):
        return {"summary": text, "model": None}
    return {"summary": draft, "model": MODEL_ID}


def _generate(text, question=""):
    model, tokenizer = _load()
    if question:
        system, user, limit = _ASK, f"Result:\n{text}\n\nQuestion: {question}", _MAX_ANSWER
    else:
        system, user, limit = _SYSTEM, text, _MAX_NEW
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True)
    from mlx_lm import generate
    with _lock:
        return generate(
            model, tokenizer, prompt=prompt, max_tokens=limit, verbose=False)


def _load():
    global _bundle
    with _lock:
        if _bundle is not None:
            return _bundle
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        try:
            from mlx_lm import load
        except ImportError as exc:
            raise RuntimeError(
                "The summary model is not installed. From the project folder run: "
                "uv sync --extra summarize"
            ) from exc
        _bundle = load(MODEL_ID)
        return _bundle


def _answer_ok(answer, source, question):
    """True when an answer stays with the result and does not add advice."""
    if not answer or len(answer) < 12:
        return False
    allowed = set(_NUMS.findall(source)) | set(_NUMS.findall(question))
    if not set(_NUMS.findall(answer)) <= allowed:
        return False
    low, src = answer.lower(), source.lower()
    if "does not say" in low:
        return True
    if any(word in low and word not in src for word in _ADVICE):
        return False
    return len(_content(answer) & _content(source)) >= 1


def _usable(summary, source):
    """True when the draft stays inside the facts it was given."""
    if not summary or len(summary) < 40:
        return False
    if not set(_NUMS.findall(summary)) <= set(_NUMS.findall(source)):
        return False
    extra = _content(summary) - _content(source)
    return len(extra) <= 2


def _content(text):
    return {w for w in _WORDS.findall(text.lower()) if len(w) > 3 and w not in _STOP}


def _two_sentences(text):
    text = " ".join(str(text).split())
    kept, buf = [], []
    for word in text.split(" "):
        if not word:
            continue
        buf.append(word)
        # A short label such as "You." should not use up one of the two sentences.
        if word[-1] in ".!?" and len(" ".join(buf)) > 20:
            kept.append(" ".join(buf))
            buf = []
            if len(kept) == 2:
                break
    if not kept:
        return text[:500].strip()
    return " ".join(kept)
