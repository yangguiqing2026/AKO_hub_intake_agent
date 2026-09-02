import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { zodToJsonSchema } from "zod-to-json-schema";
import { inboundEnvelope, outboundEnvelope } from "./ws";

// 仓库根 schemas/ 目录（相对本测试文件上溯 3 层）。
// 注意：vite 会把 `new URL(..., import.meta.url)` 重写为 http://localhost/@fs/ 基址，
// readFileSync 只接受 file: URL，故用 fileURLToPath 保真解析。
const SCHEMAS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "../../../schemas");

interface ContractFacts {
  types: string[];          // 判别联合的消息类型名（按出现序）
  requiredByType: Record<string, string[]>; // 每类型必填字段（去默认值）
  textBounds?: { min: number; max: number }; // intake_input.text 边界
  roundMin?: number;        // p0_response.round 下界
}

// 提取某消息类型 payload 层的必填字段（去掉带默认值的字段）。
// 契约事实：pydantic 侧 payload 经 $ref 间接引用，zod 侧 payload 内联。
function requiredFromPydantic(schema: unknown, typeName: string): ContractFacts["requiredByType"][string] {
  // pydantic 导出：oneOf[i].$ref → $defs[name].properties.payload.$ref → $defs[payloadName].required
  const s = schema as {
    oneOf?: { $ref?: string }[];
    $defs?: Record<string, { required?: string[]; properties?: Record<string, { const?: string; $ref?: string }> }>;
  };
  const entry = s.oneOf?.find((o) => {
    const name = (o.$ref ?? "").split("/").pop() ?? "";
    const def = s.$defs?.[name];
    return def?.properties?.type && def.properties.type.const === typeName;
  });
  const name = (entry?.$ref ?? "").split("/").pop() ?? "";
  const payloadRef = s.$defs?.[name]?.properties?.payload?.$ref ?? "";
  const payloadName = payloadRef.split("/").pop() ?? "";
  return s.$defs?.[payloadName]?.required ?? [];
}

// zod-to-json-schema 输出：anyOf[i].properties.payload.properties（payload 内联）；
// 带 .default() 的字段序列化后含 default 键，故以 default === undefined 过滤必填。
function requiredFromZod(schema: unknown, typeName: string): ContractFacts["requiredByType"][string] {
  const s = schema as {
    anyOf?: { properties?: { type?: { const?: string }; payload?: { properties?: Record<string, { type?: string; default?: unknown }> } } }[];
  };
  const entry = s.anyOf?.find((o) => o.properties?.type?.const === typeName);
  const props = entry?.properties?.payload?.properties ?? {};
  return Object.entries(props).filter(([, v]) => v.default === undefined).map(([k]) => k);
}

describe("双端契约事实（设计 7.2）", () => {
  const pydantic = JSON.parse(readFileSync(resolve(SCHEMAS_DIR, "ws_message_v2.json"), "utf-8"));
  const zodInbound = zodToJsonSchema(inboundEnvelope) as { anyOf: { properties: { type: { const: string } } }[] };
  const zodOutbound = zodToJsonSchema(outboundEnvelope) as { anyOf: { properties: { type: { const: string } } }[] };

  it("入站消息类型集合与后端一致（10 类）", () => {
    const pydTypes = (pydantic.oneOf as { $ref: string }[]).map((o) =>
      (pydantic.$defs[(o.$ref as string).split("/").pop()!].properties.type as { const: string }).const,
    );
    const zodTypes = zodInbound.anyOf.map((o) => o.properties.type.const);
    expect(zodTypes).toEqual(pydTypes);
    expect(zodTypes).toHaveLength(10);
  });

  it("auth/intake_input/p0_response 必填字段双端一致", () => {
    for (const t of ["auth", "intake_input", "p0_response"]) {
      expect(requiredFromZod(zodInbound, t).sort()).toEqual(requiredFromPydantic(pydantic, t).sort());
    }
  });

  it("intake_input.text 边界 10..2000 双端一致", () => {
    // zod 侧：payload 内联；pydantic 侧：payload 经 $ref 间接引用，需两次跳转。
    const findTextZod = (s: unknown): { min: number; max: number } => {
      const anyOf = (s as { anyOf: { properties: { type: { const: string }; payload: { properties: { text: { minLength?: number; maxLength?: number } } } } }[] }).anyOf;
      const entry = anyOf.find((o) => o.properties.type.const === "intake_input")!;
      const t = entry.properties.payload.properties.text;
      return { min: t.minLength!, max: t.maxLength! };
    };
    const findTextPydantic = (s: unknown): { min: number; max: number } => {
      const doc = s as { oneOf: { $ref: string }[]; $defs: Record<string, { properties: Record<string, { const?: string; $ref?: string; minLength?: number; maxLength?: number }> }> };
      const entry = doc.oneOf.find((o) => {
        const name = o.$ref.split("/").pop()!;
        return doc.$defs[name].properties.type.const === "intake_input";
      })!;
      const payloadName = doc.$defs[entry.$ref.split("/").pop()!].properties.payload.$ref!.split("/").pop()!;
      const t = doc.$defs[payloadName].properties.text;
      return { min: t.minLength!, max: t.maxLength! };
    };
    expect(findTextZod(zodInbound)).toEqual(findTextPydantic(pydantic));
    expect(findTextZod(zodInbound)).toEqual({ min: 10, max: 2000 });
  });

  it("出站判别联合可导出且类型集非空（14 类）", () => {
    const types = zodOutbound.anyOf.map((o) => o.properties.type.const);
    expect(types).toHaveLength(14);
  });
});
