import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { Screen, Language, RunResult, ExperimentConfig, Strategy, Sample, AIAnalysis, CustomStrategy, CustomDataset } from './types';
import Sidebar from './components/Sidebar';
import ConfigScreen from './screens/ConfigScreen';
import ExecutionScreen from './screens/ExecutionScreen';
import ResultsScreen from './screens/ResultsScreen';
import HistoryScreen from './screens/HistoryScreen';
import ExperimentListScreen from './screens/ExperimentListScreen';
import StrategiesScreen from './screens/StrategiesScreen';
import DatasetsScreen from './screens/DatasetsScreen';
import ReportModal from './components/ReportModal';
import Icon from './components/Icon';
import API from './api/client';
import './styles.css';

export default function App() {
  const { t, i18n } = useTranslation();
  const [screen, setScreen] = useState<Screen>('config');
  const [language, setLanguage] = useState<Language>((localStorage.getItem('backtest-lang') as Language) ?? 'zh');
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [strategyAnalysis, setStrategyAnalysis] = useState<{ analysis: AIAnalysis | null; thinking: string } | null>(null);
  const [pendingConfig, setPendingConfig] = useState<ExperimentConfig | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [customStrategies, setCustomStrategies] = useState<CustomStrategy[]>([]);
  const [customDatasets, setCustomDatasets] = useState<CustomDataset[]>([]);
  const [showReport, setShowReport] = useState(false);
  const [loading, setLoading] = useState(true);
  const [aiOn, setAiOn] = useState(true);

  function refreshCustomStrategies() {
    API.listCustomStrategies().then(r => setCustomStrategies(r.strategies)).catch(() => {});
  }
  function refreshCustomDatasets() {
    API.listCustomDatasets().then(r => setCustomDatasets(r.datasets)).catch(() => {});
  }

  useEffect(() => {
    Promise.all([API.listStrategies(), API.listSamples()])
      .then(([stRes, smRes]) => {
        setStrategies(stRes.strategies);
        setSamples(smRes.samples);
      })
      .finally(() => setLoading(false));
    API.listCustomStrategies().then(r => setCustomStrategies(r.strategies)).catch(() => {});
    API.listCustomDatasets().then(r => setCustomDatasets(r.datasets)).catch(() => {});
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

  function handleExecutionDone(result: RunResult, analysis: AIAnalysis | null, thinking: string) {
    setRunResult(result);
    setStrategyAnalysis({ analysis, thinking });
    setScreen('results');
  }

  function handleResultUpdate(r: RunResult) {
    setRunResult(r);
  }

  function handleOpenRun(runId: string) {
    API.getRun(runId).then(r => {
      setRunResult(r);
      setStrategyAnalysis(null);
      setScreen('results');
    }).catch(() => {});
  }

  const screenLabels: Record<Screen, string> = {
    config: t('screen_config'),
    execution: t('screen_execution'),
    results: t('screen_results'),
    history: t('screen_history'),
    list: t('screen_list'),
    strategies: t('screen_strategies'),
    datasets: t('screen_datasets'),
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--ink-4)' }}>
        <span className="dots" style={{ marginRight: 10 }}>
          <span className="dot" /><span className="dot" /><span className="dot" />
        </span>
        {t('loading')}
      </div>
    );
  }

  return (
    <div className="layout">
      <Sidebar
        screen={screen}
        onNav={(s: Screen) => setScreen(s)}
        aiOn={aiOn}
        onToggleAi={() => setAiOn(v => !v)}
      />

      <div className="main">
        {/* Top Bar */}
        <header className="topbar">
          <div className="crumbs">
            <span>ACE BackTest Studio</span>
            <span className="sep">/</span>
            <b>{screenLabels[screen] || screen}</b>
            {runResult && screen === 'results' && (
              <>
                <span className="sep">/</span>
                <span style={{ fontSize: 12, color: 'var(--ink-4)', fontFamily: 'var(--mono)' }}>{runResult.run_id}</span>
              </>
            )}
          </div>
          <div className="topbar-end">
            <button
              className="lang-btn"
              onClick={handleLanguageToggle}
              type="button"
            >
              {language === 'zh' ? 'EN' : '中'}
            </button>
            <div className="avatar">CM</div>
          </div>
        </header>

        {/* Main Content */}
        <main className="content">
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
              aiOn={aiOn}
              onDone={handleExecutionDone}
            />
          )}

          {screen === 'results' && runResult && (
            <ResultsScreen
              result={runResult}
              strategies={strategies}
              samples={samples}
              language={language}
              aiOn={aiOn}
              strategyAnalysis={strategyAnalysis}
              onResultUpdate={handleResultUpdate}
              onNewRun={() => setScreen('config')}
              onGenerateReport={() => setShowReport(true)}
            />
          )}

          {screen === 'strategies' && (
            <StrategiesScreen
              language={language}
              builtinStrategies={strategies}
              customStrategies={customStrategies}
              onChange={refreshCustomStrategies}
            />
          )}

          {screen === 'datasets' && (
            <DatasetsScreen
              language={language}
              builtinSamples={samples}
              customDatasets={customDatasets}
              customStrategies={customStrategies}
              onChange={refreshCustomDatasets}
            />
          )}

          {screen === 'list' && (
            <ExperimentListScreen
              onOpen={handleOpenRun}
              onNewRun={() => setScreen('config')}
            />
          )}

          {screen === 'history' && (
            <HistoryScreen
              language={language}
              onViewRun={(runId) => {
                API.getRun(runId).then(r => {
                  setRunResult(r);
                  setStrategyAnalysis(null);
                  setScreen('results');
                });
              }}
            />
          )}
        </main>
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
