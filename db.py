import os, sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = os.environ.get("TRACKER_DB_PATH", str(Path(__file__).resolve().parent / "tracker.db"))

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.executescript("""
    PRAGMA journal_mode=WAL;

    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT DEFAULT (datetime('now')),
      name TEXT, email TEXT UNIQUE, status TEXT DEFAULT 'active',
      email_verified INTEGER DEFAULT 0, last_login_at TEXT
    );

    CREATE TABLE IF NOT EXISTS user_settings(
      user_id INTEGER PRIMARY KEY,
      market_default TEXT DEFAULT 'IN',
      capital_pool REAL DEFAULT 500000,
      max_risk_per_trade_pct REAL DEFAULT 1.5,
      max_open_trades INTEGER DEFAULT 3,
      commission_pct REAL DEFAULT 0.03,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS invites(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL, name TEXT, token TEXT UNIQUE NOT NULL,
      expires_at TEXT NOT NULL, used_at TEXT, invited_by INTEGER,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS sessions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL, refresh_token TEXT UNIQUE NOT NULL,
      email TEXT, user_agent TEXT, created_at TEXT DEFAULT (datetime('now')),
      expires_at TEXT NOT NULL, revoked INTEGER DEFAULT 0,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS trades(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL, created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT, symbol TEXT NOT NULL, market TEXT DEFAULT 'IN',
      sector TEXT, setup_tag TEXT, capital REAL, qty INTEGER NOT NULL, buy_price REAL NOT NULL,
      sl1 REAL, sl2 REAL, t1 REAL, t2 REAL,
      status TEXT DEFAULT 'open', sell_price REAL, sell_date TEXT,
      hold_days INTEGER, pnl_abs REAL, pnl_pct REAL, fees_abs REAL,
      post_exit_move TEXT, review_comment TEXT, notes TEXT,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS missed(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL, created_at TEXT DEFAULT (datetime('now')),
      symbol TEXT NOT NULL, sector TEXT, setup_tag TEXT,
      trigger_price REAL, reason_missed TEXT, high_after REAL, move_pct REAL,
      lesson TEXT, resolved INTEGER DEFAULT 0,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(user_id);
    CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
    CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
    """)
    conn.commit()

def ensure_owner():
    owner_email = os.getenv("OWNER_EMAIL")
    owner_name = os.getenv("OWNER_NAME", "Owner")
    if not owner_email: return
    if not get_user_by_email(owner_email):
        u = create_user(owner_email, owner_name)
        return u

def dictify(row): return {k: row[k] for k in row.keys()}

# ---- users
def get_user_by_email(email: str):
    conn = get_conn()
    r = conn.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone()
    return dictify(r) if r else None

def create_user(email: str, name: str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO users(name,email,status,email_verified,last_login_at) VALUES(?,?, 'active', 1, datetime('now'))", (name, email.lower().strip()))
    uid = cur.lastrowid
    cur.execute("INSERT INTO user_settings(user_id) VALUES(?)", (uid,))
    conn.commit()
    return get_user_by_email(email)

def update_user(user_id: int, **fields):
    if not fields: return False
    conn = get_conn()
    sets = ", ".join([f"{k}=?" for k in fields.keys()])
    conn.execute(f"UPDATE users SET {sets} WHERE id=?", [*fields.values(), user_id]); conn.commit(); return True

def set_user_status(user_id: int, status: str):
    return update_user(user_id, status=status)

def list_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    return [dictify(r) for r in rows]

# ---- settings
def get_settings(user_id: int):
    conn = get_conn()
    r = conn.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
    return dictify(r) if r else {}

def update_settings(user_id: int, **fields): return update_user_settings(user_id, **fields)

def update_user_settings(user_id: int, **fields):
    conn = get_conn()
    sets = ", ".join([f"{k}=?" for k in fields.keys()])
    conn.execute(f"UPDATE user_settings SET {sets} WHERE user_id=?", [*fields.values(), user_id]); conn.commit(); return True

# ---- invites
def create_invite(email: str, name: str, token: str, expires_at: str, invited_by: int):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO invites(email,name,token,expires_at,invited_by) VALUES(?,?,?,?,?)", (email.lower().strip(), name, token, expires_at, invited_by))
    conn.commit(); return cur.lastrowid

def get_invite_by_token(token: str):
    conn = get_conn()
    r = conn.execute("SELECT * FROM invites WHERE token=?", (token,)).fetchone()
    return dictify(r) if r else None

def mark_invite_used(invite_id: int):
    conn = get_conn(); conn.execute("UPDATE invites SET used_at=datetime('now') WHERE id=?", (invite_id,)); conn.commit()

# ---- sessions
def create_session(user_id: int, refresh_token: str, expires_at: str, user_agent: str=""):
    u = get_user(user_id)
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO sessions(user_id,refresh_token,email,user_agent,expires_at) VALUES(?,?,?,?,?)", (user_id, refresh_token, u["email"], user_agent[:200], expires_at))
    conn.commit(); return cur.lastrowid

def get_user(user_id: int):
    conn = get_conn(); r = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dictify(r) if r else None

def get_session(refresh_token: str):
    conn = get_conn(); r = conn.execute("SELECT * FROM sessions WHERE refresh_token=?", (refresh_token,)).fetchone()
    return dictify(r) if r else None

def list_sessions(user_id: int):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM sessions WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    return [dictify(r) for r in rows]

def revoke_all_sessions(user_id: int):
    conn = get_conn(); conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (user_id,)); conn.commit()

# ---- trades
def add_trade(user_id:int, symbol:str, qty:int, buy_price:float, sl1=None, sl2=None, t1=None, t2=None, capital=None, sector=None, setup_tag=None, notes=None, market="IN"):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO trades(user_id,symbol,qty,buy_price,sl1,sl2,t1,t2,capital,sector,setup_tag,notes,market,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
    """,(user_id, symbol.upper().strip(), qty, buy_price, sl1, sl2, t1, t2, capital, sector, setup_tag, notes, market))
    conn.commit(); return cur.lastrowid

def list_open_trades(user_id:int):
    conn = get_conn(); rows = conn.execute("SELECT * FROM trades WHERE user_id=? AND status='open' ORDER BY created_at DESC",(user_id,)).fetchall()
    return [dictify(r) for r in rows]

def list_closed_trades(user_id:int):
    conn = get_conn(); rows = conn.execute("SELECT * FROM trades WHERE user_id=? AND status='closed' ORDER BY sell_date DESC",(user_id,)).fetchall()
    return [dictify(r) for r in rows]

def update_trade(trade_id:int, user_id:int, **fields):
    if not fields: return False
    conn = get_conn()
    sets = ", ".join([f"{k}=?" for k in fields.keys()])
    conn.execute(f"UPDATE trades SET {sets}, updated_at=datetime('now') WHERE id=? AND user_id=?", [*fields.values(), trade_id, user_id])
    conn.commit(); return True

def close_trade(trade_id:int, user_id:int, sell_price:float, commission_pct:float, post_exit:str=None, review:str=None):
    conn = get_conn(); cur = conn.cursor()
    r = cur.execute("SELECT * FROM trades WHERE id=? AND user_id=?", (trade_id, user_id)).fetchone()
    if not r: return None
    r = dictify(r)
    buy = r["buy_price"]; qty = r["qty"]
    buy_notional = (buy or 0)*qty
    sell_notional = (sell_price or 0)*qty
    fees = (commission_pct/100.0) * (buy_notional + sell_notional)
    pnl_abs_gross = (sell_price - buy) * qty
    pnl_abs = pnl_abs_gross - fees
    pnl_pct = ((sell_price - buy) / buy * 100.0) if buy else 0.0
    created = datetime.fromisoformat(r["created_at"])
    sold_at = datetime.utcnow()
    hold_days = (sold_at.date() - created.date()).days
    cur.execute("""
        UPDATE trades SET status='closed', sell_price=?, sell_date=?, hold_days=?, pnl_abs=?, pnl_pct=?, fees_abs=?, post_exit_move=?, review_comment=?, updated_at=datetime('now')
        WHERE id=? AND user_id=?
    """,(sell_price, sold_at.isoformat(), hold_days, pnl_abs, pnl_pct, fees, post_exit, review, trade_id, user_id))
    conn.commit(); return trade_id

def sum_open_capital(user_id:int) -> float:
    conn = get_conn()
    row = conn.execute("SELECT COALESCE(SUM(capital),0) AS s FROM trades WHERE user_id=? AND status='open'", (user_id,)).fetchone()
    return float(dictify(row)["s"] or 0.0)

# ---- missed
def add_missed(user_id:int, symbol:str, sector=None, setup_tag=None, trigger_price=None, reason_missed=None, high_after=None, move_pct=None, lesson=None):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO missed(user_id,symbol,sector,setup_tag,trigger_price,reason_missed,high_after,move_pct,lesson)
        VALUES (?,?,?,?,?,?,?,?,?)
    """,(user_id, symbol.upper().strip(), sector, setup_tag, trigger_price, reason_missed, high_after, move_pct, lesson))
    conn.commit(); return cur.lastrowid

def list_missed(user_id:int, active_only:bool=True):
    conn = get_conn()
    sql = "SELECT * FROM missed WHERE user_id=?"
    if active_only: sql += " AND (resolved=0 OR resolved IS NULL)"
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, (user_id,)).fetchall()
    return [dictify(r) for r in rows]

def resolve_missed(user_id:int, item_id:int, resolved:bool=True):
    conn = get_conn(); conn.execute("UPDATE missed SET resolved=? WHERE id=? AND user_id=?", (1 if resolved else 0, item_id, user_id)); conn.commit()

# ---- stats
def compute_stats(user_id:int):
    conn = get_conn()
    row = conn.execute("""
        SELECT
          SUM(CASE WHEN status='closed' THEN pnl_abs ELSE 0 END) AS realized,
          COUNT(CASE WHEN status='open' THEN 1 END) AS open_count,
          COUNT(CASE WHEN status='closed' THEN 1 END) AS closed_count,
          AVG(CASE WHEN status='closed' THEN pnl_pct END) AS avg_closed_pct,
          SUM(CASE WHEN status='closed' AND pnl_abs>0 THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN status='closed' AND pnl_abs<=0 THEN 1 ELSE 0 END) AS losses
        FROM trades WHERE user_id=?
    """,(user_id,)).fetchone()
    d = dictify(row) if row else {}
    total_closed = (d.get("wins") or 0) + (d.get("losses") or 0)
    d["win_rate_pct"] = round((d.get("wins") or 0) / total_closed * 100.0, 2) if total_closed else None
    return d
