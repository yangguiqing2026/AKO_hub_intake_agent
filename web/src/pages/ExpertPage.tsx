import { useState } from "react";

const FIELDS = ["module", "action", "scope", "rules", "prohibitions", "deliverable", "deadline"] as const;

export function ExpertPage(): JSX.Element {
  const [form, setForm] = useState<Record<string, string>>({});
  return (
    <section>
      <h2>专家模式：直接填写 ako1 工单</h2>
      <p>绕过自然语言解析，人工填写 8 个刚性字段（工单号由系统生成）。</p>
      {FIELDS.map((field) => (
        <label key={field} style={{ display: "block", margin: "8px 0" }}>
          {field}：
          <input
            style={{ width: "100%" }}
            value={form[field] ?? ""}
            onChange={(e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))}
          />
        </label>
      ))}
      <button disabled={!form.action || !form.module} onClick={() => alert("提交工单：请接入 /api/v1/hub/wo/deliver")}>
        提交工单
      </button>
    </section>
  );
}

