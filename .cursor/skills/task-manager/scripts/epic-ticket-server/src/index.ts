import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js';
import { openDatabase } from './db.js';
import { createMcpServer } from './registerMcp.js';

const db = openDatabase();

const app = new Hono();

app.use(
  '*',
  cors({
    origin: '*',
    allowMethods: ['GET', 'POST', 'DELETE', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'mcp-session-id', 'Last-Event-ID', 'mcp-protocol-version'],
    exposeHeaders: ['mcp-session-id', 'mcp-protocol-version'],
  }),
);

app.get('/health', (c) => c.json({ status: 'ok', db: process.env.EPIC_TICKET_DB ?? 'default data/epic-tickets.db' }));

app.all('/mcp', async (c) => {
  const transport = new WebStandardStreamableHTTPServerTransport();
  const server = createMcpServer(db);
  await server.connect(transport);
  return transport.handleRequest(c.req.raw);
});

const PORT = process.env.MCP_PORT ? parseInt(process.env.MCP_PORT, 10) : 3847;

console.log(`Epic ticket MCP (Hono) on http://localhost:${PORT}`);
console.log(`Health: http://localhost:${PORT}/health`);
console.log(`MCP:    http://localhost:${PORT}/mcp`);

serve({
  fetch: app.fetch,
  port: PORT,
});
