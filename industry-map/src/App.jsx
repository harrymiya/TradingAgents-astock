import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import GraphCanvas from './components/GraphCanvas';
import Controls from './components/Controls';
import Tooltip from './components/Tooltip';
import industryData from './data/industry_data.json';
import priceData from './data/price_data.json';
import './App.css';

const API_BASE = 'https://qt.gtimg.cn/q=';
const BATCH_SIZE = 30;

// 从 URL hash 获取初始参数: #industry=AI算力&metric=yearChg
function getInitParams() {
  const hash = window.location.hash.replace('#', '');
  const params = new URLSearchParams(hash);
  return {
    industry: params.get('industry') || '人形机器人',
    metric: params.get('metric') || 'chg',
    label: params.get('label') || 'both',
  };
}

export default function App() {
  const init = getInitParams();
  const [currentIndustry, setCurrentIndustry] = useState(init.industry);
  const [colorMetric, setColorMetric] = useState(init.metric);
  const [labelMode, setLabelMode] = useState(init.label);
  const [stockPrices, setStockPrices] = useState(priceData.prices || {});
  const [tooltip, setTooltip] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date().toLocaleTimeString('zh-CN'));

  const graphRef = useRef(null);

  // 收集所有产业链的股票代码
  const allCodes = React.useMemo(() => {
    const codes = new Set();
    for (const ind of Object.values(industryData)) {
      for (const link of Object.values(ind['环节'])) {
        for (const c of link['股票']) codes.add(c);
      }
    }
    return [...codes];
  }, []);

  // 获取行情数据
  const fetchPrices = useCallback(async () => {
    setLoading(true);
    const results = {};

    for (let i = 0; i < allCodes.length; i += BATCH_SIZE) {
      const batch = allCodes.slice(i, i + BATCH_SIZE);
      const qtCodes = batch.map(c => (c.startsWith('6') ? 'sh' : 'sz') + c);
      const url = `${API_BASE}${qtCodes.join(',')}&_=${Date.now()}`;

      try {
        const resp = await fetch(url);
        const text = await resp.text();
        for (const line of text.split(';')) {
          if (!line.trim() || !line.includes('~')) continue;
          const parts = line.split('~');
          const rawCode = parts[0] || '';
          const code = rawCode.replace(/^(sh|sz)/, '');
          const price = parseFloat(parts[3]) || 0;
          const chg = parseFloat(parts[32]) || 0;
          const yearChg = parseFloat(parts[69]) || 0;
          const volume = parseInt(parts[6]) || 0;
          const high = parseFloat(parts[33]) || 0;
          const low = parseFloat(parts[34]) || 0;
          const amplitude = high && low ? ((high - low) / low * 100) : 0;
          results[code] = { price, chg, yearChg, monthChg: chg, volume, amplitude, name: parts[1] || code };
        }
      } catch (e) {
        console.warn('Batch fetch error:', e);
      }
    }

    setStockPrices(prev => ({ ...prev, ...results }));
    setLastUpdate(new Date().toLocaleTimeString('zh-CN'));
    setLoading(false);
  }, [allCodes]);

  // 初始加载时刷新一次
  useEffect(() => {
    fetchPrices();
  }, []);

  return (
    <div className="app">
      <Sidebar
        industries={industryData}
        current={currentIndustry}
        onSelect={setCurrentIndustry}
      />
      <div className="main">
        <Controls
          colorMetric={colorMetric}
          onColorMetricChange={setColorMetric}
          labelMode={labelMode}
          onLabelModeChange={setLabelMode}
          onRefresh={fetchPrices}
          loading={loading}
          lastUpdate={lastUpdate}
        />
        <div className="graph-container" ref={graphRef}>
          <GraphCanvas
            industry={currentIndustry}
            industryData={industryData}
            stockPrices={stockPrices}
            colorMetric={colorMetric}
            labelMode={labelMode}
            onTooltip={setTooltip}
          />
          {tooltip && (
            <Tooltip
              data={tooltip}
              onClose={() => setTooltip(null)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
