import * as duckdb from "@duckdb/duckdb-wasm";
import ehWorkerUrl from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import mvpWorkerUrl from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";
import ehWasmUrl from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import mvpWasmUrl from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";
import type { Table } from "apache-arrow";

const BUNDLES: duckdb.DuckDBBundles = {
  mvp: { mainModule: mvpWasmUrl, mainWorker: mvpWorkerUrl },
  eh: { mainModule: ehWasmUrl, mainWorker: ehWorkerUrl },
};

let dbPromise: Promise<duckdb.AsyncDuckDB> | null = null;

async function init(dataUrl: string): Promise<duckdb.AsyncDuckDB> {
  const bundle = await duckdb.selectBundle(BUNDLES);
  const worker = new Worker(bundle.mainWorker!);
  const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING), worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  const conn = await db.connect();
  for (const table of ["core", "env", "climate"]) {
    await conn.query(
      `CREATE OR REPLACE VIEW ${table} AS SELECT * FROM read_parquet('${dataUrl}/${table}.parquet')`
    );
  }
  await conn.query(
    `CREATE OR REPLACE VIEW county_climate_daily AS
     SELECT * FROM read_parquet('${dataUrl}/county_climate_daily.parquet')`
  );
  await conn.query(
    `CREATE OR REPLACE VIEW county_climate_annual AS
     SELECT * FROM read_parquet('${dataUrl}/county_climate_annual.parquet')`
  );
  await conn.close();
  return db;
}

export function getDb(dataUrl: string): Promise<duckdb.AsyncDuckDB> {
  dbPromise ??= init(dataUrl);
  return dbPromise;
}

export async function runQuery(dataUrl: string, sql: string): Promise<Table> {
  const db = await getDb(dataUrl);
  const conn = await db.connect();
  try {
    return await conn.query(sql);
  } finally {
    await conn.close();
  }
}
