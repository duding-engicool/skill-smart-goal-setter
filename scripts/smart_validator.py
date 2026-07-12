#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_validator.py —— 通用 SMART 五维机检

对每条目标做 S/M/A/R/T 五维度机器检查，输出结构化判定与改进建议。
设计原则：
- 纯本地、无外部依赖；UTF-8 安全（Windows 下强制 UTF-8 stdout）。
- R 维（相关性）支持可选战略输入：提供 strategy 则校验关联，未提供则标「待复核」而非判失败。
- 不预设任何行业标准（如 ISO 9001）；通用适用。

用法：
  python smart_validator.py --goals "目标1|目标2" [--strategy "上层战略文本"]
  python smart_validator.py --input '{"goals":["目标1"],"strategy":"..."}' [--format json|text]
"""
import argparse
import json
import re
import sys


# 模糊动词（仅当无量化/无具体对象时视为弱）
VAGUE_WORDS = ["提高", "改善", "加强", "优化", "提升", "增强", "改进", "完善", "做好", "搞好", "强化"]
# 具体动作动词（正面信号）
ACTION_VERBS = [
    "完成", "实现", "降低", "减少", "增加", "达成", "建立", "开发", "交付", "通过",
    "获得", "缩短", "控制在", "降至", "降到", "提高到", "提升", "达到", "上线", "发布",
    "培训", "实施", "设计", "解决", "消除", "确保", "使", "将",
]
# 时间表达
TIME_PAT = re.compile(
    r"(\d{4}年|\d+月|\d+日|Q[1-4]|季度|年内|年底前|上半年|下半年|"
    r"\d+天|\d+日|\d+周|\d+个月|\d+小时|\d+周|week|month|quarter|year|202[5-9])"
)
# 量化表达（数字+单位）
NUM_PAT = re.compile(
    r"(\d+(\.\d+)?\s*(%|％|个|件|次|元|万元|人|天|小时|分|项|倍|pp|pct|起|分|级|名|台|套))"
)
# 基准-目标模式：从X到Y / 降至X / 提升X
BASELINE_PAT = re.compile(
    r"(从\s*\d|降至|降到|降低\s*到|提升\s*到|提高到|由\s*\d|控制在\s*\d|减至|增至)"
)
# 战略/相关信号
RELEVANCE_PAT = re.compile(
    r"(战略|目标|规划|方向|支撑|支持|对齐|配合|为了|旨在|对应|服务于|一致|助力|保障)"
)
# 资源/可行性信号
RESOURCE_PAT = re.compile(
    r"(资源|预算|团队|人员|能力|支持|授权|设备|资金|时间|条件|可行|通道|导师|专家|工具)"
)


def _check_specific(goal):
    issues = []
    has_action = any(v in goal for v in ACTION_VERBS)
    has_vague = any(w in goal for w in VAGUE_WORDS)
    if has_vague and not has_action and not NUM_PAT.search(goal):
        issues.append("含模糊词且无具体行动/量化，需明确'做什么 + 做到什么程度'")
    if not has_action and not has_vague:
        issues.append("未识别到明确行动动词，建议以动词开头描述具体动作")
    return (len(issues) == 0), issues


def _check_measurable(goal):
    issues = []
    if not NUM_PAT.search(goal):
        issues.append("未检测到量化指标（数字+单位），目标不可衡量")
    if not BASELINE_PAT.search(goal) and not NUM_PAT.search(goal):
        issues.append("缺少基准或对比，建议采用'从 X 到 Y'表述")
    return (len(issues) == 0), issues


def _check_achievable(goal):
    issues = []
    if not RESOURCE_PAT.search(goal):
        issues.append("未提及资源/能力/条件，可行性待确认（供参考：需说明可达成依据）")
    return (len(issues) == 0), issues


def _check_relevant(goal, has_strategy):
    issues = []
    if has_strategy:
        if not RELEVANCE_PAT.search(goal):
            issues.append("已提供上层战略/目标，但本目标未体现关联，建议标注支撑关系")
        return (len(issues) == 0), issues, "checked"
    issues.append("未提供上层战略/目标，相关性无法校验 → 待提供战略后复核")
    return False, issues, "pending"


def _check_timebound(goal):
    issues = []
    if not TIME_PAT.search(goal):
        issues.append("未检测到时间期限或里程碑，需明确完成时间")
    return (len(issues) == 0), issues


def evaluate(goal, has_strategy):
    s, s_i = _check_specific(goal)
    m, m_i = _check_measurable(goal)
    a, a_i = _check_achievable(goal)
    r, r_i, r_state = _check_relevant(goal, has_strategy)
    t, t_i = _check_timebound(goal)
    dims = {
        "S_具体": {"passed": s, "issues": s_i},
        "M_可衡量": {"passed": m, "issues": m_i},
        "A_可达成": {"passed": a, "issues": a_i},
        "R_相关": {"passed": r, "issues": r_i, "state": r_state},
        "T_时限": {"passed": t, "issues": t_i},
    }
    passed_count = sum(1 for d in dims.values() if d["passed"])
    return dims, passed_count


def main():
    parser = argparse.ArgumentParser(description="通用 SMART 五维机检")
    parser.add_argument("--goals", help="目标列表，用 | 分隔，如: 提高质量|缺陷率降至1.5%")
    parser.add_argument("--strategy", default="", help="上层战略/目标文本（可选，用于校验 R 维）")
    parser.add_argument("--input", help="JSON 输入，如: {\"goals\":[...],\"strategy\":\"...\"}")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()

    goals = []
    strategy = args.strategy or ""
    if args.input:
        try:
            data = json.loads(args.input)
            goals = data.get("goals", [])
            strategy = data.get("strategy", strategy)
        except (ValueError, AttributeError) as e:
            print(json.dumps({"status": "error", "message": "JSON 解析失败: %s" % e}, ensure_ascii=False))
            sys.exit(1)
    elif args.goals:
        goals = [g.strip() for g in args.goals.split("|") if g.strip()]
    else:
        print(json.dumps({"status": "error", "message": "需提供 --goals 或 --input"}, ensure_ascii=False))
        sys.exit(1)

    if not goals:
        print(json.dumps({"status": "error", "message": "目标列表为空"}, ensure_ascii=False))
        sys.exit(1)

    has_strategy = bool(strategy.strip())
    results = []
    total_pass = 0
    for g in goals:
        dims, pc = evaluate(g, has_strategy)
        total_pass += pc
        results.append({"goal": g, "dimensions": dims, "passed_dims": pc, "total_dims": 5})

    summary = {
        "status": "ok",
        "strategy_provided": has_strategy,
        "strategy_note": "已校验 R 维相关性" if has_strategy else "R 维标注「待提供战略后复核」",
        "goals_count": len(goals),
        "avg_passed_dims": round(total_pass / len(goals), 2),
        "results": results,
    }

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        lines = []
        lines.append("===== SMART 五维机检 =====")
        lines.append("战略输入: %s" % ("已提供，校验 R 维" if has_strategy else "未提供，R 维待复核"))
        lines.append("目标数: %d，平均通过维度: %.2f/5" % (len(goals), summary["avg_passed_dims"]))
        lines.append("-" * 40)
        for r in results:
            lines.append("目标: %s" % r["goal"])
            for dim, info in r["dimensions"].items():
                mark = "✓" if info["passed"] else "✗"
                lines.append("  [%s] %s" % (mark, dim))
                for issue in info["issues"]:
                    lines.append("      - %s" % issue)
            lines.append("")
        print("\n".join(lines))


if __name__ == "__main__":
    main()
