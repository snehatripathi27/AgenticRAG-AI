"""Metrics receive prediction and reference; model backends never receive references."""

import re
import string
from collections import Counter
from decimal import Decimal, InvalidOperation
from importlib.metadata import entry_points


def normalize(text: str) -> str:
    return " ".join(text.lower().translate(str.maketrans("", "", string.punctuation)).split())


def exact_match(prediction: str, reference: str) -> float:
    return float(normalize(prediction) == normalize(reference))


def choice_accuracy(prediction: str, reference: str) -> float:
    match = re.match(r"^\s*(?:answer\s*:\s*)?\(?([A-Z])(?:\b|[).:])", prediction, re.IGNORECASE)
    return float(bool(match) and match[1].upper() == reference.upper())


def numeric_match(prediction: str, reference: str) -> float:
    def number(text):
        matches = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text.replace(",", ""))
        return Decimal(matches[-1]) if matches else None

    try:
        actual, expected = number(prediction), number(reference)
        return float(actual is not None and expected is not None and actual == expected)
    except InvalidOperation:
        return 0.0


def token_f1(prediction: str, reference: str) -> float:
    p, r = normalize(prediction).split(), normalize(reference).split()
    if not p or not r:
        return float(p == r)
    overlap = sum((Counter(p) & Counter(r)).values())
    return 2 * overlap / (len(p) + len(r))


def metrics():
    registry = {
        "exact_match": exact_match,
        "choice_accuracy": choice_accuracy,
        "numeric_match": numeric_match,
        "token_f1": token_f1,
    }
    for entry in entry_points(group="benchlab.metrics"):
        if entry.name in registry:
            raise ValueError(f"Duplicate metric: {entry.name}")
        registry[entry.name] = entry.load()
    return registry
