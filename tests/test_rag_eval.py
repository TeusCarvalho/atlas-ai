"""Regressão das métricas do benchmark de RAG, sem chamadas externas."""
import json
from pathlib import Path

import pytest
from backend import rag_eval

ROOT = Path(__file__).resolve().parents[1]


def test_cases_are_labeled_and_nonempty():
    cases = json.loads((ROOT / 'evals/rag_cases.json').read_text(encoding='utf-8'))
    assert len(cases) >= 8
    assert len({case['id'] for case in cases}) == len(cases)
    assert any(case['answerable'] for case in cases)
    assert any(not case['answerable'] for case in cases)
    for case in cases:
        assert case['question'] and len(case['question']) > 3
        assert bool(case['expected']) == case['answerable']
        assert all(isinstance(group, list) and group for group in case['expected'])


def test_normalization_handles_accents_and_punctuation():
    assert rag_eval.normalize('Acuracidade!  Wi-Fi.') == 'acuracidade wi fi'
    assert rag_eval.evidence_coverage('assinatura DIGITAL', [['assinatura digital']]) == 1.0


def test_evidence_coverage_requires_all_groups():
    assert rag_eval.evidence_coverage('Nota fiscal e embalagem', [['nota fiscal'], ['protocolo']]) == 0.5
    assert rag_eval.evidence_coverage('contagem semanal', [['semanalmente', 'semanal']]) == 1.0


def test_cosine_and_dimension_safety():
    assert rag_eval.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert rag_eval.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert rag_eval.cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
    with pytest.raises(ValueError):
        rag_eval.cosine_similarity([1.0], [1.0, 0.0])
    with pytest.raises(ValueError):
        rag_eval.cosine_similarity([float('nan')], [1.0])


def test_rank_chunks_threshold_and_order():
    chunks = [{'content': 'relevante'}, {'content': 'irrelevante'}, {'content': 'meio'}]
    vectors = [[1., 0.], [0., 1.], [.5, .5]]
    ranked = rag_eval.rank_chunks([1., 0.], chunks, vectors, top_k=2, threshold=0.3)
    assert [row['content'] for row in ranked] == ['relevante', 'meio']
    assert len(rag_eval.rank_chunks([1., 0.], chunks, vectors, top_k=3, threshold=.95)) == 1


def test_grounded_answer_has_evidence_and_real_citation():
    case = {'id': 'ok', 'question': 'liberacao', 'answerable': True,
            'expected': [['registro da conferência'], ['assinatura digital']]}
    sources = [{'content': 'Registro da conferência e assinatura digital.'}]
    answer = {'resposta': 'Exige registro da conferência e assinatura digital. [Fonte 1]\n\n**Trechos consultados:**\n- [Fonte 1]'}
    row = rag_eval.score_case(case, sources, answer)
    assert row['passed_heuristic']
    assert row['retrieval_evidence_coverage'] == 1.0
    assert row['answer_phrase_coverage'] == 1.0
    assert row['valid_citation_in_body']


def test_appended_source_list_cannot_fake_citation():
    case = {'id': 'citation', 'question': 'Q', 'answerable': True, 'expected': [['assinatura digital']]}
    sources = [{'content': 'assinatura digital'}]
    answer = {'resposta': 'Assinatura digital.\n\n**Trechos consultados:**\n- [Fonte 1]'}
    assert not rag_eval.score_case(case, sources, answer)['passed_heuristic']
    assert not rag_eval.score_case(case, sources, answer)['valid_citation_in_body']


def test_invalid_citation_fails_even_with_matching_facts():
    case = {'id': 'citation', 'question': 'Q', 'answerable': True, 'expected': [['assinatura digital']]}
    sources = [{'content': 'assinatura digital'}]
    assert not rag_eval.score_case(case, sources, {'resposta': 'Assinatura digital [Fonte 99].'})['passed_heuristic']


def test_correct_abstention_and_hallucinated_wifi_password():
    case = {'id': 'wifi', 'question': 'Senha wifi', 'answerable': False, 'expected': []}
    assert rag_eval.score_case(case, [], {'resposta': 'Não há evidência suficiente para responder.'})['passed_heuristic']
    assert not rag_eval.score_case(case, [], {'resposta': 'A senha é admin123.'})['passed_heuristic']


def test_summary_reports_metric_denominators():
    first = rag_eval.score_case({'id': 'a', 'question': 'Q', 'answerable': True, 'expected': [['a']]},
                                [{'content': 'a'}], {'resposta': 'a [Fonte 1]'})
    second = rag_eval.score_case({'id': 'b', 'question': 'Q', 'answerable': False, 'expected': []},
                                 [], {'resposta': 'Não consta nos documentos.'})
    result = rag_eval.summarize([first, second])
    assert result['cases'] == 2 and result['passed'] == 2
    assert result['abstention_rate'] == 1.0 and result['valid_citation_rate'] == 1.0
