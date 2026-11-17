import type { Book, OpenOrder } from "../types";

interface Props {
  book?: Book;
  myOrders: OpenOrder[];
  onPick: (price: number) => void;
}

const ROWS = 10;

export function OrderBook({ book, myOrders, onPick }: Props) {
  if (!book) return <div className="panel book empty">Waiting for market data...</div>;

  const asks = book.asks.slice(0, ROWS).reverse();
  const bids = book.bids.slice(0, ROWS);
  const maxQty = Math.max(1, ...asks.map((l) => l.qty), ...bids.map((l) => l.qty));
  const mine = new Map<string, number>();
  for (const order of myOrders) {
    if (order.symbol !== book.symbol) continue;
    const key = `${order.side}:${order.price.toFixed(2)}`;
    mine.set(key, (mine.get(key) ?? 0) + order.qty);
  }
  const spread = book.asks.length && book.bids.length ? book.asks[0].price - book.bids[0].price : 0;

  const row = (side: "buy" | "sell", price: number, qty: number, orders: number) => {
    const own = mine.get(`${side}:${price.toFixed(2)}`);
    return (
      <div key={`${side}${price}`} className={`ladder-row ${side}`} onClick={() => onPick(price)}>
        <div className="depth-bar" style={{ width: `${(qty / maxQty) * 100}%` }} />
        <span className="mine">{own ? own : ""}</span>
        <span className="price">{price.toFixed(2)}</span>
        <span className="qty">{qty}</span>
        <span className="count">{orders}</span>
      </div>
    );
  };

  return (
    <div className="panel book">
      <div className="panel-title">
        Order book <span className="muted">click a price to trade</span>
      </div>
      <div className="ladder-head">
        <span>Mine</span>
        <span>Price</span>
        <span>Size</span>
        <span>Orders</span>
      </div>
      {asks.map((level) => row("sell", level.price, level.qty, level.orders))}
      <div className="spread-row">
        <span>Mid {book.mid.toFixed(3)}</span>
        <span>Spread {spread.toFixed(2)}</span>
      </div>
      {bids.map((level) => row("buy", level.price, level.qty, level.orders))}
    </div>
  );
}
