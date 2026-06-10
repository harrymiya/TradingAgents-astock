import React, { useState, useCallback } from 'react';
import './ScreeningPanel.css';

const API_URL = '/api/screening';
const QT_API = 'https://qt.gtimg.cn/q=';
const STRATEGY_META = {
  pipeline: { label: '流水线选股', icon: '📋', desc: 'S3超跌反弹 + 三买v2 并集' },
  s3: { label: 'S3选股', icon: '⚡', desc: '超跌反弹(位<20,涨3-7%,vr1.2-2.5,MA20<-8%)' },
  sanmai: { label: '三买选股', icon: '🔱', desc: '中枢突破+回抽不破ZG' },
  sanyin: { label: '三阴选股', icon: '🌧️', desc: '涨停启动→3日缩量回调→今日企稳' },
};

async function fetchRealTimePrices(codes) {
  if (!codes || codes.length === 0) return {};
  // 每批30个，从腾讯API拉实时数据
  const results = {};
  const BATCH = 30;
  for (let i = 0; i < codes.length; i += BATCH) {
    const batch = codes.slice(i, i + BATCH);
    const qtCodes = batch.map(c => (c.startsWith('6') ? 'sh' : 'sz') + c);
    try {
      const resp = await fetch(`${QT_API}${qtCodes.join(',')}&_=${Date.now()}`);
      const buf = await resp.arrayBuffer();
      const decoder = new TextDecoder('gb18030');
      const text = decoder.decode(buf);
      for (const line of text.split(';')) {
        if (!line.trim() || !line.includes('~')) continue;
        const parts = line.split('~');
        const codeMatch = (parts[0] || '').match(/(\d{6})/);
        const code = codeMatch ? codeMatch[1] : null;
        if (!code) continue;
        const price = parseFloat(parts[3]) || 0;
        const chg = parseFloat(parts[32]) || 0;
        results[code] = { price, chg };
      }
    } catch (e) {
      console.warn('QT batch error:', e);
    }
  }
  return results;
}

export default function ScreeningPanel({ onSelectScreening, selectedCode }) {
  const [activeStrategy, setActiveStrategy] = useState(null);
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState({});
  const [error, setError] = useState({});

  const runStrategy = useCallback(async (strategy) => {
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
        // 拉取实时行情替换chg和close
        const codes = (data.results || []).map(r => r.code);
        const realTime = await fetchRealTimePrices(codes);
        const merged = (data.results || []).map(r => {
          const rt = realTime[r.code];
          if (rt) {
            return { ...r, chg: rt.chg, close: rt.price };
          }
          return r;
        });
        setResults(prev => ({ ...prev, [strategy]: { ...data, results: merged } }));
      }
    } catch (e) {
      setError(prev => ({ ...prev, [strategy]: e.message }));
    } finally {
      setLoading(prev => ({ ...prev, [strategy]: false }));
    }
  }, [results]);

  const handleClickStock = (item) => {
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
                  <span className="screening-name">{item.name}</span>
                  <span className={`screening-chg ${chg >= 0 ? 'up' : 'down'}`}>
                    {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%
                  </span>
                  <span className="screening-price">{item.close?.toFixed(2)}</span>
                </div>
                {item.strategy && (
                  <div className="screening-item-detail">
                    <span className="screening-strategy-tag">{item.strategy}</span>
                    <span className="screening-detail-text">{item.detail || ''}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {activeStrategy && !loading[activeStrategy] && currentData && currentResults.length === 0 && (
        <div className="screening-empty">暂无符合条件的股票</div>
      )}
    </div>
  );
}
