// Disposable test database and user; never uses a developer database or dotenv.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawn, spawnSync } from "node:child_process";

const directory = mkdtempSync(join(tmpdir(), "twf-auth-e2e-"));
const api = resolve("../api");
const python = join(api, ".venv/bin/python");
const env = Object.fromEntries(
  Object.entries(process.env).filter(([name]) => !name.startsWith("TWF_")),
);
Object.assign(env, {
  TWF_ENVIRONMENT: "test",
  TWF_DATABASE_URL: `sqlite+pysqlite:///${directory}/auth.db`,
  TWF_CORS_ORIGINS: '["http://127.0.0.1:3100"]',
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
    "twf.main:create_app",
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
