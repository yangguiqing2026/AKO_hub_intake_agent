import { useState } from "react";
import type { Question } from "../api/client";

interface Props {
  questions: Question[];
  onAnswer: (answers: { qid: string; value: string }[]) => void;
}

export function QuestionCard({ questions, onAnswer }: Props): JSX.Element {
  const [values, setValues] = useState<Record<string, string>>({});
  const submit = (): void => {
    const answers = questions.map((q) => ({ qid: q.qid, value: values[q.qid] ?? "" }));
    if (answers.every((a) => a.value)) onAnswer(answers);
  };
  return (
    <div style={{ border: "1px solid #c9a227", borderRadius: 8, padding: 12, background: "#fff" }}>
      <h3>P0 歧义澄清</h3>
      {questions.map((q) => (
        <div key={q.qid} style={{ margin: "8px 0" }}>
          <p>{q.text}</p>
          {q.type === "single_choice" ? (
            <select value={values[q.qid] ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, [q.qid]: e.target.value }))}>
              <option value="">请选择</option>
              {q.options.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          ) : (
            <input value={values[q.qid] ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, [q.qid]: e.target.value }))} />
          )}
        </div>
      ))}
      <button onClick={submit}>提交答复</button>
    </div>
  );
}

