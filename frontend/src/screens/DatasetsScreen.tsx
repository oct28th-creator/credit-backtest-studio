import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { Sample, CustomDataset, CustomStrategy, DatasetColumn, Language, MappingResult } from '../types';
import Icon from '../components/Icon';
import API from '../api/client';

interface DatasetsScreenProps {
  language: Language;
  builtinSamples: Sample[];
  customDatasets: CustomDataset[];
  customStrategies: CustomStrategy[];
  onChange: () => void;
}

const DEFAULT_REQUIRED_INPUTS = [
  'score', 'dti', 'mob', 'inquiries_6m', 'utilization', 'delinquency_12m',
  'income', 'loan_amount', 'tenure', 'open_accounts', 'credit_limit', 'age', 'region',
];

const PROTECTED_ROLES = ['gender', 'age_band', 'channel'];
const BUSINESS_ROLES = ['loan_amount', 'limit_increase'];

export default function DatasetsScreen({ language, builtinSamples, customDatasets, customStrategies, onChange }: DatasetsScreenProps) {
  const { t } = useTranslation();
  const [columns, setColumns] = useState<DatasetColumn[] | null>(null);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [nRows, setNRows] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [strategyId, setStrategyId] = useState('');
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [roleColumns, setRoleColumns] = useState<Record<string, string>>({});
  const [savingMap, setSavingMap] = useState(false);
  const [mapResult, setMapResult] = useState<MappingResult | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);

  const selectedStrategy = customStrategies.find(s => s.id === strategyId);
  const requiredInputs = selectedStrategy ? selectedStrategy.required_inputs : DEFAULT_REQUIRED_INPUTS;

  function resetMapping() {
    setMapping({});
    setRoleColumns({});
    setMapResult(null);
    setMapError(null);
  }

  async function openColumns(id: string) {
    setUploadError(null);
    setDatasetId(id);
    resetMapping();
    try {
      const res = await API.getDatasetColumns(id);
      setColumns(res.columns);
      setNRows(res.n_rows);
    } catch (e) {
      setUploadError((e as Error).message);
    }
  }

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    resetMapping();
    try {
      const res = await API.uploadDataset(file);
      setDatasetId(res.id);
      setColumns(res.columns);
      setNRows(res.n_rows);
      onChange();
    } catch (err) {
      setUploadError((err as Error).message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleDelete(id: string) {
    try {
      await API.deleteCustomDataset(id);
      if (datasetId === id) { setColumns(null); setDatasetId(null); }
      onChange();
    } catch { /* ignore */ }
  }

  async function handleSaveMapping() {
    if (!datasetId) return;
    setSavingMap(true);
    setMapResult(null);
    setMapError(null);
    try {
      const res = await API.saveMapping({
        dataset_id: datasetId,
        strategy_id: strategyId,
        mapping,
        role_columns: roleColumns,
      });
      setMapResult(res);
    } catch (e) {
      setMapError((e as Error).message);
    } finally {
      setSavingMap(false);
    }
  }

  const colOptions = (columns ?? []).map(c => c.name);
  const ColSelect = ({ value, onChange: onSel }: { value: string; onChange: (v: string) => void }) => (
    <select className="sel" value={value} onChange={e => onSel(e.target.value)} style={{ width: '100%' }}>
      <option value="">—</option>
      {colOptions.map(c => <option key={c} value={c}>{c}</option>)}
    </select>
  );

  return (
    <div className="page">
      <div className="page-hd">
        <div>
          <div className="page-title">{t('data_page_title')}</div>
          <div className="page-sub">{t('data_page_sub')}</div>
        </div>
        <button className="btn primary lg" type="button" onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? <span className="ai-spin" /> : <Icon name="plus" size={12} />} {t('data_upload')}
        </button>
        <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={onPickFile} />
      </div>

      {uploadError && (
        <div className="text-xs mb16" style={{ color: 'var(--amber)' }}>
          <Icon name="warn" size={12} /> {uploadError}
        </div>
      )}

      {columns && (
        <div className="card mb16">
          <div className="card-hd">
            <div>
              <div className="card-title">{t('data_col_preview')}</div>
              <div className="card-sub">{(nRows / 1000).toFixed(1)}k {t('data_rows_unit')} · {columns.length} {t('data_cols_unit')}</div>
            </div>
            <button className="btn" type="button" onClick={() => { setColumns(null); setDatasetId(null); }}>
              <Icon name="x" size={12} />
            </button>
          </div>
          <div className="card-body">
            <div style={{ overflowX: 'auto' }}>
              <table className="text-xs" style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', padding: '4px 8px' }}>{t('data_col_name')}</th>
                    <th style={{ textAlign: 'left', padding: '4px 8px' }}>{t('data_col_dtype')}</th>
                    <th style={{ textAlign: 'left', padding: '4px 8px' }}>{t('data_col_sample')}</th>
                  </tr>
                </thead>
                <tbody>
                  {columns.map(c => (
                    <tr key={c.name}>
                      <td className="num bold" style={{ padding: '4px 8px' }}>{c.name}</td>
                      <td className="muted" style={{ padding: '4px 8px' }}>{c.dtype}</td>
                      <td className="muted num" style={{ padding: '4px 8px' }}>{c.sample_values.slice(0, 3).join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="divider" />

            <div className="card-title mb8">{t('data_mapping_title')}</div>
            <div className="mb8">
              <div className="text-xs muted bold" style={{ marginBottom: 4 }}>{t('data_map_strategy')}</div>
              <select
                className="sel"
                value={strategyId}
                onChange={e => { setStrategyId(e.target.value); setMapping({}); setMapResult(null); }}
                style={{ width: '100%' }}
              >
                <option value="">{t('data_map_builtin')}</option>
                {customStrategies.map(s => <option key={s.id} value={s.id}>{s.name} ({s.version})</option>)}
              </select>
            </div>

            <div className="text-xs muted bold mb8">{t('data_map_inputs')}</div>
            <div className="g2" style={{ gap: 8 }}>
              {requiredInputs.map(inp => (
                <div key={inp}>
                  <div className="text-xs muted" style={{ marginBottom: 2 }}>{inp}</div>
                  <ColSelect value={mapping[inp] ?? ''} onChange={v => setMapping(m => ({ ...m, [inp]: v }))} />
                </div>
              ))}
            </div>

            <div className="divider" />
            <div className="text-xs muted bold mb8">{t('data_role_outcome')}</div>
            <ColSelect value={roleColumns.outcome ?? ''} onChange={v => setRoleColumns(r => ({ ...r, outcome: v }))} />

            <div className="text-xs muted bold mb8" style={{ marginTop: 12 }}>{t('data_role_protected')}</div>
            <div className="g3" style={{ gap: 8 }}>
              {PROTECTED_ROLES.map(role => (
                <div key={role}>
                  <div className="text-xs muted" style={{ marginBottom: 2 }}>{role}</div>
                  <ColSelect value={roleColumns[role] ?? ''} onChange={v => setRoleColumns(r => ({ ...r, [role]: v }))} />
                </div>
              ))}
            </div>

            <div className="text-xs muted bold mb8" style={{ marginTop: 12 }}>{t('data_role_business')}</div>
            <div className="g2" style={{ gap: 8 }}>
              {BUSINESS_ROLES.map(role => (
                <div key={role}>
                  <div className="text-xs muted" style={{ marginBottom: 2 }}>{role}</div>
                  <ColSelect value={roleColumns[role] ?? ''} onChange={v => setRoleColumns(r => ({ ...r, [role]: v }))} />
                </div>
              ))}
            </div>

            <div className="mt8">
              <button className="btn primary" type="button" onClick={handleSaveMapping} disabled={savingMap}>
                {savingMap ? <span className="ai-spin" /> : <Icon name="check" size={12} />} {t('data_save_mapping')}
              </button>
            </div>

            {mapError && (
              <div className="text-xs mt8" style={{ color: 'var(--amber)' }}>
                <Icon name="warn" size={12} /> {mapError}
              </div>
            )}

            {mapResult && (
              <div className="mt8">
                <div className="flex" style={{ gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
                  {(['l1', 'l2', 'l3', 'l4', 'l5'] as const).map(layer => (
                    <span key={layer} className={`tag ${mapResult.available_layers[layer] ? 'green' : ''}`}>
                      {mapResult.available_layers[layer] ? '✓' : '–'} {layer.toUpperCase()} {mapResult.available_layers[layer] ? t('data_layer_available') : t('data_layer_skipped')}
                    </span>
                  ))}
                </div>
                {mapResult.warnings.length > 0 && (
                  <div className="text-xs" style={{ color: 'var(--amber)' }}>
                    {mapResult.warnings.map((w, i) => <div key={i}><Icon name="warn" size={11} /> {w}</div>)}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="cmp-grid">
        {builtinSamples.map(s => (
          <div key={s.id} className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">{language === 'zh' ? s.name_zh : s.name_en}</div>
                <div className="card-sub num">{s.vintage} · {(s.n_rows / 1000).toFixed(0)}k {t('data_rows_unit')}</div>
              </div>
              <span className="tag green">{t('strat_builtin_badge')}</span>
            </div>
            <div className="card-body">
              <div className="text-xs muted" style={{ lineHeight: 1.6 }}>
                {language === 'zh' ? s.product_mix_zh : s.product_mix_en}<br />
                {language === 'zh' ? s.channels_zh : s.channels_en}
              </div>
            </div>
          </div>
        ))}

        {customDatasets.map(d => (
          <div key={d.id} className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">{d.name}</div>
                <div className="card-sub num">{(d.n_rows / 1000).toFixed(1)}k {t('data_rows_unit')} · {d.columns.length} {t('data_cols_unit')}</div>
              </div>
              <span className="tag blue">{t('strat_custom_badge')}</span>
            </div>
            <div className="card-body">
              <div className="flex" style={{ gap: 6 }}>
                <button className="btn" type="button" onClick={() => openColumns(d.id)}>
                  <Icon name="eye" size={12} /> {t('data_view_columns')}
                </button>
                <button className="btn" type="button" onClick={() => handleDelete(d.id)}>
                  <Icon name="x" size={12} /> {t('strat_delete')}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
