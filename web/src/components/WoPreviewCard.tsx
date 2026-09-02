import { useState } from "react";

interface Props {
  wo: Record<string, unknown>;
  confidenceScore: number;
  reviewScore?: number | null;
  riskFlag?: string;
  onEdit: (draft: Record<string, unknown>) => void;
  onConfirm: () => void;
  onDiscard: () => void;
}

const FIELDS: { key: string; label: string }[] = [
  { key: "module", label: "模块" }, { key: "action", label: "动作" }, { key: "scope", label: "范围" },
  { key: "rules", label: "铁律" }, { key: "prohibitions", label: "禁止" },
  { key: "deliverable", label: "交付" }, { key: "deadline", label: "时限" },
];

export function WoPreviewCard({ wo, confidenceScore, reviewScore, riskFlag, onEdit, onConfirm, onDiscard }: Props): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown>>(wo);
  const [piiMasked] = useState(true); // 后端出站已 mask_pii（设计 3.6 第三重），徽章仅展示

  const save = (): void => { onEdit(draft); setEditing(false); };

  return (
    <div style={{ border: "1px solid var(--c-gold)", borderRadius: "var(--radius)", padding: 12, background: "var(--c-card)" }}>
      <h3 style={{ marginTop: 0 }}>
        工单预览
        {piiMasked && <span style={{ fontSize: 11, marginLeft: 8, color: "var(--c-info)" }}>PII 已脱敏</span>}
        {riskFlag && <span style={{ fontSize: 11, marginLeft: 8, color: "var(--c-danger)" }}>{riskFlag}</span>}
      </h3>
      <p style={{ fontSize: 13 }}>置信度 {Math.round(confidenceScore * 100)}%{reviewScore !== undefined && reviewScore !== null ? ` · 评审分 ${reviewScore.toFixed(2)}` : ""} · 编号 {String(wo.wo_number ?? "—")}</p>
      {FIELDS.map((f) => (
        <div key={f.key} style={{ margin: "6px 0" }}>
          <strong style={{ fontSize: 13 }}>{f.label}：</strong>
          {editing ? (
            <input value={String(draft[f.key] ?? "")} onChange={(e) => setDraft((prev) => ({ ...prev, [f.key]: e.target.value }))} style={{ width: "100%" }} />
          ) : (
            <span style={{ fontSize: 13 }}>{formatValue(wo[f.key])}</span>
          )}
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
        {editing ? (
          <>
            <button onClick={() => { setDraft(wo); setEditing(false); }}>取消</button>
            <button onClick={save}>保存修改</button>
          </>
        ) : (
          <>
            <button onClick={() => setEditing(true)}>编辑</button>
            <button onClick={onDiscard}>放弃</button>
            <button onClick={onConfirm} style={{ background: "var(--c-gold-grad)", color: "#fff" }}>确认投递</button>
          </>
        )}
      </div>
    </div>
  );
}

function formatValue(v: unknown): string {
  if (Array.isArray(v)) return v.join("；");
  if (v === null || v === undefined) return "";
  return String(v);
}
