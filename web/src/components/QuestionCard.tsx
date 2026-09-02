import { useState } from "react";
import type { Question } from "../schemas/ws";

interface Props {
  questions: Question[];
  onAnswer: (answers: { qid: string; value: string }[]) => void;
  onConservative: () => void;
}

export function QuestionCard({ questions, onAnswer, onConservative }: Props): JSX.Element {
  const [values, setValues] = useState<Record<string, string>>({});
  const allFilled = questions.every((q) => (values[q.qid] ?? "").trim().length > 0);
  const submit = (): void => {
    if (!allFilled) return;
    onAnswer(questions.map((q) => ({ qid: q.qid, value: values[q.qid] ?? "" })));
  };
  return (
    <div style={{ border: "1px solid var(--c-gold)", borderRadius: "var(--radius)", padding: 12, background: "var(--c-card)" }}>
      <h3 style={{ marginTop: 0 }}>P0 歧义澄清</h3>
      {questions.map((q) => (
        <div key={q.qid} style={{ margin: "8px 0" }}>
          <p style={{ margin: "4px 0" }}>{q.text}{q.required ? " *" : ""}</p>
          {q.type === "single_choice" ? (
            <select value={values[q.qid] ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, [q.qid]: e.target.value }))}>
              <option value="">请选择</option>
              {q.options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
            </select>
          ) : (
            <input placeholder="请填写" value={values[q.qid] ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, [q.qid]: e.target.value }))} style={{ width: "100%" }} />
          )}
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
        <button onClick={onConservative}>按最保守策略处理</button>
        <button onClick={submit} disabled={!allFilled}>提交答复</button>
      </div>
    </div>
  );
}
