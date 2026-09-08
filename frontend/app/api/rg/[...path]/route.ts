import { auth } from "@/auth";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

async function proxy(req: Request, path: string[]) {
  const session = await auth();
  const token = (session as unknown as { accessToken?: string })?.accessToken;

  const url = new URL(req.url);
  const target = `${BACKEND}/${path.join("/")}${url.search}`;

  const headers = new Headers();
  const ct = req.headers.get("content-type");
  if (ct) headers.set("content-type", ct);
  if (token) headers.set("authorization", `Bearer ${token}`);

  const init: RequestInit = { method: req.method, headers };
  if (!["GET", "HEAD"].includes(req.method)) {
    init.body = await req.arrayBuffer();
  }

  const res = await fetch(target, init);
  const body = await res.arrayBuffer();
  return new Response(body, {
    status: res.status,
    headers: {
      "content-type": res.headers.get("content-type") ?? "application/json",
    },
  });
}

type Ctx = { params: Promise<{ path: string[] }> };
export async function GET(req: Request, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: Request, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: Request, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: Request, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
