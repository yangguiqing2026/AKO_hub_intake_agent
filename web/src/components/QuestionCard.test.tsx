import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QuestionCard } from "./QuestionCard";
import type { Question } from "../schemas/ws";

const QUESTIONS: Question[] = [
  { qid: "q-1-action", field: "action", text: "您说的动作是？", type: "single_choice", options: ["审计", "修复"], required: true },
  { qid: "q-1-scope", field: "scope", text: "请明确范围", type: "open", options: [], required: true },
];

// vitest 未开 globals，RTL 自动 cleanup 不生效，显式注册避免多次 render 累积干扰断言。
afterEach(cleanup);

beforeEach(() => vi.restoreAllMocks());

describe("QuestionCard", () => {
  it("渲染单选与填空两种形态", () => {
    render(<QuestionCard questions={QUESTIONS} onAnswer={vi.fn()} onConservative={vi.fn()} />);
    expect(screen.getByText(/您说的动作是？/)).toBeDefined();
    expect(screen.getByText(/请明确范围/)).toBeDefined();
  });
  it("必答校验：未填全时提交不回调", () => {
    const onAnswer = vi.fn();
    render(<QuestionCard questions={QUESTIONS} onAnswer={onAnswer} onConservative={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "提交答复" }));
    expect(onAnswer).not.toHaveBeenCalled();
  });
  it("填全后提交回调 answers", () => {
    const onAnswer = vi.fn();
    render(<QuestionCard questions={QUESTIONS} onAnswer={onAnswer} onConservative={vi.fn()} />);
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "审计" } });
    fireEvent.change(screen.getByPlaceholderText("请填写"), { target: { value: "全局审计" } });
    fireEvent.click(screen.getByRole("button", { name: "提交答复" }));
    expect(onAnswer).toHaveBeenCalledWith([
      { qid: "q-1-action", value: "审计" },
      { qid: "q-1-scope", value: "全局审计" },
    ]);
  });
  it("点击保守策略按钮回调 onConservative", () => {
    const onConservative = vi.fn();
    render(<QuestionCard questions={QUESTIONS} onAnswer={vi.fn()} onConservative={onConservative} />);
    fireEvent.click(screen.getByRole("button", { name: "按最保守策略处理" }));
    expect(onConservative).toHaveBeenCalled();
  });
});
