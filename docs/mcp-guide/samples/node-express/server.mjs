// MCP server mẫu cho phân hệ DNS (ví dụ: Kho) – Node.js 20 + Express + jose.
// Chuẩn MCP 2025-06-18 (Streamable HTTP, chỉ phản hồi JSON) + profile DNS (chỉ đọc, lọc quyền, x-dns).
// Chạy: npm i && MCP_AGENT_TOKEN=... OIDC_ACCEPTED_AUDIENCES=... node server.mjs
import crypto from 'node:crypto';
import express from 'express';
import { createRemoteJWKSet, jwtVerify } from 'jose';

const PROTOCOL_VERSION = '2025-06-18';
const SUPPORTED = new Set(['2025-06-18', '2025-03-26']);
const SERVER_INFO = { name: 'svc-kho', title: 'Kho – Tồn kho', version: '1.0.0' };
const INSTRUCTIONS = 'Dữ liệu kho: tồn kho theo mặt hàng/kho. Chỉ đọc; đã lọc theo kho người hỏi được phân quyền.';
const ISSUER = process.env.OIDC_ISSUER ?? 'https://sopbase.digigov.vn/auth';
const AUDIENCES = (process.env.OIDC_ACCEPTED_AUDIENCES ?? '').split(',').map((s) => s.trim()).filter(Boolean);
const JWKS = createRemoteJWKSet(new URL(process.env.OIDC_JWKS_URL ?? 'https://sopbase.digigov.vn/auth/jwks'));
const AGENT_TOKEN = process.env.MCP_AGENT_TOKEN ?? '';

// ── Dữ liệu & RBAC demo (thực tế: DB + RBAC của phân hệ) ──
const STOCK = [
  { tenant: 't1', sku: 'SP001', name: 'Giấy A4 Double A', warehouse: 'HN', qty: 120, unit: 'ram' },
  { tenant: 't1', sku: 'SP001', name: 'Giấy A4 Double A', warehouse: 'HCM', qty: 40, unit: 'ram' },
  { tenant: 't1', sku: 'SP002', name: 'Mực in HP 12A', warehouse: 'HN', qty: 5, unit: 'hộp' },
];
const MEMBERS = new Map([
  ['t1|sale1@test.com', { perms: ['kho:stock:read'], warehouses: ['HN'] }],
  ['t1|manager@test.com', { perms: ['kho:stock:read'], warehouses: ['HN', 'HCM'] }],
]);

const TOOLS = [
  {
    name: 'kho_ton_kho',
    title: 'Tồn kho theo mặt hàng',
    description: 'Tra số lượng tồn theo tên hoặc mã hàng (SP…), lọc theo kho. Chỉ trả kho người hỏi được phân quyền.',
    permissions: ['kho:stock:read'],
    inputSchema: {
      type: 'object', additionalProperties: false, required: ['query'],
      properties: {
        query: { type: 'string', minLength: 1, maxLength: 80, description: 'Tên hoặc mã hàng' },
        warehouse: { type: 'string', enum: ['HN', 'HCM'], description: 'Mã kho (tuỳ chọn)' },
      },
    },
    meta: { group: 'Kho', keywords: ['\\bton kho\\b', '\\bcon bao nhieu\\b'], priority: 20, queryArg: 'query',
            suggestion: 'Giấy A4 còn bao nhiêu trong kho?' },
    handler(ctx, args) {
      const q = args.query.toLowerCase();
      const rows = STOCK.filter((r) => r.tenant === ctx.tenant && ctx.warehouses.includes(r.warehouse)
        && (!args.warehouse || r.warehouse === args.warehouse)
        && (r.name.toLowerCase().includes(q) || r.sku.toLowerCase() === q)).slice(0, 20);
      return { total: rows.length, items: rows.map(({ tenant, ...r }) => r),
               link: { web: `/inventory/stock?q=${encodeURIComponent(args.query)}`, label: 'Mở tồn kho' } };
    },
  },
];

const descriptor = (t) => ({
  name: t.name, title: t.title, description: t.description, inputSchema: t.inputSchema,
  annotations: { title: t.title, readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  'x-dns': { title: t.title, module: 'kho', readOnly: true, permissions: t.permissions, permissionMode: 'any',
             roles: [], sensitive: false, ...t.meta },
});
const allowedTools = (ctx) => TOOLS.filter((t) => t.permissions.some((p) => ctx.perms.includes(p)));

function validateArgs(schema, args) {
  const props = schema.properties ?? {};
  for (const r of schema.required ?? []) if (!(r in args)) throw new Error(`thiếu tham số '${r}'`);
  for (const k of Object.keys(args)) if (!(k in props)) throw new Error(`tham số không hỗ trợ: ${k}`);
  for (const [k, s] of Object.entries(props)) {
    if (!(k in args)) continue;
    const v = args[k];
    if (s.type === 'string' && (typeof v !== 'string' || v.length < (s.minLength ?? 0) || v.length > (s.maxLength ?? 1e4)))
      throw new Error(`'${k}' không hợp lệ`);
    if (s.enum && !s.enum.includes(v)) throw new Error(`'${k}' phải thuộc ${s.enum.join(', ')}`);
  }
  return args;
}

const ok = (id, result) => ({ jsonrpc: '2.0', id, result });
const err = (id, code, message) => ({ jsonrpc: '2.0', id, error: { code, message } });
const toolResult = (data) => ({ content: [{ type: 'text', text: JSON.stringify(data) }], structuredContent: data,
                                isError: Boolean(data && data.error) });

function handle(ctx, msg) {
  if (msg?.jsonrpc !== '2.0' || typeof msg.method !== 'string') return err(msg?.id ?? null, -32600, 'Invalid Request');
  const { id, method } = msg;
  const params = msg.params ?? {};
  if (id === undefined || id === null) return null; // notification
  if (method === 'initialize') {
    const v = SUPPORTED.has(params.protocolVersion) ? params.protocolVersion : PROTOCOL_VERSION;
    return ok(id, { protocolVersion: v, capabilities: { tools: { listChanged: false } }, serverInfo: SERVER_INFO, instructions: INSTRUCTIONS });
  }
  if (method === 'ping') return ok(id, {});
  if (method === 'tools/list') return ok(id, { tools: allowedTools(ctx).map(descriptor) });
  if (method === 'tools/call') {
    const tool = allowedTools(ctx).find((t) => t.name === params.name); // kiểm quyền lần 2
    if (!tool) return ok(id, toolResult({ error: 'not_permitted_or_unknown_tool' }));
    const args = params.arguments ?? {};
    if (typeof args !== 'object' || Array.isArray(args)) return err(id, -32602, 'arguments phải là object');
    try {
      const data = tool.handler(ctx, validateArgs(tool.inputSchema, args));
      console.info(`mcp tools/call tool=${tool.name} user=${ctx.email} tenant=${ctx.tenant} ok=${!data.error}`);
      return ok(id, toolResult(data));
    } catch (e) {
      return ok(id, toolResult({ error: 'invalid_arguments', message: String(e.message).slice(0, 200) }));
    }
  }
  return err(id, -32601, `Method không hỗ trợ: ${method}`);
}

// ── HTTP ──
const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '64kb' }));

function safeEqual(a, b) {
  const x = Buffer.from(a ?? ''), y = Buffer.from(b ?? '');
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}
const deny = (res, status, error, message) => {
  if (status === 401) res.set('WWW-Authenticate', `Bearer error="${error}"`);
  return res.status(status).json({ error, message });
};

app.post('/mcp', async (req, res) => {
  if (!AGENT_TOKEN) return deny(res, 503, 'mcp_disabled', 'MCP chưa bật (thiếu MCP_AGENT_TOKEN)');
  if (!safeEqual(AGENT_TOKEN, req.get('X-Agent-Token'))) return deny(res, 401, 'invalid_agent_token', 'X-Agent-Token không hợp lệ');
  const auth = req.get('Authorization') ?? '';
  if (!/^bearer /i.test(auth) || AUDIENCES.length === 0) return deny(res, 401, 'invalid_token', 'Thiếu token người dùng');
  let claims;
  try {
    ({ payload: claims } = await jwtVerify(auth.slice(7).trim(), JWKS, {
      issuer: ISSUER, audience: AUDIENCES, algorithms: ['RS256'], clockTolerance: 30, requiredClaims: ['sub', 'exp'],
    }));
  } catch (e) {
    console.warn('mcp auth failed:', e.code ?? e.name); // không log token
    return deny(res, 401, 'invalid_token', 'Token người dùng không hợp lệ hoặc hết hạn');
  }
  const tenant = (req.get('tenant-id') ?? '').trim();
  if (!tenant || tenant.length > 64) return deny(res, 400, 'tenant_required', 'Thiếu header tenant-id');
  const email = String(claims.email ?? '').toLowerCase().trim();
  const member = MEMBERS.get(`${tenant}|${email}`);
  if (!member) return deny(res, 403, 'forbidden', 'Người dùng không thuộc tenant này');
  const ctx = { tenant, email, claims, perms: member.perms, warehouses: member.warehouses };

  const body = req.body;
  if (Array.isArray(body)) {
    const out = body.slice(0, 20).map((m) => handle(ctx, m)).filter(Boolean);
    return out.length ? res.json(out) : res.status(202).end();
  }
  const r = handle(ctx, body);
  return r ? res.json(r) : res.status(202).end();
});
app.get('/mcp', (_req, res) => res.set('Allow', 'POST').status(405).end());
app.get('/health', (_req, res) => res.json({ status: 'ok' }));
// JSON hỏng → lỗi JSON-RPC Parse error
app.use((e, _req, res, _next) => res.status(400).json(err(null, -32700, 'Parse error')));

const port = Number(process.env.PORT ?? 8301);
app.listen(port, () => console.info(`svc-kho MCP listening on :${port}`));

