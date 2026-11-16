"""Loading: the printer register (printers.csv), the print server queues (queues.csv), what the devices report about themselves
(devices.csv, from the managed print portal or an SNMP scan), the consumables (supplies.csv), the monthly page counters (counters.csv),
the print contracts (contracts.csv), the printer tickets (tickets.csv) and the settings (settings.json). Forgiving column names, into
plain dataclasses. printers.csv is required; every other file adds its checks when it is there."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

PRINTER_ALIASES = {
    "id": ["Printer", "Name", "Asset", "Asset tag", "Device"],
    "site": ["Site", "Office", "Store", "Location site"],
    "location": ["Location", "Floor", "Area", "Room"],
    "kind": ["Type", "Kind", "Class", "Device type"],
    "model": ["Model", "Model name"],
    "serial": ["Serial", "SerialNumber", "Serial number", "S/N"],
    "ip": ["IP", "IPAddress", "IP address", "Address"],
    "department": ["Department", "Owner", "Cost centre", "Cost center", "Team"],
    "contract": ["Contract", "Contract id", "Agreement"],
    "installed": ["Installed", "Install date", "Installed on", "Purchase date"],
    "lease_end": ["LeaseEnd", "Lease end", "Contract end", "End of lease"],
    "secure_release": ["SecureRelease", "Secure release", "Pull printing", "Follow-me"],
    "sensitive": ["Sensitive", "SensitiveArea", "Sensitive area", "Confidential"],
    "status": ["Status", "State", "Lifecycle"],
}
QUEUE_ALIASES = {
    "server": ["Server", "ComputerName", "PSComputerName", "Print server"],
    "queue": ["Queue", "Name", "Printer name"],
    "share": ["ShareName", "Share", "Share name"],
    "port_ip": ["PrinterHostAddress", "PortIP", "Port IP", "Port address", "HostAddress"],
    "driver": ["DriverName", "Driver", "Driver name"],
    "driver_version": ["DriverVersion", "Driver version"],
    "status": ["PrinterStatus", "Status", "State"],
    "jobs": ["JobCount", "Jobs", "Jobs pending"],
    "oldest": ["OldestJobMinutes", "Oldest job (min)", "OldestJob", "Oldest job minutes"],
    "printer": ["Printer", "Asset", "Device"],
}
DEVICE_ALIASES = {
    "serial": ["Serial", "SerialNumber", "Serial number"],
    "ip": ["IP", "IPAddress", "IP address"],
    "model": ["Model"],
    "last_seen": ["LastSeen", "Last seen", "Last contact", "LastContact"],
    "state": ["Status", "State", "Device status"],
    "message": ["Message", "Error", "Alert", "Status message"],
    "firmware": ["Firmware", "FirmwareVersion", "Firmware version"],
    "protocols": ["Protocols", "Services", "Enabled protocols"],
    "snmp": ["SNMP", "SnmpVersion", "SNMP version"],
    "default_admin": ["DefaultAdminPassword", "Default admin password", "DefaultPassword"],
}
SUPPLY_ALIASES = {
    "serial": ["Serial", "SerialNumber"],
    "supply": ["Supply", "Consumable", "Item"],
    "level": ["Level", "Level %", "Percent", "Remaining"],
    "level_before": ["Level30DaysAgo", "Level 30 days ago", "PreviousLevel", "Level before"],
    "on_order": ["OnOrder", "On order", "Ordered"],
}
COUNTER_ALIASES = {
    "serial": ["Serial", "SerialNumber"],
    "month": ["Month", "Period"],
    "mono": ["Mono", "Black", "Mono pages", "BW"],
    "colour": ["Colour", "Color", "Colour pages", "Color pages"],
}
CONTRACT_ALIASES = {
    "id": ["Contract", "Id", "Contract id"],
    "vendor": ["Vendor", "Supplier", "Provider"],
    "kind": ["Type", "Kind"],
    "click_mono": ["ClickMono", "Mono click", "Mono price", "Price per mono page"],
    "click_colour": ["ClickColour", "ClickColor", "Colour click", "Price per colour page"],
    "monthly_fee": ["MonthlyFee", "Monthly fee", "Rental", "Fee per device"],
    "response_hours": ["ResponseHours", "Response hours", "SLA hours", "Response SLA"],
    "end": ["End", "End date", "Expires"],
    "notice_days": ["NoticeDays", "Notice days", "Notice"],
    "credit": ["CreditPerBreach", "Credit per breach", "Service credit"],
}
TICKET_ALIASES = {
    "id": ["Ticket", "Number", "Id", "Incident"],
    "printer": ["Printer", "Asset", "Configuration item", "CI"],
    "opened": ["Opened", "Created", "Opened at"],
    "category": ["Category", "Subcategory", "Type"],
    "vendor_called": ["VendorCalled", "Vendor called", "Logged with vendor"],
    "vendor_arrived": ["VendorArrived", "Vendor arrived", "Engineer on site", "Responded"],
    "resolved": ["Resolved", "Closed", "Resolved at"],
}
YES = {"yes", "y", "true", "1", "x", "si", "enabled", "on"}
FILES = {"printers.csv": "Printer register", "queues.csv": "Print server queues", "devices.csv": "Device status (portal or SNMP)",
         "supplies.csv": "Consumables", "counters.csv": "Page counters", "contracts.csv": "Contracts", "tickets.csv": "Tickets"}
KINDS = {"mfp-a3": "A3 multifunction", "mfp-a4": "A4 multifunction", "desk": "Desktop printer", "label": "Label printer",
         "receipt": "Receipt printer"}
DIRECT = {"label", "receipt"}          # printed to directly by an application, not through a print server queue


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def num(v) -> float | None:
    s = re.sub(r"[€$£%\s]|eur", "", str(v or "").strip().lower())
    if not s:
        return None
    if re.fullmatch(r"-?0[.,]\d+", s):                    # 0,008 or 0.008 is a price per page, not 8 thousand
        s = s.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def yes(v) -> bool:
    return _norm(v) in YES


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            pass
    return None


def parse_d(v) -> date | None:
    x = parse_dt(v)
    return x.date() if x else None


def kind(v, model: str = "") -> str:
    n = _norm(v) + " " + _norm(model)
    if "label" in n or "zpl" in n:
        return "label"
    if "receipt" in n or "ticket printer" in n or "pos" in n.split():
        return "receipt"
    if "a3" in n:
        return "mfp-a3"
    if "mfp" in n or "multifunc" in n or "a4" in n:
        return "mfp-a4"
    return "desk"


def version(v) -> tuple:
    """'4.12.3' -> (4, 12, 3); text around the numbers is ignored."""
    return tuple(int(x) for x in re.findall(r"\d+", str(v or "")))


def ip(v) -> str:
    m = re.search(r"\d{1,3}(?:\.\d{1,3}){3}", str(v or ""))
    return m.group(0) if m else ""


def queue_status(v) -> str:
    n = _norm(v)
    for key, words in (("offline", ("offline", "not available", "unavailable")), ("error", ("error", "jam", "door", "no toner",
                       "paper out", "out of paper")), ("paused", ("paused",))):
        if any(w in n for w in words):
            return key
    return "normal"


def device_state(v) -> str:
    n = _norm(v)
    if any(w in n for w in ("offline", "no response", "unreachable", "not responding")):
        return "offline"
    if any(w in n for w in ("error", "down", "jam", "critical")):
        return "error"
    if any(w in n for w in ("warning", "low")):
        return "warning"
    return "ready"


def _read(path: Path) -> tuple[list[str], list[dict]]:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig") if not raw.startswith(b"\xff\xfe") else raw.decode("utf-16")
    sample = text[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.DictReader(text.splitlines(), delimiter=delim))
    return (list(rows[0].keys()) if rows else []), rows


def _rows(path: Path, aliases: dict) -> list[dict]:
    fields, rows = _read(path)
    lower = {_norm(f): f for f in fields}
    pick = {}
    for key, names in aliases.items():
        for n in names:
            if _norm(n) in lower:
                pick[key] = lower[_norm(n)]
                break
    return [{k: (r.get(f) or "").strip() for k, f in pick.items()} for r in rows]


@dataclass
class Printer:
    id: str
    site: str
    location: str
    kind: str
    model: str
    serial: str
    ip: str
    department: str
    contract: str
    installed: date | None
    lease_end: date | None
    secure_release: bool
    sensitive: bool
    active: bool = True


@dataclass
class Queue:
    server: str
    queue: str
    share: str
    port_ip: str
    driver: str
    driver_version: str
    status: str
    jobs: int
    oldest: float
    printer: str = ""         # register id, matched on load


@dataclass
class Device:
    serial: str
    ip: str
    model: str
    last_seen: datetime | None
    state: str
    message: str
    firmware: str
    protocols: set
    snmp: str
    default_admin: bool


@dataclass
class Supply:
    serial: str
    supply: str
    level: float
    level_before: float | None
    on_order: bool


@dataclass
class Counter:
    serial: str
    month: str
    mono: float
    colour: float


@dataclass
class Contract:
    id: str
    vendor: str
    kind: str
    click_mono: float
    click_colour: float
    monthly_fee: float
    response_hours: float
    end: date | None
    notice_days: int
    credit: float


@dataclass
class Ticket:
    id: str
    printer: str
    opened: datetime | None
    category: str
    vendor_called: datetime | None
    vendor_arrived: datetime | None
    resolved: datetime | None


@dataclass
class Settings:
    organisation: str = "Your organisation"
    review_date: datetime | None = None
    approved_firmware: dict = field(default_factory=dict)       # model -> minimum firmware
    approved_drivers: dict = field(default_factory=dict)        # driver name -> minimum version
    recommended_volume: dict = field(default_factory=lambda: {"mfp-a3": 12000, "mfp-a4": 5000, "desk": 1500, "label": 20000,
                                                              "receipt": 30000})
    low_volume: dict = field(default_factory=lambda: {"mfp-a3": 1500, "mfp-a4": 600, "desk": 150})
    owned_cost_per_page: dict = field(default_factory=lambda: {"desk": 0.03, "mfp-a4": 0.02, "mfp-a3": 0.02})   # toner and parts
    replacement_cost: dict = field(default_factory=lambda: {"desk": 350, "mfp-a4": 1800, "mfp-a3": 6000, "label": 1500})
    supply_days: int = 10               # warn when a consumable runs out within this many days
    order_lead_days: int = 3            # delivery time of a consumable order
    stuck_minutes: int = 30             # a queue whose oldest job is older than this is stuck
    offline_hours: int = 24             # a device not seen for this long is offline
    max_age_years: int = 7
    lease_warning_days: int = 120
    colour_share_max: float = 35.0      # colour pages as a share of all pages, per device
    repeat_tickets: int = 3             # tickets on one printer in the window that make it a repeat
    repeat_window_days: int = 30
    insecure_protocols: list = field(default_factory=lambda: ["telnet", "ftp", "http", "snmpv1", "snmpv2c"])
    owners: dict = field(default_factory=lambda: {"SUPPORT": "Service desk", "PRINT": "Print services team",
                                                  "SECURITY": "IT security", "VENDOR": "Vendor manager",
                                                  "DECISION": "IT site leads"})

    @classmethod
    def load(cls, path: Path) -> "Settings":
        s = cls()
        if not path.exists():
            return s
        raw = json.loads(path.read_text(encoding="utf-8"))
        for k, v in raw.items():
            if k == "review_date":
                s.review_date = parse_dt(v)
            elif k in ("owners", "recommended_volume", "low_volume", "owned_cost_per_page", "replacement_cost"):
                getattr(s, k).update(v)
            elif hasattr(s, k):
                setattr(s, k, v)
        return s


@dataclass
class Data:
    settings: Settings
    printers: list
    queues: list
    devices: dict          # serial -> Device
    supplies: list
    counters: list
    contracts: dict
    tickets: list
    sources: dict = field(default_factory=dict)

    def printer(self, pid: str) -> Printer | None:
        return next((p for p in self.printers if p.id == pid), None)


def load(folder: Path) -> Data:
    folder = Path(folder)
    if not (folder / "printers.csv").exists():
        raise FileNotFoundError(f"missing in {folder}: printers.csv (the printer register)")
    s = Settings.load(folder / "settings.json")
    sources: dict[str, int] = {}

    def rows(name: str, aliases: dict) -> list[dict]:
        p = folder / name
        if not p.exists():
            return []
        r = _rows(p, aliases)
        sources[name] = len(r)
        return r

    printers = []
    for r in rows("printers.csv", PRINTER_ALIASES):
        if not r.get("id"):
            continue
        printers.append(Printer(r["id"], r.get("site", ""), r.get("location", ""), kind(r.get("kind"), r.get("model", "")),
                                r.get("model", ""), r.get("serial", ""), ip(r.get("ip")), r.get("department", ""),
                                r.get("contract", ""), parse_d(r.get("installed")), parse_d(r.get("lease_end")),
                                yes(r.get("secure_release")), yes(r.get("sensitive")),
                                _norm(r.get("status")) not in {"retired", "disposed", "decommissioned", "inactive"}))
    if not printers:
        raise ValueError("printers.csv has no printers")
    by_ip = {p.ip: p.id for p in printers if p.ip and p.active}
    by_name = {_norm(p.id): p.id for p in printers}
    queues = []
    for r in rows("queues.csv", QUEUE_ALIASES):
        if not r.get("queue"):
            continue
        q = Queue(r.get("server", ""), r["queue"], r.get("share", ""), ip(r.get("port_ip")), r.get("driver", ""),
                  r.get("driver_version", ""), queue_status(r.get("status")), int(num(r.get("jobs")) or 0), num(r.get("oldest")) or 0.0)
        q.printer = (by_name.get(_norm(r.get("printer"))) or by_name.get(_norm(q.queue)) or by_name.get(_norm(q.share))
                     or by_ip.get(q.port_ip, ""))
        queues.append(q)
    devices = {}
    for r in rows("devices.csv", DEVICE_ALIASES):
        if not r.get("serial"):
            continue
        prot = {_norm(x).replace(" ", "") for x in re.split(r"[;,|]", r.get("protocols", "")) if x.strip()}
        snmp = _norm(r.get("snmp")).replace(" ", "")
        if snmp and snmp not in ("v3", "snmpv3", "off", "disabled", "none"):
            prot.add("snmpv1" if "1" in snmp and "2" not in snmp else "snmpv2c")
        devices[r["serial"]] = Device(r["serial"], ip(r.get("ip")), r.get("model", ""), parse_dt(r.get("last_seen")),
                                      device_state(r.get("state")), r.get("message", ""), r.get("firmware", ""), prot,
                                      r.get("snmp", ""), yes(r.get("default_admin")))
    supplies = [Supply(r["serial"], r.get("supply", ""), num(r.get("level")) or 0.0, num(r.get("level_before")), yes(r.get("on_order")))
                for r in rows("supplies.csv", SUPPLY_ALIASES) if r.get("serial")]
    counters = [Counter(r["serial"], r.get("month", ""), num(r.get("mono")) or 0.0, num(r.get("colour")) or 0.0)
                for r in rows("counters.csv", COUNTER_ALIASES) if r.get("serial")]
    contracts = {r["id"]: Contract(r["id"], r.get("vendor", ""), r.get("kind", ""), num(r.get("click_mono")) or 0.0,
                                   num(r.get("click_colour")) or 0.0, num(r.get("monthly_fee")) or 0.0,
                                   num(r.get("response_hours")) or 0.0, parse_d(r.get("end")), int(num(r.get("notice_days")) or 0),
                                   num(r.get("credit")) or 0.0)
                 for r in rows("contracts.csv", CONTRACT_ALIASES) if r.get("id")}
    tickets = []
    for r in rows("tickets.csv", TICKET_ALIASES):
        if not r.get("id"):
            continue
        tickets.append(Ticket(r["id"], by_name.get(_norm(r.get("printer")), r.get("printer", "")), parse_dt(r.get("opened")),
                              r.get("category", ""), parse_dt(r.get("vendor_called")), parse_dt(r.get("vendor_arrived")),
                              parse_dt(r.get("resolved"))))
    return Data(s, printers, queues, devices, supplies, counters, contracts, tickets, sources)
