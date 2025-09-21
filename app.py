import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import secrets

from config import app_cfg
from db import (
    init_db, ensure_owner,
    get_user_by_email, create_user, update_user, list_users, set_user_status,
    get_settings, update_settings,
    create_invite, get_invite_by_token, mark_invite_used,
    create_session, get_session, revoke_all_sessions, list_sessions,
    add_trade, update_trade, list_open_trades, list_closed_trades, close_trade,
    add_missed, list_missed, resolve_missed, compute_stats, sum_open_capital,
)
from tokens import make_token, verify_token
from mailer import send_email
from risk import risk_nudges

st.set_page_config(page_title="Swing Tracker v2.2 — Invite Only", layout="centered")
init_db()
ensure_owner()  # optional auto-owner via env (OWNER_EMAIL)

# ------------- helpers -------------
def _qp(name: str):
    try:
        # Streamlit >= 1.30
        return st.query_params.get(name)
    except Exception:
        return st.experimental_get_query_params().get(name, [None])[0]

def _set_user(u: dict, rt: str):
    st.session_state.user = u
    st.session_state.refresh_token = rt

def _login_with_refresh():
    rt = st.session_state.get("refresh_token")
    if not rt:
        return None
    row = get_session(rt)
    if not row or row.get("revoked"):
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        return None
    u = get_user_by_email(row["email"])
    if not u or u.get("status") != "active":
        return None
    update_user(u["id"], last_login_at=datetime.utcnow().isoformat())
    _set_user(u, rt)
    return u

def _very_long_session_days():
    # default ~10 years
    return int(st.secrets.get("VERY_LONG_SESSION_DAYS", 3650))

def _create_very_long_session(u: dict):
    rt = secrets.token_urlsafe(32)
    exp = (datetime.utcnow() + timedelta(days=_very_long_session_days())).isoformat()
    create_session(user_id=u["id"], refresh_token=rt, expires_at=exp, user_agent=st.session_state.get("_user_agent",""))
    _set_user(u, rt)

def logout_here():
    st.session_state.pop("user", None)
    st.session_state.pop("refresh_token", None)

# ------------- Login / Invite accept -------------
def show_login():
    st.title("Swing Tracker (Invite Only)")
    # Accept invite
    invite_token = _qp("invite")
    if invite_token:
        ok, payload = verify_token(invite_token)
        if not ok:
            st.error("Invite link invalid/expired.")
        else:
            inv = get_invite_by_token(invite_token)
            if not inv or inv.get("used_at"):
                st.error("Invite already used or invalid.")
            else:
                st.success(f"Invite verified for {inv['email']}. Click Accept to create account.")
                name = st.text_input("Your name", value=inv.get("name") or inv["email"].split("@")[0])
                if st.button("Accept Invite"):
                    u = get_user_by_email(inv["email"])
                    if not u:
                        u = create_user(email=inv["email"], name=name)
                    mark_invite_used(inv["id"])
                    _create_very_long_session(u)
                    st.success("Account created. You are signed in.")
                    st.rerun()

    st.subheader("Login link")
    email = st.text_input("Your email")
    if st.button("Send me a login link"):
        u = get_user_by_email(email)
        if not u:
            st.error("No account found. Ask the admin for an invite.")
        elif u.get("status") != "active":
            st.error("Account suspended. Contact admin.")
        else:
            t = make_token(email.lower().strip(), ttl_seconds=15*60)
            link = f"{app_cfg.app_url}/?login={t}"
            result = send_email(email, "Your login link", f"<p>Click to sign in: <a href='{link}'>Sign in</a> (valid 15 min)</p>")
            if result.get("mock"):
                st.info("SMTP not configured; showing the link here:")
                st.code(link, language="text")
            st.success("Login link sent (or displayed above).")

    login_t = _qp("login")
    if login_t:
        ok, payload = verify_token(login_t)
        if ok:
            u = get_user_by_email(payload)
            if u and u.get("status") == "active":
                _create_very_long_session(u)
                update_user(u["id"], last_login_at=datetime.utcnow().isoformat())
                st.success("Signed in.")
                st.rerun()
            else:
                st.error("Invalid or suspended account.")
        else:
            st.error("Login link invalid/expired.")

# ------------- Try auto-login by refresh token -------------
if "user" not in st.session_state:
    st.session_state.user = None
if st.session_state.user is None:
    _login_with_refresh()

# ------------- Not logged in? show login -------------
if not st.session_state.user:
    show_login()
    st.stop()

# ------------- App UI (tabs) -------------
user = st.session_state.user
uid = user["id"]

st.sidebar.write(f"Logged in as **{user.get('name') or user['email']}**")
if st.sidebar.button("Logout (this device)"):
    logout_here()
    st.rerun()
if st.sidebar.button("Logout everywhere"):
    revoke_all_sessions(uid)
    logout_here()
    st.rerun()

home_tab, trades_tab, missed_tab, insights_tab, settings_tab, admin_tab = st.tabs(
    ["Home (Quick Add)", "Trades", "Missed", "Insights", "Settings", "Admin"]
)

# -------- HOME --------
with home_tab:
    st.subheader("➕ Add Trade (India-first)")
    s = get_settings(uid)
    with st.form("quick_add", clear_on_submit=True):
        col1, col2 = st.columns(2)
        symbol = col1.text_input("Symbol*", placeholder="e.g., JIOFIN").upper().strip()
        qty = col2.number_input("Qty*", min_value=1, step=1)
        col3, col4 = st.columns(2)
        buy = col3.number_input("Buy Price (₹)*", min_value=0.0, step=0.05, format="%.2f")
        capital = col4.number_input("Capital Used (₹)", min_value=0.0, step=100.0)
        col5, col6 = st.columns(2)
        sl1 = col5.number_input("SL1 (₹)", min_value=0.0, step=0.05, format="%.2f")
        sl2 = col6.number_input("SL2 (₹)", min_value=0.0, step=0.05, format="%.2f")
        col7, col8 = st.columns(2)
        t1 = col7.number_input("T1 (₹)", min_value=0.0, step=0.05, format="%.2f")
        t2 = col8.number_input("T2 (₹)", min_value=0.0, step=0.05, format="%.2f")
        sector = st.text_input("Sector (optional)", placeholder="e.g., Financials")
        setup_tag = st.selectbox("Setup (optional)", ["", "Breakout", "Pullback", "Reversal", "Retest", "Momentum"], index=0)
        notes = st.text_area("Notes (optional)")

        if st.form_submit_button("Save"):
            if not symbol or qty <= 0 or buy <= 0:
                st.error("Symbol, Qty, Buy are required.")
            else:
                tid = add_trade(uid, symbol, qty, buy,
                                sl1 or None, sl2 or None, t1 or None, t2 or None,
                                capital or None, sector or None, setup_tag or None, notes or None, market="IN")
                st.success(f"Saved trade #{tid} — {symbol}")
                open_trades = list_open_trades(uid)
                this_trade = next((t for t in open_trades if t["id"] == tid), None)
                if this_trade:
                    for a in risk_nudges(uid, this_trade, open_trades):
                        getattr(st, "warning" if a.level=="warn" else ("error" if a.level=="error" else "info"))(a.message)

    st.markdown("---")
    st.subheader("🔎 Quick Lookup")
    q = st.text_input("Find by Symbol or Trade ID", placeholder="e.g., VBL or 12")
    if st.button("Show"):
        res = [t for t in list_open_trades(uid) + list_closed_trades(uid) if q and (q.upper() in t["symbol"] or q == str(t["id"]))]
        if not res:
            st.info("No matches.")
        else:
            r = res[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("Buy", f"{r['buy_price']:.2f}")
            c2.metric("SL1", f"{(r.get('sl1') or 0):.2f}")
            c3.metric("T1", f"{(r.get('t1') or 0):.2f}")
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("SL2", f"{(r.get('sl2') or 0):.2f}")
            cc2.metric("T2", f"{(r.get('t2') or 0):.2f}")
            cc3.metric("Qty", f"{r['qty']}")

# -------- TRADES --------
with trades_tab:
    st.subheader("Open Trades")
    data = list_open_trades(uid)
    if data:
        df = pd.DataFrame(data)
        cols = ["id","created_at","symbol","qty","buy_price","sl1","sl2","t1","t2","capital","sector","setup_tag"]
        st.dataframe(df[cols], use_container_width=True)
    else:
        st.caption("No open trades.")

    st.markdown("---")
    st.subheader("Close (Tap Sold)")
    c1, c2 = st.columns(2)
    tid = c1.number_input("Trade ID", min_value=1, step=1)
    sell_price = c2.number_input("Sell Price (₹)", min_value=0.0, step=0.05, format="%.2f")
    post_exit = st.text_input("Post-exit move (optional)")
    review = st.selectbox("Review", ["", "Good trade", "Bad trade", "Emotional exit", "Emotional buy", "Could have waited", "Perfect execution"], index=0)
    if st.button("Close Now"):
        if sell_price > 0:
            commission_pct = float(get_settings(uid).get("commission_pct") or 0.03)
            res = close_trade(int(tid), uid, float(sell_price), commission_pct, post_exit or None, review or None)
            if res:
                st.success(f"Closed #{tid} at ₹{sell_price:.2f}. P&L and hold days computed.")
            else:
                st.error("Trade not found or not yours.")
        else:
            st.error("Provide a valid Sell Price.")

    st.markdown("---")
    st.subheader("Closed Trades (recent)")
    closed = list_closed_trades(uid)
    if closed:
        cdf = pd.DataFrame(closed)
        show = ["id","symbol","qty","buy_price","sell_price","hold_days","fees_abs","pnl_abs","pnl_pct","sell_date","review_comment"]
        st.dataframe(cdf[show], use_container_width=True)
    else:
        st.caption("No closed trades yet.")

# -------- MISSED --------
with missed_tab:
    st.subheader("Missed Opportunities")
    with st.form("missed_add", clear_on_submit=True):
        ms = st.text_input("Symbol*", placeholder="e.g., APOLLOTYRE").upper().strip()
        c1, c2 = st.columns(2)
        msec = c1.text_input("Sector", placeholder="Auto Ancillaries")
        msetup = c2.text_input("Setup Tag", placeholder="Breakout")
        c3, c4 = st.columns(2)
        mtrig = c3.number_input("Trigger Price", min_value=0.0, step=0.05, format="%.2f")
        mmove = c4.number_input("Move % after skip", min_value=0.0, step=0.1, format="%.2f")
        mwhy = st.text_area("Why we missed it?")
        mlesson = st.text_area("Lesson / Fix")
        if st.form_submit_button("Save Missed Idea"):
            if not ms:
                st.error("Symbol required.")
            else:
                add_missed(uid, ms, sector=msec or None, setup_tag=msetup or None,
                           trigger_price=mtrig or None, reason_missed=mwhy or None,
                           move_pct=mmove or None, lesson=mlesson or None)
                st.success("Saved.")

    st.markdown("---")
    miss = list_missed(uid, True)
    if miss:
        mdf = pd.DataFrame(miss)
        show = ["id","created_at","symbol","sector","setup_tag","trigger_price","move_pct","lesson"]
        st.dataframe(mdf[show], use_container_width=True)
        sel = st.number_input("Mark ID as resolved", min_value=0, step=1)
        if st.button("Resolve"):
            if sel > 0:
                resolve_missed(uid, int(sel), True)
                st.success(f"Resolved {sel}.")
    else:
        st.caption("No active missed ideas.")

# -------- INSIGHTS --------
with insights_tab:
    st.subheader("Insights")
    stats = compute_stats(uid)
    col1, col2, col3 = st.columns(3)
    col1.metric("Win Rate", f"{(stats.get('win_rate_pct') or 0):.1f}%")
    col2.metric("Realized P&L", f"₹{(stats.get('realized') or 0):,.0f}")
    col3.metric("Closed Trades", stats.get("closed_count") or 0)

    st.markdown("---")
    open_cap = sum_open_capital(uid)
    pool = float(get_settings(uid).get("capital_pool") or 500000)
    remaining = max(0.0, pool - open_cap)
    st.write(f"**Capital Pool:** ₹{pool:,.0f}  |  **Open Allocation:** ₹{open_cap:,.0f}  |  **Available:** ₹{remaining:,.0f}")

# -------- SETTINGS --------
with settings_tab:
    st.subheader("Preferences (per user)")
    s = get_settings(uid)
    with st.form("prefs"):
        colA, colB, colC = st.columns(3)
        market_default = colA.selectbox("Default Market", ["IN","US","AU"], index=["IN","US","AU"].index(s.get("market_default","IN")))
        capital_pool = colB.number_input("Capital Pool (₹)", value=float(s.get("capital_pool") or 500000), step=10000.0)
        commission_pct = colC.number_input("Commission % (one-way)", value=float(s.get("commission_pct") or 0.03), step=0.01, format="%.2f")

        colD, colE = st.columns(2)
        max_risk = colD.number_input("Max Risk per Trade (%)", value=float(s.get("max_risk_per_trade_pct") or 1.5), step=0.1, format="%.1f")
        max_open = colE.number_input("Max Open Trades", value=int(s.get("max_open_trades") or 3), step=1)

        if st.form_submit_button("Save Settings"):
            update_settings(uid, market_default=market_default, capital_pool=capital_pool,
                            commission_pct=commission_pct, max_risk_per_trade_pct=max_risk, max_open_trades=int(max_open))
            st.success("Settings saved.")

# -------- ADMIN --------
with admin_tab:
    st.subheader("Invite & Manage Users")
    st.caption("Magic links are single-use; sessions are long-lived until you revoke.")

    with st.form("invite_form", clear_on_submit=True):
        name = st.text_input("Name")
        email = st.text_input("Email")
        ttl_mins = st.number_input("Invite link expiry (minutes)", value=60, min_value=5, step=5)
        if st.form_submit_button("Send Invite"):
            raw = secrets.token_urlsafe(24)
            signed = make_token(raw, ttl_seconds=int(ttl_mins*60))
            exp = (datetime.utcnow() + timedelta(minutes=int(ttl_mins))).isoformat()
            create_invite(email=email, name=name or "", token=signed, expires_at=exp, invited_by=uid)
            link = f"{app_cfg.app_url}/?invite={signed}"
            result = send_email(email, "You're invited to Swing Tracker", f"<p>Hi {name or ''},</p><p>Accept your invite: <a href='{link}'>Open</a>. The link expires in {ttl_mins} minutes.</p>")
            if result.get("mock"):
                st.info("SMTP not configured; share this link manually:")
                st.code(link, language="text")
            st.success("Invite sent (or shown above).")

    st.markdown("---")
    st.write("**Users**")
    udf = pd.DataFrame(list_users())
    if not udf.empty:
        st.dataframe(udf[["id","name","email","status","last_login_at","created_at"]], use_container_width=True)
        uid_edit = st.number_input("User ID", min_value=0, step=1)
        colx, coly, colz = st.columns(3)
        if colx.button("Suspend"):
            set_user_status(int(uid_edit), "suspended"); st.success("Suspended.")
        if coly.button("Activate"):
            set_user_status(int(uid_edit), "active"); st.success("Activated.")
        if colz.button("Logout everywhere"):
            revoke_all_sessions(int(uid_edit)); st.success("All sessions revoked.")
    else:
        st.caption("No users yet.")
