"use client";
import { useCallback, useSyncExternalStore } from "react";

export type CartItem = {
  product_id: string;
  name: string;
  price: number;
  qty: number;
};
const KEY = "rg_cart";
const EMPTY: CartItem[] = [];

// Cache the parsed array keyed by the raw string so getSnapshot() returns a
// stable reference while the store is unchanged (useSyncExternalStore requires
// it — a fresh array every call would loop forever).
let _rawCache = "";
let _parsedCache: CartItem[] = EMPTY;

function read(): CartItem[] {
  if (typeof window === "undefined") return EMPTY;
  const raw = localStorage.getItem(KEY) ?? "[]";
  if (raw === _rawCache) return _parsedCache;
  _rawCache = raw;
  try {
    _parsedCache = JSON.parse(raw);
  } catch {
    _parsedCache = EMPTY;
  }
  return _parsedCache;
}

function write(items: CartItem[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
  window.dispatchEvent(new Event("rg-cart"));
}

function subscribe(cb: () => void): () => void {
  window.addEventListener("rg-cart", cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener("rg-cart", cb);
    window.removeEventListener("storage", cb);
  };
}

export function useCart() {
  const items = useSyncExternalStore(subscribe, read, () => EMPTY);

  const add = useCallback((it: Omit<CartItem, "qty">, qty = 1) => {
    const cur = [...read()];
    const found = cur.find((c) => c.product_id === it.product_id);
    if (found) found.qty += qty;
    else cur.push({ ...it, qty });
    write(cur);
  }, []);

  const setQty = useCallback((product_id: string, qty: number) => {
    const cur = read();
    write(
      qty <= 0
        ? cur.filter((c) => c.product_id !== product_id)
        : cur.map((c) => (c.product_id === product_id ? { ...c, qty } : c)),
    );
  }, []);

  const clear = useCallback(() => write([]), []);

  const count = items.reduce((n, i) => n + i.qty, 0);
  const total = items.reduce((s, i) => s + i.qty * i.price, 0);
  return { items, add, setQty, clear, count, total };
}
