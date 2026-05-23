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
  { key: 'load', labelKey: 'exec_step_load', duration: 1200 },
  { key: 'score', labelKey: 'exec_step_score', duration: 2500 },
  { key: 'metrics', labelKey: 'exec_step_metrics', duration: 3000 },
  { key: 'ai', labelKey: 'exec_step_ai', duration: 2000 },
];

export default function ExecutionScreen({ config, onDone }: ExecutionScreenProps) {
  const { t } = useTranslation();
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

  return (
    <div className="execution-screen">
      <div className="execution-card">
        <div className="execution-title">
          {done ? (
            <><Icon name="check" size={22} style={{ color: 'var(--green)' }} />{t('exec_done')}</>
          ) : (
            <><span className="dots-spinner" />{t('exec_title')}</>
          )}
        </div>

        <div className="execution-steps">
          {STEPS.map((step, i) => {
            const completed = stepIndex > i;
            const running = stepIndex === i;
            return (
              <div key={step.key} className={`exec-step ${completed ? 'exec-step-done' : running ? 'exec-step-running' : 'exec-step-pending'}`}>
                <div className="exec-step-icon">
                  {completed ? (
                    <Icon name="check" size={16} />
                  ) : running ? (
                    <span className="exec-step-spinner" />
                  ) : (
                    <span className="exec-step-num">{i + 1}</span>
                  )}
                </div>
                <span className="exec-step-label">{t(step.labelKey)}</span>
              </div>
            );
          })}
        </div>

        <div className="execution-elapsed">
          {t('exec_elapsed')}: <strong>{elapsedSec}{t('exec_seconds')}</strong>
        </div>

        <div className="execution-config-summary">
          <span className="config-summary-item"><strong>{t('role_challenger')}:</strong> {config.challenger}</span>
          <span className="config-summary-sep">·</span>
          <span className="config-summary-item"><strong>{t('role_champion')}:</strong> {config.champion}</span>
          {config.beta && (
            <>
              <span className="config-summary-sep">·</span>
              <span className="config-summary-item"><strong>β:</strong> {config.beta}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
