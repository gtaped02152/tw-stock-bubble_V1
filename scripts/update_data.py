import json
import math
import os
import time
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
import yfinance as yf

TW_TZ = timezone(timedelta(hours=8))

# 14 大細分族群、80 檔上市(tse) / 上櫃(otc) 核心代表股
SECTORS_CONFIG = [
    {
        "id": "foundry", "name": "晶圓代工", "market": "上市櫃",
        "stocks": [
            ("tse", "2330", "台積電"), ("tse", "2303", "聯電"),
            ("tse", "6770", "力積電"), ("otc", "5347", "世界"), ("otc", "3707", "漢磊")
        ]
    },
    {
        "id": "equip", "name": "設備CoWoS", "market": "上市櫃",
        "stocks": [
            ("tse", "3583", "辛耘"), ("otc", "3131", "弘塑"),
            ("otc", "6187", "萬潤"), ("otc", "3680", "家登"),
            ("tse", "2467", "志聖"), ("otc", "5443", "均豪")
        ]
    },
    {
        "id": "fab", "name": "廠務無塵室", "market": "上市櫃",
        "stocks": [
            ("tse", "2404", "漢唐"), ("tse", "6139", "亞翔"),
            ("tse", "6691", "洋基工程"), ("tse", "6196", "帆宣"),
            ("otc", "5536", "聖暉*"), ("otc", "6667", "信紘科")
        ]
    },
    {
        "id": "osat", "name": "封測介面", "market": "上市櫃",
        "stocks": [
            ("tse", "3711", "日月光投控"), ("tse", "2449", "京元電子"),
            ("tse", "6239", "力成"), ("tse", "6515", "穎崴"), ("otc", "6223", "旺矽")
        ]
    },
    {
        "id": "ic_design", "name": "IC設計IP", "market": "上市櫃",
        "stocks": [
            ("tse", "2454", "聯發科"), ("tse", "3661", "世芯-KY"),
            ("tse", "3443", "創意"), ("tse", "3034", "聯詠"),
            ("tse", "2379", "瑞昱"), ("otc", "5274", "信驊")
        ]
    },
    {
        "id": "mem", "name": "記憶體", "market": "上市櫃",
        "stocks": [
            ("tse", "2408", "南亞科"), ("tse", "2344", "華邦電"),
            ("tse", "2337", "旺宏"), ("otc", "3260", "威剛"),
            ("otc", "8299", "群聯"), ("tse", "4967", "十銓")
        ]
    },
    {
        "id": "ai", "name": "AI伺服器", "market": "上市",
        "stocks": [
            ("tse", "2317", "鴻海"), ("tse", "2382", "廣達"),
            ("tse", "3231", "緯創"), ("tse", "6669", "緯穎"),
            ("tse", "2356", "英業達"), ("tse", "2308", "台達電")
        ]
    },
    {
        "id": "cool", "name": "散熱機殼", "market": "上市櫃",
        "stocks": [
            ("tse", "3017", "奇鋐"), ("otc", "3324", "雙鴻"),
            ("tse", "3653", "健策"), ("tse", "2059", "川湖"),
            ("tse", "8210", "勤誠"), ("tse", "2421", "建準")
        ]
    },
    {
        "id": "cpo", "name": "矽光子CPO", "market": "上市櫃",
        "stocks": [
            ("tse", "3450", "聯鈞"), ("otc", "4979", "華星光"),
            ("tse", "6442", "光聖"), ("otc", "3163", "波若威"),
            ("otc", "3363", "上詮"), ("tse", "2345", "智邦")
        ]
    },
    {
        "id": "pcb", "name": "PCB載板", "market": "上市櫃",
        "stocks": [
            ("tse", "2383", "台光電"), ("tse", "2368", "金像電"),
            ("tse", "3037", "欣興"), ("tse", "8046", "南電"),
            ("tse", "3189", "景碩"), ("otc", "6274", "台燿")
        ]
    },
    {
        "id": "power", "name": "重電電網", "market": "上市",
        "stocks": [
            ("tse", "1519", "華城"), ("tse", "1513", "中興電"),
            ("tse", "1503", "士電"), ("tse", "1514", "亞力"), ("tse", "1609", "大亞")
        ]
    },
    {
        "id": "robot", "name": "機器人光學", "market": "上市",
        "stocks": [
            ("tse", "2049", "上銀"), ("tse", "2359", "所羅門"),
            ("tse", "3019", "亞光"), ("tse", "4576", "大銀微系統"),
            ("tse", "2464", "盟立"), ("tse", "3008", "大立光")
        ]
    },
    {
        "id": "ship", "name": "航運航空", "market": "上市",
        "stocks": [
            ("tse", "2603", "長榮"), ("tse", "2609", "陽明"),
            ("tse", "2615", "萬海"), ("tse", "2618", "長榮航"), ("tse", "2610", "華航")
        ]
    },
    {
        "id": "fin", "name": "金融傳產", "market": "上市",
        "stocks": [
            ("tse", "2881", "富邦金"), ("tse", "2882", "國泰金"),
            ("tse", "2891", "中信金"), ("tse", "2886", "兆豐金"),
            ("tse", "1301", "台塑"), ("tse", "2002", "中鋼")
        ]
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def build_5m_slot_labels():
    """產生台股當日 09:00 ~ 13:25 共 54 個 5 分鐘時間標籤"""
    labels = []
    cur = 9 * 60
    while cur < 13 * 60 + 30:
        labels.append(f"{cur // 60:02d}:{cur % 60:02d}")
        cur += 5
    return labels


SLOT_LABELS_5M = build_5m_slot_labels()


def fetch_taiex_30d():
    """優先抓 TWSE FMTQIK 官方日收盤，遇雲端限流則自動切換 yfinance ^TWII"""
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
            time.sleep(1.2)
    except Exception as e:
        print(f"TWSE FMTQIK fallback triggered: {e}")

    if len(records) >= 30:
        records.sort(key=lambda x: x["date"])
        return records[-30:], "TWSE 官方 FMTQIK"

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


def fetch_taiex_today_avg(target_date, fallback_close):
    """抓取大盤 ^TWII 當日 09:00~13:30 真實 5 分 K 計算當天均價；若無則退回日線 (H+L+C)/3"""
    try:
        df5 = yf.download("^TWII", period="5d", interval="5m", auto_adjust=False, progress=False)
        if isinstance(df5.columns, pd.MultiIndex):
            df5.columns = df5.columns.get_level_values(0)
        df5 = df5.dropna(subset=["Close"])
        if len(df5) > 0:
            if df5.index.tz is None:
                df5.index = df5.index.tz_localize("UTC").tz_convert(TW_TZ)
            else:
                df5.index = df5.index.tz_convert(TW_TZ)

            day_df = df5[df5.index.strftime("%Y-%m-%d") == target_date]
            if len(day_df) == 0:
                latest_d = df5.index.max().strftime("%Y-%m-%d")
                day_df = df5[df5.index.strftime("%Y-%m-%d") == latest_d]

            vals = [float(v) for v in day_df["Close"].tolist() if math.isfinite(float(v)) and float(v) > 0]
            if vals:
                return round(sum(vals) / len(vals), 2), f"當日5分K均價 ({len(vals)}筆)"
    except Exception as e:
        print(f"TAIEX 5m avg fallback triggered: {e}")

    # 備援：取當日真實日線 (高+低+收)/3
    try:
        dfd = yf.download("^TWII", period="5d", auto_adjust=False, progress=False)
        if isinstance(dfd.columns, pd.MultiIndex):
            dfd.columns = dfd.columns.get_level_values(0)
        dfd = dfd.dropna(subset=["High", "Low", "Close"])
        if len(dfd) > 0:
            last_row = dfd.iloc[-1]
            h, l, c = float(last_row["High"]), float(last_row["Low"]), float(last_row["Close"])
            if all(math.isfinite(x) and x > 0 for x in [h, l, c]):
                return round((h + l + c) / 3.0, 2), "當日高低收均 (H+L+C)/3"
    except Exception as e:
        print(f"TAIEX daily HLC fallback skipped: {e}")

    return round(float(fallback_close), 2), "當日收盤基準"


def fetch_twse_t86(date_iso):
    """抓取 TWSE 上市三大法人買賣超（單位：張）"""
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
            result[code] = round(shares / 1000)
    except Exception as e:
        print(f"TWSE T86 skipped: {e}")
    return result


def fetch_tpex_insti(date_iso):
    """抓取 TPEx 上櫃三大法人買賣超（單位：張）"""
    slash_date = date_iso.replace("-", "/")
    url = f"https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date={slash_date}&response=json"
    result = {}
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        js = r.json()
        tables = js.get("tables", [])
        if not tables:
            return result
        t0 = tables[0]
        fields = t0.get("fields", [])
        code_idx = next((i for i, f in enumerate(fields) if "代號" in f), 0)
        net_idx = next((i for i, f in enumerate(fields) if "三大法人買賣超股數" in f), -1)
        if net_idx == -1:
            net_idx = len(fields) - 1
        for row in t0.get("data", []):
            code = str(row[code_idx]).strip()
            raw_val = str(row[net_idx]).replace(",", "").strip()
            if raw_val and raw_val != "--":
                result[code] = round(int(float(raw_val)) / 1000)
    except Exception as e:
        print(f"TPEx insti skipped: {e}")
    return result


def fetch_all_stock_data():
    """一次批量抓取 80 檔個股近 3 個月日線 + 近 5 日 5 分 K"""
    yf_tickers = []
    ticker_map = {}
    for sec in SECTORS_CONFIG:
        for mkt, code, _ in sec["stocks"]:
            yt = f"{code}.TW" if mkt == "tse" else f"{code}.TWO"
            yf_tickers.append(yt)
            ticker_map[code] = yt

    daily_raw = yf.download(yf_tickers, period="3mo", group_by="ticker", auto_adjust=False, progress=False)
    intraday_raw = yf.download(yf_tickers, period="5d", interval="5m", group_by="ticker", auto_adjust=False, progress=False)

    daily_map = {}
    intraday_map = {}
    latest_intraday_date = None

    for code, yt in ticker_map.items():
        try:
            sub = daily_raw[yt].dropna(subset=["Close", "Volume"]) if isinstance(daily_raw.columns, pd.MultiIndex) else daily_raw.dropna(subset=["Close", "Volume"])
            if len(sub) >= 2:
                daily_map[code] = sub.tail(25)
        except Exception as e:
            print(f"Daily skip {yt}: {e}")

        try:
            sub5 = intraday_raw[yt].dropna(subset=["Open", "High", "Low", "Close", "Volume"]) if isinstance(intraday_raw.columns, pd.MultiIndex) else intraday_raw.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
            if len(sub5) > 0:
                idx = sub5.index
                if idx.tz is None:
                    sub5.index = idx.tz_localize("UTC").tz_convert(TW_TZ)
                else:
                    sub5.index = idx.tz_convert(TW_TZ)
                d_max = sub5.index.max().strftime("%Y-%m-%d")
                if latest_intraday_date is None or d_max > latest_intraday_date:
                    latest_intraday_date = d_max
                intraday_map[code] = sub5
        except Exception as e:
            print(f"5m skip {yt}: {e}")

    return daily_map, intraday_map, latest_intraday_date


def compute_sector_intraday_5m(sec_stocks, intraday_map, target_date):
    """計算該族群在 target_date 當天 09:00~13:25 每 5 分鐘真實主力買賣力道 (-100 ~ +100)"""
    if not target_date:
        return [None] * len(SLOT_LABELS_5M)

    slot_signed = {lbl: 0.0 for lbl in SLOT_LABELS_5M}
    slot_amt = {lbl: 0.0 for lbl in SLOT_LABELS_5M}
    has_any_bar = {lbl: False for lbl in SLOT_LABELS_5M}

    for _, code, _ in sec_stocks:
        df5 = intraday_map.get(code)
        if df5 is None or len(df5) == 0:
            continue
        day_df = df5[df5.index.strftime("%Y-%m-%d") == target_date]
        if len(day_df) == 0:
            continue

        prev_c = None
        for ts, row in day_df.iterrows():
            o, h, l, c, v = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), float(row["Volume"])
            if not all(math.isfinite(x) for x in [o, h, l, c, v]) or c <= 0:
                continue

            mins = ts.hour * 60 + ts.minute
            if mins < 540 or mins > 815:
                prev_c = c
                continue
            bucket_min = min(805, (mins // 5) * 5)
            lbl = f"{bucket_min // 60:02d}:{bucket_min % 60:02d}"
            if lbl not in slot_signed:
                prev_c = c
                continue

            amt_b = (c * v) / 1e8
            clv = ((c - l) - (h - c)) / (h - l) if h > l else 0.0
            ref = prev_c if (prev_c and prev_c > 0) else o
            body_dir = max(-1.0, min(1.0, ((c - ref) / ref) / 0.004)) if ref > 0 else 0.0
            pressure = 0.55 * clv + 0.45 * body_dir

            slot_signed[lbl] += amt_b * pressure
            slot_amt[lbl] += amt_b
            has_any_bar[lbl] = True
            prev_c = c

    active_vals = [abs(slot_signed[lbl]) for lbl in SLOT_LABELS_5M if has_any_bar[lbl] and slot_amt[lbl] > 0]
    if not active_vals:
        return [None] * len(SLOT_LABELS_5M)

    sorted_abs = sorted(active_vals)
    scale_ref = max(sorted_abs[int(len(sorted_abs) * 0.85)], 0.05)

    scores = []
    for lbl in SLOT_LABELS_5M:
        if not has_any_bar[lbl]:
            scores.append(None)
        else:
            val = max(-100, min(100, round((slot_signed[lbl] / scale_ref) * 100)))
            scores.append(int(val))
    return scores


def main():
    history_30d, taiex_source = fetch_taiex_30d()
    if not history_30d:
        raise RuntimeError("無法取得加權指數歷史收盤資料")

    latest_taiex = history_30d[-1]
    latest_date = latest_taiex["date"]
    prev_close = history_30d[-2]["close"] if len(history_30d) >= 2 else latest_taiex["close"]
    taiex_pct = round((latest_taiex["diff"] / prev_close) * 100, 2) if prev_close else 0.0

    # 計算大盤當天均價
    today_avg, today_avg_source = fetch_taiex_today_avg(latest_date, latest_taiex["close"])

    inst_map = {}
    inst_map.update(fetch_twse_t86(latest_date))
    inst_map.update(fetch_tpex_insti(latest_date))

    daily_map, intraday_map, intraday_date = fetch_all_stock_data()
    effective_intraday_date = latest_date if intraday_date == latest_date else (intraday_date or latest_date)

    sectors_out = []
    for sec in SECTORS_CONFIG:
        sec_daily_turnover = {}
        stocks_out = []

        for mkt, code, name in sec["stocks"]:
            df = daily_map.get(code)
            if df is None or len(df) < 2:
                continue

            closes = df["Close"].tolist()
            vols = df["Volume"].tolist()
            dates = [idx.strftime("%Y-%m-%d") for idx in df.index]

            for i in range(len(closes)):
                c_val, v_val = float(closes[i]), float(vols[i])
                if not (math.isfinite(c_val) and math.isfinite(v_val)):
                    continue
                d_str = dates[i]
                sec_daily_turnover[d_str] = sec_daily_turnover.get(d_str, 0.0) + (c_val * v_val) / 1e8

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
                "instNetLots": inst_map.get(code, None)
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

        intraday_scores = compute_sector_intraday_5m(sec["stocks"], intraday_map, effective_intraday_date)

        sectors_out.append({
            "id": sec["id"],
            "name": sec["name"],
            "market": sec["market"],
            "turnoverBillion": today_amt,
            "avg5": round(avg5, 2),
            "avg20": round(avg20, 2),
            "prev4Sum": prev4_sum,
            "y": accel_y,
            "intraday5m": intraday_scores,
            "stocks": stocks_out
        })

    avg_all_today = sum(s["turnoverBillion"] for s in sectors_out) / len(sectors_out) if sectors_out else 1.0
    for s in sectors_out:
        s["x"] = round(((s["turnoverBillion"] - avg_all_today) / avg_all_today) * 100, 1)

    output = {
        "generatedAt": datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S CST"),
        "dataDate": latest_date,
        "intradayDate": effective_intraday_date,
        "intradaySlots": SLOT_LABELS_5M,
        "taiexSource": taiex_source,
        "taiex": {
            "close": latest_taiex["close"],
            "diff": latest_taiex["diff"],
            "pct": taiex_pct,
            "todayAvg": today_avg,
            "todayAvgSource": today_avg_source
        },
        "history30d": history_30d,
        "sectors": sectors_out
    }

    os.makedirs("data", exist_ok=True)
    with open("data/market_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"Updated data/market_data.json for {latest_date} (todayAvg: {today_avg})")


if __name__ == "__main__":
    main()
