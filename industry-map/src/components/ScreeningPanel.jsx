import React, { useState, useEffect, useCallback } from 'react';
import './ScreeningPanel.css';

const API_URL = '/api/screening';
const QT_API = 'https://qt.gtimg.cn/q=';

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
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [analysisState, setAnalysisState] = useState({});

  // 自动运行黄金坑
  const runGoldenPit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'golden_pit', realtime: true }),
      });
      const data = await resp.json();
      if (data.error) {
        setError(data.error);
      } else {
        setResults(data);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // 挂载时自动加载
  useEffect(() => {
    runGoldenPit();
  }, [runGoldenPit]);

  // refreshKey变化时刷新实时行情（不走新API调用，只覆盖chg）
  useEffect(() => {
    if (!results || !results.results || results.results.length === 0) return;
    const codes = results.results.map(r => r.code);
    const updatePrices = async () => {
      const realTime = await fetchRealTimePrices(codes);
      const merged = results.results.map(r => {
        const rt = realTime[r.code];
        if (rt) return { ...r, chg: rt.chg, close: rt.price };
        return r;
      });
      setResults(prev => ({ ...prev, results: merged }));
    };
    updatePrices();
  }, [refreshKey]);

  const startAnalysis = useCallback(async (code) => {
    setAnalysisState(prev => ({ ...prev, [code]: { analyzing: true, result: null, error: null } }));
    try {
      const resp = await fetch('/api/analyze_stock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
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
      let attempts = 0;
      const maxAttempts = 120;
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
        } catch (e) {}
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
    if (onSelectScreening) onSelectScreening(item);
    if (item.code) startAnalysis(item.code);
  }, [onSelectScreening, startAnalysis]);

  const currentData = results;
  const currentResults = results?.results || [];

  // 当前选中股票的分析状态
  const selectedAnalysis = selectedCode ? analysisState[selectedCode] : null;

  // 信号统计
  const g1 = currentResults.filter(r => r.total_score >= 15).length;
  const g2 = currentResults.filter(r => r.total_score >= 10 && r.total_score < 15).length;
  const g3 = currentResults.filter(r => r.total_score < 10).length;

  return (
    <div className="screening-panel">
      <h3>🕳️ 黄金坑选股 <span className="gp-version-badge">V3</span></h3>

      {error && <div className="screening-error">{error}</div>}

      {currentData && !error && (
        <div className="screening-summary">
          <div className="summary-row">
            <span className="summary-count">共 {currentData.count} 只 → Top{Math.min(currentResults.length, 15)}</span>
          </div>
          <div className="summary-row market-row">
            <span className={`market-tag-${currentData.market_tag?.includes('强势') ? 'up' : currentData.market_tag?.includes('弱势') ? 'down' : 'mid'}`}>
              {currentData.market_tag || '?'}
            </span>
            <span className="summary-detail">涨跌比{currentData.market_up_ratio}%</span>
            <span className="summary-detail">ma60&gt;{currentData.ma60_threshold}%</span>
            {currentData.market_warning && (
              <span className="summary-warning">{currentData.market_warning.replace(/→ma60.*/,'')}</span>
            )}
          </div>
          <div className="summary-row signal-dist">
            {g1 > 0 && <span className="signal-count s1">⭐1×{g1}</span>}
            {g2 > 0 && <span className="signal-count s2">✨2×{g2}</span>}
            {g3 > 0 && <span className="signal-count s3">🔹3×{g3}</span>}
          </div>
          <div className="summary-row hint">
            点击任一只启动TradingAgents深度分析
          </div>
        </div>
      )}

      {loading && !currentData && (
        <div className="screening-loading">⏳ 正在扫描优质产业链黄金坑...</div>
      )}

      {/* 分析状态信息 */}
      {selectedCode && selectedAnalysis && (
        <AnalysisInfo
          analysisResult={selectedAnalysis.result}
          analysisError={selectedAnalysis.error}
          analyzing={selectedAnalysis.analyzing}
        />
      )}

      <div className="screening-results">
        {currentResults.map((item) => {
          const isSelected = selectedCode && item.code === selectedCode;
          const chg = parseFloat(item.chg) || 0;
          const itemAnalysis = analysisState[item.code];
          const itemAnalyzing = itemAnalysis?.analyzing;
          const sd = item.score_detail || {};

          return (
            <div
              key={item.code}
              className={`screening-item golden-pit-item ${isSelected ? 'selected' : ''} ${itemAnalyzing ? 'analyzing' : ''}`}
              onClick={() => handleClickStock(item)}
            >
              <div className="screening-item-header">
                <span className="screening-code">{item.code}</span>
                <span className="screening-name">{item.name}</span>
                {item.chain && (
                  <span className="screening-chain-tag">{item.chain.replace(/\(qcc\)/g,'').slice(0, 8)}</span>
                )}
                <span className={`screening-chg ${chg >= 0 ? 'up' : 'down'}`}>
                  {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%
                </span>
                <span className="screening-price">{item.close?.toFixed(2)}</span>
                {itemAnalyzing && <span className="screening-spin">🔄</span>}
              </div>
              <div className="golden-pit-detail-v3">
                <div className="golden-pit-metrics">
                  <span className="gp-metric">ma60={item.ma60}%</span>
                  <span className="gp-metric">pos20={item.pos20}%</span>
                  <span className="gp-metric">ma20={item.ma20}%</span>
                  <span className="gp-metric">vr5={item.vr5?.toFixed(2)}x</span>
                  {item.mcap > 0 && <span className="gp-metric">{item.mcap >= 100 ? `${(item.mcap/100).toFixed(0)}百亿` : `${item.mcap.toFixed(0)}亿`}</span>}
                  {item.dd > 0 && <span className="gp-metric">连跌{item.dd}天</span>}
                </div>
                <div className="golden-pit-score-detail">
                  <span>链{sd.chain ?? 0}</span>
                  <span className="sd-sep">|</span>
                  <span>60{sd.ma60 ?? 0}</span>
                  <span className="sd-sep">|</span>
                  <span>量{sd.vr ?? 0}</span>
                  <span className="sd-sep">|</span>
                  <span>位{sd.pos ?? 0}</span>
                  <span className="sd-sep">|</span>
                  <span>跌{sd.dd ?? 0}</span>
                  <span className="sd-sep">|</span>
                  <span>实{sd.real ?? 0}</span>
                  <span className="sd-sep">|</span>
                  <span>盘{sd.market ?? 0}</span>
                </div>
              </div>
              {/* 选中时展开星球双圈评价（谢SS + Macro独立） */}
              {isSelected && (item.xies_comment || item.macro_comment) && (
                <div className="zsxq-dual-panel">
                  {item.xies_comment && (
                    <div className="zsxq-eval-block xies-block">
                      <div className="zsxq-eval-title">📖 谢SS评价（股道价值投资）</div>
                      <div className="zsxq-eval-body">
                        {item.xies_comment.split('|').map((line, j) => (
                          <div key={j} className="zsxq-eval-line">{line}</div>
                        ))}
                      </div>
                    </div>
                  )}
                  {item.macro_comment && (
                    <div className="zsxq-eval-block macro-block">
                      <div className="zsxq-eval-title">📖 Macro评价（Labubu产业链）</div>
                      <div className="zsxq-eval-body">
                        {item.macro_comment.split('|').map((line, j) => (
                          <div key={j} className="zsxq-eval-line">{line}</div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {!loading && currentData && currentResults.length === 0 && (
        <div className="screening-empty">暂无符合条件的黄金坑</div>
      )}

      {/* 操作纪律 */}
      {currentResults.length > 0 && g1 > 0 && (
        <div className="golden-pit-discipline">
          <div className="discipline-title">📖 操作纪律（谢SS）</div>
          <div className="discipline-text">⭐1级信号{g1}只 — 中线持有，止损设60日线-12%</div>
          <div className="discipline-text">\"利润来自持有，不是频繁交易\"</div>
          <div className="discipline-text">\"AI是主线\" — TMT赛道景气1.2x</div>
        </div>
      )}
    </div>
  );
}
