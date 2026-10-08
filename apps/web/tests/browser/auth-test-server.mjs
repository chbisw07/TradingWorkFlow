// Disposable test database and user; never uses a developer database or dotenv.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { randomBytes } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";

const directory = mkdtempSync(join(tmpdir(), "twf-auth-e2e-"));
const api = resolve("../api");
const python = join(api, ".venv/bin/python");
const env = Object.fromEntries(
  Object.entries(process.env).filter(([name]) => !name.startsWith("TWF_")),
);
Object.assign(env, {
  TWF_ENVIRONMENT: "test",
  TWF_CREDENTIAL_MASTER_KEY: randomBytes(32).toString("base64url") + "=",
  TWF_BROKER_CALLBACK_URL: "http://127.0.0.1:3100/brokers/callback",
  TWF_SERVICE_CLIENTS: JSON.stringify(
    ["SCANNER", "TI", "TM", "LLM"].map((kind) => ({
      identity: {
        service_id: `synthetic-${kind.toLowerCase()}`,
        service_kind: kind,
        provider: "twf-fixture",
        service_version: "1",
      },
      mode: "SYNTHETIC",
      enabled: true,
    })),
  ),
  TWF_DATABASE_URL: `sqlite+pysqlite:///${directory}/auth.db`,
  TWF_CORS_ORIGINS: '["http://127.0.0.1:3100"]',
  TWF_MCP_PROVIDERS: JSON.stringify([
    {
      schema_version: "mcp.connection.v1",
      provider_id: "tapetide",
      display_name: "TapTide",
      category: "MARKET_INTELLIGENCE",
      endpoint: "https://mcp.tapetide.com/mcp",
      auth_mode: "API_KEY",
      timeout_seconds: 10,
      max_response_bytes: 262144,
      max_tools: 64,
      max_pages: 4,
      required_tools: [
        "get_market_pulse",
        "get_india_vix",
        "get_fii_dii_detail",
        "get_fpi_sectors",
        "get_index_performance",
        "get_market_news",
        "get_stock_events",
      ],
      retry_count: 0,
      refresh_policy: "EXPLICIT",
      health_policy: "INITIALIZE_AND_LIST_TOOLS",
    },
  ]),
});
const setup = spawnSync(
  python,
  [
    "-c",
    `from alembic import command
from alembic.config import Config
from twf.auth import create_user
from twf.config.settings import Settings
from twf.infrastructure.database import create_database_engine,create_session_factory,session_scope
command.upgrade(Config(${JSON.stringify(join(api, "alembic.ini"))}), 'head')
engine=create_database_engine(Settings())
with session_scope(create_session_factory(engine)) as session:
    create_user(session, 'browser-user', 'Browser Trader', 'test-only-browser-password')
    for browser in ('chromium', 'webkit'):
        for width in (390,768,1024,1440,1920,2560):
            create_user(session, f'watchlist-{browser}-{width}', 'Watchlist Trader', 'test-only-browser-password')
            create_user(session, f'builtin-{browser}-{width}', 'Built-in Watchlist Trader', 'test-only-browser-password')
            create_user(session, f'order-{browser}-{width}', 'Order Trader', 'test-only-browser-password')
            create_user(session, f'broker-{browser}-{width}', 'Broker Trader', 'test-only-browser-password')
            create_user(session, f'settings-{browser}-{width}', 'Settings Trader', 'test-only-browser-password')
            create_user(session, f'discovery-{browser}-{width}', 'Discovery Analyst', 'test-only-browser-password')
    session.commit()
engine.dispose()`,
  ],
  { cwd: directory, env, stdio: "inherit" },
);
if (setup.status !== 0) {
  rmSync(directory, { recursive: true });
  process.exit(1);
}
const child = spawn(
  python,
  [
    "-m",
    "uvicorn",
    "service_fixture_api:create_app",
    "--app-dir",
    resolve("tests/browser"),
    "--factory",
    "--host",
    "127.0.0.1",
    "--port",
    "8100",
    "--no-access-log",
  ],
  { cwd: directory, env, stdio: "inherit" },
);
for (const signal of ["SIGTERM", "SIGINT"])
  process.on(signal, () => child.kill(signal));
child.on("exit", (code) => {
  rmSync(directory, { recursive: true });
  process.exit(code || 0);
});
