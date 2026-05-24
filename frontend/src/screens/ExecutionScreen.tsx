import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { ExperimentConfig, RunResult } from '../types';
import Icon from '../components/Icon';
import API from '../api/client';

interface ExecutionScreenProps {
  config: ExperimentConfig;
  onDone: (result: RunResult) => void;
}

const STEPS = [
  { key: 'load', labelKey: 'exec_step_load', subZh: '从快照读取决策日志', subEn: 'Reading decision logs from snapshot', duration: 1200 },
  { key: 'score', labelKey: 'exec_step_score', subZh: '三策略并行打分', subEn: 'Scoring three strategies in parallel', duration: 2500 },
  { key: 'metrics', labelKey: 'exec_step_metrics', subZh: 'L1-L5 确定性引擎', subEn: 'L1-L5 deterministic engine', duration: 3000 },
  { key: 'ai', labelKey: 'exec_step_ai', subZh: '策略差异深度分析', subEn: 'Deep strategy-diff analysis', duration: 2000 },
];

export default function ExecutionScreen({ config, onDone }: ExecutionScreenProps) {
  const { t, i18n } = useTranslation();
  const zh = i18n.language !== 'en';
  const [stepIndex, setStepIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [done, setDone] = useState(false);
  const startRef = useRef(Date.now());
  const ranRef = useRef(false);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed(Date.now() - startRef.current);
    }, 100);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    // Advance steps visually while API call runs in background
    let idx = 0;
    let apiDone = false;
    let stepsAnimDone = false;
    let result: RunResult | null = null;

    function checkFinish() {
      if (apiDone && stepsAnimDone && result) {
        setDone(true);
        setTimeout(() => onDone(result!), 600);
      }
    }

    // Run steps animation
    function advanceStep() {
      if (idx < STEPS.length) {
        setStepIndex(idx + 1);
        idx++;
        if (idx < STEPS.length) {
          setTimeout(advanceStep, STEPS[idx - 1].duration);
        } else {
          stepsAnimDone = true;
          checkFinish();
        }
      }
    }
    setTimeout(advanceStep, STEPS[0].duration);

    // API call
    API.run(config).then((r) => {
      result = r;
      apiDone = true;
      checkFinish();
    }).catch(() => {
      apiDone = true;
      result = null;
      checkFinish();
    });
  }, [config, onDone]);

  const elapsedSec = (elapsed / 1000).toFixed(1);
  const lastStep = stepIndex >= STEPS.length - 1;

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

      <div className="card" style={{ padding: '36px 24px', textAlign: 'center' }}>
        {done ? (
          <div style={{ color: 'var(--green)', fontSize: 15, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <Icon name="check" size={16} /> {t('exec_done')}
          </div>
        ) : lastStep ? (
          <div style={{ color: 'var(--purple-2)', fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
            <Icon name="sparkles" size={16} /> {zh ? 'AI 正在分析策略差异…' : 'AI is analyzing strategy differences…'}
            <span className="dots-spinner" />
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
