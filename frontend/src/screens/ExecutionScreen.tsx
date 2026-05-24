import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { ExperimentConfig, RunResult, AIAnalysis } from '../types';
import Icon from '../components/Icon';
import Thinking from '../components/Thinking';
import API from '../api/client';

interface ExecutionScreenProps {
  config: ExperimentConfig;
  onDone: (result: RunResult, analysis: AIAnalysis | null, thinking: string) => void;
}

const STEPS = [
  { key: 'load', labelKey: 'exec_step_load', subZh: '从快照读取决策日志', subEn: 'Reading decision logs from snapshot', duration: 900 },
  { key: 'score', labelKey: 'exec_step_score', subZh: '三策略并行打分', subEn: 'Scoring three strategies in parallel', duration: 1400 },
  { key: 'metrics', labelKey: 'exec_step_metrics', subZh: 'L1-L5 确定性引擎', subEn: 'L1-L5 deterministic engine', duration: 1500 },
  { key: 'ai', labelKey: 'exec_step_ai', subZh: '策略差异深度分析', subEn: 'Deep strategy-diff analysis', duration: 0 },
];

export default function ExecutionScreen({ config, onDone }: ExecutionScreenProps) {
  const { t, i18n } = useTranslation();
  const zh = i18n.language !== 'en';
  const [stepIndex, setStepIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [done, setDone] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [aiThinking, setAiThinking] = useState('');
  const [aiStart, setAiStart] = useState<number | null>(null);
  const startRef = useRef(Date.now());
  const ranRef = useRef(false);

  useEffect(() => {
    const timer = setInterval(() => setElapsed(Date.now() - startRef.current), 100);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    let apiResult: RunResult | null = null;
    let atAiStep = false;
    let aiStarted = false;
    let aiCleanup: (() => void) | null = null;

    // Animate load → score → metrics, then hold at the AI step
    let idx = 0;
    function advance() {
      idx++;
      setStepIndex(idx);
      if (idx < 3) setTimeout(advance, STEPS[idx].duration);
      else { atAiStep = true; maybeStartAi(); }
    }
    setTimeout(advance, STEPS[0].duration);

    API.run(config)
      .then(r => { apiResult = r; maybeStartAi(); })
      .catch(() => { apiResult = null; maybeStartAi(); });

    function maybeStartAi() {
      if (aiStarted || !atAiStep || !apiResult) return;
      aiStarted = true;
      const result = apiResult;
      setAnalyzing(true);
      setAiStart(Date.now());
      let thinkBuf = '';
      let resBuf = '';
      const finish = (analysis: AIAnalysis | null) => {
        setDone(true);
        setTimeout(() => onDone(result, analysis, thinkBuf), 700);
      };
      aiCleanup = API.streamAnalyzeLayer(
        result.run_id,
        'strategy',
        config.language ?? 'zh',
        (c) => { thinkBuf += c; setAiThinking(thinkBuf); },
        (c) => { resBuf += c; },
        () => { let a: AIAnalysis | null = null; try { a = JSON.parse(resBuf); } catch { /* keep null */ } finish(a); },
        () => finish(null),
      );
    }

    return () => { if (aiCleanup) aiCleanup(); };
  }, [config, onDone]);

  const elapsedSec = (elapsed / 1000).toFixed(1);

  return (
    <div className="page">
      <div className="page-hd">
        <div>
          <div className="page-title">{t('exec_title')}</div>
          <div className="page-sub">
            {config.challenger} vs {config.champion}
            {config.beta ? ` · Beta ${config.beta}` : ''} · {config.sample_id} · {elapsedSec}{t('exec_seconds')}
          </div>
        </div>
      </div>

      <div className="card mb16">
        <div className="exec-track">
          {STEPS.map((step, i) => {
            const completed = stepIndex > i || done;
            const running = stepIndex === i && !done;
            return (
              <React.Fragment key={step.key}>
                <div className="exec-step">
                  <div className={`exec-node ${completed ? 'done' : running ? 'active' : 'idle'}`}>
                    {completed ? <Icon name="check" size={14} /> : i + 1}
                  </div>
                  <div className="exec-lbl" style={{ color: completed ? 'var(--green)' : running ? 'var(--blue)' : 'var(--ink-4)', fontWeight: running ? 600 : 400 }}>
                    {t(step.labelKey)}
                  </div>
                  <div className="exec-sub" style={{ color: completed ? 'var(--green)' : running ? 'var(--blue-2)' : 'transparent' }}>
                    {completed ? (zh ? '完成' : 'Done') : running ? (zh ? step.subZh : step.subEn) : ''}
                  </div>
                </div>
                {i < STEPS.length - 1 && <div className={`exec-conn ${stepIndex > i || done ? 'done' : 'idle'}`} />}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      <div className="card" style={{ padding: analyzing && !done ? '20px 22px' : '36px 24px' }}>
        {done ? (
          <div style={{ color: 'var(--green)', fontSize: 15, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <Icon name="check" size={16} /> {t('exec_done')}
          </div>
        ) : analyzing ? (
          <div style={{ maxWidth: 760, margin: '0 auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--purple-2)', fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
              <Icon name="sparkles" size={16} />
              {zh ? '策略对比 · AI 正在分析挑战者与基线的差异…' : 'Strategy Comparison · AI is analyzing challenger vs baseline…'}
            </div>
            <Thinking text={aiThinking} loading startTime={aiStart} defaultOpen />
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
            <div style={{ color: 'var(--ink-3)', fontSize: 14 }}>
              {zh ? STEPS[stepIndex]?.subZh : STEPS[stepIndex]?.subEn}
            </div>
            <span className="dots-spinner" />
          </div>
        )}
      </div>
    </div>
  );
}
