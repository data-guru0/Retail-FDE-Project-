"use client";
import { useEffect, useState, useCallback } from "react";

export type CartItem = { product_id: string; name: string; price: number; qty: number };
const KEY = "rg_cart";

function read(): CartItem[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}
function write(items: CartItem[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
  window.dispatchEvent(new Event("rg-cart"));
}

export function useCart() {
  const [items, setItems] = useState<CartItem[]>([]);
  useEffect(() => {
    setItems(read());
    const h = () => setItems(read());
    window.addEventListener("rg-cart", h);
    window.addEventListener("storage", h);
    return () => {
      window.removeEventListener("rg-cart", h);
      window.removeEventListener("storage", h);
    };
  }, []);

  const add = useCallback((it: Omit<CartItem, "qty">, qty = 1) => {
    const cur = read();
    const found = cur.find((c) => c.product_id === it.product_id);
    if (found) found.qty += qty;
    else cur.push({ ...it, qty });
    write(cur);
  }, []);
  const setQty = useCallback((product_id: string, qty: number) => {
    let cur = read();
    cur = qty <= 0 ? cur.filter((c) => c.product_id !== product_id)
                   : cur.map((c) => (c.product_id === product_id ? { ...c, qty } : c));
    write(cur);
  }, []);
  const clear = useCallback(() => write([]), []);

  const count = items.reduce((n, i) => n + i.qty, 0);
  const total = items.reduce((s, i) => s + i.qty * i.price, 0);
  return { items, add, setQty, clear, count, total };
}
