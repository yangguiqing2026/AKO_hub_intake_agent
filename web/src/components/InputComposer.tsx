import { useState } from "react";

interface Props { onSubmit: (text: string) => void }

const MIN_LEN = 10;
const MAX_LEN = 2000;

export function InputComposer({ onSubmit }: Props): JSX.Element {
  const [text, setText] = useState("");
  const tooShort = text.length > 0 && text.length < MIN_LEN;
  return (
    <div>
      <textarea
        rows={4} style={{ width: "100%", fontFamily: "inherit" }}
        placeholder="描述你的需求，例如：帮我看看报价模块最近的数据有没有问题"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
        <span style={{ color: tooShort ? "var(--c-danger)" : "var(--c-text)", fontSize: 12 }}>
          {text.length}/{MAX_LEN}（须 10~2000 字符）
        </span>
        <button
          disabled={text.length < MIN_LEN || text.length > MAX_LEN}
          onClick={() => { onSubmit(text.trim()); setText(""); }}
        >
          提交
        </button>
      </div>
      {tooShort && <p style={{ color: "var(--c-danger)", fontSize: 12 }}>文本须 10~2000 字符</p>}
    </div>
  );
}
