import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import re

# ==============================
# 全局配置
# ==============================
st.set_page_config(
    page_title="股票分析工具",
    layout="centered"
)

# ==============================
# 构建股票查询映射表（支持首字母/名称/代码）
# ==============================
@st.cache_data(ttl=86400)
def get_stock_search_map():
    """构建A股查询映射表（支持首字母/名称/代码模糊匹配）"""
    try:
        stock_df = ak.stock_info_a_code_name()
        stock_df = stock_df[stock_df['code'].str.len() == 6].dropna()
        
        code2name = dict(zip(stock_df['code'], stock_df['name']))
        search_map = {}
        
        # 简易拼音首字母生成（兼容无pypinyin场景）
        def get_initials(name):
            try:
                import pypinyin
                return ''.join([p[0][0].upper() for p in pypinyin.pinyin(name, style=pypinyin.NORMAL)])
            except:
                return name
        
        for code, name in zip(stock_df['code'], stock_df['name']):
            initials = get_initials(name)
            for key in [initials, name, code]:
                if key not in search_map:
                    search_map[key] = []
                search_map[key].append((code, name))
        return code2name, search_map
    except Exception as e:
        st.warning(f"股票映射表加载失败：{str(e)[:30]}")
        return {}, {}

def search_stock(keyword):
    """根据关键词搜索股票（首字母/名称/代码）"""
    _, search_map = get_stock_search_map()
    results = []
    for key in search_map:
        if keyword.upper() in key.upper() or keyword in key:
            results.extend(search_map[key])
    results = list(set(results))
    results.sort(key=lambda x: x[0])
    return results[:10]

# ==============================
# 获取行情数据
# ==============================
def get_stock_data(stock_code):
    try:
        clean_code = stock_code.strip()
        if clean_code.startswith(("6", "5")):
            full_code = clean_code + ".SS"
        elif clean_code.startswith(("0", "3")):
            full_code = clean_code + ".SZ"
        else:
            st.error("仅支持A股（6/5/0/3开头）！")
            return None, ""
        
        code2name, _ = get_stock_search_map()
        stock_name = code2name.get(clean_code, f"[{clean_code}]")
        
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=240)).strftime("%Y%m%d")
        data = ak.stock_zh_a_hist(
            symbol=clean_code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )
        
        if data.empty:
            st.error(f"未查询到 {full_code} 的行情数据，请检查代码！")
            return None, stock_name
        
        data = data.rename(columns={
            "日期": "Date", "收盘": "Close", "最高": "High", "最低": "Low", "成交量": "Volume"
        })
        data["Date"] = pd.to_datetime(data["Date"])
        data = data.set_index("Date").sort_index()
        return data, stock_name
    except Exception as e:
        st.error(f"数据获取失败：{str(e)[:80]}")
        return None, ""

# ==============================
# 计算核心指标
# ==============================
def calculate_indicators(data, lookback_days):
    results = []
    current_price = round(float(data['Close'].iloc[-1]), 4)
    for days in lookback_days:
        period_data = data.tail(days) if len(data) >= days else data
        high_price = round(float(period_data['High'].max()), 4)
        low_price = round(float(period_data['Low'].min()), 4)
        drop_rate = round((high_price - current_price)/high_price*100, 2)
        rise_rate = round((current_price - low_price)/low_price*100, 2)
        ma_value = round(float(period_data['Close'].rolling(window=days, min_periods=1).mean().iloc[-1]), 4)
        vol_avg = round(period_data['Volume'].mean(), 0)
        results.append({
            "周期(天)": days,
            "当前价格(元)": current_price,
            "压力位(元)": high_price,
            "支撑位(元)": low_price,
            "相对压力回撤(%)": drop_rate,
            "相对支撑涨幅(%)": rise_rate,
            f"{days}日MA(元)": ma_value,
            "日均成交量(手)": vol_avg
        })
    return pd.DataFrame(results)

# ==============================
# UI主界面
# ==============================
st.title("📈 股票高低点+动态MA+成交量分析工具")

# 1. 股票搜索区域
search_keyword = st.text_input("股票代码/名称/首字母（如：shkj、上海科技、600601）", placeholder="请输入查询词")
selected_code = None

if search_keyword:
    search_results = search_stock(search_keyword)
    if search_results:
        options = [f"{code} - {name}" for code, name in search_results]
        selected_option = st.selectbox("匹配结果", options)
        selected_code = selected_option.split(" - ")[0]
    else:
        st.info("未匹配到股票，请换个关键词试试！")

# 2. 周期选择
lookback_days = st.multiselect("分析周期（天）", [10,20,30,60], default=[20])

# 3. 查询按钮
if st.button("查询", type="primary") and selected_code:
    with st.spinner("加载数据中..."):
        data, stock_name = get_stock_data(selected_code)
        if data is not None:
            st.subheader(f"📊 {stock_name}（{selected_code}）分析结果")
            df = calculate_indicators(data, lookback_days)
            st.dataframe(df.style.format({
                "当前价格(元)": "{:.2f}",
                "压力位(元)": "{:.2f}",
                "支撑位(元)": "{:.2f}",
                "相对压力回撤(%)": "{:.2f}",
                "相对支撑涨幅(%)": "{:.2f}",
                "日均成交量(手)": "{:.0f}"
            }).set_properties(**{'text-align':'center'}), use_container_width=True)

# 使用说明
st.markdown("---")
st.markdown("""
### 使用说明
1. **查询方式**：支持输入股票代码（如600601）、名称（如上海科技）、拼音首字母（如shkj）；
2. **核心指标**：
   - 压力位/支撑位：判断股价上涨压力与下跌支撑；
   - 动态MA：对应周期趋势线（选20天则显示MA20）；
   - 日均成交量：数值越高，交易越活跃，趋势越可靠；
3. **数据说明**：仅支持A股，数据为日K线收盘后数据，非实时盘中数据。
""")
