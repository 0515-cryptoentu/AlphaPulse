const { useEffect, useState } = React;

function App() {
  const [balance, setBalance] = useState(null);
  const [trades, setTrades] = useState([]);
  const [metrics, setMetrics] = useState({});
  const [pnl, setPnl] = useState({});
  const [portfolio, setPortfolio] = useState([]);

  useEffect(() => {
    fetch('/balance').then(r => r.json()).then(setBalance);
    fetch('/trades').then(r => r.json()).then(data => setTrades(data.trades || []));
    fetch('/metrics').then(r => r.json()).then(setMetrics);
    fetch('/pnl').then(r => r.json()).then(setPnl);
    fetch('/portfolio').then(r => r.json()).then(data => setPortfolio(data.portfolio || []));
  }, []);

  useEffect(() => {
    if (!trades.length || !window.Chart) return;
    const ctx = document.getElementById('balanceChart').getContext('2d');
    const ordered = [...trades].sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp));
    let bal = 0;
    const points = ordered.map(t => {
      bal += t.token_symbol === 'AUTOSELL' ? t.usd_value : -t.usd_value;
      return {x: t.timestamp, y: bal};
    });
    new Chart(ctx, {type:'line', data:{datasets:[{label:'PnL', data:points, borderColor:'blue', tension:0.1}]}, options:{scales:{x:{type:'time', time:{unit:'hour'}}}}});

    const ctx2 = document.getElementById('tokenChart').getContext('2d');
    const totals = {};
    trades.forEach(t => { totals[t.token_symbol] = (totals[t.token_symbol] || 0) + t.usd_value; });
    new Chart(ctx2, {type:'bar', data:{labels:Object.keys(totals), datasets:[{label:'USD', data:Object.values(totals), backgroundColor:'orange'}]}});
  }, [trades]);

  return (
    <div>
      <h1>AlphaPulse Dashboard</h1>
      <p>Balance: {balance ? balance.balance_sol.toFixed(4) : '...' } SOL</p>
      <h2>PNL</h2>
      <div>Profit/Loss: {pnl.pnl_usd}</div>
      <h2>Metrics</h2>
      <div>Total USD Spent: {metrics.total_usd}</div>
      <div>Total SOL Spent: {metrics.total_sol}</div>
      <div>Trades: {metrics.num_trades}</div>
      <canvas id="balanceChart" height="100"></canvas>
      <canvas id="tokenChart" height="100"></canvas>
      <h2>Portfolio</h2>
      <ul>
        {portfolio.map((p,i) => (
          <li key={i}>{p.token_mint} - {p.amount}</li>
        ))}
      </ul>
      <h2>Recent Trades</h2>
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Token</th>
            <th>SOL</th>
            <th>USD</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i}>
              <td>{t.timestamp}</td>
              <td>{t.token_symbol}</td>
              <td>{t.amount_sol}</td>
              <td>{t.usd_value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
