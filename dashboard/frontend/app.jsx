const { useEffect, useState } = React;

function App() {
  const [balance, setBalance] = useState(null);
  const [trades, setTrades] = useState([]);
  const [metrics, setMetrics] = useState({});

  useEffect(() => {
    fetch('/balance').then(r => r.json()).then(setBalance);
    fetch('/trades').then(r => r.json()).then(data => setTrades(data.trades || []));
    fetch('/metrics').then(r => r.json()).then(setMetrics);
  }, []);

  return (
    <div>
      <h1>AlphaPulse Dashboard</h1>
      <p>Balance: {balance ? balance.balance_sol.toFixed(4) : '...' } SOL</p>
      <h2>Metrics</h2>
      <div>Total USD Spent: {metrics.total_usd}</div>
      <div>Total SOL Spent: {metrics.total_sol}</div>
      <div>Trades: {metrics.num_trades}</div>
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
