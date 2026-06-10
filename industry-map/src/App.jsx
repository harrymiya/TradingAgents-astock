import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import GraphCanvas from './components/GraphCanvas';
import Controls from './components/Controls';
import Tooltip from './components/Tooltip';
import DetailPanel from './components/DetailPanel';
import industryData from './data/industry_data.json';
import priceData from './data/price_data.json';
import featData from './data/feat_data.json';
import './App.css';

const API_BASE = 'https://qt.gtimg.cn/q=';
const BATCH_SIZE = 30;

// 从 URL hash 获取初始参数
function getInitParams() {
  const hash = window.location.hash.replace('#', '');
  const params = new URLSearchParams(hash);
  return {
    industry: params.get('industry') || '人形机器人',
    metric: params.get('metric') || 'chg',
    label: params.get('label') || 'both',
  };
}

// 收集指定产业链内所有股票代码
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

export default function App() {
  const init = getInitParams();
  const [currentIndustry, setCurrentIndustry] = useState(init.industry);
  const [colorMetric, setColorMetric] = useState(init.metric);
  const [layoutMode, setLayoutMode] = useState('horizontal');
  const [stockPrices, setStockPrices] = useState(priceData.prices || {});
  const [tooltip, setTooltip] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date().toLocaleTimeString('zh-CN'));

  // 详情栏状态
  const [selectedNode, setSelectedNode] = useState(null);
  const [detailHistory, setDetailHistory] = useState([]);

  const graphRef = useRef(null);
  const autoRefreshRef = useRef(null);

  // 获取当前产业链的行情（只拉图中显示的公司）
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

  // 产业链切换 → 立即拉行情
  useEffect(() => {
    fetchPrices();
  }, [currentIndustry, fetchPrices]);

  // 自动刷新：每30秒轮询当前产业链的实时数据
  useEffect(() => {
    const interval = setInterval(() => {
      fetchPrices();
    }, 30000);
    autoRefreshRef.current = interval;
    return () => clearInterval(interval);
  }, [fetchPrices]);

  // 点击节点处理
  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node);
    setDetailHistory([]);
  }, []);

  // 从环节详情点击公司（进入二级）
  const handleSelectStock = useCallback(({ code, name, linkName }) => {
    setDetailHistory(prev => [...prev, { code, name, linkName }]);
  }, []);

  // 二级返回
  const handleBack = useCallback(() => {
    setDetailHistory(prev => prev.slice(0, -1));
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
          layoutMode={layoutMode}
          onLayoutModeChange={setLayoutMode}
          onRefresh={fetchPrices}
          loading={loading}
          lastUpdate={lastUpdate}
        />
        <div className="graph-container" ref={graphRef}>
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
          {tooltip && (
            <Tooltip
              data={tooltip}
              onClose={() => setTooltip(null)}
            />
          )}
        </div>
      </div>
      <DetailPanel
        selectedNode={selectedNode}
        stockPrices={stockPrices}
        stockIndustry={{}}
        industryName={currentIndustry}
        onClose={() => { setSelectedNode(null); setDetailHistory([]); }}
        onSelectStock={handleSelectStock}
        onBack={handleBack}
        history={detailHistory}
      />
    </div>
  );
}
