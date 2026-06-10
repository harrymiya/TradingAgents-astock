import React, { useState } from 'react';
import './ScreeningPanel.css';

const API_URL = '/api/screening';
const STRATEGY_META = {
  pipeline: { label: '流水线选股', icon: '📋', desc: 'S3超跌反弹 + 三买v2 并集' },
  s3: { label: 'S3选股', icon: '⚡', desc: '超跌反弹(位<20,涨3-7%,vr1.2-2.5,MA20<-8%)' },
  sanmai: { label: '三买选股', icon: '🔱', desc: '中枢突破+回抽不破ZG' },
  sanyin: { label: '三阴选股', icon: '🌧️', desc: '涨停启动→3日缩量回调→今日企稳' },
};

export default function ScreeningPanel({ onSelectScreening, selectedCode }) {
  const [activeStrategy, setActiveStrategy] = useState(null);
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState({});
  const [error, setError] = useState({});

  const runStrategy = async (strategy) => {
    setActiveStrategy(strategy);
    if (results[strategy]) return;

    setLoading(prev => ({ ...prev, [strategy]: true }));
    setError(prev => ({ ...prev, [strategy]: null }));

    try {
      const resp = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: strategy }),
      });
      const data = await resp.json();
      if (data.error) {
        setError(prev => ({ ...prev, [strategy]: data.error }));
      } else {
        setResults(prev => ({ ...prev, [strategy]: data }));
      }
    } catch (e) {
      setError(prev => ({ ...prev, [strategy]: e.message }));
    } finally {
      setLoading(prev => ({ ...prev, [strategy]: false }));
    }
  };

  const handleClickStock = (item) => {
    // 不切换tab，只通知父组件跳产业链+选中
    if (onSelectScreening) {
      onSelectScreening(item);
    }
  };

  const currentData = activeStrategy ? results[activeStrategy] : null;
  const currentResults = currentData?.results || [];
  const currentMeta = STRATEGY_META[activeStrategy] || {};

  return (
    <div className="screening-panel">
      <h3>🔍 选股策略</h3>
      <div className="strategy-buttons">
        {Object.entries(STRATEGY_META).map(([key, meta]) => (
          <button
            key={key}
            className={`strategy-btn ${activeStrategy === key ? 'active' : ''} ${loading[key] ? 'loading' : ''}`}
            onClick={() => runStrategy(key)}
            disabled={loading[key]}
            title={meta.desc}
          >
            <span className="strategy-icon">{meta.icon}</span>
            <span className="strategy-label">{meta.label}</span>
            {loading[key] && <span className="spin">⏳</span>}
          </button>
        ))}
      </div>

      {error[activeStrategy] && (
        <div className="screening-error">{error[activeStrategy]}</div>
      )}

      {activeStrategy && !loading[activeStrategy] && currentData && (
        <div className="screening-summary">
          共 {currentData.count} 只符合条件的股票
          {currentData.s3_count !== undefined && (
            <> (S3: {currentData.s3_count} | 三买: {currentData.sanmai_count})</>
          )}
        </div>
      )}

      {loading[activeStrategy] && (
        <div className="screening-loading">⏳ 正在扫描全市场...</div>
      )}

      {activeStrategy && currentResults.length > 0 && (
        <div className="screening-results">
          {currentResults.map((item) => {
            const isSelected = selectedCode && item.code === selectedCode;
            const chg = parseFloat(item.chg) || 0;
            return (
              <div
                key={item.code}
                className={`screening-item ${isSelected ? 'selected' : ''}`}
                onClick={() => handleClickStock(item)}
              >
                <div className="screening-item-header">
                  <span className="screening-code">{item.code}</span>
                  <span className="screening-name" title={item.name}>{item.name}</span>
                  <span className={`screening-chg ${chg >= 0 ? 'up' : 'down'}`}>
                    {chg > 0 ? '+' : ''}{chg.toFixed(2)}%
                  </span>
                  <span className="screening-price">{parseFloat(item.close || 0).toFixed(2)}</span>
                </div>
                <div className="screening-item-detail">
                  <span className="screening-strategy-tag">{item.strategy}</span>
                  <span className="screening-detail-text">{item.detail}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {activeStrategy && !loading[activeStrategy] && currentResults.length === 0 && !error[activeStrategy] && (
        <div className="screening-empty">暂无符合条件的股票</div>
      )}
    </div>
  );
}
