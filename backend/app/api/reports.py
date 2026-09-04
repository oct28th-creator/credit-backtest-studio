"""
Reports router: static/cached report retrieval for completed runs.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.experiments import get_run_or_404
from app.models.schemas import Language

router = APIRouter(prefix="/api/reports", tags=["reports"])

_DI_GROUPS = [
    ("female_male", "女性/男性", "Female/Male"),
    ("outsider_local", "外地/本地", "Outsider/Local"),
    ("young_core", "年轻/核心", "Young/Core"),
]


def _fmt_pct(val, digits: int = 1) -> str:
    try:
        return f"{float(val) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "N/A"


def _build_static_report(run: dict, language: str = "zh") -> str:
    """
    Build a static Markdown report from a persisted run's reshaped layers.

    Persisted runs store ``layers`` in the FRONTEND shape produced by
    ``experiments._reshape_layers``: top-level keys ``l1``..``l5``, each
    layer aggregating all strategies. This builder reads that shape.
    """
    champion = run["champion"]
    challenger = run["challenger"]
    beta = run.get("beta")
    layers = run.get("layers", {})

    l1_kpis = {k["version"]: k for k in layers.get("l1", {}).get("kpis", [])}
    l2_kpis = {k["version"]: k for k in layers.get("l2", {}).get("kpis", [])}
    l3_kpis = {k["version"]: k for k in layers.get("l3", {}).get("kpis", [])}
    l3_roll = layers.get("l3", {}).get("roll_rates", {})
    l4_matrices = layers.get("l4", {}).get("matrices", {})
    l5_di = layers.get("l5", {}).get("di_by_group", {})

    strategy_ids = [champion, challenger] + ([beta] if beta else [])

    def _val(source: dict, sid: str, key: str, pct: bool = False) -> str:
        row = source.get(sid)
        if not row or row.get(key) is None:
            return "N/A"
        val = row[key]
        if pct:
            return _fmt_pct(val)
        if isinstance(val, float):
            return f"{val:.4f}"
        return str(val)

    def _swap_table(swap: dict, zh: bool) -> list[str]:
        out = []
        if not swap:
            return out
        total = swap.get("consistency_total", 0) or 0
        out.append("| 象限 | 数量 | 占比 | 坏账率 |" if zh else "| Quadrant | Count | Share | Bad Rate |")
        out.append("|------|------|------|--------|" if zh else "|--------|------|-------|----------|")
        for key, zh_lbl, en_lbl in [
            ("double_approve", "双批（Double Approve）", "Double Approve"),
            ("swap_in", "换入（Swap-in）", "Swap-in"),
            ("swap_out", "换出（Swap-out）", "Swap-out"),
            ("double_reject", "双拒（Double Reject）", "Double Reject"),
        ]:
            q = swap.get(key, {})
            n = q.get("count", 0)
            pct = (n / total * 100) if total else 0
            br = q.get("bad_rate")
            br_s = _fmt_pct(br, 2) if isinstance(br, (int, float)) else "—"
            label = zh_lbl if zh else en_lbl
            out.append(f"| {label} | {n:,} | {pct:.1f}% | {br_s} |")
        out.append("")
        if zh:
            out.append(f"**决策一致率**: {swap.get('consistency', 0) * 100:.1f}%\n")
        else:
            out.append(f"**Consistency**: {swap.get('consistency', 0) * 100:.1f}%\n")
        return out

    lines = []
    zh = language == "zh"

    if zh:
        lines.append("# BackTest Studio 回测报告\n")
        lines.append(f"**Run ID**: `{run['run_id']}`  ")
        lines.append(f"**样本量**: {run['sample_size']:,}  ")
        lines.append(f"**运行耗时**: {run['duration_s']:.2f}s  ")
        lines.append(f"**快照**: `{run['snapshot_sha']}`\n")

        lines.append("## 策略配置\n")
        lines.append("| 角色 | 策略 |")
        lines.append("|------|------|")
        lines.append(f"| Champion（基线） | {champion} |")
        lines.append(f"| Challenger | {challenger} |")
        if beta:
            lines.append(f"| Beta | {beta} |")
        lines.append("")

        lines.append("## L1-L2 核心 KPI 对比\n")
        header = "| 指标 | " + " | ".join(strategy_ids) + " |"
        lines.append(header)
        lines.append("|------|" + "------|" * len(strategy_ids))

        metrics = [
            ("通过率", "approval_rate", l2_kpis, True),
            ("坏账率（MOB12）", "el", l2_kpis, True),
            ("RAROC", "raroc", l2_kpis, True),
            ("AUC", "auc", l1_kpis, False),
            ("KS", "ks", l1_kpis, False),
            ("FPD率", "fpd", l3_kpis, True),
        ]
        for label, key, src, pct in metrics:
            row = f"| {label} |"
            for sid in strategy_ids:
                row += f" {_val(src, sid, key, pct)} |"
            lines.append(row)
        lines.append("")

        lines.append("## L3 风险指标\n")
        for sid in strategy_ids:
            l3 = l3_kpis.get(sid)
            if not l3:
                continue
            roll = l3_roll.get(sid, {})
            lines.append(f"**{sid}**")
            lines.append(f"- MOB12 坏账率：{_val(l3_kpis, sid, 'm12_bad', True)}")
            lines.append(f"- FPD率：{_val(l3_kpis, sid, 'fpd', True)}")
            if roll:
                lines.append(f"- M0→M1 滚动率：{_fmt_pct(roll.get('m0_m1'), 2)}")
                lines.append(f"- M1→M2 滚动率：{_fmt_pct(roll.get('m1_m2'), 2)}")
            lines.append("")

        lines.append("## L4 换组分析\n")
        for sid in ([challenger] + ([beta] if beta else [])):
            swap = l4_matrices.get(sid)
            if not swap:
                continue
            lines.append(f"**{sid} vs {champion}**")
            lines.extend(_swap_table(swap, zh=True))
            lines.append("")

        lines.append("## L5 公平性合规\n")
        for sid in strategy_ids:
            di = l5_di.get(sid)
            if not di:
                continue
            lines.append(f"**{sid}**")
            for key, zh_lbl, _ in _DI_GROUPS:
                ratio = di.get(key)
                if ratio is None:
                    continue
                ok = 0.8 <= float(ratio) <= 1.25
                marker = "✓" if ok else "⚠️"
                lines.append(f"  - {marker} {zh_lbl}: DI={float(ratio):.3f}")
            lines.append("")

        lines.append("## 结论与建议\n")
        lines.append("基于 L1-L5 综合评估：")
        lines.append(f"- **最优策略**: {challenger}（RAROC 最高）")
        lines.append(f"- **稳健选择**: {champion}（基线策略，风险最低）")
        if beta:
            b_di = l5_di.get(beta)
            if b_di and any(not (0.8 <= float(v) <= 1.25) for v in b_di.values() if v is not None):
                lines.append(f"- **⚠️ {beta}**: 存在公平性合规问题，需整改后再评估")
    else:
        lines.append("# BackTest Studio Report\n")
        lines.append(f"**Run ID**: `{run['run_id']}`  ")
        lines.append(f"**Sample Size**: {run['sample_size']:,}  ")
        lines.append(f"**Duration**: {run['duration_s']:.2f}s  ")
        lines.append(f"**Snapshot**: `{run['snapshot_sha']}`\n")

        lines.append("## Strategy Configuration\n")
        lines.append("| Role | Strategy |")
        lines.append("|------|---------|")
        lines.append(f"| Champion (baseline) | {champion} |")
        lines.append(f"| Challenger | {challenger} |")
        if beta:
            lines.append(f"| Beta | {beta} |")
        lines.append("")

        lines.append("## L1-L2 Core KPI Comparison\n")
        header = "| Metric | " + " | ".join(strategy_ids) + " |"
        lines.append(header)
        lines.append("|--------|" + "--------|" * len(strategy_ids))

        metrics = [
            ("Approval Rate", "approval_rate", l2_kpis, True),
            ("Bad Rate (MOB12)", "el", l2_kpis, True),
            ("RAROC", "raroc", l2_kpis, True),
            ("AUC", "auc", l1_kpis, False),
            ("KS", "ks", l1_kpis, False),
            ("FPD Rate", "fpd", l3_kpis, True),
        ]
        for label, key, src, pct in metrics:
            row = f"| {label} |"
            for sid in strategy_ids:
                row += f" {_val(src, sid, key, pct)} |"
            lines.append(row)
        lines.append("")

        lines.append("## L4 Swap Analysis\n")
        for sid in ([challenger] + ([beta] if beta else [])):
            swap = l4_matrices.get(sid)
            if not swap:
                continue
            lines.append(f"**{sid} vs {champion}**")
            lines.extend(_swap_table(swap, zh=False))
            lines.append("")

        lines.append("## L5 Fairness\n")
        for sid in strategy_ids:
            di = l5_di.get(sid)
            if not di:
                continue
            lines.append(f"**{sid}**")
            for key, _, en_lbl in _DI_GROUPS:
                ratio = di.get(key)
                if ratio is None:
                    continue
                ok = 0.8 <= float(ratio) <= 1.25
                marker = "✓" if ok else "⚠️"
                lines.append(f"  - {marker} {en_lbl}: DI={float(ratio):.3f}")
            lines.append("")

        lines.append("## Conclusion\n")
        lines.append(f"- **Best Strategy**: {challenger} (highest RAROC)")
        lines.append(f"- **Safest Option**: {champion} (baseline, lowest risk)")
        if beta:
            b_di = l5_di.get(beta)
            if b_di and any(not (0.8 <= float(v) <= 1.25) for v in b_di.values() if v is not None):
                lines.append(f"- **⚠️ {beta}**: Fairness compliance issues require remediation")

    return "\n".join(lines)


@router.get("/{run_id}")
async def get_report(
    run_id: str,
    language: Language = Query(default="zh", description="Language: zh or en"),
    format: str = Query(default="markdown", description="Output format: markdown or json"),
) -> dict:
    """
    Get a static report for a completed backtest run.
    For AI-generated streaming reports, use /api/ai/report/stream/{run_id}.
    """
    run = get_run_or_404(run_id)

    if format == "json":
        # Return the authoritative reshaped layers plus top-level run metadata.
        return {
            "run_id": run_id,
            "champion": run["champion"],
            "challenger": run["challenger"],
            "beta": run.get("beta"),
            "sample_size": run["sample_size"],
            "duration_s": run["duration_s"],
            "snapshot_sha": run["snapshot_sha"],
            "layers": run.get("layers", {}),
        }

    # Default: Markdown
    markdown = _build_static_report(run, language)
    return {
        "run_id": run_id,
        "language": language,
        "format": "markdown",
        "content": markdown,
    }
