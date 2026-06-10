import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import GraphCanvas from './components/GraphCanvas';
import Controls from './components/Controls';
import Tooltip from './components/Tooltip';
import DetailPanel from './components/DetailPanel';
import industryData from './data/industry_data.json';
import priceData from './data/price_data.json';
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

// 收集所有代码（包含每个环节的股票列表信息）
function buildAllCodes(data) {
  const codes = new Set();
  const stockToLink = {};  // code -> 所属环节名
  const linkStocks = {};   // 环节名 -> 该环节的股票列表
  
  for (const [indName, indData] of Object.entries(data)) {
    for (const [linkName, linkData] of Object.entries(indData['环节'])) {
      if (!linkStocks[indName]) linkStocks[indName] = {};
      linkStocks[indName][linkName] = [];
      for (const c of linkData['股票']) {
        codes.add(c);
        stockToLink[c] = linkName;
        linkStocks[indName][linkName].push({ code: c, name: '' });
      }
    }
  }
  return { codes: [...codes], stockToLink, linkStocks };
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

  // 详情栏状态
  const [selectedNode, setSelectedNode] = useState(null);
  const [detailHistory, setDetailHistory] = useState([]);  // 二级导航栈

  const graphRef = useRef(null);

  // 构建所有代码和映射
  const { codes: allCodes, stockToLink, linkStocks } = React.useMemo(() => buildAllCodes(industryData), []);

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
  }, [allCodes]);

  // 初始加载
  useEffect(() => {
    fetchPrices();
  }, []);

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
