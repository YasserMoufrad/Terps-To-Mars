// Small structured logger for the browser app (CLAUDE.md section 16).
// Every event is one JSON-friendly object: UTC timestamp, level, the run_id shared
// by every event in this page load, a stage (which part of the app) and an event name.
// It has no dependencies, so it can also be loaded by the Node test runner.

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogEvent {
  ts: string;
  level: LogLevel;
  run_id: string;
  stage: string;
  event: string;
  [field: string]: unknown;
}

export type LogSink = (entry: LogEvent) => void;

export interface Logger {
  readonly runId: string;
  debug(stage: string, event: string, fields?: Record<string, unknown>): void;
  info(stage: string, event: string, fields?: Record<string, unknown>): void;
  warn(stage: string, event: string, fields?: Record<string, unknown>): void;
  error(stage: string, event: string, fields?: Record<string, unknown>): void;
}

export interface LoggerOptions {
  runId?: string;
  debug?: boolean; // DEBUG events are dropped unless this is true
  sink?: LogSink;
}

// Field names that must never reach a log, whatever their value.
const SECRET_KEY = /(token|secret|password|passwd|api[-_]?key|authorization|cookie)/i;

function newRunId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  return `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function redact(fields: Record<string, unknown>): Record<string, unknown> {
  const clean: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(fields)) {
    clean[key] = SECRET_KEY.test(key) ? '[redacted]' : value;
  }
  return clean;
}

// Default sink: the browser console, keeping the level so DevTools filters work.
const consoleSink: LogSink = (entry) => {
  const method = entry.level === 'debug' ? 'debug' : entry.level;
  console[method](`[${entry.stage}] ${entry.event}`, entry);
};

export function createLogger(options: LoggerOptions = {}): Logger {
  const runId = options.runId ?? newRunId();
  const sink = options.sink ?? consoleSink;
  const debugEnabled = options.debug ?? false;

  const emit = (level: LogLevel, stage: string, event: string, fields: Record<string, unknown> = {}) => {
    if (level === 'debug' && !debugEnabled) return;
    try {
      // Standard fields go last so a caller can never overwrite ts, level or run_id.
      sink({ ...redact(fields), ts: new Date().toISOString(), level, run_id: runId, stage, event });
    } catch {
      // A broken log sink must never break the app or change what it shows.
    }
  };

  return {
    runId,
    debug: (stage, event, fields) => emit('debug', stage, event, fields),
    info: (stage, event, fields) => emit('info', stage, event, fields),
    warn: (stage, event, fields) => emit('warn', stage, event, fields),
    error: (stage, event, fields) => emit('error', stage, event, fields),
  };
}

// A logger that discards everything; the default where logging is optional.
export const silentLogger: Logger = createLogger({ runId: 'silent', sink: () => {} });
