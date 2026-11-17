import { useEffect, useState } from "react";
import { api } from "../api";
import type { Book, Side } from "../types";

interface Props {
  apiKey: string;
  symbol: string;
  book?: Book;
  pickedPrice: { price: number; click: number } | null;
  maxQty: number;
}

export function OrderTicket({ apiKey, symbol, book, pickedPrice, maxQty }: Props) {
  const [side, setSide] = useState<Side>("buy");
  const [type, setType] = useState<"limit" | "market">("limit");
  const [price, setPrice] = useState("");
  const [qty, setQty] = useState("10");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (pickedPrice !== null) {
      setPrice(pickedPrice.price.toFixed(2));
      setType("limit");
    }
  }, [pickedPrice]);

  useEffect(() => {
    setPrice("");
    setMessage(null);
  }, [symbol]);

  const bestBid = book?.bids[0]?.price;
  const bestAsk = book?.asks[0]?.price;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const quantity = Number(qty);
    if (!Number.isInteger(quantity) || quantity <= 0) {
      setMessage({ ok: false, text: "Quantity must be a whole number above zero" });
      return;
    }
    const order: { symbol: string; side: Side; type: "limit" | "market"; qty: number; price?: number } = {
      symbol,
      side,
      type,
      qty: quantity,
    };
    if (type === "limit") {
      const value = Number(price);
      if (!(value > 0)) {
        setMessage({ ok: false, text: "Enter a limit price" });
        return;
      }
      order.price = value;
    }
    setBusy(true);
    try {
      const result = await api.placeOrder(apiKey, order);
      let text = `Filled ${result.filled}`;
      if (result.fills.length) {
        let notional = 0;
        for (const fill of result.fills) notional += fill.price * fill.qty;
        text += ` @ avg ${(notional / result.filled).toFixed(3)}`;
      }
      if (result.resting) text += `, ${result.resting} resting`;
      setMessage({ ok: true, text });
    } catch (error) {
      setMessage({ ok: false, text: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel ticket" onSubmit={submit}>
      <div className="panel-title">Order ticket</div>
      <div className="toggle">
        <button type="button" className={side === "buy" ? "on buy" : ""} onClick={() => setSide("buy")}>
          Buy
        </button>
        <button type="button" className={side === "sell" ? "on sell" : ""} onClick={() => setSide("sell")}>
          Sell
        </button>
      </div>
      <div className="toggle small">
        <button type="button" className={type === "limit" ? "on" : ""} onClick={() => setType("limit")}>
          Limit
        </button>
        <button type="button" className={type === "market" ? "on" : ""} onClick={() => setType("market")}>
          Market
        </button>
      </div>
      {type === "limit" && (
        <label>
          Price
          <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" placeholder="0.00" />
          <span className="quick">
            <button type="button" disabled={!bestBid} onClick={() => bestBid && setPrice(bestBid.toFixed(2))}>
              Bid {bestBid?.toFixed(2) ?? "-"}
            </button>
            <button type="button" disabled={!bestAsk} onClick={() => bestAsk && setPrice(bestAsk.toFixed(2))}>
              Ask {bestAsk?.toFixed(2) ?? "-"}
            </button>
          </span>
        </label>
      )}
      <label>
        Quantity <span className="muted">max {maxQty}</span>
        <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="numeric" />
      </label>
      <button className={`submit ${side}`} disabled={busy}>
        {busy ? "Sending..." : `${side === "buy" ? "Buy" : "Sell"} ${symbol}`}
      </button>
      {message && <div className={message.ok ? "note ok" : "note err"}>{message.text}</div>}
    </form>
  );
}
