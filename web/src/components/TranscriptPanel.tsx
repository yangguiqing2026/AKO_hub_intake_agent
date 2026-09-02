export function TranscriptPanel({ lines }: { lines: string[] }): JSX.Element | null {
  if (lines.length === 0) return null;
  return (
    <div style={{ marginTop: 16 }}>
      <h4>澄清记录（可追溯，US-005）</h4>
      {lines.map((line, i) => (
        <p key={i} style={{ fontSize: 13, borderBottom: "1px solid var(--c-border)", padding: 4, margin: 0 }}>{line}</p>
      ))}
    </div>
  );
}
