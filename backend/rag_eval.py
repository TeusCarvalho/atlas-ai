"""Avaliação local e heurística de respostas do Deep Research.

Métricas transparentes de presença textual, evidência, citação e abstenção.
Não representa juiz semântico, pgvector real nem garantia contra alucinações.
"""
from __future__ import annotations

from math import isfinite, sqrt
import re
import unicodedata

ABSTENTION_MARKERS = (
    'nao ha', 'nao foi informad', 'nao consta', 'nao encontrei',
    'nao e informad', 'nao aparece', 'nao menciona', 'nao e mencionad',
    'nao esta disponivel', 'nao possui', 'nao contem', 'nao existe',
    'sem evidencia', 'evidencia insuficiente', 'informacao insuficiente',
    'nao e possivel determinar', 'nao posso determinar',
    'nao pode ser determinado', 'nao sei com base',
)


def normalize(text: str) -> str:
    raw = unicodedata.normalize('NFKD', str(text))
    clean = ''.join(char for char in raw if not unicodedata.combining(char))
    return ' '.join(re.sub(r'[^\w]+', ' ', clean.casefold()).split())


def evidence_coverage(text: str, required_groups: list[list[str]]) -> float:
    if not required_groups:
        return 1.0
    normalized = normalize(text)
    found = sum(any(normalize(phrase) in normalized for phrase in group)
                for group in required_groups)
    return round(found / len(required_groups), 4)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError('Dimensões incompatíveis nos embeddings.')
    if not all(isfinite(x) for x in left + right):
        raise ValueError('Embedding contém valor não finito.')
    a = sqrt(sum(x * x for x in left))
    b = sqrt(sum(x * x for x in right))
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(left, right)) / (a * b)


def rank_chunks(question_vector: list[float], chunks: list[dict],
                vectors: list[list[float]], top_k: int = 3,
                threshold: float = 0.28) -> list[dict]:
    if len(chunks) != len(vectors) or not 1 <= top_k <= 8:
        raise ValueError('Corpus ou top_k inválido.')
    ranked = sorted(
        ({**chunk, 'similarity': round(cosine_similarity(question_vector, vector), 4)}
         for chunk, vector in zip(chunks, vectors)),
        key=lambda item: item['similarity'], reverse=True,
    )
    return [item for item in ranked if item['similarity'] >= threshold][:top_k]


def score_case(case: dict, sources: list[dict], response: dict) -> dict:
    # Exclui a lista automática de fontes: somente citações escritas pelo LLM contam.
    body = str(response.get('resposta') or '').split('\n\n**Trechos consultados:**')[0]
    expected = case.get('expected', [])
    answerable = bool(case['answerable'])
    citations = [int(n) for n in re.findall(r'\[Fonte\s+(\d+)\]', body, re.I)]
    citations_valid = bool(citations) and all(1 <= n <= len(sources) for n in citations)
    retrieved_text = '\n'.join(str(source.get('content', '')) for source in sources)
    retrieval_coverage = evidence_coverage(retrieved_text, expected) if answerable else None
    answer_coverage = evidence_coverage(body, expected) if answerable else None
    abstained = any(marker in normalize(body) for marker in ABSTENTION_MARKERS)
    passed = (
        (retrieval_coverage == 1.0 and answer_coverage >= 0.75 and citations_valid and not abstained)
        if answerable else abstained
    )
    return {
        'id': case['id'], 'question': case['question'],
        'expected_behavior': 'answer_with_evidence' if answerable else 'abstain',
        'retrieval_evidence_coverage': retrieval_coverage,
        'answer_phrase_coverage': answer_coverage,
        'valid_citation_in_body': citations_valid if answerable else None,
        'abstained_heuristic': abstained,
        'passed_heuristic': bool(passed),
        'retrieved_chunks': len(sources),
        'answer': body,
        'sources': [{'similarity': s.get('similarity'), 'section': s.get('section')}
                    for s in sources],
    }


def summarize(rows: list[dict]) -> dict:
    answerable = [row for row in rows if row['expected_behavior'] == 'answer_with_evidence']
    unknown = [row for row in rows if row['expected_behavior'] == 'abstain']

    def average(key, group):
        return round(sum((row[key] or 0) for row in group) / len(group), 4) if group else None

    return {
        'cases': len(rows),
        'passed': sum(bool(row['passed_heuristic']) for row in rows),
        'retrieval_evidence_coverage_mean': average('retrieval_evidence_coverage', answerable),
        'answer_phrase_coverage_mean': average('answer_phrase_coverage', answerable),
        'valid_citation_rate': (
            round(sum(bool(row['valid_citation_in_body']) for row in answerable) / len(answerable), 4)
            if answerable else None
        ),
        'abstention_rate': (
            round(sum(bool(row['abstained_heuristic']) for row in unknown) / len(unknown), 4)
            if unknown else None
        ),
    }
