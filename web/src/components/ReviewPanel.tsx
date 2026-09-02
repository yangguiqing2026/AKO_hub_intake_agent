import type { ReviewRecord } from "../schemas/ws";

interface Props {
  review: ReviewRecord;
  threshold: number;
  onConfirmHuman: () => void;
  onConfirmed: boolean;
}

export function ReviewPanel({ review, threshold, onConfirmHuman, onConfirmed }: Props): JSX.Element | null {
  if (review.review_score >= threshold) return null;
  return (
    <div style={{ border: "1px solid var(--c-review)", borderRadius: "var(--radius)", padding: 12, marginTop: 12, background: "var(--c-card)" }}>
      <h3 style={{ marginTop: 0, color: "var(--c-review)" }}>需人工确认（评审分 {review.review_score.toFixed(2)} &lt; {threshold}）</h3>
      {review.differences.length > 0 && (
        <ul style={{ fontSize: 13 }}>{review.differences.map((d, i) => <li key={i}>{d}</li>)}</ul>
      )}
      {onConfirmed ? <p style={{ fontSize: 13, color: "var(--c-success)" }}>已确认，请继续投递。</p> : (
        <button onClick={onConfirmHuman}>人工确认通过</button>
      )}
    </div>
  );
}
