from __future__ import annotations

import math
from collections import Counter


def tokenize(text: str) -> list[str]:
    return [token for token in text.lower().replace(".", " ").replace(",", " ").split() if token]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = tokenize(reference)
    hyp = tokenize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    distances = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        distances[i][0] = i
    for j in range(len(hyp) + 1):
        distances[0][j] = j
    for i, ref_token in enumerate(ref, start=1):
        for j, hyp_token in enumerate(hyp, start=1):
            cost = 0 if ref_token == hyp_token else 1
            distances[i][j] = min(
                distances[i - 1][j] + 1,
                distances[i][j - 1] + 1,
                distances[i - 1][j - 1] + cost,
            )
    return distances[-1][-1] / len(ref)


def corpus_wer(pairs: list[tuple[str, str]]) -> float:
    total_words = 0
    total_errors = 0.0
    for reference, hypothesis in pairs:
        words = len(tokenize(reference))
        total_words += words
        total_errors += word_error_rate(reference, hypothesis) * words
    return total_errors / total_words if total_words else 0.0


def sentence_gleu(source_or_candidate: str, references: list[str], max_order: int = 4) -> float:
    candidate = tokenize(source_or_candidate)
    if not candidate or not references:
        return 0.0
    reference_tokens = [tokenize(reference) for reference in references]
    precisions: list[float] = []
    for order in range(1, max_order + 1):
        candidate_ngrams = _ngram_counts(candidate, order)
        if not candidate_ngrams:
            continue
        max_ref_counts: Counter[tuple[str, ...]] = Counter()
        for ref in reference_tokens:
            max_ref_counts |= _ngram_counts(ref, order)
        overlap = sum(min(count, max_ref_counts[ngram]) for ngram, count in candidate_ngrams.items())
        precisions.append(overlap / sum(candidate_ngrams.values()))
    if not precisions:
        return 0.0
    closest_ref_len = min((len(ref) for ref in reference_tokens), key=lambda length: abs(length - len(candidate)))
    brevity = 1.0 if len(candidate) > closest_ref_len else math.exp(1 - closest_ref_len / len(candidate))
    return brevity * math.exp(sum(math.log(max(precision, 1e-9)) for precision in precisions) / len(precisions))


def corpus_gleu(items: list[tuple[str, list[str]]]) -> float:
    if not items:
        return 0.0
    return sum(sentence_gleu(candidate, references) for candidate, references in items) / len(items)


def pearson_correlation(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denominator_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    denominator = denominator_x * denominator_y
    return numerator / denominator if denominator else 0.0


def mean_absolute_error(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or not xs:
        return 0.0
    return sum(abs(x - y) for x, y in zip(xs, ys, strict=True)) / len(xs)


def _ngram_counts(tokens: list[str], order: int) -> Counter[tuple[str, ...]]:
    return Counter(tuple(tokens[index : index + order]) for index in range(len(tokens) - order + 1))
