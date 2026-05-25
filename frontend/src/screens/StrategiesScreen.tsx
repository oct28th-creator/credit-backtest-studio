import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { Strategy, CustomStrategy, Language } from '../types';
import Icon from '../components/Icon';
import API from '../api/client';

interface StrategiesScreenProps {
  language: Language;
  builtinStrategies: Strategy[];
  customStrategies: CustomStrategy[];
  onChange: () => void;
}

interface ValidationState {
  ok: boolean;
  error?: string;
  sample_metrics?: Record<string, number>;
}

export default function StrategiesScreen({ language, builtinStrategies, customStrategies, onChange }: StrategiesScreenProps) {
  const { t } = useTranslation();
  const [showUpload, setShowUpload] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [validation, setValidation] = useState<ValidationState | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!name) setName(file.name.replace(/\.py$/i, ''));
    const reader = new FileReader();
    reader.onload = () => setCode(String(reader.result ?? ''));
    reader.readAsText(file);
  }

  async function handleSubmit() {
    if (!code.trim()) return;
    setSubmitting(true);
    setValidation(null);
    try {
      const res = await API.uploadStrategy(name.trim(), code);
      setValidation(res.validation);
      if (res.validation?.ok) {
        onChange();
        setName('');
        setCode('');
      }
    } catch (e) {
      setValidation({ ok: false, error: (e as Error).message });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await API.deleteCustomStrategy(id);
      onChange();
    } catch { /* ignore */ }
  }

  return (
    <div className="page">
      <div className="page-hd">
        <div>
          <div className="page-title">{t('strat_page_title')}</div>
          <div className="page-sub">{t('strat_page_sub')}</div>
        </div>
        <button className="btn primary lg" type="button" onClick={() => setShowUpload(v => !v)}>
          <Icon name="plus" size={12} /> {t('strat_upload')}
        </button>
      </div>

      {showUpload && (
        <div className="card mb16">
          <div className="card-hd">
            <div>
              <div className="card-title">{t('strat_upload')}</div>
              <div className="card-sub">{t('strat_upload_sub')}</div>
            </div>
          </div>
          <div className="card-body">
            <div className="mb8">
              <div className="text-xs muted bold" style={{ marginBottom: 4 }}>{t('strat_upload_name')}</div>
              <input
                className="sel"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder={t('strat_upload_name')}
                style={{ width: '100%' }}
              />
            </div>
            <div className="mb8">
              <div className="flex" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <span className="text-xs muted bold">{t('strat_upload_code')}</span>
                <button className="btn" type="button" onClick={() => fileRef.current?.click()}>
                  <Icon name="download" size={12} /> {t('strat_upload_file')}
                </button>
                <input ref={fileRef} type="file" accept=".py" style={{ display: 'none' }} onChange={onPickFile} />
              </div>
              <textarea
                className="ai-ta"
                rows={10}
                value={code}
                onChange={e => setCode(e.target.value)}
                placeholder={t('strat_upload_placeholder')}
                style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: 12 }}
              />
            </div>
            <button className="btn primary" type="button" onClick={handleSubmit} disabled={submitting || !code.trim()}>
              {submitting ? <span className="ai-spin" /> : <Icon name="check" size={12} />} {t('strat_upload_submit')}
            </button>

            {validation && (
              <div className="mt8">
                {validation.ok ? (
                  <div className="text-xs" style={{ color: 'var(--green)' }}>
                    <Icon name="check" size={12} /> {t('strat_valid_ok')}
                    {validation.sample_metrics && (
                      <span className="muted" style={{ marginLeft: 8 }}>
                        {Object.entries(validation.sample_metrics).map(([k, v]) => `${k}=${v}`).join(' · ')}
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="text-xs" style={{ color: 'var(--amber)' }}>
                    <Icon name="warn" size={12} /> {t('strat_valid_fail')}: {validation.error}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="cmp-grid">
        {builtinStrategies.map(s => (
          <div key={s.id} className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">{language === 'en' ? (s.nickname_en ?? s.nickname) : s.nickname}</div>
                <div className="card-sub num">{s.id}</div>
              </div>
              <span className="tag green">{t('strat_builtin_badge')}</span>
            </div>
            <div className="card-body">
              <div className="text-xs muted" style={{ marginBottom: 8, lineHeight: 1.6 }}>
                {language === 'zh' ? s.desc_zh : s.desc_en}
              </div>
              <div className="flex" style={{ gap: 6, flexWrap: 'wrap' }}>
                <span className="tag blue">{t('strat_role')}: {s.role}</span>
                {s.score_cutoff != null && <span className="tag">cutoff {s.score_cutoff}</span>}
                <span className="tag">DTI {s.dti_limit}</span>
                <span className="tag">MOB {s.mob_months}</span>
              </div>
            </div>
          </div>
        ))}

        {customStrategies.map(s => (
          <div key={s.id} className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">{s.name}</div>
                <div className="card-sub num">{s.version} · {s.id}</div>
              </div>
              <span className="tag blue">{t('strat_custom_badge')}</span>
            </div>
            <div className="card-body">
              <div className="flex" style={{ gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                <span className="tag blue">{t('strat_role')}: {s.role}</span>
                {s.required_inputs.map(inp => <span key={inp} className="tag">{inp}</span>)}
              </div>
              {Object.keys(s.params).length > 0 && (
                <div className="text-xs muted" style={{ marginBottom: 8 }}>
                  {t('strat_params')}: {Object.keys(s.params).join(', ')}
                </div>
              )}
              <button className="btn" type="button" onClick={() => handleDelete(s.id)}>
                <Icon name="x" size={12} /> {t('strat_delete')}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
