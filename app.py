
import sqlite3
from pathlib import Path
from datetime import date
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).with_name("wealth_v2.db")

st.set_page_config(page_title="Wealth AI Manager V2", layout="wide")

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_name TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        quantity REAL NOT NULL DEFAULT 0,
        cost_per_unit REAL NOT NULL DEFAULT 0,
        current_price REAL NOT NULL DEFAULT 0,
        annual_income REAL NOT NULL DEFAULT 0,
        note TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cashflows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flow_date TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        source TEXT,
        note TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        goal_name TEXT NOT NULL,
        target_amount REAL NOT NULL DEFAULT 0,
        current_amount REAL NOT NULL DEFAULT 0,
        monthly_contribution REAL NOT NULL DEFAULT 0,
        expected_return REAL NOT NULL DEFAULT 0,
        years INTEGER NOT NULL DEFAULT 1,
        note TEXT
    )
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM assets")
    if cur.fetchone()[0] == 0:
        seed_assets = [
            ("SCB", "หุ้น", 200, 130, 121, 2088, "หุ้นปันผล"),
            ("KTB", "หุ้น", 1700, 25.8, 18.5, 2057, "ธนาคาร"),
            ("BGRIM", "หุ้น", 2800, 11.71, 10.8, 0, "เก็งฟื้นตัว"),
            ("Gold Fund", "ทอง", 1, 137000, 161000, 0, "กองทุนทอง"),
            ("Rental Land", "อสังหา/ค่าเช่า", 1, 0, 0, 600000, "ค่าเช่าต่อปี"),
            ("Deposit", "เงินสด", 1, 468000, 468000, 7488, "ดอกเบี้ย 1.6%"),
        ]
        cur.executemany("""
            INSERT INTO assets (asset_name, asset_type, quantity, cost_per_unit, current_price, annual_income, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, seed_assets)

    cur.execute("SELECT COUNT(*) FROM cashflows")
    if cur.fetchone()[0] == 0:
        seed_flows = [
            ("2026-01-05", "ค่าเช่าเข้า", 50000, "Rental Land", "รายได้ค่าเช่า"),
            ("2026-02-10", "เงินปันผล", 4200, "SCB", "ตัวอย่าง"),
            ("2026-03-15", "ลงทุนเพิ่ม", -30000, "BGRIM", "ซื้อเพิ่ม"),
            ("2026-03-30", "ดอกเบี้ย", 624, "Deposit", "ประมาณการรายเดือน"),
        ]
        cur.executemany("""
            INSERT INTO cashflows (flow_date, category, amount, source, note)
            VALUES (?, ?, ?, ?, ?)
        """, seed_flows)

    cur.execute("SELECT COUNT(*) FROM goals")
    if cur.fetchone()[0] == 0:
        seed_goals = [
            ("รายได้ปันผล 40,000/เดือน", 480000, 611632, 15000, 0.07, 10, "ดูรายได้เชิงรับเทียบเป้า"),
            ("เงินสำรองฉุกเฉิน", 300000, 150000, 5000, 0.02, 3, "เอาไว้กันช็อต"),
        ]
        cur.executemany("""
            INSERT INTO goals (goal_name, target_amount, current_amount, monthly_contribution, expected_return, years, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, seed_goals)

    conn.commit()
    conn.close()

def load_table(table):
    conn = get_conn()
    df = pd.read_sql_query(f"SELECT * FROM {table} ORDER BY id DESC", conn)
    conn.close()
    return df

def load_assets():
    df = load_table("assets")
    if not df.empty:
        df["cost_value"] = df["quantity"] * df["cost_per_unit"]
        df["market_value"] = df["quantity"] * df["current_price"]
        df["unrealized_pl"] = df["market_value"] - df["cost_value"]
        df["yield_pct_on_cost"] = df.apply(
            lambda r: (r["annual_income"] / r["cost_value"] * 100) if r["cost_value"] else 0, axis=1
        )
    return df

def load_cashflows():
    df = load_table("cashflows")
    if not df.empty:
        df["flow_date"] = pd.to_datetime(df["flow_date"])
    return df

def load_goals():
    return load_table("goals")

def insert_row(sql, params):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    conn.close()

def add_asset(asset_name, asset_type, quantity, cost_per_unit, current_price, annual_income, note):
    insert_row("""
        INSERT INTO assets (asset_name, asset_type, quantity, cost_per_unit, current_price, annual_income, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (asset_name, asset_type, quantity, cost_per_unit, current_price, annual_income, note))

def add_cashflow(flow_date, category, amount, source, note):
    insert_row("""
        INSERT INTO cashflows (flow_date, category, amount, source, note)
        VALUES (?, ?, ?, ?, ?)
    """, (flow_date, category, amount, source, note))

def add_goal(goal_name, target_amount, current_amount, monthly_contribution, expected_return, years, note):
    insert_row("""
        INSERT INTO goals (goal_name, target_amount, current_amount, monthly_contribution, expected_return, years, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (goal_name, target_amount, current_amount, monthly_contribution, expected_return, years, note))

def future_value(current_amount, monthly_contribution, expected_return, years):
    r = expected_return / 12
    n = years * 12
    if r == 0:
        return current_amount + monthly_contribution * n
    return current_amount * ((1+r) ** n) + monthly_contribution * (((1+r) ** n - 1) / r)

def suggest_allocation(lump_sum, style, cash_buffer_need=True):
    if lump_sum <= 0:
        return pd.DataFrame(columns=["bucket", "amount", "reason"])

    if style == "อนุรักษ์":
        weights = {
            "เงินสด/กองทุนตลาดเงิน": 0.35,
            "หุ้นปันผล/กองทุนปันผล": 0.30,
            "กองทุนดัชนี/เติบโต": 0.20,
            "ทอง": 0.15,
        }
    elif style == "สมดุล":
        weights = {
            "เงินสด/กองทุนตลาดเงิน": 0.20,
            "หุ้นปันผล/กองทุนปันผล": 0.35,
            "กองทุนดัชนี/เติบโต": 0.30,
            "ทอง": 0.15,
        }
    else:
        weights = {
            "เงินสด/กองทุนตลาดเงิน": 0.10,
            "หุ้นปันผล/กองทุนปันผล": 0.35,
            "กองทุนดัชนี/เติบโต": 0.40,
            "ทอง": 0.15,
        }

    rows = []
    reasons = {
        "เงินสด/กองทุนตลาดเงิน": "กันชนสภาพคล่อง เผื่อโอกาสและเหตุฉุกเฉิน",
        "หุ้นปันผล/กองทุนปันผล": "เน้นกระแสเงินสดระหว่างทาง",
        "กองทุนดัชนี/เติบโต": "เผื่อการโตของพอร์ตระยะยาว",
        "ทอง": "กันความผันผวนและความเสี่ยงมหภาค",
    }
    for k, w in weights.items():
        amt = lump_sum * w
        rows.append({"bucket": k, "amount": amt, "reason": reasons[k]})

    df = pd.DataFrame(rows)
    if cash_buffer_need:
        df.loc[df["bucket"] == "เงินสด/กองทุนตลาดเงิน", "amount"] += lump_sum * 0.05
        df.loc[df["bucket"] == "กองทุนดัชนี/เติบโต", "amount"] -= lump_sum * 0.05
    return df

def ai_summary(df_assets, df_flows):
    if df_assets.empty:
        return "ยังไม่มีข้อมูลพอร์ต"

    total_cost = float(df_assets["cost_value"].sum())
    total_value = float(df_assets["market_value"].sum())
    total_income = float(df_assets["annual_income"].sum())
    total_pl = total_value - total_cost
    income_month = total_income / 12 if total_income else 0

    type_alloc = df_assets.groupby("asset_type")["market_value"].sum().sort_values(ascending=False)
    top_type = type_alloc.index[0] if len(type_alloc) else "-"
    top_pct = (type_alloc.iloc[0] / total_value * 100) if total_value and len(type_alloc) else 0

    losers = df_assets[df_assets["unrealized_pl"] < 0].sort_values("unrealized_pl")
    winner = df_assets.sort_values("market_value", ascending=False).iloc[0]

    flow_text = "ยังไม่มีกระแสเงินสด"
    if not df_flows.empty:
        df_flows2 = df_flows.copy()
        df_flows2["month"] = df_flows2["flow_date"].dt.strftime("%Y-%m")
        this_month = pd.Timestamp.today().strftime("%Y-%m")
        month_net = float(df_flows2.loc[df_flows2["month"] == this_month, "amount"].sum())
        flow_text = f"กระแสเงินสดสุทธิเดือนนี้ {month_net:,.0f} บาท"

    lines = []
    lines.append("AI Wealth Summary")
    lines.append(f"- มูลค่าพอร์ตปัจจุบัน: {total_value:,.0f} บาท")
    lines.append(f"- ต้นทุนรวม: {total_cost:,.0f} บาท")
    lines.append(f"- กำไร/ขาดทุนคงค้าง: {total_pl:,.0f} บาท")
    lines.append(f"- รายได้เชิงรับต่อปี: {total_income:,.0f} บาท หรือเฉลี่ยเดือนละ {income_month:,.0f} บาท")
    lines.append(f"- หมวดใหญ่สุดในพอร์ต: {top_type} ({top_pct:,.1f}%)")
    lines.append(f"- สินทรัพย์ตัวใหญ่สุด: {winner['asset_name']} มูลค่า {winner['market_value']:,.0f} บาท")
    lines.append(f"- {flow_text}")

    if top_pct > 50:
        lines.append("- เตือน: พอร์ตกระจุกตัวค่อนข้างสูง ควรระวังถ้าหมวดนี้โดนพร้อมกัน")
    if not losers.empty:
        worst = losers.iloc[0]
        lines.append(f"- จุดถ่วงพอร์ตตอนนี้: {worst['asset_name']} ติดลบ {worst['unrealized_pl']:,.0f} บาท")
    if income_month < 40000:
        lines.append(f"- ยังขาดรายได้เชิงรับจากเป้า 40,000/เดือน ประมาณ {40000-income_month:,.0f} บาท")
    else:
        lines.append("- รายได้เชิงรับถึงเป้า 40,000/เดือนแล้ว")

    lines.append("- มุมมองใช้งานจริง: ใช้ตัวนี้เป็นสมองสรุปภาพรวมก่อน แล้วค่อยเชื่อมราคาจริง/แจ้งเตือนภายหลัง")
    return "\n".join(lines)

init_db()

st.title("Wealth AI Manager V2")
st.caption("เวอร์ชันต่อยอด: พอร์ต + Cashflow + Goal Planning + Allocation Assistant")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Dashboard", "Assets", "Cashflow", "Goals", "AI Assistant"
])

with tab1:
    df_assets = load_assets()
    df_flows = load_cashflows()

    if df_assets.empty:
        st.info("ยังไม่มีข้อมูลสินทรัพย์")
    else:
        total_cost = df_assets["cost_value"].sum()
        total_value = df_assets["market_value"].sum()
        total_income = df_assets["annual_income"].sum()
        total_pl = df_assets["unrealized_pl"].sum()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("มูลค่าปัจจุบัน", f"{total_value:,.0f} บาท")
        c2.metric("ต้นทุนรวม", f"{total_cost:,.0f} บาท")
        c3.metric("กำไร/ขาดทุนคงค้าง", f"{total_pl:,.0f} บาท")
        c4.metric("รายได้เชิงรับ/ปี", f"{total_income:,.0f} บาท")

        st.subheader("สัดส่วนตามประเภทสินทรัพย์")
        alloc = df_assets.groupby("asset_type", as_index=False)["market_value"].sum()
        st.bar_chart(alloc.set_index("asset_type"))

        st.subheader("สินทรัพย์มูลค่าสูงสุด")
        top_assets = df_assets.sort_values("market_value", ascending=False)[["asset_name", "asset_type", "market_value", "unrealized_pl"]].head(10)
        st.dataframe(top_assets, use_container_width=True)

        if not df_flows.empty:
            st.subheader("กระแสเงินสดล่าสุด")
            st.dataframe(df_flows.head(10), use_container_width=True)

with tab2:
    st.subheader("เพิ่มสินทรัพย์")
    with st.form("asset_form"):
        c1, c2 = st.columns(2)
        asset_name = c1.text_input("ชื่อสินทรัพย์")
        asset_type = c2.selectbox("ประเภท", ["หุ้น", "กองทุน", "ทอง", "เงินสด", "อสังหา/ค่าเช่า", "คริปโต", "อื่นๆ"])
        c3, c4, c5 = st.columns(3)
        quantity = c3.number_input("จำนวน", min_value=0.0, value=1.0, step=1.0)
        cost_per_unit = c4.number_input("ต้นทุนต่อหน่วย", min_value=0.0, value=0.0, step=100.0)
        current_price = c5.number_input("ราคาปัจจุบันต่อหน่วย", min_value=0.0, value=0.0, step=100.0)
        c6, c7 = st.columns([1,2])
        annual_income = c6.number_input("รายได้ต่อปี", min_value=0.0, value=0.0, step=100.0)
        note = c7.text_input("หมายเหตุ")
        submitted = st.form_submit_button("บันทึกสินทรัพย์")
        if submitted and asset_name.strip():
            add_asset(asset_name.strip(), asset_type, quantity, cost_per_unit, current_price, annual_income, note.strip())
            st.success("บันทึกเรียบร้อยแล้ว")

    st.subheader("ตารางสินทรัพย์")
    df_assets = load_assets()
    if not df_assets.empty:
        st.dataframe(df_assets[[
            "asset_name", "asset_type", "quantity", "cost_per_unit",
            "current_price", "cost_value", "market_value", "unrealized_pl",
            "annual_income", "yield_pct_on_cost", "note"
        ]], use_container_width=True)

with tab3:
    st.subheader("บันทึกกระแสเงินสด")
    with st.form("flow_form"):
        c1, c2, c3 = st.columns(3)
        flow_date = c1.date_input("วันที่", value=date.today())
        category = c2.selectbox("หมวด", ["ค่าเช่าเข้า", "เงินปันผล", "ดอกเบี้ย", "ลงทุนเพิ่ม", "ถอนเงิน", "รายได้ธุรกิจ", "ค่าใช้จ่าย"])
        amount = c3.number_input("จำนวนเงิน (+ รายรับ / - รายจ่าย)", value=0.0, step=100.0)
        c4, c5 = st.columns(2)
        source = c4.text_input("ที่มา")
        note = c5.text_input("หมายเหตุ")
        submitted_flow = st.form_submit_button("บันทึก")
        if submitted_flow:
            add_cashflow(str(flow_date), category, amount, source.strip(), note.strip())
            st.success("บันทึกแล้ว")

    df_flows = load_cashflows()
    if not df_flows.empty:
        st.subheader("รายการกระแสเงินสด")
        st.dataframe(df_flows, use_container_width=True)

        monthly = df_flows.copy()
        monthly["month"] = monthly["flow_date"].dt.strftime("%Y-%m")
        monthly_sum = monthly.groupby("month", as_index=False)["amount"].sum().sort_values("month")
        st.subheader("สรุปสุทธิต่อเดือน")
        st.bar_chart(monthly_sum.set_index("month"))

with tab4:
    st.subheader("Goal Planning")
    with st.form("goal_form"):
        goal_name = st.text_input("ชื่อเป้าหมาย", placeholder="เช่น ปันผล 40,000/เดือน")
        c1, c2, c3 = st.columns(3)
        target_amount = c1.number_input("เป้าหมาย (บาท)", min_value=0.0, value=480000.0, step=10000.0)
        current_amount = c2.number_input("มีแล้วตอนนี้", min_value=0.0, value=0.0, step=10000.0)
        monthly_contribution = c3.number_input("เติมต่อเดือน", min_value=0.0, value=5000.0, step=1000.0)
        c4, c5 = st.columns(2)
        expected_return = c4.number_input("ผลตอบแทนคาดหวัง/ปี (เช่น 0.07)", min_value=0.0, value=0.07, step=0.01, format="%.2f")
        years = c5.number_input("จำนวนปี", min_value=1, value=10, step=1)
        note = st.text_input("หมายเหตุ")
        submitted_goal = st.form_submit_button("บันทึกเป้าหมาย")
        if submitted_goal and goal_name.strip():
            add_goal(goal_name.strip(), target_amount, current_amount, monthly_contribution, expected_return, years, note.strip())
            st.success("บันทึกเป้าหมายแล้ว")

    df_goals = load_goals()
    if not df_goals.empty:
        df_show = df_goals.copy()
        df_show["future_value"] = df_show.apply(
            lambda r: future_value(r["current_amount"], r["monthly_contribution"], r["expected_return"], int(r["years"])),
            axis=1
        )
        df_show["progress_pct"] = df_show.apply(
            lambda r: (r["current_amount"] / r["target_amount"] * 100) if r["target_amount"] else 0, axis=1
        )
        df_show["gap"] = df_show["target_amount"] - df_show["future_value"]

        st.dataframe(df_show[[
            "goal_name", "target_amount", "current_amount",
            "monthly_contribution", "expected_return", "years",
            "future_value", "progress_pct", "gap", "note"
        ]], use_container_width=True)

with tab5:
    st.subheader("AI Assistant")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### สรุปภาพรวมพอร์ต")
        df_assets = load_assets()
        df_flows = load_cashflows()
        summary = ai_summary(df_assets, df_flows)
        st.code(summary, language="text")

    with col_b:
        st.markdown("### ตัวช่วยจัดเงินก้อน")
        lump_sum = st.number_input("มีเงินก้อนเท่าไร", min_value=0.0, value=200000.0, step=10000.0)
        style = st.selectbox("สไตล์พอร์ต", ["อนุรักษ์", "สมดุล", "โตระยะยาว"])
        keep_buffer = st.checkbox("เผื่อเงินสำรองเพิ่มอีก 5%", value=True)
        alloc_df = suggest_allocation(lump_sum, style, keep_buffer)
        if not alloc_df.empty:
            st.dataframe(alloc_df, use_container_width=True)
            st.bar_chart(alloc_df.set_index("bucket")["amount"])

            total_passive = df_assets["annual_income"].sum() if not df_assets.empty else 0
            st.markdown("### ความเห็นเชิงใช้งาน")
            if style == "อนุรักษ์":
                st.write("เหมาะถ้าตอนนี้คุณเน้นอยู่รอดก่อนโต เน้นเงินสดกับรายได้สม่ำเสมอ")
            elif style == "สมดุล":
                st.write("สมดุลดีสำหรับคนที่อยากโตแต่ยังไม่อยากผันผวนจนใจแกว่ง")
            else:
                st.write("พอร์ตนี้โอกาสโตดีกว่า แต่ตอนตลาดเหวี่ยงก็ต้องใจแข็งกว่าปกติ")
            st.write(f"รายได้เชิงรับปัจจุบันของพอร์ตประมาณ {total_passive/12:,.0f} บาท/เดือน")

st.markdown("---")
st.caption("V2 นี้ยังใช้ข้อมูลกรอกเองก่อน แต่โครงสร้างพร้อมต่อยอดไปสู่ AI ที่เชื่อมราคาจริงและระบบแจ้งเตือน")
