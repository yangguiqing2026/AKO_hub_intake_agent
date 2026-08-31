interface Props {
  wo: Record<string, unknown>;
  onConfirm: () => void;
}

export function WoPreviewCard({ wo, onConfirm }: Props): JSX.Element {
  return (
    <div style={{ border: "1px solid #c9a227", borderRadius: 8, padding: 12, background: "#fff" }}>
      <h3>工单预览</h3>
      <pre style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{JSON.stringify(wo, null, 2)}</pre>
      <button onClick={onConfirm}>确认投递</button>
    </div>
  );
}

