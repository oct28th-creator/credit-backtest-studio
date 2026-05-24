import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from './Icon';

interface SliceFilterProps {
  onSliceChange: (dim: string | null, value: string | null) => void;
  currentDim: string | null;
  currentValue: string | null;
}

const SLICE_DIMS = [
  { key: 'all', labelKey: 'slice_all', values: [] },
  { key: 'channel', labelKey: 'slice_channel', values: ['online', 'offline', 'app'] },
  { key: 'vintage', labelKey: 'slice_vintage', values: ['2023-11', '2023-10', '2023-12'] },
  { key: 'product', labelKey: 'slice_product', values: ['credit_card', 'consumer_loan'] },
  { key: 'age_band', labelKey: 'slice_age_band', values: ['18-25', '26-35', '36-45', '46+'] },
];

export default function SliceFilter({ onSliceChange, currentDim, currentValue }: SliceFilterProps) {
  const { t } = useTranslation();
  const [activeDim, setActiveDim] = useState<string | null>(currentDim);
  const [showValues, setShowValues] = useState(false);
  const [pulse, setPulse] = useState(false);

  function selectDim(key: string) {
    if (key === 'all') {
      setActiveDim(null);
      setShowValues(false);
      onSliceChange(null, null);
      flashPulse();
      return;
    }
    if (activeDim === key) {
      setShowValues(v => !v);
    } else {
      setActiveDim(key);
      setShowValues(true);
    }
  }

  function selectValue(dimKey: string, val: string) {
    onSliceChange(dimKey, val);
    flashPulse();
  }

  function flashPulse() {
    setPulse(true);
    setTimeout(() => setPulse(false), 2000);
  }

  const selectedDimObj = SLICE_DIMS.find(d => d.key === activeDim);

  return (
    <>
      <div className="slice-bar">
        <span className="slice-lbl">{t('slice_title')}</span>
        {SLICE_DIMS.map(dim => (
          <button
            key={dim.key}
            className={`slice-chip ${(dim.key === 'all' && !activeDim) || activeDim === dim.key ? 'on' : ''}`}
            onClick={() => selectDim(dim.key)}
            type="button"
          >
            {t(dim.labelKey)}
            {dim.values.length > 0 && (
              <Icon name={showValues && activeDim === dim.key ? 'chevron_up' : 'chevron_down'} size={12} />
            )}
          </button>
        ))}
        {pulse && (
          <span className="slice-status">{t('slice_updated')}</span>
        )}
      </div>

      {showValues && selectedDimObj && selectedDimObj.values.length > 0 && (
        <div className="slice-sub">
          {selectedDimObj.values.map(val => (
            <button
              key={val}
              className={`slice-chip ${currentDim === selectedDimObj.key && currentValue === val ? 'on' : ''}`}
              onClick={() => selectValue(selectedDimObj.key, val)}
              type="button"
            >
              {val}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
