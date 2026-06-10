import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import GraphCanvas from './components/GraphCanvas';
import Controls from './components/Controls';
import Tooltip from './components/Tooltip';
import DetailPanel from './components/DetailPanel';
import RevealPanel from './components/RevealPanel';
import IndustrySwitcher from './components/IndustrySwitcher';
import industryData from './data/industry_data.json';
import priceData from './data/price_data.json';
import featData from './data/feat_data.json';
import './App.css';

const API_BASE = 'https://qt.gtimg.cn/q=';
const BATCH_SIZE = 30;

function getInitParams() {
  const hash = window.location.hash.replace('#', '');
  const params = new URLSearchParams(hash);
  return {
    industry: params.get('industry') || '人形机器人',
    metric: params.get('metric') || 'chg',
    label: params.get('label') || 'both',
  };
}

function buildCodeToIndustryMap(data) {
  const map = {};
  for (const [indName, indData] of Object.entries(data)) {
    if (indName.startsWith('_') || !indData['环节']) continue;
    for (const [linkName, linkData] of Object.entries(indData['环节'])) {
      for (const c of (linkData['股票'] || [])) {
        if (/^\d{6}$/.test(c)) {
          if (!map[c]) map[c] = [];
          if (!map[c].includes(indName)) map[c].push(indName);
        }
      }
    }
  }
  return map;
}

function getIndustryCodes(data, industryName) {
  const indData = data[industryName];
  if (!indData || !indData['环节']) return [];
  const codes = [];
  for (const [linkName, linkData] of Object.entries(indData['环节'])) {
    for (const c of linkData['股票']) {
      if (/^\d{6}$/.test(c)) codes.push(c);
    }
  }
  return codes;
}

const codeToIndustry = buildCodeToIndustryMap(industryData);

export default function App() {
  const init = getInitParams();
  const [currentIndustry, setCurrentIndustry] = useState(init.industry);
  const [colorMetric, setColorMetric] = useState(init.metric);
  const [layoutMode, setLayoutMode] = useState('horizontal');
  const [stockPrices, setStockPrices] = useState(priceData.prices || {});
  const [tooltip, setTooltip] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date().toLocaleTimeString('zh-CN'));

  const [selectedNode, setSelectedNode] = useState(null);
  const [detailHistory, setDetailHistory] = useState([]);
  const [screeningInfo, setScreeningInfo] = useState(null);
  // 选股互动：选中的代码 + 该代码所有产业链列表
  const [screeningCode, setScreeningCode] = useState(null);
  const [availableChains, setAvailableChains] = useState([]);

  const graphRef = useRef(null);
  const autoRefreshRef = useRef(null);

  const fetchPrices = useCallback(async () => {
    const codes = getIndustryCodes(industryData, currentIndustry);
    if (codes.length === 0) return;

    setLoading(true);
    const results = {};

    for (let i = 0; i < codes.length; i += BATCH_SIZE) {
      const batch = codes.slice(i, i + BATCH_SIZE);
      const qtCodes = batch.map(c => (c.startsWith('6') ? 'sh' : 'sz') + c);
      const url = `${API_BASE}${qtCodes.join(',')}&_=${Date.now()}`;

      try {
        const resp = await fetch(url);
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
          const price = parseFloat(parts[3]) || 0;
          const chg = parseFloat(parts[32]) || 0;
          const yearChg = parseFloat(parts[69]) || 0;
          const volume = parseInt(parts[6]) || 0;
          const high = parseFloat(parts[33]) || 0;
          const low = parseFloat(parts[34]) || 0;
          const amplitude = high && low ? ((high - low) / low * 100) : 0;
          const pe = parseFloat(parts[39]) || 0;
          const pb = parseFloat(parts[48]) || 0;
          results[code] = {
            price, chg, yearChg, monthChg: chg,
            volume, amplitude, pe, pb,
            name: parts[1] || code,
          };
        }
      } catch (e) {
        console.warn('Batch fetch error:', e);
      }
    }

    setStockPrices(prev => ({ ...prev, ...results }));
    setLastUpdate(new Date().toLocaleTimeString('zh-CN'));
    setLoading(false);
  }, [currentIndustry]);

  useEffect(() => {
    fetchPrices();
  }, [currentIndustry, fetchPrices]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchPrices();
    }, 30000);
    autoRefreshRef.current = interval;
    return () => clearInterval(interval);
  }, [fetchPrices]);

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node);
    setDetailHistory([]);
    setScreeningInfo(null);
    setTooltip(null);
  }, []);

  const handleSelectStock = useCallback(({ code, name, linkName }) => {
    setDetailHistory(prev => [...prev, { code, name, linkName }]);
  }, []);

  const handleBack = useCallback(() => {
    setDetailHistory(prev => prev.slice(0, -1));
  }, []);

  // 选股结果点击：跳转产业链+选中（不切sidebar tab）
  const handleSelectScreening = useCallback((item) => {
    const code = item.code;
    const chains = codeToIndustry[code] || [];
    setScreeningCode(code);
    setAvailableChains(chains);

    if (chains.length > 0) {
      setCurrentIndustry(chains[0]);
    }
    // 设置为选中节点
    setSelectedNode({ code, name: item.name, type: 'stock', id: code });
    setDetailHistory([]);
    setScreeningInfo({
      code: item.code, name: item.name,
      strategy: item.strategy, detail: item.detail,
      chg: item.chg, close: item.close,
    });
  }, []);

  // 下拉框切换产业链
  const handleSwitchIndustry = useCallback((newIndustry) => {
    setCurrentIndustry(newIndustry);
    // 保留selectedNode和screeningInfo，不重置
  }, []);

  const hasIndustry = currentIndustry && industryData[currentIndustry] && industryData[currentIndustry]['环节'];

  return (
    <div className="app">
      <Sidebar
        industries={industryData}
        current={currentIndustry}
        onSelect={setCurrentIndustry}
        onSelectScreening={handleSelectScreening}
        selectedCode={screeningCode}
      />
      <div className="main">
        {availableChains.length > 1 && screeningCode && (
          <IndustrySwitcher
            chains={availableChains}
            current={currentIndustry}
            onSwitch={handleSwitchIndustry}
          />
        )}
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
          {hasIndustry ? (
            <GraphCanvas
              layoutMode={layoutMode}
              industry={currentIndustry}
              industryData={industryData}
              stockPrices={stockPrices}
              featData={featData}
              colorMetric={colorMetric}
              onTooltip={setTooltip}
              onNodeClick={handleNodeClick}
              selectedNode={selectedNode}
            />
          ) : screeningCode ? (
            <div className="no-industry-hint">该股票暂无匹配的产业链</div>
          ) : null}
          {tooltip && (
            <Tooltip data={tooltip} onClose={() => setTooltip(null)} />
          )}
        </div>
      </div>
      <DetailPanel
        selectedNode={selectedNode}
        stockPrices={stockPrices}
        stockIndustry={{}}
        industryName={currentIndustry}
        onClose={() => { setSelectedNode(null); setDetailHistory([]); setScreeningInfo(null); setScreeningCode(null); setAvailableChains([]); }}
        onSelectStock={handleSelectStock}
        onBack={handleBack}
        history={detailHistory}
        screeningInfo={screeningInfo}
      />
    </div>
  );
}
