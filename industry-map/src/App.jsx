import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import GraphCanvas from './components/GraphCanvas';
import Controls from './components/Controls';
import Tooltip from './components/Tooltip';
import DetailPanel from './components/DetailPanel';
import KlinePanel from './components/KlinePanel';
import frameworksData from './data/frameworks_data.json';
import stockNames from './data/stock_names.json';
import './App.css';

const API_BASE = 'https://qt.gtimg.cn/q=';
const BATCH_SIZE = 30;

function getInitParams() {
  const hash = window.location.hash.replace('#', '');
  const params = new URLSearchParams(hash);
  let savedMode = localStorage.getItem('layoutMode') || 'horizontal';
  if (params.get('mode') === 'horizontal' || params.get('mode') === 'force' || params.get('mode') === 'star') {
    savedMode = params.get('mode');
  }
  const keys = Object.keys(frameworksData);
  return {
    industry: params.get('industry') || (keys[0] || ''),
    metric: params.get('metric') || 'chg',
    layout: savedMode,
  };
}

function collectCodes(industry) {
  if (!industry || !industry.sections) return [];
  const codes = [];
  for (const sec of industry.sections) {
    for (const link of sec.links) {
      for (const c of (link.stocks || [])) {
        if (/^\d{6}$/.test(c)) codes.push(c);
      }
    }
  }
  return [...new Set(codes)];
}

async function batchFetchQtCodes(codes) {
  if (!codes || codes.length === 0) return {};
  const results = {};
  for (let i = 0; i < codes.length; i += BATCH_SIZE) {
    const batch = codes.slice(i, i + BATCH_SIZE);
    const qtCodes = batch.map(c => (c.startsWith('6') ? 'sh' : 'sz') + c);
    try {
      const resp = await fetch(`${API_BASE}${qtCodes.join(',')}&_=${Date.now()}`);
      const buf = await resp.arrayBuffer();
      const decoder = new TextDecoder('gb18030');
      const text = decoder.decode(buf);
      for (const line of text.split(';')) {
        if (!line.trim() || !line.includes('~')) continue;
        const parts = line.split('~');
        const rawCode = parts[0] || '';
        const codeMatch = rawCode.match(/(\d{6})/);
        const code = codeMatch ? codeMatch[1] : rawCode;
        if (!code) continue;
        const name = parts[1] || stockNames[code] || code;
        results[code] = {
          price: parseFloat(parts[3]) || 0,
          chg: parseFloat(parts[32]) || 0,
          yearChg: parseFloat(parts[69]) || 0,
          volume: parseInt(parts[6]) || 0,
          amplitude: (parseFloat(parts[33]) && parseFloat(parts[34])) ?
            ((parseFloat(parts[33]) - parseFloat(parts[34])) / parseFloat(parts[34]) * 100) : 0,
          pe: parseFloat(parts[39]) || 0,
          pb: parseFloat(parts[48]) || 0,
          name,
        };
      }
    } catch (e) {
      console.warn('Batch fetch error:', e);
    }
  }
  return results;
}

export default function App() {
  const init = getInitParams();
  const [currentIndustry, setCurrentIndustry] = useState(init.industry);
  const [colorMetric, setColorMetric] = useState(init.metric);
  const [layoutMode, setLayoutMode] = useState(init.layout);
  const [stockPrices, setStockPrices] = useState({});
  const [tooltip, setTooltip] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date().toLocaleTimeString('zh-CN'));
  const [selectedNode, setSelectedNode] = useState(null);
  const [klineStock, setKlineStock] = useState(null);
  const [detailHistory, setDetailHistory] = useState([]);

  const graphRef = useRef(null);

  const getQryCodes = useCallback(() => {
    return collectCodes(frameworksData[currentIndustry]);
  }, [currentIndustry]);

  const fetchPrices = useCallback(async () => {
    const codes = getQryCodes();
    if (codes.length === 0) {
      setLastUpdate(new Date().toLocaleTimeString('zh-CN'));
      return;
    }
    setLoading(true);
    const results = await batchFetchQtCodes(codes);
    setStockPrices(prev => ({ ...prev, ...results }));
    setLastUpdate(new Date().toLocaleTimeString('zh-CN'));
    setLoading(false);
  }, [getQryCodes]);

  useEffect(() => { fetchPrices(); }, [currentIndustry, fetchPrices]);

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node);
    setTooltip(null);
    setDetailHistory([]);
    // 公司节点显示K线
    if (node && node.code && /^\d{6}$/.test(node.code)) {
      setKlineStock({ code: node.code, name: node.name || node.code });
    } else {
      setKlineStock(null);
    }
  }, []);

  const handleSelectStock = useCallback(({ code, name, linkName }) => {
    setDetailHistory(prev => [...prev, { code, name, linkName }]);
    setKlineStock({ code, name: name || code });
  }, []);

  const handleBack = useCallback(() => {
    setDetailHistory(prev => prev.slice(0, -1));
  }, []);

  const currentData = frameworksData[currentIndustry];

  return (
    <div className="app">
      <Sidebar
        industries={frameworksData}
        current={currentIndustry}
        onSelect={setCurrentIndustry}
      />
      <div className="main">
        <Controls
          colorMetric={colorMetric}
          onColorMetricChange={setColorMetric}
          layoutMode={layoutMode}
          onLayoutModeChange={setLayoutMode}
          onRefresh={fetchPrices}
          loading={loading}
          lastUpdate={lastUpdate}
        />
        <div className="graph-container" ref={graphRef}>
          <div className="graph-canvas-wrap">
            {currentData ? (
              <GraphCanvas
                layoutMode={layoutMode}
                industry={currentData}
                stockPrices={stockPrices}
                colorMetric={colorMetric}
                onTooltip={setTooltip}
                onNodeClick={handleNodeClick}
                selectedNode={selectedNode}
              />
            ) : (
              <div className="no-industry-hint">请选择产业链</div>
            )}
            {tooltip && (
              <Tooltip data={tooltip} onClose={() => setTooltip(null)} />
            )}
          </div>
        </div>
        {klineStock && (
          <KlinePanel
            code={klineStock.code}
            name={klineStock.name}
            onClose={() => setKlineStock(null)}
          />
        )}
      </div>
      <DetailPanel
        selectedNode={selectedNode}
        stockPrices={stockPrices}
        industryName={currentIndustry}
        industryData={frameworksData}
        onSelectStock={handleSelectStock}
        onBack={handleBack}
        history={detailHistory}
      />
    </div>
  );
}
