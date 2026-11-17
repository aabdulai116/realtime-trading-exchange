import { useEffect, useRef, useState } from "react";
import type { Account, Book, Candle, LeaderRow, MarketMessage, News, OpenOrder, Side, Trade } from "./types";

const KEY_STORAGE = "exchange_api_key";

export function loadKey(): string | null {
  try {
    return localStorage.getItem(KEY_STORAGE);
  } catch {
    return null;
  }
}

export function saveKey(key: string | null): void {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key);
    else localStorage.removeItem(KEY_STORAGE);
  } catch {
    // Storage can be unavailable (private mode); the key then lasts for this tab only.
  }
}

async function request<T>(path: string, init: RequestInit = {}, apiKey?: string | null): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (apiKey) headers["X-API-Key"] = apiKey;
  const response = await fetch(path, { ...init, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "request failed";
    throw new Error(detail);
  }
  return body as T;
}

export const api = {
  register: (name: string) =>
    request<{ api_key: string; name: string }>("/api/register", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  candles: (symbol: string) => request<Candle[]>(`/api/candles/${symbol}`),
  me: (key: string) => request<Account>("/api/me", {}, key),
  placeOrder: (
    key: string,
    order: { symbol: string; side: Side; type: "limit" | "market"; qty: number; price?: number },
  ) =>
    request<{ order_id: number | null; filled: number; resting: number; fills: { price: number; qty: number }[] }>(
      "/api/orders",
      { method: "POST", body: JSON.stringify(order) },
      key,
    ),
  cancel: (key: string, orderId: number) =>
    request(`/api/orders/${orderId}`, { method: "DELETE" }, key),
  cancelAll: (key: string, symbol?: string) =>
    request<{ cancelled: number }>(
      symbol ? `/api/orders?symbol=${symbol}` : "/api/orders",
      { method: "DELETE" },
      key,
    ),
};

export interface MarketState {
  connected: boolean;
  books: Record<string, Book>;
  trades: Record<string, Trade[]>;
  news: News[];
  leaderboard: LeaderRow[];
  account: Account | null;
  orders: OpenOrder[];
}

const EMPTY: MarketState = {
  connected: false,
  books: {},
  trades: {},
  news: [],
  leaderboard: [],
  account: null,
  orders: [],
};

/** Live market feed over WebSocket, with automatic reconnect. */
export function useMarket(apiKey: string | null): MarketState {
  const [state, setState] = useState<MarketState>(EMPTY);
  const retry = useRef(0);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let closed = false;

    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const query = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
      socket = new WebSocket(`${scheme}://${location.host}/ws${query}`);

      socket.onopen = () => {
        retry.current = 0;
        setState((s) => ({ ...s, connected: true }));
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as MarketMessage;
        setState((s) => {
          const trades = { ...s.trades };
          for (const trade of message.trades) {
            const list = trades[trade.symbol] ? [...trades[trade.symbol]] : [];
            list.unshift(trade);
            trades[trade.symbol] = list.slice(0, 80);
          }
          return {
            connected: true,
            books: message.books,
            trades,
            news: message.news,
            leaderboard: message.leaderboard,
            account: message.account ?? null,
            orders: message.orders ?? [],
          };
        });
      };

      socket.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (closed) return;
        const delay = Math.min(5000, 500 * 2 ** retry.current);
        retry.current += 1;
        timer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, [apiKey]);

  return state;
}
