import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { Screen, Language, RunResult, ExperimentConfig, Strategy, Sample } from './types';
import Sidebar from './components/Sidebar';
import ConfigScreen from './screens/ConfigScreen';
import ExecutionScreen from './screens/ExecutionScreen';
import ResultsScreen from './screens/ResultsScreen';
import HistoryScreen from './screens/HistoryScreen';
import ReportModal from './components/ReportModal';
import Icon from './components/Icon';
import API from './api/client';
import './styles.css';

export default function App() {
  const { t, i18n } = useTranslation();
  const [screen, setScreen] = useState<Screen>('config');
  const [language, setLanguage] = useState<Language>((localStorage.getItem('backtest-lang') as Language) ?? 'zh');
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [pendingConfig, setPendingConfig] = useState<ExperimentConfig | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [showReport, setShowReport] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([API.listStrategies(), API.listSamples()])
      .then(([stRes, smRes]) => {
        setStrategies(stRes.strategies);
        setSamples(smRes.samples);
      })
      .finally(() => setLoading(false));
  }, []);

  function handleLanguageToggle() {
    const next: Language = language === 'zh' ? 'en' : 'zh';
    setLanguage(next);
    i18n.changeLanguage(next);
    localStorage.setItem('backtest-lang', next);
  }

  function handleRun(config: ExperimentConfig) {
    setPendingConfig({ ...config, language });
    setScreen('execution');
  }

  function handleExecutionDone(result: RunResult) {
    setRunResult(result);
    setScreen('results');
  }

  function handleResultUpdate(r: RunResult) {
    setRunResult(r);
  }

  const breadcrumbs: Record<Screen, string> = {
    config: t('nav_config'),
    execution: t('nav_execution'),
    results: t('nav_results'),
    history: t('nav_history'),
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--ink-4)' }}>
        <span className="dots-spinner" style={{ marginRight: 10 }} />
        {t('loading')}
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar
        screen={screen}
        onNav={setScreen}
        hasResult={!!runResult}
      />

      <div className="main-area">
        {/* Top Bar */}
        <header className="topbar">
          <div className="topbar-breadcrumb">
            <strong>{t('app_name')}</strong>
            <span style={{ margin: '0 8px', color: 'var(--ink-6)' }}>›</span>
            <span>{breadcrumbs[screen]}</span>
          </div>
          <div className="topbar-actions">
            {screen === 'results' && runResult && (
              <button
                className="btn-primary btn-sm"
                onClick={() => setShowReport(true)}
                type="button"
              >
                <Icon name="download" size={14} />
                {t('results_generate_report')}
              </button>
            )}
            <button
              className="btn-ghost btn-sm"
              onClick={handleLanguageToggle}
              type="button"
              title={t('language')}
            >
              <Icon name="globe" size={14} />
              {language === 'zh' ? 'EN' : '中'}
            </button>
          </div>
        </header>

        {/* Main Content */}
        <div className="main-scroll">
          {screen === 'config' && (
            <ConfigScreen
              strategies={strategies}
              samples={samples}
              language={language}
              onRun={handleRun}
            />
          )}

          {screen === 'execution' && pendingConfig && (
            <ExecutionScreen
              config={pendingConfig}
              onDone={handleExecutionDone}
            />
          )}

          {screen === 'results' && runResult && (
            <ResultsScreen
              result={runResult}
              strategies={strategies}
              samples={samples}
              language={language}
              onResultUpdate={handleResultUpdate}
            />
          )}

          {screen === 'history' && (
            <HistoryScreen
              language={language}
              onViewRun={(runId) => {
                API.getRun(runId).then(r => {
                  setRunResult(r);
                  setScreen('results');
                });
              }}
            />
          )}
        </div>
      </div>

      {/* Report Modal */}
      {showReport && runResult && (
        <ReportModal
          runId={runResult.run_id}
          language={language}
          onClose={() => setShowReport(false)}
        />
      )}
    </div>
  );
}
