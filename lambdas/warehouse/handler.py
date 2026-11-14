import os, re, boto3, duckdb
from _common import envelope, dispatch

BUCKET = os.environ["DATA_BUCKET"]
TABLES = {"daily_payment_stats": "snowflake/daily_payment_stats.csv", "query_logs": "snowflake/query_logs.csv"}
BLOCK = re.compile(r"\b(insert|update|delete|drop|create|alter|copy|attach|detach|pragma|install|load|export|call|set|truncate|read_csv|read_parquet|glob)\b", re.I)
SCAN_CAP = 50_000          # simulated cost cap, in rows scanned
ROW_CAP = 200
_con, _counts = None, {}


def con():
    global _con
    if _con is None:
        s3 = boto3.client("s3")
        _con = duckdb.connect(":memory:")
        for t, key in TABLES.items():
            path = f"/tmp/{t}.csv"
            s3.download_file(BUCKET, key, path)
            _con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto('{path}')")
            _counts[t] = _con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        _con.execute("SET enable_external_access=false")
    return _con


def query_history(ev):
    sql = ev["sql"].strip().rstrip(";")
    if ";" in sql:
        raise ValueError("only a single statement is allowed")
    if not re.match(r"^(select|with)\b", sql, re.I) or BLOCK.search(sql):
        raise ValueError("SELECT only: DDL/DML and file functions are rejected")
    c = con()
    used = [t for t in TABLES if re.search(rf"\b{t}\b", sql)]
    est = sum(_counts[t] for t in used)
    if re.search(r"\bjoin\b", sql, re.I) and not re.search(r"\b(on|using)\b", sql, re.I) or re.search(r"\bcross\b", sql, re.I):
        est = 1
        for t in used:
            est *= _counts[t]
    if est > SCAN_CAP:
        raise ValueError(f"estimated scan {est} rows exceeds cap {SCAN_CAP} (simulated cost cap)")
    cur = c.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchmany(ROW_CAP)
    data = [dict(zip(cols, [str(v) if not isinstance(v, (int, float, type(None))) else v for v in r])) for r in rows]
    return envelope("warehouse:duckdb(snowflake-mock)", sql, {"estimated_rows_scanned": est, "row_count": len(data), "rows": data})


def lambda_handler(event, context):
    return dispatch(event, context, {"query_history": query_history})
