import type { ConclusionReview } from '../../utils/conclusionReview';

function EvidenceFields({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="px-muted">Not available</span>;
  if (Array.isArray(value)) return <ul>{value.map((item, index) => <li key={index}><EvidenceFields value={item} /></li>)}</ul>;
  if (typeof value === 'object') return <dl>{Object.entries(value as Record<string, unknown>).map(([key, item]) =>
    <div key={key} style={{ margin: '6px 0' }}><dt style={{ fontWeight: 600 }}>{key.replace(/_/g, ' ')}</dt><dd style={{ margin: '2px 0 0 12px', overflowWrap: 'anywhere' }}><EvidenceFields value={item} /></dd></div>)}</dl>;
  return <span>{String(value)}</span>;
}

export default function ConclusionCardView({ review }: { review: ConclusionReview }) {
  const acceptable = review.verdict === 'accepted';
  return <details className="px-conclusion" aria-label="Conclusion review" style={{ margin: '12px 0' }}>
    <summary style={{ cursor: 'pointer' }}>
      <span className={'px-tag ' + (acceptable ? 'is-ok' : 'is-warn')}>Conclusion: {review.verdict}</span>
      <span style={{ marginLeft: 8 }}>{review.notPassedCount} checks need review</span>
    </summary>
    <div style={{ padding: '8px 12px', maxHeight: 560, overflow: 'auto' }}>
      {typeof review.card.text_label === 'string' && <p><strong>{review.card.text_label}</strong></p>}
      <EvidenceFields value={review.card} />
    </div>
  </details>;
}
