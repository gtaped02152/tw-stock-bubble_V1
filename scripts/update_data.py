import json
import os
import time
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
import yfinance as yf

TW_TZ = timezone(timedelta(hours=8))

# 上市 (tse) 與上櫃 (otc) 核心追蹤族群與代表股
SECTORS_CONFIG = [
    {
        "id": "semi", "name": "半導體", "market": "上市櫃",
        "stocks": [
            ("tse", "2330", "台積電"), ("tse", "2454", "聯發科"),
            ("tse", "2303", "聯電"), ("tse", "3711", "日月光投控"), ("otc", "5347", "世界")
        ]
    },
    {
        "id": "mem", "name": "記憶體", "market": "上市櫃",
        "stocks": [
            ("tse", "2408", "南亞科"), ("tse", "2344", "華邦電"),
            ("otc", "3260", "威剛"), ("otc", "8299", "群聯")
        ]
    },
    {
        "id": "ai", "name": "AI伺服器", "market": "上市",
        "stocks": [
            ("tse", "2317", "鴻海"), ("tse", "2382", "廣達"),
            ("tse", "3231", "緯創"), ("tse", "6669", "緯穎"), ("tse", "2308", "台達電")
        ]
    },
    {
        "id": "cool", "name": "散熱機殼", "market": "上市櫃",
        "stocks": [
            ("tse", "3017", "奇鋐"), ("otc", "3324", "雙鴻"),
            ("tse", "3653", "健策"), ("tse", "8210", "勤誠")
        ]
    },
    {
        "id": "cpo", "name": "網通CPO", "market": "上市櫃",
        "stocks": [
            ("tse", "3450", "聯鈞"), ("otc", "4979", "華星光"),
            ("otc", "3163", "波若威"), ("tse", "6442", "光聖")
        ]
    },
    {
        "id": "pcb", "name": "PCB載板", "market": "上市",
        "stocks": [
            ("tse", "3037", "欣興"), ("tse", "2383", "台光電"),
            ("tse", "8046", "南電"), ("tse", "3189", "景碩")
        ]
    },
    {
        "id": "ind", "name": "重電機器人", "market": "上市",
        "stocks": [
            ("tse", "1519", "華城"), ("tse", "1513", "中興電"),
            ("tse", "2049", "上銀"), ("tse", "2359", "所羅門")
        ]
    },
    {
        "id": "fin", "name": "金融保險", "market": "上市",
        "stocks": [
            ("tse", "2881", "富邦金"), ("tse", "2882", "國泰金"),
            ("tse", "2891", "中信金"), ("tse", "2886", "兆豐金")
        ]
    },
    {
        "id": "trad", "name": "航運傳產", "market": "上市",
        "stocks": [
            ("tse", "2603", "長榮"), ("tse", "2609", "陽明"),
            ("tse", "1301", "台塑"), ("tse", "2002", "中鋼")
        ]
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_taiex_30d():
    """優先抓 TWSE FMTQIK 官方日收盤，若遇雲端 IP 限流則自動切換 yfinance ^TWII"""
    now = datetime.now(TW_TZ)
    records = []
    try:
        for offset in [2, 1, 0]:
            y, m = now.year, now.month - offset
            if m <= 0:
                m += 12
                y -= 1
            url = f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?response=json&date={y}{m:02d}01"
            r = requests.get(url, headers=HEADERS, timeout=10)
            js = r.json()
            if js.get("stat") == "OK":
                for row in js.get("data", []):
                    parts = row[0].strip().split("/")
                    iso_date = f"{int(parts[0]) + 1911}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                    turnover_b = round(float(row[2].replace(",", "")) / 1e8, 1)
                    close_val = float(row[4].replace(",", ""))
                    diff_val = float(row[5].replace(",", ""))
                    records.append({
                        "date": iso_date,
                        "close": round(close_val, 2),
                        "diff": round(diff_val, 2),
                        "turnoverBillion": turnover_b
                    })
            time.sleep(1.5)
    except Exception as e:
        print(f"TWSE FMTQIK fallback triggered: {e}")

    if len(records) >= 30:
        records.sort(key=lambda x: x["date"])
        return records[-30:], "TWSE 官方 FMTQIK"

    # 備援：Yahoo Finance ^TWII（同樣是真實交易所收盤點位）
    df = yf.download("^TWII", period="3mo", auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Close"])
    records = []
    closes = df["Close"].tolist()
    dates = [idx.strftime("%Y-%m-%d") for idx in df.index]
    for i in range(len(closes)):
        c = round(float(closes[i]), 2)
        prev = round(float(closes[i - 1]), 2) if i > 0 else c
        records.append({
            "date": dates[i],
            "close": c,
            "diff": round(c - prev, 2),
            "turnoverBillion": None
        })
    return records[-30:], "Yahoo Finance (^TWII 實盤收盤)"


def fetch_twse_t86(date_iso):
    """抓取 TWSE 上市三大法人買賣超日報（動態對應欄位名稱，單位：張）"""
    ymd = date_iso.replace("-", "")
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={ymd}&selectType=ALLBUT0999"
    result = {}
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        js = r.json()
        if js.get("stat") != "OK":
            return result
        fields = js.get("fields", [])
        code_idx = next((i for i, f in enumerate(fields) if "證券代號" in f), 0)
        net_idx = next((i for i, f in enumerate(fields) if "三大法人買賣超股數" in f), -1)
        if net_idx == -1:
            return result
        for row in js.get("data", []):
            code = str(row[code_idx]).strip()
            shares = int(str(row[net_idx]).replace(",", "").strip() or 0)
            result[code] = round(shares / 1000)  # 轉成張
    except Exception as e:
        print(f"TWSE T86 fetch skipped: {e}")
    return result


def fetch_stock_histories():
    """批量抓所有成分股近 3 個月真實日收盤與成交量（計算真實 5D/20D 成交額）"""
    yf_tickers = []
    ticker_map = {}
    for sec in SECTORS_CONFIG:
        for mkt, code, name in sec["stocks"]:
            suffix = ".TW" if mkt == "tse" else ".TWO"
            yt = f"{code}{suffix}"
            yf_tickers.append(yt)
            ticker_map[code] = yt

    raw = yf.download(yf_tickers, period="3mo", group_by="ticker", auto_adjust=False, progress=False)
    stock_df_map = {}
    for code, yt in ticker_map.items():
        try:
            sub = raw[yt].dropna(subset=["Close", "Volume"]) if isinstance(raw.columns, pd.MultiIndex) else raw.dropna(subset=["Close", "Volume"])
            if len(sub) >= 2:
                stock_df_map[code] = sub.tail(25)
        except Exception as e:
            print(f"Skip {yt}: {e}")
    return stock_df_map


def main():
    history_30d, taiex_source = fetch_taiex_30d()
    if not history_30d:
        raise RuntimeError("無法取得加權指數歷史收盤資料")

    latest_taiex = history_30d[-1]
    latest_date = latest_taiex["date"]
    prev_close = history_30d[-2]["close"] if len(history_30d) >= 2 else latest_taiex["close"]
    taiex_pct = round((latest_taiex["diff"] / prev_close) * 100, 2) if prev_close else 0.0

    t86_map = fetch_twse_t86(latest_date)
    stock_dfs = fetch_stock_histories()

    sectors_out = []
    for sec in SECTORS_CONFIG:
        sec_daily_turnover = {}  # date -> total 億元
        sec_daily_signed = {}    # date -> signed momentum score
        stocks_out = []

        for mkt, code, name in sec["stocks"]:
            df = stock_dfs.get(code)
            if df is None or len(df) < 2:
                continue

            closes = df["Close"].tolist()
            vols = df["Volume"].tolist()
            dates = [idx.strftime("%Y-%m-%d") for idx in df.index]

            for i in range(len(closes)):
                d_str = dates[i]
                amt_b = (float(closes[i]) * float(vols[i])) / 1e8
                sec_daily_turnover[d_str] = sec_daily_turnover.get(d_str, 0.0) + amt_b
                if i > 0:
                    chg_ratio = (float(closes[i]) - float(closes[i - 1])) / float(closes[i - 1])
                    sec_daily_signed[d_str] = sec_daily_signed.get(d_str, 0.0) + (amt_b * chg_ratio * 100)

            last_close = round(float(closes[-1]), 2)
            prev_c = float(closes[-2])
            chg_pct = round(((last_close - prev_c) / prev_c) * 100, 2) if prev_c else 0.0
            last_amt_b = round((last_close * float(vols[-1])) / 1e8, 2)

            stocks_out.append({
                "ex": mkt,
                "code": code,
                "name": name,
                "close": last_close,
                "prevClose": round(prev_c, 2),
                "chgPct": chg_pct,
                "turnoverBillion": last_amt_b,
                "instNetLots": t86_map.get(code, None)  # 真實三大法人淨買賣超(張)，無則 None
            })

        sorted_dates = sorted(sec_daily_turnover.keys())
        turnovers = [sec_daily_turnover[d] for d in sorted_dates]
        if not turnovers:
            continue

        today_amt = round(turnovers[-1], 2)
        prev4_sum = round(sum(turnovers[-5:-1]), 2) if len(turnovers) >= 5 else round(sum(turnovers[:-1]), 2)
        avg5 = sum(turnovers[-5:]) / min(5, len(turnovers))
        avg20 = sum(turnovers[-20:]) / min(20, len(turnovers))
        accel_y = round(avg5 - avg20, 2)

        # 近 8 個交易日真實日線量價動能分數（盤後無盤中5分紀錄時顯示，並清楚標註為日線）
        recent_8d = sorted_dates[-8:]
        daily_heat = []
        for d_str in recent_8d:
            raw_score = sec_daily_signed.get(d_str, 0.0)
            norm = max(-100, min(100, round((raw_score / max(avg20, 1.0)) * 25)))
            daily_heat.append({"label": d_str[5:], "score": norm})

        sectors_out.append({
            "id": sec["id"],
            "name": sec["name"],
            "market": sec["market"],
            "turnoverBillion": today_amt,
            "avg5": round(avg5, 2),
            "avg20": round(avg20, 2),
            "prev4Sum": prev4_sum,
            "y": accel_y,
            "dailyHeat8d": daily_heat,
            "stocks": stocks_out
        })

    # 計算 X 軸：相對全族群平均成交規模偏離 (%)
    avg_all_today = sum(s["turnoverBillion"] for s in sectors_out) / len(sectors_out) if sectors_out else 1.0
    for s in sectors_out:
        s["x"] = round(((s["turnoverBillion"] - avg_all_today) / avg_all_today) * 100, 1)

    output = {
        "generatedAt": datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S CST"),
        "dataDate": latest_date,
        "taiexSource": taiex_source,
        "taiex": {
            "close": latest_taiex["close"],
            "diff": latest_taiex["diff"],
            "pct": taiex_pct
        },
        "history30d": history_30d,
        "sectors": sectors_out
    }

    os.makedirs("data", exist_ok=True)
    with open("data/market_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Updated data/market_data.json for {latest_date} (TAIEX: {latest_taiex['close']})")


if __name__ == "__main__":
    main()
