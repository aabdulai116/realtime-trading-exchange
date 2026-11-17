export type Side = "buy" | "sell";

export interface Level {
  price: number;
  qty: number;
  orders: number;
}

export interface Book {
  symbol: string;
  bids: Level[];
  asks: Level[];
  mid: number;
  last: number;
  volume: number;
}

export interface Trade {
  id: number;
  symbol: string;
  price: number;
  qty: number;
  aggressor: Side;
  buyer: string;
  seller: string;
  time: number;
}

export interface News {
  time: number;
  symbol: string;
  headline: string;
}

export interface Position {
  symbol: string;
  qty: number;
  mark: number;
  value: number;
}

export interface Account {
  trader_id: number;
  name: string;
  cash: number;
  pnl: number;
  volume: number;
  trades: number;
  positions: Position[];
  limits: { position: number; max_order_qty: number };
}

export interface OpenOrder {
  order_id: number;
  symbol: string;
  side: Side;
  price: number;
  qty: number;
}

export interface LeaderRow {
  rank: number;
  name: string;
  is_bot: boolean;
  pnl: number;
  volume: number;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketMessage {
  type: "market";
  time: number;
  books: Record<string, Book>;
  trades: Trade[];
  news: News[];
  leaderboard: LeaderRow[];
  account?: Account;
  orders?: OpenOrder[];
}
