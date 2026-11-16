"""The demo: Northwind Traders, a made-up home goods retailer with a head office in Madrid (three floors), a distribution centre in
Zaragoza and eight stores in Spain and Portugal. 40 printers on two print servers, reviewed on Monday 16 November 2026. Writes the
files the review reads to sample_data/. Deterministic: the same files every time."""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ORG = "Northwind Traders"
REVIEW = datetime(2026, 11, 16, 8, 30)
MODELS = {  # fictional models: kind, colour, approved firmware (internal standard)
    "NX-A3C 4500": ("mfp-a3", True, "4.12.3"),
    "NX-A4M 3200": ("mfp-a4", False, "3.8.1"),
    "NX-A4C 3300": ("mfp-a4", True, "3.8.1"),
    "LP-210 desk laser": ("desk", False, "2.4.0"),
    "LBL-4T label printer": ("label", False, "1.9.2"),
}
DRIVER, DRIVER_OK = "NX Universal PCL6", "7.4.0.0"
STORES = [("Store Madrid Gran Via", "10.21", "MGV"), ("Store Madrid Serrano", "10.22", "MSR"),
          ("Store Barcelona Diagonal", "10.31", "BDG"), ("Store Barcelona Gracia", "10.32", "BGR"), ("Store Valencia", "10.41", "VLC"),
          ("Store Sevilla", "10.51", "SVQ"), ("Store Lisboa Chiado", "10.61", "LIS"), ("Store Porto", "10.62", "OPO")]


def fleet() -> list[dict]:
    rows = []

    def add(pid, site, loc, model, ip, dept, contract, installed, lease_end="", secure="no", sensitive="no", status="active"):
        rows.append(dict(id=pid, site=site, loc=loc, model=model, ip=ip, dept=dept, contract=contract, installed=installed,
                         lease_end=lease_end, secure=secure, sensitive=sensitive, status=status,
                         serial=f"NX{abs(hash_(pid)) % 10**7:07d}"))
    hq = "Madrid HQ"
    add("HQ-F1-MFP1", hq, "Floor 1", "NX-A3C 4500", "10.10.1.21", "Finance", "MPS-2024", "2024-02-12", "2028-01-31", "yes", "yes")
    add("HQ-F1-MFP2", hq, "Floor 1", "NX-A3C 4500", "10.10.1.22", "HR", "MPS-2024", "2024-02-12", "2028-01-31", "no", "yes")
    add("HQ-F1-P01", hq, "Floor 1", "LP-210 desk laser", "10.10.1.31", "Finance", "", "2018-03-05")
    add("HQ-F1-P02", hq, "Floor 1", "LP-210 desk laser", "10.10.1.32", "HR", "", "2021-09-20")
    add("HQ-F2-MFP1", hq, "Floor 2", "NX-A3C 4500", "10.10.2.21", "Marketing", "MPS-2024", "2024-02-12", "2028-01-31")
    add("HQ-F2-MFP2", hq, "Floor 2", "NX-A3C 4500", "10.10.2.22", "Sales", "MPS-2024", "2024-02-12", "2028-01-31")
    for i, dept in enumerate(["Marketing", "Marketing", "Sales", "Sales", "Sales"], 1):
        add(f"HQ-F2-P0{i}", hq, "Floor 2", "LP-210 desk laser", f"10.10.2.3{i}", dept, "", "2017-06-12" if i <= 2 else "2019-04-08")
    add("HQ-F3-MFP1", hq, "Floor 3", "NX-A3C 4500", "10.10.3.21", "Legal", "MPS-2024", "2024-02-12", "2028-01-31", "no", "yes")
    add("HQ-F3-MFP2", hq, "Floor 3", "NX-A4M 3200", "10.10.3.22", "IT", "MPS-2021", "2021-01-25", "2027-01-20")
    add("HQ-F3-P01", hq, "Floor 3", "LP-210 desk laser", "10.10.3.31", "IT", "", "2018-11-02")
    add("HQ-F3-P02", hq, "Floor 3", "LP-210 desk laser", "10.10.3.32", "Executive", "", "2022-05-16", sensitive="yes",
        secure="yes")
    dc = "Zaragoza DC"
    add("DC-OF-MFP1", dc, "Office", "NX-A3C 4500", "10.70.1.21", "Logistics", "MPS-2021", "2021-01-25", "2027-01-31")
    add("DC-OF-MFP2", dc, "Office", "NX-A4M 3200", "10.70.1.22", "Logistics", "MPS-2021", "2021-01-25", "2027-01-31")
    for i in range(1, 5):
        add(f"DC-DOCK-L0{i}", dc, "Dock", "LBL-4T label printer", f"10.70.5.4{i}", "Logistics", "LBL-2023", "2023-03-01")
    for name, net, short in STORES:
        code = "ST-" + short
        add(f"{code}-MFP", name, "Back office", "NX-A4C 3300", f"{net}.2.20", "Retail", "MPS-2024", "2024-05-06", "2028-04-30")
        add(f"{code}-P01", name, "Counter", "LP-210 desk laser", f"{net}.2.30", "Retail", "", "2019-10-01" if net in ("10.51",
            "10.62") else "2022-03-14")
    add("HQ-F2-P06", hq, "Floor 2", "LP-210 desk laser", "10.10.2.36", "Sales", "", "2016-02-01", status="retired")
    return rows


def hash_(s: str) -> int:
    h = 7
    for ch in s:
        h = (h * 131 + ord(ch)) % 10**9
    return h


def _w(path: Path, head: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(head)
        w.writerows(rows)


def write(folder: Path) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(55)
    ps = fleet()
    by = {p["id"]: p for p in ps}
    active = [p for p in ps if p["status"] == "active"]
    _w(folder / "printers.csv", ["Printer", "Site", "Location", "Type", "Model", "Serial", "IP", "Department", "Contract", "Installed",
                                 "LeaseEnd", "SecureRelease", "Sensitive", "Status"],
       [[p["id"], p["site"], p["loc"], MODELS[p["model"]][0], p["model"], p["serial"], p["ip"], p["dept"], p["contract"],
         p["installed"], p["lease_end"], p["secure"], p["sensitive"], p["status"]] for p in ps])

    # ---- print server queues
    q = []
    gracia = by["ST-BGR-MFP"]
    for p in active:
        if MODELS[p["model"]][0] == "label":
            continue
        status, jobs, oldest = "Normal", 0, 0
        if p["id"] == "DC-OF-MFP2":
            status, jobs, oldest = "Normal", 37, 140
        elif p["id"] == "ST-BDG-P01":
            status = "Paused"
        elif p["id"] == "ST-BGR-MFP":
            status, jobs, oldest = "Offline", 6, 95
        elif p["id"] == "HQ-F3-P01":
            status, jobs, oldest = "Error", 2, 12
        elif rnd.random() < 0.3:
            jobs, oldest = rnd.randint(1, 3), rnd.randint(0, 4)
        q.append(["PRT-SRV01", p["id"], p["id"], p["ip"], DRIVER, DRIVER_OK if p["id"] != "HQ-F3-MFP2" else "7.1.2.0", status,
                  jobs, oldest])
    for pid in ["HQ-F1-MFP1", "HQ-F1-MFP2", "HQ-F1-P01", "HQ-F2-MFP1", "HQ-F2-MFP2", "HQ-F3-MFP1"]:
        q.append(["PRT-SRV02", pid, pid + "-OLD", by[pid]["ip"], DRIVER, "7.1.2.0", "Normal", 0, 0])
    q.append(["PRT-SRV01", "HQ-F2-PLOTTER", "HQ-F2-PLOTTER", "10.10.2.60", "Plotter HPGL2", "1.0.0.0", "Normal", 0, 0])
    q.append(["PRT-SRV01", "MKT-COLOUR-TEMP", "MKT-COLOUR-TEMP", "10.10.2.61", DRIVER, DRIVER_OK, "Normal", 0, 0])
    _w(folder / "queues.csv", ["Server", "Name", "ShareName", "PrinterHostAddress", "DriverName", "DriverVersion", "PrinterStatus",
                               "JobCount", "OldestJobMinutes"], q)

    # ---- what the devices report (managed print portal)
    dev = []
    old_fw = {"HQ-F3-MFP2", "DC-OF-MFP1", "DC-OF-MFP2", "ST-SVQ-P01", "ST-OPO-P01", "HQ-F2-P01"}
    for p in active:
        kind, colour, fw = MODELS[p["model"]]
        firmware = fw
        if p["id"] in old_fw:
            parts = fw.split(".")
            firmware = f"{parts[0]}.{max(0, int(parts[1]) - 3)}.0"
        seen = REVIEW - timedelta(minutes=rnd.randint(2, 40))
        state, msg, ipaddr = "Ready", "", p["ip"]
        if p["id"] == "ST-SVQ-P01":
            seen, state, msg = REVIEW - timedelta(days=3, hours=4), "Offline", "No response"
        elif p["id"] == "HQ-F3-P01":
            state, msg = "Error", "Paper jam in tray 2"
        elif p["id"] == "ST-BGR-MFP":
            ipaddr = gracia["ip"].rsplit(".", 1)[0] + ".57"          # the device took a new address from DHCP after a power cut
        protocols = ["HTTPS"]
        if p["installed"] < "2020" or p["id"] in ("DC-OF-MFP1", "DC-OF-MFP2"):
            protocols += ["Telnet", "FTP", "HTTP"]
        snmp = "v3" if kind.startswith("mfp") and p["contract"] == "MPS-2024" else "v2c"
        default_admin = "yes" if p["id"] in ("DC-OF-MFP2", "ST-OPO-MFP") else "no"
        dev.append([p["serial"], ipaddr, p["model"], seen.strftime("%Y-%m-%d %H:%M"), state, msg, firmware, ";".join(protocols), snmp,
                    default_admin])
    dev.append(["CN7Q1188X", "10.10.2.240", "Consumer inkjet", (REVIEW - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"), "Ready", "",
                "1.0", "HTTP", "v1", "yes"])
    _w(folder / "devices.csv", ["Serial", "IP", "Model", "LastSeen", "Status", "Message", "Firmware", "Protocols", "SNMP",
                                "DefaultAdminPassword"], dev)

    # ---- page counters, August to October
    volume = {"mfp-a3": 5200, "mfp-a4": 2600, "desk": 420, "label": 9000}
    special = {"ST-MGV-MFP": 7300, "HQ-F2-MFP1": 3100, "HQ-F2-MFP2": 2900, "HQ-F2-P01": 60, "HQ-F2-P02": 95, "HQ-F2-P03": 120,
               "HQ-F2-P04": 45, "HQ-F2-P05": 80, "HQ-F3-P02": 260}
    cnt = []
    for p in active:
        kind, colour, _ = MODELS[p["model"]]
        base = special.get(p["id"], volume[kind])
        for m in ("2026-08", "2026-09", "2026-10"):
            total = base * rnd.uniform(0.9, 1.1) * (0.8 if m == "2026-08" else 1)
            share = 0.52 if p["id"] == "HQ-F2-MFP1" else (0.18 if colour else 0)
            cnt.append([p["serial"], m, round(total * (1 - share)), round(total * share)])
    _w(folder / "counters.csv", ["Serial", "Month", "Mono", "Colour"], cnt)

    # ---- consumables
    sup = []
    empty = {"HQ-F1-MFP1": "Yellow toner", "ST-VLC-MFP": "Black toner", "DC-DOCK-L02": "Ribbon"}
    soon = {"HQ-F2-MFP2": "Black toner", "ST-MSR-MFP": "Black toner", "ST-LIS-MFP": "Cyan toner", "HQ-F3-MFP2": "Drum",
            "DC-OF-MFP1": "Black toner", "ST-BDG-P01": "Black toner"}
    ordered = {"HQ-F3-MFP1": "Magenta toner", "ST-SVQ-MFP": "Black toner"}
    for p in active:
        kind, colour, _ = MODELS[p["model"]]
        items = ["Ribbon", "Labels"] if kind == "label" else (["Black toner", "Cyan toner", "Magenta toner", "Yellow toner"]
                                                             if colour else ["Black toner"]) + (["Drum"] if kind.startswith("mfp") else [])
        for it in items:
            if empty.get(p["id"]) == it:
                lvl, before, on = rnd.choice([2, 3, 4]), 38, "no"
            elif soon.get(p["id"]) == it:
                lvl, before, on = rnd.randint(9, 14), rnd.randint(52, 70), "no"
            elif ordered.get(p["id"]) == it:
                lvl, before, on = 4, 41, "yes"
            else:
                lvl = rnd.randint(30, 95)
                before, on = min(100, lvl + rnd.randint(5, 25)), "no"
            sup.append([p["serial"], it, lvl, before, on])
    _w(folder / "supplies.csv", ["Serial", "Supply", "Level", "Level30DaysAgo", "OnOrder"], sup)

    # ---- contracts (fictional vendors)
    _w(folder / "contracts.csv", ["Contract", "Vendor", "Type", "ClickMono", "ClickColour", "MonthlyFee", "ResponseHours", "End",
                                  "NoticeDays", "CreditPerBreach"],
       [["MPS-2024", "Litware Print Services", "Managed print", "0.008", "0.055", "38", "8", "2028-04-30", "90", "150"],
        ["MPS-2021", "Litware Print Services", "Managed print", "0.009", "0.060", "42", "8", "2027-01-31", "60", "150"],
        ["LBL-2023", "Tailspin Label Systems", "Lease and support", "0", "0", "25", "24", "2028-02-28", "60", "0"]])

    # ---- tickets, the last six weeks
    tk, n = [], 4100
    cats = ["Paper jam", "Toner", "Print quality", "Scan to email", "Offline", "Driver"]

    def ticket(pid, opened, cat, called=None, arrived=None, resolved=None):
        nonlocal n
        n += 1
        f = "%Y-%m-%d %H:%M"
        tk.append([f"INC{n}", pid, opened.strftime(f), cat, called.strftime(f) if called else "", arrived.strftime(f) if arrived else "",
                   resolved.strftime(f) if resolved else ""])
    for d in (24, 17, 9, 3):
        o = REVIEW - timedelta(days=d, hours=-1)
        ticket("ST-BGR-MFP", o, "Offline", resolved=o + timedelta(hours=2))
    for d in (25, 19, 6):
        o = REVIEW - timedelta(days=d)
        ticket("HQ-F3-P01", o, "Paper jam", resolved=o + timedelta(hours=1))
    late = {("DC-OF-MFP1", 20): 14, ("HQ-F1-MFP2", 15): 11, ("ST-MGV-MFP", 11): 26, ("DC-OF-MFP2", 4): 9.5}
    for (pid, d), h in late.items():
        o = REVIEW - timedelta(days=d)
        ticket(pid, o, "Print quality", o + timedelta(hours=1), o + timedelta(hours=1 + h), o + timedelta(hours=3 + h))
    for _ in range(22):
        p = rnd.choice(active)
        o = REVIEW - timedelta(days=rnd.randint(1, 42), hours=rnd.randint(0, 8))
        c = rnd.choice(cats)
        if MODELS[p["model"]][0].startswith("mfp") and c == "Print quality" and p["contract"]:
            ticket(p["id"], o, c, o + timedelta(hours=1), o + timedelta(hours=1 + rnd.uniform(2, 7)), o + timedelta(hours=10))
        else:
            ticket(p["id"], o, c, resolved=o + timedelta(hours=rnd.uniform(0.5, 6)))
    _w(folder / "tickets.csv", ["Ticket", "Printer", "Opened", "Category", "VendorCalled", "VendorArrived", "Resolved"], tk)

    (folder / "settings.json").write_text(json.dumps({
        "organisation": ORG, "review_date": REVIEW.strftime("%Y-%m-%d %H:%M"),
        "approved_firmware": {m: v[2] for m, v in MODELS.items()}, "approved_drivers": {DRIVER: DRIVER_OK},
        "recommended_volume": {"mfp-a3": 12000, "mfp-a4": 5000, "desk": 1500, "label": 20000},
        "low_volume": {"mfp-a3": 1500, "mfp-a4": 600, "desk": 150},
        "supply_days": 10, "order_lead_days": 3, "stuck_minutes": 30, "offline_hours": 24, "max_age_years": 7,
        "lease_warning_days": 120, "colour_share_max": 35, "repeat_tickets": 3, "repeat_window_days": 30,
        "owners": {"SUPPORT": "Service desk", "PRINT": "Print services team", "SECURITY": "IT security", "VENDOR": "Vendor manager",
                   "DECISION": "IT site leads"}}, indent=2) + "\n", encoding="utf-8")
