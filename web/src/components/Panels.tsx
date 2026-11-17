import { api } from "../api";
import type { Account, LeaderRow, News, OpenOrder, Trade } from "../types";

function money(value: number): string {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function clock(seconds: number): string {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour12: false });
}

export function Positions({ account }: { account: Account | null }) {
  if (!account) return null;
  return (
    <div className="panel positions">
      <div className="panel-title">
        Positions <span className={account.pnl >= 0 ? "pos" : "neg"}>P&amp;L {money(account.pnl)}</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Qty</th>
            <th>Mark</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {account.positions.map((p) => (
            <tr key={p.symbol}>
              <td>{p.symbol}</td>
              <td className={p.qty > 0 ? "pos" : p.qty < 0 ? "neg" : ""}>{p.qty}</td>
              <td>{p.mark.toFixed(2)}</td>
              <td>{money(p.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="muted small-print">
        Cash {money(account.cash)} · {account.trades} trades · limit ±{account.limits.position} shares
      </div>
    </div>
  );
}

export function OpenOrders({ apiKey, orders }: { apiKey: string; orders: OpenOrder[] }) {
  return (
    <div className="panel orders">
      <div className="panel-title">
        Open orders
        {orders.length > 0 && (
          <button className="link" onClick={() => api.cancelAll(apiKey)}>
            Cancel all
          </button>
        )}
      </div>
      {orders.length === 0 ? (
        <div className="muted">No resting orders</div>
      ) : (
        <table>
          <tbody>
            {orders.map((o) => (
              <tr key={o.order_id}>
                <td>{o.symbol}</td>
                <td className={o.side === "buy" ? "pos" : "neg"}>{o.side}</td>
                <td>{o.qty}</td>
                <td>@ {o.price.toFixed(2)}</td>
                <td>
                  <button className="link" onClick={() => api.cancel(apiKey, o.order_id)}>
                    cancel
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function TradeTape({ trades, me }: { trades: Trade[]; me?: string }) {
  return (
    <div className="panel tape">
      <div className="panel-title">
        Time and sales <span className="muted">green = buyer crossed the spread</span>
      </div>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Price</th>
              <th>Size</th>
              <th>Buyer</th>
              <th>Seller</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => {
              const mine = me && (t.buyer === me || t.seller === me);
              return (
                <tr key={t.id} className={mine ? "highlight" : ""}>
                  <td className="muted">{clock(t.time)}</td>
                  <td className={t.aggressor === "buy" ? "pos" : "neg"}>{t.price.toFixed(2)}</td>
                  <td>{t.qty}</td>
                  <td className="muted">{t.buyer}</td>
                  <td className="muted">{t.seller}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function NewsFeed({ news }: { news: News[] }) {
  return (
    <div className="panel news">
      <div className="panel-title">News</div>
      <div className="scroll">
        {news.length === 0 && <div className="muted">No headlines yet. Watch this space.</div>}
        {news.map((n) => (
          <div key={`${n.time}${n.headline}`} className="headline">
            <span className="muted">{clock(n.time)}</span> {n.headline}
          </div>
        ))}
      </div>
    </div>
  );
}

export function Leaderboard({ rows, me }: { rows: LeaderRow[]; me?: string }) {
  return (
    <div className="panel leaderboard">
      <div className="panel-title">Leaderboard</div>
      <table>
        <tbody>
          {rows.slice(0, 10).map((r) => (
            <tr key={r.name} className={r.name === me ? "highlight" : ""}>
              <td className="muted">{r.rank}</td>
              <td>
                {r.name} {r.is_bot && <span className="tag">bot</span>}
              </td>
              <td className={r.pnl >= 0 ? "pos" : "neg"}>{money(r.pnl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
