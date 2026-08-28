const JSON_HEADERS = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" };

function unauthorized() {
  return new Response(JSON.stringify({ error: "unauthorized" }), { status: 401, headers: JSON_HEADERS });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/api/planner") return env.ASSETS.fetch(request);

    const pairingKey = request.headers.get("X-M87-Workspace-Key") || "";
    if (!pairingKey || pairingKey !== env.PLANNER_PAIRING_KEY) return unauthorized();

    if (request.method === "GET") {
      const row = await env.DB.prepare("SELECT payload FROM planner_state WHERE id = 1").first();
      return new Response(row?.payload || '{"version":1,"weeks":{},"approvals":[]}', { headers: JSON_HEADERS });
    }

    if (request.method === "PUT") {
      let payload;
      try { payload = await request.json(); } catch { return new Response(JSON.stringify({ error: "invalid_json" }), { status: 400, headers: JSON_HEADERS }); }
      if (!payload || typeof payload !== "object" || !payload.weeks) return new Response(JSON.stringify({ error: "invalid_planner" }), { status: 400, headers: JSON_HEADERS });
      await env.DB.prepare("INSERT INTO planner_state (id, payload, updated_at) VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at").bind(JSON.stringify(payload), Date.now()).run();
      return new Response(JSON.stringify({ ok: true }), { headers: JSON_HEADERS });
    }
    return new Response(null, { status: 405, headers: { Allow: "GET, PUT" } });
  },
};
