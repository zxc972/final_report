"""Review source scope for the second independent annotation packet.

Only completes quotations or narrows claims to their cited text. Reads no
canonicalizer predictions and assigns no condition labels. Original cards,
model responses and extraction freezes remain available for audit.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.knowledge import prepare_condition_test_cards_v2 as cards
from tools.knowledge import run_condition_canonicalization as base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    out = Path(parser.parse_args().out)
    review = out / 'source_review'
    originals = review / 'original_cards'
    cards.METHODS = list(cards.METHODS) + list(cards.BACKUP_METHODS)
    all_cards = {}
    for method in cards.METHODS:
        filename = method['method_id'] + '.json'
        original = originals / filename
        assert original.is_file(), original
        all_cards[method['method_id']] = json.loads(original.read_text(encoding='utf-8'))
    packet = out / 'claude_annotation_packet'
    original_packet = review / 'original_combined_packet'
    if not original_packet.exists():
        shutil.copytree(packet, original_packet)
    selected = json.loads((review / 'selected_statement_changes.json').read_text(encoding='utf-8'))
    other = json.loads((review / 'non_annotation_changes.json').read_text(encoding='utf-8'))
    changes = []
    for patch in selected + other:
        claims = all_cards[patch['method']][patch['field']]
        candidates = [(n, c) for n, c in enumerate(claims, 1)
                      if c['statement'] == patch['old_statement'] and c['quote'] == patch['old_quote']]
        assert len(candidates) == 1, patch
        index, claim = candidates[0]
        before = dict(claim)
        for key in ('statement', 'quote'):
            if patch.get(key) is not None:
                claim[key] = patch[key]
        text = (out / 'sources' / (claim['source_id'] + '.txt')).read_text(encoding='utf-8')
        assert 8 <= len(claim['quote']) <= 250 and claim['quote'] in text
        assert len(claim['statement']) <= 220
        start = text.index(claim['quote'])
        claim['source_span'] = {'start': start, 'end': start + len(claim['quote']),
                                'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
        changes.append({'method': patch['method'], 'field': patch['field'], 'index': index,
                        'annotation_id_before_review': patch.get('annotation_id'),
                        'before': before, 'after': dict(claim), 'reason': patch['reason']})
    screened = 0
    quarantine_count = 0
    for method in cards.METHODS:
        card = all_cards[method['method_id']]
        quarantined = list(card.get('quarantined_claims', []))
        texts = {sid: (out / 'sources' / (sid + '.txt')).read_text(encoding='utf-8')
                 for sid in method['sources']}
        card, retained, rejected = cards.validate_card(card, method, texts)
        assert not rejected, (method['method_id'], rejected)
        assert all(len(c['statement']) <= 220 for c in retained)
        for field in cards.FIELDS:
            for claim in card[field]:
                span = claim['source_span']
                text = texts[claim['source_id']]
                assert text[span['start']:span['end']] == claim['quote']
                assert hashlib.sha256(text.encode('utf-8')).hexdigest() == span['text_sha256']
        card['quarantined_claims'] = quarantined
        card['evidence_status'] = 'exact_quotes_verified_agent_scope_reviewed_blind_gold_pending'
        screened += len(retained)
        quarantine_count += len(quarantined)
        base.save_json(out / 'method_extractions' / (method['method_id'] + '.json'), card)
    audit = {
        'reviewer': 'Codex source-scope check; not expert gold annotation',
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
        'screened_statements': screened, 'annotation_fields': cards.ANNOTATION_FIELDS,
        'changed_items': len(changes), 'edits': changes,
        'quarantined_claims_preserved': quarantine_count,
        'source_documents_modified': False,
        'extraction_prompt_schema_model_settings_changed': False,
        'algorithm_outputs_read': False, 'gold_labels_created': False,
        'source_ambiguities': [{'annotation_ids': [2032, 2033],
            'source_id': 'fs_surf2surf',
            'note': 'Official paint-output path descriptions differ between the BUG ALERT and paint-path paragraph. Both source claims are retained for blind annotation; no expert resolution is asserted.'}],
    }
    base.save_json(review / 'review_audit.json', audit)
    cards.prepare_annotation(out)
    provenance = []
    for record in json.loads((out / 'source_manifest_combined.json').read_text(encoding='utf-8')):
        sid = record['source_id']
        original = out / 'sources' / (sid + '.txt')
        text = original.read_text(encoding='utf-8')
        canonical = text.encode('utf-8')
        target = packet / 'sources' / original.name
        target.write_bytes(canonical)
        provenance.append({'source_id': sid, 'url': record['url'],
                           'original_source_bytes_sha256': base.sha256(original),
                           'packet_utf8_lf_sha256': hashlib.sha256(canonical).hexdigest(),
                           'span_convention': 'Unicode code-point offsets in UTF-8 LF source text',
                           'normalization': 'CRLF/CR to LF only; no content edits'})
    base.save_json(packet / 'source_provenance.json', provenance)
    base.save_json(packet / 'source_ambiguities.json', audit['source_ambiguities'])
    readme = packet / 'README.md'
    with readme.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write('\n原文范围核对已完成；引文均为来源文本的连续原文。sources 使用 UTF-8 LF，偏移以 Unicode 字符计；原始字节摘要见 source_provenance.json。\n官方原文的歧义见 source_ambiguities.json，请保留歧义记录，不据此猜测算法输出。\n')
    rows = json.loads((packet / 'statements_unlabelled.json').read_text(encoding='utf-8'))['items']
    for row in rows:
        text = (packet / 'sources' / (row['source_id'] + '.txt')).read_bytes().decode('utf-8')
        span = row['source_span']
        assert text[span['start']:span['end']] == row['quote']
        assert hashlib.sha256(text.encode()).hexdigest() == span['text_sha256']
        assert not any(key.startswith('gold') for key in row)
    hashes = {p.relative_to(packet).as_posix(): base.sha256(p) for p in sorted(packet.rglob('*'))
              if p.is_file() and p.name != 'HANDOFF_MANIFEST.json'}
    manifest = {'status': 'ready_for_Claude_not_transmitted_by_a_Claude_tool',
                'files': hashes, 'n_statements': len(rows),
                'fields': dict(Counter(r['field'] for r in rows)),
                'algorithm_predictions_included': False, 'gold_labels_included': False,
                'algorithm_evaluation_calls': 0, 'source_scope_review_completed': True}
    base.save_json(packet / 'HANDOFF_MANIFEST.json', manifest)
    base.save_json(review / 'frozen.json', {
        'script_sha256': base.sha256(__file__),
        'review_audit_sha256': base.sha256(review / 'review_audit.json'),
        'handoff_manifest_sha256': base.sha256(packet / 'HANDOFF_MANIFEST.json'),
        'reviewed_at_utc': audit['reviewed_at_utc'], 'annotation_frozen': False,
        'freeze_type': 'source_cards_only', 'retained_claims': screened,
        'annotation_statements': len(rows), 'quarantined': quarantine_count,
        'fields': manifest['fields']})
    print(json.dumps({'screened': screened, 'changed': len(changes),
                     'annotation_statements': len(rows), 'quarantined': quarantine_count,
                     'fields': manifest['fields']}, ensure_ascii=False))


if __name__ == '__main__':
    main()