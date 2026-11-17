import { useState } from "react";
import { api, loadKey, saveKey, useMarket } from "./api";
import { OrderBook } from "./components/OrderBook";
import { OrderTicket } from "./components/OrderTicket";
import { Leaderboard, NewsFeed, OpenOrders, Positions, TradeTape } from "./components/Panels";
import { PriceChart } from "./components/PriceChart";

function Register({ onKey }: { onKey: (key: string) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      const result = await api.register(name);
      onKey(result.api_key);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <form className="register" onSubmit={submit}>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Pick a trader name" maxLength={32} />
      <button disabled={!name.trim()}>Start trading</button>
      {error && <span className="neg">{error}</span>}
    </form>
  );
}

export default function App() {
  const [apiKey, setApiKey] = useState<string | null>(loadKey());
  const market = useMarket(apiKey);
  const symbols = Object.keys(market.books);
  const [symbol, setSymbol] = useState("ACME");
  const [picked, setPicked] = useState<{ price: number; click: number } | null>(null);

  const book = market.books[symbol];
  const me = market.account?.name;

  const changeKey = (key: string | null) => {
    saveKey(key);
    setApiKey(key);
  };

  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="logo">◆</span> Realtime Exchange
        </div>
        <nav className="symbols">
          {symbols.map((s) => {
            const b = market.books[s];
            return (
              <button key={s} className={s === symbol ? "on" : ""} onClick={() => setSymbol(s)}>
                <b>{s}</b> {b?.last.toFixed(2)}
              </button>
            );
          })}
        </nav>
        <div className="status">
          <span className={market.connected ? "dot live" : "dot"} />
          {market.connected ? "Live" : "Reconnecting"}
          <a href="/docs" target="_blank" rel="noreferrer">
            Bot API
          </a>
          {me && (
            <span className="who">
              {me}
              <button className="link" onClick={() => changeKey(null)}>
                sign out
              </button>
            </span>
          )}
        </div>
      </header>

      {!apiKey && (
        <div className="banner">
          You're watching the market. Register to trade against the bots and other people.
          <Register onKey={changeKey} />
        </div>
      )}

      <main>
        <section className="col left">
          <OrderBook
            book={book}
            myOrders={market.orders}
            onPick={(price) => setPicked((prev) => ({ price, click: (prev?.click ?? 0) + 1 }))}
          />
        </section>
        <section className="col center">
          <PriceChart symbol={symbol} />
          <TradeTape trades={market.trades[symbol] ?? []} me={me} />
        </section>
        <section className="col right">
          {apiKey && (
            <>
              <OrderTicket
                apiKey={apiKey}
                symbol={symbol}
                book={book}
                pickedPrice={picked}
                maxQty={market.account?.limits.max_order_qty ?? 100}
              />
              <Positions account={market.account} />
              <OpenOrders apiKey={apiKey} orders={market.orders} />
            </>
          )}
          <NewsFeed news={market.news} />
          <Leaderboard rows={market.leaderboard} me={me} />
        </section>
      </main>
    </div>
  );
}
