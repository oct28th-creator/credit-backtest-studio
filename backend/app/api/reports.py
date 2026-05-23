"""
Reports router: static/cached report retrieval for completed runs.
"""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Query

from app.api.experiments import _RUN_STORE
from app.data.fixtures import STRATEGIES

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _build_static_report(run: dict, language: str = "zh") -> str:
    """
    Build a static Markdown report from computed run data.
    This is the fallback report when AI streaming is not used.
    """
    champion = run["champion"]
    challenger = run["challenger"]
    beta = run.get("beta")
    layers = run.get("layers", {})
    summary = layers.get("_summary", [])

    def _kpi(sid: str, key: str) -> str:
        for row in summary:
            if row["strategy_id"] == sid:
                val = row.get(key)
                if val is None:
                    return "N/A"
                if isinstance(val, float):
                    if key in ("approval_rate", "bad_rate", "raroc"):
                        return f"{val*100:.1f}%"
                    return f"{val:.4f}"
                return str(val)
        return "N/A"

    lines = []

    if language == "zh":
        lines.append(f"# BackTest Studio 回测报告\n")
        lines.append(f"**Run ID**: `{run['run_id']}`  ")
        lines.append(f"**样本量**: {run['sample_size']:,}  ")
        lines.append(f"**运行耗时**: {run['duration_s']:.2f}s  ")
        lines.append(f"**快照**: `{run['snapshot_sha']}`\n")

        lines.append("## 策略配置\n")
        lines.append(f"| 角色 | 策略 |")
        lines.append(f"|------|------|")
        lines.append(f"| Champion（基线） | {champion} |")
        lines.append(f"| Challenger | {challenger} |")
        if beta:
            lines.append(f"| Beta | {beta} |")
        lines.append("")

        lines.append("## L1-L2 核心 KPI 对比\n")
        header = "| 指标 | " + " | ".join([champion, challenger] + ([beta] if beta else [])) + " |"
        separator = "|------|" + "------|" * (3 if beta else 2)
        lines.append(header)
        lines.append(separator)

        metrics = [
            ("通过率", "approval_rate"),
            ("坏账率（MOB12）", "bad_rate"),
            ("RAROC", "raroc"),
            ("AUC", "auc"),
            ("KS", "ks"),
            ("FPD率", "fpd_rate"),
        ]
        strategy_ids = [champion, challenger] + ([beta] if beta else [])
        for label, key in metrics:
            row = f"| {label} |"
            for sid in strategy_ids:
                row += f" {_kpi(sid, key)} |"
            lines.append(row)
        lines.append("")

        lines.append("## L3 风险指标\n")
        for sid in strategy_ids:
            sid_layers = layers.get(sid, {})
            l3 = sid_layers.get("l3", {})
            if l3:
                roll = l3.get("roll_rates", {})
                lines.append(f"**{sid}**")
                lines.append(f"- MOB12 坏账率：{l3.get('mob12_bad_rate', 0)*100:.2f}%")
                lines.append(f"- FPD率：{l3.get('fpd_rate', 0)*100:.3f}%")
                lines.append(f"- M0→M1 滚动率：{roll.get('m0_to_m1', 0)*100:.2f}%")
                lines.append(f"- M1→M2 滚动率：{roll.get('m1_to_m2', 0)*100:.2f}%")
                lines.append("")

        lines.append("## L4 换组分析（Challenger vs Champion）\n")
        swap_key = "_swap_chall_vs_champ"
        swap = layers.get(swap_key, {})
        if swap:
            da = swap.get("double_approve", {})
            si = swap.get("swap_in", {})
            so = swap.get("swap_out", {})
            dr = swap.get("double_reject", {})
            lines.append(f"| 象限 | 数量 | 占比 | 坏账率 |")
            lines.append(f"|------|------|------|--------|")
            lines.append(f"| 双批（Double Approve） | {da.get('n', 0):,} | {da.get('pct', 0)*100:.1f}% | {da.get('bad_rate', 0)*100:.2f}% |")
            lines.append(f"| 换入（Swap-in） | {si.get('n', 0):,} | {si.get('pct', 0)*100:.1f}% | {si.get('bad_rate', 0)*100:.2f}% |")
            lines.append(f"| 换出（Swap-out） | {so.get('n', 0):,} | {so.get('pct', 0)*100:.1f}% | {so.get('bad_rate', 0)*100:.2f}% |")
            lines.append(f"| 双拒（Double Reject） | {dr.get('n', 0):,} | {dr.get('pct', 0)*100:.1f}% | — |")
            lines.append(f"\n**决策一致率**: {swap.get('consistency_pct', 0)*100:.1f}%\n")

        lines.append("## L5 公平性合规\n")
        for sid in strategy_ids:
            sid_layers = layers.get(sid, {})
            l5 = sid_layers.get("l5", {})
            if l5:
                lines.append(f"**{sid}**")
                has_issue = l5.get("has_compliance_issue", False)
                issue_marker = "⚠️ " if has_issue else ""
                lines.append(f"{issue_marker}{'合规问题存在' if has_issue else '公平性合规'}")
                for di in l5.get("di_ratios", []):
                    compliant = di.get("compliant", True)
                    marker = "⚠️" if not compliant else "✓"
                    lines.append(f"  - {marker} {di.get('group_zh', di.get('group'))}: DI={di.get('di_ratio', 0):.3f}")
                lines.append("")

        lines.append("## 结论与建议\n")
        lines.append("基于 L1-L5 综合评估：")
        lines.append(f"- **最优策略**: {challenger}（RAROC 最高）")
        lines.append(f"- **稳健选择**: {champion}（基线策略，风险最低）")
        if beta:
            b_issue = any(
                not g.get("compliant", True)
                for g in layers.get(beta, {}).get("l5", {}).get("di_ratios", [])
            )
            if b_issue:
                lines.append(f"- **⚠️ {beta}**: 存在公平性合规问题，需整改后再评估")

    else:
        lines.append(f"# BackTest Studio Report\n")
        lines.append(f"**Run ID**: `{run['run_id']}`  ")
        lines.append(f"**Sample Size**: {run['sample_size']:,}  ")
        lines.append(f"**Duration**: {run['duration_s']:.2f}s  ")
        lines.append(f"**Snapshot**: `{run['snapshot_sha']}`\n")

        lines.append("## Strategy Configuration\n")
        lines.append(f"| Role | Strategy |")
        lines.append(f"|------|---------|")
        lines.append(f"| Champion (baseline) | {champion} |")
        lines.append(f"| Challenger | {challenger} |")
        if beta:
            lines.append(f"| Beta | {beta} |")
        lines.append("")

        lines.append("## L1-L2 Core KPI Comparison\n")
        header = "| Metric | " + " | ".join([champion, challenger] + ([beta] if beta else [])) + " |"
        separator = "|--------|" + "--------|" * (3 if beta else 2)
        lines.append(header)
        lines.append(separator)

        metrics = [
            ("Approval Rate", "approval_rate"),
            ("Bad Rate (MOB12)", "bad_rate"),
            ("RAROC", "raroc"),
            ("AUC", "auc"),
            ("KS", "ks"),
            ("FPD Rate", "fpd_rate"),
        ]
        strategy_ids = [champion, challenger] + ([beta] if beta else [])
        for label, key in metrics:
            row = f"| {label} |"
            for sid in strategy_ids:
                row += f" {_kpi(sid, key)} |"
            lines.append(row)
        lines.append("")

        lines.append("## L5 Fairness & Compliance\n")
        for sid in strategy_ids:
            sid_layers = layers.get(sid, {})
            l5 = sid_layers.get("l5", {})
            if l5:
                has_issue = l5.get("has_compliance_issue", False)
                lines.append(f"**{sid}** {'⚠️ Compliance Issue' if has_issue else '✓ Compliant'}")
                for di in l5.get("di_ratios", []):
                    compliant = di.get("compliant", True)
                    marker = "⚠️" if not compliant else "✓"
                    lines.append(f"  - {marker} {di.get('group_en', di.get('group'))}: DI={di.get('di_ratio', 0):.3f}")
                lines.append("")

        lines.append("## Conclusion\n")
        lines.append(f"- **Best Strategy**: {challenger} (highest RAROC)")
        lines.append(f"- **Safest Option**: {champion} (baseline, lowest risk)")
        if beta:
            b_issue = any(
                not g.get("compliant", True)
                for g in layers.get(beta, {}).get("l5", {}).get("di_ratios", [])
            )
            if b_issue:
                lines.append(f"- **⚠️ {beta}**: Fairness compliance issues require remediation")

    return "\n".join(lines)


@router.get("/{run_id}")
async def get_report(
    run_id: str,
    language: str = Query(default="zh", description="Language: zh or en"),
    format: str = Query(default="markdown", description="Output format: markdown or json"),
) -> dict:
    """
    Get a static report for a completed backtest run.
    For AI-generated streaming reports, use /api/ai/report/stream/{run_id}.
    """
    if run_id not in _RUN_STORE:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    run = _RUN_STORE[run_id]

    if format == "json":
        # Return structured JSON report data
        layers = run.get("layers", {})
        return {
            "run_id": run_id,
            "champion": run["champion"],
            "challenger": run["challenger"],
            "beta": run.get("beta"),
            "sample_size": run["sample_size"],
            "duration_s": run["duration_s"],
            "snapshot_sha": run["snapshot_sha"],
            "summary": layers.get("_summary", []),
            "swap_analysis": layers.get("_swap_chall_vs_champ", {}),
        }

    # Default: Markdown
    markdown = _build_static_report(run, language)
    return {
        "run_id": run_id,
        "language": language,
        "format": "markdown",
        "content": markdown,
    }
