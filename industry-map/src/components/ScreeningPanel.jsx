import React, { useState, useEffect, useCallback } from 'react';
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

/** 分析状态信息显示组件 */
function AnalysisInfo({ analysisResult, analysisError, analyzing }) {
  if (analyzing) {
    return <div className="analysis-info analyzing">⏳ 正在深度分析（8位分析师辩论中，约3-5分钟）...</div>;
  }
  if (analysisError) {
    return <div className="analysis-info error">❌ 分析失败: {analysisError}</div>;
  }
  if (analysisResult && analysisResult.status === 'ok') {
    const r = analysisResult;
    return (
      <div className="analysis-info done">
        <div><strong>✅ 分析完成</strong>（{r.elapsed || '?'}秒）</div>
        {r.judge_decision && (
          <div className="analysis-judge">⚖️ 裁判判决: {r.judge_decision.slice(0, 200)}</div>
        )}
        {r.trader_plan && (
          <div className="analysis-plan">📋 交易计划: {r.trader_plan.slice(0, 200)}</div>
        )}
      </div>
    );
  }
  return null;
}

export default function ScreeningPanel({ onSelectScreening, selectedCode, refreshKey }) {
  const [activeStrategy, setActiveStrategy] = useState(null);
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState({});
  const [error, setError] = useState({});
  // 异步分析状态
  const [analysisState, setAnalysisState] = useState({});  // { code: { analyzing, result, error } }

  // refreshKey变化时，重拉当前策略的实时行情
  useEffect(() => {
    if (!activeStrategy || !results[activeStrategy]) return;
    const data = results[activeStrategy];
    const codes = (data.results || []).map(r => r.code);
    if (codes.length === 0) return;
    
    const updatePrices = async () => {
      const realTime = await fetchRealTimePrices(codes);
      const merged = (data.results || []).map(r => {
        const rt = realTime[r.code];
        if (rt) return { ...r, chg: rt.chg, close: rt.price };
        return r;
      });
      setResults(prev => ({ ...prev, [activeStrategy]: { ...data, results: merged } }));
    };
    updatePrices();
  }, [refreshKey]);

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

  /** 启动分析 + 轮询状态 */
  const startAnalysis = useCallback(async (code) => {
    setAnalysisState(prev => ({ ...prev, [code]: { analyzing: true, result: null, error: null } }));

    try {
      // 提交分析任务
      const resp = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'analyze_stock', code }),
      });
      const data = await resp.json();

      if (data.cached && data.result) {
        setAnalysisState(prev => ({ ...prev, [code]: { analyzing: false, result: data.result, error: null } }));
        return;
      }

      if (data.error) {
        setAnalysisState(prev => ({ ...prev, [code]: { analyzing: false, result: null, error: data.error } }));
        return;
      }

      const taskId = data.task_id;
      if (!taskId) {
        setAnalysisState(prev => ({ ...prev, [code]: { analyzing: false, result: null, error: '无task_id' } }));
        return;
      }

      // 轮询结果
      let attempts = 0;
      const maxAttempts = 120;  // 最多等10分钟（5秒/次）
      const poll = async () => {
        attempts++;
        try {
          const statusResp = await fetch(`/api/analyze_status?task_id=${taskId}&code=${code}`);
          const status = await statusResp.json();

          if (status.status === 'ok' && status.result) {
            setAnalysisState(prev => ({ ...prev, [code]: { analyzing: false, result: status.result, error: null } }));
            return;
          }
          if (status.status === 'error') {
            setAnalysisState(prev => ({ ...prev, [code]: { analyzing: false, result: null, error: status.error } }));
            return;
          }
        } catch (e) {
          // 轮询错误忽略，继续重试
        }

        if (attempts < maxAttempts) {
          setTimeout(poll, 5000);
        } else {
          setAnalysisState(prev => ({ ...prev, [code]: { analyzing: false, result: null, error: '分析超时' } }));
        }
      };

      poll();
    } catch (e) {
      setAnalysisState(prev => ({ ...prev, [code]: { analyzing: false, result: null, error: e.message } }));
    }
  }, []);

  const handleClickStock = useCallback((item) => {
    // 通知父组件（跳产业链/选中）
    if (onSelectScreening) {
      onSelectScreening(item);
    }
    // 启动异步分析
    if (item.code) {
      startAnalysis(item.code);
    }
  }, [onSelectScreening, startAnalysis]);

  const currentData = activeStrategy ? results[activeStrategy] : null;
  const currentResults = currentData?.results || [];
  const currentMeta = STRATEGY_META[activeStrategy] || {};

  // 当前选中股票的分析状态
  const selectedAnalysis = selectedCode ? analysisState[selectedCode] : null;

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

      {/* 分析状态信息 */}
      {selectedCode && selectedAnalysis && (
        <AnalysisInfo
          analysisResult={selectedAnalysis.result}
          analysisError={selectedAnalysis.error}
          analyzing={selectedAnalysis.analyzing}
        />
      )}

      {error[activeStrategy] && (
        <div className="screening-error">{error[activeStrategy]}</div>
      )}

      {activeStrategy && !loading[activeStrategy] && currentData && (
        <div className="screening-summary">
          共 {currentData.count} 只 → Top10（评分排名）｜点击任一只启动深度分析
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
            const itemAnalysis = analysisState[item.code];
            const itemAnalyzing = itemAnalysis?.analyzing;
            return (
              <div
                key={item.code}
                className={`screening-item ${isSelected ? 'selected' : ''} ${itemAnalyzing ? 'analyzing' : ''}`}
                onClick={() => handleClickStock(item)}
              >
                <div className="screening-item-header">
                  <span className="screening-code">{item.code}</span>
                  <span className="screening-name">{item.name}</span>
                  {item.total_score !== undefined && (
                    <span className={`screening-score ${item.total_score >= 12 ? 'high' : item.total_score >= 9 ? 'mid' : ''}`}>
                      {item.total_score}分
                    </span>
                  )}
                  <span className={`screening-chg ${chg >= 0 ? 'up' : 'down'}`}>
                    {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%
                  </span>
                  <span className="screening-price">{item.close?.toFixed(2)}</span>
                  {itemAnalyzing && <span className="screening-spin">🔄</span>}
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
