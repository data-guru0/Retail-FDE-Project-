"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { useCart } from "@/app/lib/cart";
import { client } from "@/app/lib/api";

/** FastAPI errors are `{detail: string}` or `{detail: [{msg}, …]}` — never render the object. */
function errText(error: unknown, status?: number): string {
  const d = (error as { detail?: unknown } | null | undefined)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d.map((e) => (e as { msg?: string })?.msg ?? String(e)).join("; ");
  return status ? `checkout failed (HTTP ${status})` : "checkout failed";
}

export default function CheckoutPage() {
  const { items, total, clear } = useCart();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({
    line1: "1 Market St",
    city: "San Francisco",
    zip: "94105",
    card_number: "4242 4242 4242 4242",
    card_exp: "12/30",
    card_cvc: "123",
  });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function submit() {
    setBusy(true);
    setErr("");
    const { data, error, response } = await client.POST("/orders", {
      body: {
        lines: items.map((i) => ({ product_id: i.product_id, qty: i.qty })),
        shipping_address: { line1: form.line1, city: form.city, zip: form.zip },
        card_number: form.card_number,
        card_exp: form.card_exp,
        card_cvc: form.card_cvc,
      },
    });
    if (error || !data) {
      if (response?.status === 401) {
        // not signed in (or session expired) — send them to Keycloak, then back
        // here; the cart is in localStorage so it survives the round trip.
        void signIn("keycloak", { callbackUrl: "/shop/checkout" });
        return;
      }
      setErr(errText(error, response?.status));
      setBusy(false);
      return;
    }
    clear();
    router.push(`/orders/${data.id}`);
  }

  if (items.length === 0) return <p>Your cart is empty.</p>;

  return (
    <div
      style={{
        maxWidth: 480,
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <h1 style={{ fontSize: 22, fontWeight: 700 }}>Checkout</h1>
      <label>Address</label>
      <input className="input" value={form.line1} onChange={set("line1")} />
      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          value={form.city}
          onChange={set("city")}
          placeholder="City"
        />
        <input
          className="input"
          value={form.zip}
          onChange={set("zip")}
          placeholder="ZIP"
        />
      </div>
      <label>Card (test — no real charge, Luhn-checked)</label>
      <input
        className="input"
        value={form.card_number}
        onChange={set("card_number")}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          value={form.card_exp}
          onChange={set("card_exp")}
          placeholder="MM/YY"
        />
        <input
          className="input"
          value={form.card_cvc}
          onChange={set("card_cvc")}
          placeholder="CVC"
        />
      </div>
      {err && <div style={{ color: "#ff8a8a" }}>{err}</div>}
      <button className="btn" disabled={busy} onClick={submit}>
        {busy ? "Placing…" : `Pay $${total.toFixed(2)}`}
      </button>
    </div>
  );
}
