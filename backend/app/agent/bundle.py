"""Evidence bundle — everything an approval committee needs, in one document.

A backtest tool outputs numbers. What a策略上线评审 actually needs is a
document somebody can sign: what was run, on what data, under which assumed
world, what it showed, what the deterministic checks said, whether the result
survived resampling, how wrong the estimation method is, and — the part most
packs omit — which experiments were *not* run.

Assembled from existing artefacts only: run record, manifest, environment,
guardrails, swap attribution, lineage and any recorded conclusion. Nothing
here is generated prose; the AI layer may add a summary on top, clearly
attributed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.agent import guardrails, insights
from app.core import runs as runs_service
from app.core.manifest import ENGINE_VERSION, METRIC_VERSION
from app.db import repository


def _pct(v, digits: int = 2) -> str:
    return f"{v * 100:.{digits}f}%" if isinstance(v, (int, float)) else "—"


def _money(v) -> str:
    return f"{v:,.0f}" if isinstance(v, (int, float)) else "—"


def _kpi(layer: dict, version: str) -> dict:
    for k in layer.get("kpis", []) or []:
        if k.get("version") == version:
            return k
    return {}


def build(run_id: str, replication: Optional[dict] = None,
          ri_comparison: Optional[dict] = None,
          ai_summary: Optional[str] = None) -> dict:
    """Collect the bundle for one run. Returns {markdown, data}."""
    run = runs_service.get_run(run_id)
    stored = repository.get_run(run_id) or {}
    report = guardrails.check_run(run)
    layers = run.get("layers", {})
    env = run.get("environment") or {}
    config = run.get("config", {})
    matrices = layers.get("l4", {}).get("matrices", {})
    challenger = run.get("challenger")
    decomposition = decompose(matrices, challenger)
    lineage = repository.get_lineage(stored.get("root_run_id") or run_id)

    data = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_sha": run.get("manifest_sha"),
        "engine_version": run.get("engine_version", ENGINE_VERSION),
        "metric_version": run.get("metric_version", METRIC_VERSION),
        "config": config,
        "environment": env,
        "guardrails": report,
        "decomposition": decomposition,
        "replication": replication,
        "ri_comparison": ri_comparison,
        "lineage": lineage,
        "hypothesis": stored.get("hypothesis"),
        "conclusion": stored.get("conclusion"),
        "recommendation": _recommendation(report, replication, env),
        "open_questions": _open_questions(report, replication, env, ri_comparison),
    }
    return {"markdown": _render(run, data, ai_summary), "data": data}


def decompose(matrices: dict, challenger: Optional[str]) -> Optional[dict]:
    m = matrices.get(challenger) if challenger else None
    return insights.decompose_swap(m) if m else None


def _recommendation(report: dict, replication: Optional[dict], env: dict) -> dict:
    """The bundle takes a position — and it is never "ship it"."""
    if report["blocking"]:
        return {"verdict": "不可推进",
                "why": f"存在 {len(report['blocking'])} 项阻断级红线，必须先解决"}
    if replication and replication.get("stable") is False:
        return {"verdict": "不可推进",
                "why": "多种子复现下策略排序发生翻转，该差异来自抽样而非策略"}
    if replication is None:
        return {"verdict": "证据不足",
                "why": "未做多种子复现，无法区分策略差异与抽样差异"}
    caveat = "；".join(w["detail"] for w in report["warnings"][:2])
    return {"verdict": "可提交人工评审",
            "why": f"红线通过、排序稳健。仍需人工判断的保留项：{caveat or '无'}",
            "note": f"本结论的适用边界由仿真环境 {env.get('id')}（{env.get('level')}）决定，"
                    f"不覆盖：{'；'.join(env.get('not_valid_for', [])[:2])}"}


def _open_questions(report: dict, replication: Optional[dict], env: dict,
                    ri: Optional[dict]) -> list:
    """What this pack does NOT answer. Most packs leave this out, which is
    exactly why they get waved through."""
    out = []
    if replication is None:
        out.append("未做多种子复现：本结论仍基于单次抽样")
    if env.get("level") == "L0a":
        out.append("历史回放环境：拒绝客群无表现数据，放开准入后的客群变化未被验证")
    if ri is None and env.get("id") == "reject_inference":
        out.append("未横比拒绝推断方法：当前误差可能不是最小的")
    if env.get("level") != "L0c":
        out.append("无行为反馈仿真：接受率、用信率随额度变化的影响未被建模")
    for w in report["warnings"]:
        out.append(f"待澄清：{w['detail']}")
    return out


def _render(run: dict, d: dict, ai_summary: Optional[str]) -> str:
    layers = run.get("layers", {})
    versions = [v for v in [run.get("champion"), run.get("challenger"), run.get("beta")] if v]
    env = d["environment"]
    rec = d["recommendation"]
    L = []
    a = L.append

    a(f"# 策略评审材料 · {run.get('challenger')} vs {run.get('champion')}")
    a("")
    a(f"> 生成时间 {d['generated_at']} · run `{d['run_id']}` · manifest `{(d['manifest_sha'] or '')[:16]}…`")
    a(f"> 引擎 {d['engine_version']} · 指标口径 {d['metric_version']}")
    a("")

    a(f"## 结论：{rec['verdict']}")
    a("")
    a(rec["why"])
    if rec.get("note"):
        a("")
        a(rec["note"])
    if d["hypothesis"]:
        a("")
        a(f"**原始假设**：{d['hypothesis']}")
    if d["conclusion"]:
        a(f"**已记录结论**：{d['conclusion']}")
    if ai_summary:
        a("")
        a(f"**AI 摘要**（由模型生成，数字均取自下表，不构成独立证据）：{ai_summary}")
    a("")

    a("## 1. 实验配置")
    a("")
    a("| 项 | 值 |")
    a("|---|---|")
    a(f"| 冠军 / 挑战者 | {run.get('champion')} / {run.get('challenger')} |")
    a(f"| Beta | {run.get('beta') or '—'} |")
    a(f"| 样本 | {d['config'].get('sample_id')} · {run.get('sample_size'):,} 行 |")
    a(f"| 随机种子 | {d['config'].get('seed')} |")
    a(f"| 切片 | {d['config'].get('slice_dim') or '全量'} = {d['config'].get('slice_value') or '—'} |")
    a(f"| 策略旋钮覆盖 | `{d['config'].get('policy_overrides') or '{}'}` |")
    a(f"| 仿真环境 | {env.get('name_zh')}（{env.get('level')}，置信度 {env.get('confidence')}）|")
    a("")

    a("## 2. 核心指标")
    a("")
    a("| 策略 | 通过率 | 坏账率 | RAROC | KS | AUC | 核准户数 | 增量余额 | 利润 |")
    a("|---|---|---|---|---|---|---|---|---|")
    for v in versions:
        k1, k2 = _kpi(layers.get("l1", {}), v), _kpi(layers.get("l2", {}), v)
        a(f"| {v} | {_pct(k2.get('approval_rate'))} | {_pct(k2.get('el'))} | "
          f"{_pct(k2.get('raroc'))} | {k1.get('ks', '—')} | {k1.get('auc', '—')} | "
          f"{_money(k2.get('n_approved'))} | {_money(k2.get('total_balance'))} | "
          f"{_money(k2.get('total_profit'))} |")
    a("")

    dec = d["decomposition"]
    if dec:
        a("## 3. 增量来源分解")
        a("")
        a(dec["headline"])
        a("")
        a("| 来源 | 户数 | 占比 | 该客群坏账 |")
        a("|---|---|---|---|")
        a(f"| 模型区分度 | {dec['model_driven']['n']:,} | {_pct(dec['model_driven']['share'], 0)} | "
          f"{_pct(dec['model_driven']['bad_rate'])} |")
        a(f"| 政策放宽 | {dec['policy_driven']['n']:,} | {_pct(dec['policy_driven']['share'], 0)} | "
          f"{_pct(dec['policy_driven']['bad_rate'])} |")
        a("")
        a("按规则拆分：")
        a("")
        a("| 冠军拒绝规则 | 户数 | 该客群坏账 |")
        a("|---|---|---|")
        for r in dec["model_driven"]["rules"] + dec["policy_driven"]["rules"]:
            a(f"| {r['reason']}（`{r['rule']}`）| {r['n']:,} | {_pct(r['bad_rate'])} |")
        a("")

    a("## 4. 红线检查")
    a("")
    if not d["guardrails"]["blocking"] and not d["guardrails"]["warnings"]:
        a("全部通过。")
    for b in d["guardrails"]["blocking"]:
        a(f"- **阻断** `{b['code']}` — {b['detail']}")
    for w in d["guardrails"]["warnings"]:
        a(f"- 警告 `{w['code']}` — {w['detail']}")
    a("")

    a("## 5. 稳健性")
    a("")
    rep = d["replication"]
    if rep:
        a(f"{rep.get('verdict', '')}（种子 {', '.join(str(s) for s in rep.get('seeds', []))}）")
        a("")
        a("| 策略 | RAROC 均值 | 标准差 | 95% 置信区间 |")
        a("|---|---|---|---|")
        for sid, m in (rep.get("strategies") or {}).items():
            r = m.get("raroc") or {}
            ci = r.get("ci95")
            a(f"| {sid} | {_pct(r.get('mean'))} | {_pct(r.get('std'))} | "
              f"{(_pct(ci[0]) + ' – ' + _pct(ci[1])) if ci else '—'} |")
    else:
        a("**未做多种子复现** —— 本结论仍基于单次抽样，无法区分策略差异与抽样差异。")
    a("")

    ri_report = env.get("reject_inference")
    if ri_report or d["ri_comparison"]:
        a("## 6. 拒绝推断误差")
        a("")
        if ri_report:
            a(f"方法：{ri_report.get('mode')} · 遮蔽 {ri_report.get('n_masked'):,} 户")
            a("")
            a("| 策略 | 估计坏账 | 真实坏账 | 偏差 | 相对误差 |")
            a("|---|---|---|---|---|")
            for sid, s in (ri_report.get("strategies") or {}).items():
                if not s.get("n_swap_in"):
                    continue
                a(f"| {sid} | {_pct(s.get('estimated_bad_rate'))} | {_pct(s.get('oracle_bad_rate'))} | "
                  f"{s.get('bias_pp', 0):+.2f}pp | {_pct(s.get('relative_error'), 0)} |")
            a("")
            a("> oracle 列仅在合成账簿上可得，用于标定方法误差；生产环境没有这一列。")
        if d["ri_comparison"]:
            a("")
            a("方法横比（相对误差，越小越好）：")
            a("")
            for r in d["ri_comparison"].get("ranked", []):
                err = r.get("max_relative_error")
                a(f"- `{r['mode']}` — {_pct(err, 0) if err is not None else '—'}")
        a("")

    a("## 7. 本材料未回答的问题")
    a("")
    for q in d["open_questions"]:
        a(f"- {q}")
    a("")

    a("## 8. 证据链")
    a("")
    a(f"- 复现哈希 `{d['manifest_sha']}` —— 相同哈希必得相同数值")
    a(f"- 实验线索共 {len(d['lineage'])} 次运行：")
    for r in d["lineage"][:12]:
        a(f"  - `{r['run_id']}` · {r.get('created_by', 'user')} · {r.get('conclusion') or r.get('hypothesis') or ''}")
    a("")
    a("---")
    a("")
    a("本材料由 BackTest Studio 自动组装，数字均来自已记录的运行，未经二次加工。"
      "上线决策由人做出。")
    return "\n".join(L)
