export type Product = {
  id: string;
  sku: string;
  name: string;
  description: string;
  category: string;
  price: string;
  image_url: string;
  stock: number;
};

export type OrderItem = {
  id: string;
  product_id: string;
  name: string;
  unit_price: string;
  qty: number;
};
export type Order = {
  id: string;
  status: string;
  total: string;
  payment_last4: string;
  placed_at: string;
  items: OrderItem[];
};

export type ReturnRow = {
  id: string;
  order_id: string;
  order_item_id: string;
  reason_code: string;
  reason_text: string;
  status: string;
  refund_state: string;
  amount: string;
  decision: string | null;
  decision_reason: string | null;
  final_decision: string | null;
  created_at: string;
  photo_urls: string[];
};

const BASE = "/api/rg";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}
