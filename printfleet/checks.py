"""The review: is every printer in the register, on a working queue and answering (unregistered and duplicate queues, queues pointing
to the wrong address, stuck and offline queues); consumables that will run out before the next delivery; how much each device prints
against what it is built for (consolidation candidates, overworked devices, colour share) and what it costs per site and department;
security (firmware, management protocols, SNMP, default passwords, secure release where documents are confidential, drivers);
lifecycle (age, leases ending) and service (repeat tickets, vendor response against the contract). Every finding has an owner and a
due date, and the choices become decisions."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .model import DIRECT, KINDS, Data, Printer, version

RED, AMBER, GREEN = "RED", "AMBER", "GREEN"
GROUPS = {"fleet": "Fleet and queues", "supplies": "Consumables", "usage": "Usage and cost", "security": "Security",
          "lifecycle": "Lifecycle", "service": "Service"}


@dataclass
class Finding:
    severity: str
    code: str
    group: str
    title: str
    subject: str
    detail: str
    action: str
    items: list = field(default_factory=list)
    owner: str = ""
    due: date | None = None
    site: str = ""

    @property
    def count(self) -> int:
        return len(self.items) or 1


@dataclass
class Decision:
    id: str
    decision: str
    why: str
    options: str
    proposed: str
    owner: str
    needed_by: date | None


def _n(x: float) -> str:
    return f"{x:,.0f}"


def _eur(x: float) -> str:
    return _n(x) + " EUR"


class Review:
    def __init__(self, d: Data):
        self.d = d
        self.s = d.settings
        self.now: datetime = self.s.review_date or datetime.now().replace(second=0, microsecond=0)
        self.today = self.now.date()
        self.findings: list[Finding] = []
        self.active = [p for p in d.printers if p.active]
        self.by_serial = {p.serial: p for p in d.printers if p.serial}
        self.usage = self._usage()
        self.supply_rows = self._supplies()
        self.cost = {p.id: self._cost(p) for p in self.active}
        self.consolidation: list[dict] = []
        self.sla_rows: list[dict] = []

    # -------------------------------------------------- figures
    def _usage(self) -> dict:
        """Average monthly mono and colour pages per printer over the last three months in counters.csv."""
        by = defaultdict(list)
        for c in self.d.counters:
            p = self.by_serial.get(c.serial)
            if p:
                by[p.id].append(c)
        out = {}
        for pid, cs in by.items():
            cs = sorted(cs, key=lambda c: c.month)[-3:]
            mono = sum(c.mono for c in cs) / len(cs)
            colour = sum(c.colour for c in cs) / len(cs)
            first, last = cs[0].mono + cs[0].colour, cs[-1].mono + cs[-1].colour
            out[pid] = {"mono": mono, "colour": colour, "total": mono + colour, "months": len(cs),
                        "colour_pct": colour / (mono + colour) * 100 if mono + colour else 0.0,
                        "trend_pct": (last - first) / first * 100 if first else 0.0}
        return out

    def _supplies(self) -> list[dict]:
        rows = []
        for x in self.d.supplies:
            p = self.by_serial.get(x.serial)
            if not p or not p.active:
                continue
            rate = (x.level_before - x.level) / 30 if x.level_before is not None and x.level_before > x.level else None
            days = x.level / rate if rate else None
            if x.level <= 0:
                days = 0.0
            order_by = self.today + timedelta(days=max(0, int(days) - self.s.order_lead_days)) if days is not None else None
            rows.append({"printer": p, "supply": x.supply, "level": x.level, "per_day": rate, "days": days, "on_order": x.on_order,
                         "order_by": order_by})
        return rows

    def _cost(self, p: Printer) -> float:
        """Monthly cost: rental plus clicks under a contract; consumables and parts per page for an owned device."""
        c = self.d.contracts.get(p.contract)
        u = self.usage.get(p.id)
        if not c:
            return u["total"] * self.s.owned_cost_per_page.get(p.kind, 0.0) if u else 0.0
        return c.monthly_fee + (u["mono"] * c.click_mono + u["colour"] * c.click_colour if u else 0.0)

    def device(self, p: Printer):
        return self.d.devices.get(p.serial)

    def queues_of(self, p: Printer) -> list:
        return [q for q in self.d.queues if q.printer == p.id]

    # -------------------------------------------------- helpers
    def due(self, sev: str) -> date:
        return self.today + timedelta(days=2 if sev == RED else 14)

    def add(self, sev, code, group, title, subject, detail, action, owner_key, items=None, site=""):
        self.findings.append(Finding(sev, code, group, title, subject, detail, action, items or [],
                                     self.s.owners.get(owner_key, owner_key), self.due(sev), site))

    # -------------------------------------------------- fleet and queues
    def check_fleet(self):
        d, s = self.d, self.s
        known_ips = {p.ip for p in d.printers if p.ip}
        known_serials = {p.serial for p in d.printers if p.serial}
        unreg = [q for q in d.queues if not q.printer]
        if unreg:
            self.add(AMBER, "PRN-UNREGISTERED", "fleet", "Queues for printers that are not in the register",
                     f"{len(unreg)} queue(s)", "; ".join(f"{q.server}\\{q.queue} ({q.port_ip or 'no address'})" for q in unreg) + ".",
                     "Add the printer to the register with its site, owner and contract, or delete the queue.", "PRINT",
                     [f"{q.server}\\{q.queue}" for q in unreg])
        strangers = [x for x in d.devices.values() if x.serial not in known_serials and x.ip not in known_ips]
        if strangers:
            self.add(AMBER, "PRN-UNKNOWN-DEVICE", "fleet", "Devices on the network that nobody registered",
                     f"{len(strangers)} device(s)", "; ".join(f"{x.model or 'unknown model'} at {x.ip} (serial {x.serial})"
                                                              for x in strangers) + ".",
                     "Find out who installed it; register it under a contract or take it off the network.", "PRINT",
                     [x.serial for x in strangers])
        by_printer = defaultdict(list)
        for q in d.queues:
            if q.printer:
                by_printer[q.printer].append(q)
        dup = {pid: qs for pid, qs in by_printer.items() if len({q.server for q in qs}) > 1}
        if dup:
            servers = sorted({q.server for qs in dup.values() for q in qs})
            self.add(AMBER, "PRN-DUP-QUEUE", "fleet", "The same printer shared from more than one print server",
                     f"{len(dup)} printer(s)", f"Servers involved: {', '.join(servers)}. Users mapped to the old queue keep "
                     "working until that server is switched off, then they cannot print: "
                     + "; ".join(f"{pid} ({', '.join(q.server for q in qs)})" for pid, qs in sorted(dup.items())) + ".",
                     "Move the users to the queue on the current server (group policy or print management) and delete the old queue.",
                     "PRINT", sorted(dup))
        for p in self.active:
            qs = by_printer.get(p.id, [])
            dev = self.device(p)
            if not qs and p.kind not in DIRECT and d.queues:
                self.add(AMBER, "PRN-NOQUEUE", "fleet", "Printer with no print queue", p.id,
                         f"{KINDS[p.kind]} at {p.site}, {p.location}: no queue on any print server, so users print to it directly "
                         "or not at all.", "Publish it on the print server, or retire it.", "PRINT", [p.id], p.site)
            for q in qs:
                seen = dev.ip if dev and dev.ip else p.ip
                if q.port_ip and seen and q.port_ip != seen:
                    self.add(RED, "PRN-QUEUE-IP", "fleet", "Queue sends jobs to the wrong address", p.id,
                             f"{q.server}\\{q.queue} prints to {q.port_ip}, but the printer is at {seen}. Jobs wait in the queue and "
                             "users see it as offline.", "Point the queue port at the printer's address and give the printer a "
                             "reservation or a fixed address so it does not move again.", "PRINT", [p.id], p.site)
                if q.oldest >= s.stuck_minutes and q.jobs:
                    sev = RED if q.oldest >= 2 * s.stuck_minutes or q.jobs >= 10 else AMBER
                    self.add(sev, "PRN-QUEUE-STUCK", "fleet", "Stuck queue", p.id,
                             f"{q.server}\\{q.queue}: {q.jobs} job(s) waiting, the oldest for {q.oldest:.0f} minutes.",
                             "Find the job that blocks it (state, size, owner), cancel it and check that the rest print.", "SUPPORT",
                             [p.id], p.site)
            offline = False
            why = ""
            if dev and dev.last_seen and (self.now - dev.last_seen).total_seconds() > s.offline_hours * 3600:
                offline, why = True, f"not seen by the portal since {dev.last_seen:%d %b %H:%M}"
            elif dev and dev.state in ("offline", "error"):
                offline, why = True, f"reports {dev.state}" + (f" ({dev.message})" if dev.message else "")
            elif any(q.status in ("offline", "error") for q in qs):
                q = next(q for q in qs if q.status in ("offline", "error"))
                offline, why = True, f"queue {q.server}\\{q.queue} is {'offline' if q.status == 'offline' else 'in error'}"
            if offline:
                self.add(RED, "PRN-DOWN", "fleet", "Printer not working", p.id, f"{KINDS[p.kind]} at {p.site}, {p.location}: {why}.",
                         "Check it on site (power, network, error on the panel) and log a call with the vendor if it is a fault.",
                         "SUPPORT", [p.id], p.site)
            if any(q.status == "paused" for q in qs):
                self.add(AMBER, "PRN-PAUSED", "fleet", "Queue paused", p.id, "Someone paused the queue and nobody resumed it.",
                         "Resume it or write down why it stays paused.", "SUPPORT", [p.id], p.site)

    # -------------------------------------------------- consumables
    def check_supplies(self):
        empty = [r for r in self.supply_rows if not r["on_order"] and (r["level"] <= 5 or (r["days"] is not None and r["days"] <= 2))]
        soon = [r for r in self.supply_rows if r not in empty and not r["on_order"] and r["days"] is not None
                and r["days"] <= self.s.supply_days]
        if empty:
            self.add(RED, "SUP-EMPTY", "supplies", "Consumables empty or about to run out, not ordered", f"{len(empty)} item(s)",
                     "; ".join(f"{r['printer'].id} {r['supply']} {r['level']:.0f} %" for r in empty) + ".",
                     "Order them today or send one from the spares; the device stops when they run out.", "SUPPORT",
                     [r["printer"].id for r in empty])
        if soon:
            self.add(AMBER, "SUP-SOON", "supplies", f"Consumables that run out within {self.s.supply_days} days",
                     f"{len(soon)} item(s)", "; ".join(f"{r['printer'].id} {r['supply']} ({r['days']:.0f} days)" for r in soon) + ".",
                     f"Order them before the date in supplies-forecast.csv ({self.s.order_lead_days} days for delivery).",
                     "SUPPORT", [r["printer"].id for r in soon])

    # -------------------------------------------------- usage and cost
    def check_usage(self):
        s = self.s
        by_place = defaultdict(list)
        for p in self.active:
            by_place[(p.site, p.location)].append(p)
        under, over, colour = [], [], []
        for p in self.active:
            u = self.usage.get(p.id)
            if not u:
                continue
            if p.kind in s.low_volume and u["total"] < s.low_volume[p.kind]:
                under.append(p)
            if u["total"] > s.recommended_volume.get(p.kind, 1e12):
                over.append(p)
            if u["colour"] and u["colour_pct"] > s.colour_share_max and u["total"] >= 300:
                colour.append(p)
        for p in under:
            others = [o for o in by_place[(p.site, p.location)] if o.id != p.id and o.kind.startswith("mfp") and o not in under
                      and o.id in self.usage and self.usage[o.id]["total"] < 0.6 * s.recommended_volume[o.kind]]
            target = others[0] if others else None
            self.consolidation.append({"printer": p, "pages": self.usage[p.id]["total"], "target": target,
                                       "monthly_cost": self.cost.get(p.id, 0.0)})
        if under:
            movable = [r for r in self.consolidation if r["target"]]
            run = sum(r["monthly_cost"] for r in movable) * 12
            old = [r["printer"] for r in movable if r["printer"].installed
                   and (self.today - r["printer"].installed).days > s.max_age_years * 365]
            avoided = sum(s.replacement_cost.get(p.kind, 0) for p in old)
            self.add(AMBER, "USE-UNDER", "usage", "Printers that hardly print", f"{len(under)} printer(s)",
                     f"{len(under)} print less than the low-use level for their type; {len(movable)} have a multifunction on the "
                     f"same floor with room to spare. Removing those saves about {_eur(run)} a year in rental and consumables, "
                     f"one device each to support and patch, and {_eur(avoided)} of replacements ({len(old)} are past "
                     f"{s.max_age_years} years).", "Agree with each team which ones go (consolidation.csv) and move "
                     "their users to the multifunction.", "DECISION", [p.id for p in under])
        if over:
            self.add(AMBER, "USE-OVER", "usage", "Printers working above what they are built for", f"{len(over)} printer(s)",
                     "; ".join(f"{p.id} ({_n(self.usage[p.id]['total'])} pages a month, recommended "
                               f"{_n(s.recommended_volume[p.kind])})" for p in over) + ". Expect more jams and "
                     "parts.", "Move part of the volume to a bigger device or replace it with one sized for the volume.",
                     "DECISION", [p.id for p in over])
        if colour:
            self.add(AMBER, "USE-COLOUR", "usage", "High colour share", f"{len(colour)} printer(s)",
                     "; ".join(f"{p.id} {self.usage[p.id]['colour_pct']:.0f} % colour ({p.department})" for p in colour)
                     + f". Policy: {s.colour_share_max:g} %; a colour page costs several times a mono one.",
                     "Set mono as the default in the driver for these queues and keep colour for who needs it.", "PRINT",
                     [p.id for p in colour])

    # -------------------------------------------------- security
    def check_security(self):
        s = self.s
        insecure = {x.lower() for x in s.insecure_protocols}
        fw, prot, snmp, admin, release, driver = [], [], [], [], [], []
        for p in self.active:
            dev = self.device(p)
            if dev:
                need = s.approved_firmware.get(p.model)
                if need and dev.firmware and version(dev.firmware) < version(need):
                    fw.append((p, dev.firmware, need))
                bad = sorted(x for x in dev.protocols if x in insecure and not x.startswith("snmp"))
                if bad:
                    prot.append((p, bad))
                if any(x.startswith("snmpv") and x in insecure for x in dev.protocols):
                    snmp.append(p)
                if dev.default_admin:
                    admin.append(p)
            if p.sensitive and not p.secure_release and p.kind not in DIRECT:
                release.append(p)
            for q in self.queues_of(p):
                need = s.approved_drivers.get(q.driver)
                if need and version(q.driver_version) < version(need):
                    driver.append((p, q))
        if admin:
            self.add(RED, "SEC-DEFAULT-ADMIN", "security", "Factory admin password on the device", f"{len(admin)} printer(s)",
                     "Anyone on the network can change settings, read the address book or redirect scans: "
                     + ", ".join(p.id for p in admin) + ".", "Set a unique admin password (stored in the vault) today.", "SECURITY",
                     [p.id for p in admin])
        if release:
            self.add(RED, "SEC-RELEASE", "security", "Confidential area without secure release", f"{len(release)} printer(s)",
                     "Documents wait in the tray until someone collects them: " + "; ".join(f"{p.id} ({p.department}, {p.location})"
                                                                                         for p in release) + ".",
                     "Turn on secure release (badge or PIN at the device) for these queues.", "DECISION", [p.id for p in release])
        if prot:
            self.add(AMBER, "SEC-PROTOCOLS", "security",
                     "Unencrypted management protocols enabled", f"{len(prot)} printer(s)",
                     "; ".join(f"{p.id}: {', '.join(b)}" for p, b in prot) + ".",
                     "Turn them off in the device settings (or a fleet policy) and manage over HTTPS only.", "SECURITY",
                     [p.id for p, _ in prot])
        if snmp:
            self.add(AMBER, "SEC-SNMP", "security", "SNMP v1 or v2c", f"{len(snmp)} printer(s)",
                     "Community strings travel in clear text: " + ", ".join(p.id for p in snmp) + ".",
                     "Move the monitoring to SNMPv3, or at least change the community and limit who can query.", "SECURITY",
                     [p.id for p in snmp])
        if fw:
            self.add(AMBER, "SEC-FIRMWARE", "security", "Firmware below the approved version", f"{len(fw)} printer(s)",
                     "; ".join(f"{p.id} {have} (approved {need})" for p, have, need in fw) + ".",
                     "Update them in the next maintenance window, after a test on one device per model.", "PRINT",
                     [p.id for p, _, _ in fw])
        if driver:
            self.add(AMBER, "SEC-DRIVER", "security", "Queues on a driver older than the approved one", f"{len(driver)} queue(s)",
                     "; ".join(f"{q.server}\\{q.queue} {q.driver} {q.driver_version}" for _, q in driver) + ".",
                     "Update the driver on the print server, then check printing from one client of each type.", "PRINT",
                     [p.id for p, _ in driver])

    # -------------------------------------------------- lifecycle
    def check_lifecycle(self):
        s = self.s
        old = [p for p in self.active if p.installed and (self.today - p.installed).days > s.max_age_years * 365]
        if old:
            self.add(AMBER, "LIFE-AGE", "lifecycle", f"Printers older than {s.max_age_years} years", f"{len(old)} printer(s)",
                     "; ".join(f"{p.id} ({p.installed:%Y})" for p in old) + ".",
                     "Plan their replacement in next year's budget, or retire them if usage is low.", "DECISION",
                     [p.id for p in old])
        for p in self.active:
            if not p.lease_end:
                continue
            c = self.d.contracts.get(p.contract)
            notice = p.lease_end - timedelta(days=c.notice_days if c else 0)
            left = (p.lease_end - self.today).days
            if left < 0:
                self.add(RED, "LIFE-LEASE", "lifecycle", "Lease already ended", p.id,
                         f"The lease ended on {p.lease_end:%d %b %Y}; the device is out of contract.",
                         "Agree an extension or return it.", "VENDOR", [p.id], p.site)
            elif left <= s.lease_warning_days:
                sev = RED if (notice - self.today).days <= 14 else AMBER
                self.add(sev, "LIFE-LEASE", "lifecycle", "Lease ending", p.id,
                         f"Lease ends {p.lease_end:%d %b %Y}; notice to the vendor by {notice:%d %b %Y}"
                         + (" (within two weeks)" if sev == RED else "") + ".",
                         "Decide: renew, replace with a different size, or consolidate (see the usage).", "VENDOR", [p.id], p.site)

    # -------------------------------------------------- service
    def check_service(self):
        s = self.s
        since = self.now - timedelta(days=s.repeat_window_days)
        recent = defaultdict(list)
        for t in self.d.tickets:
            if t.opened and t.opened >= since:
                recent[t.printer].append(t)
        for pid, ts in recent.items():
            if len(ts) < s.repeat_tickets:
                continue
            p = self.d.printer(pid)
            cats = defaultdict(int)
            for t in ts:
                cats[t.category or "other"] += 1
            hint = ""
            if p and any(f.code == "PRN-QUEUE-IP" and pid in f.items for f in self.findings):
                hint = " The queue points to an old address (PRN-QUEUE-IP): that is likely the cause."
            self.add(RED if len(ts) >= s.repeat_tickets + 2 else AMBER, "SVC-REPEAT", "service", "Repeat tickets on one printer",
                     pid, f"{len(ts)} tickets in {s.repeat_window_days} days: " + ", ".join(f"{k} {v}" for k, v in sorted(cats.items()))
                     + "." + hint, "Open a problem record and fix the cause instead of the symptom.", "SUPPORT", [pid],
                     p.site if p else "")
        breaches = []
        for t in self.d.tickets:
            p = self.d.printer(t.printer)
            c = self.d.contracts.get(p.contract) if p else None
            if not (c and c.response_hours and t.vendor_called):
                continue
            end = t.vendor_arrived or (self.now if not t.resolved else None)
            if not end:
                continue
            hours = (end - t.vendor_called).total_seconds() / 3600
            row = {"ticket": t, "printer": p, "contract": c, "hours": hours, "breach": hours > c.response_hours,
                   "open": t.vendor_arrived is None}
            self.sla_rows.append(row)
            if row["breach"]:
                breaches.append(row)
        if breaches:
            credit = sum(r["contract"].credit for r in breaches)
            vendors = sorted({r["contract"].vendor for r in breaches})
            self.add(AMBER, "SVC-VENDOR-SLA", "service", "Vendor late to break-fix calls", f"{len(breaches)} call(s)",
                     f"{', '.join(vendors)}: " + "; ".join(f"{r['ticket'].id} {r['printer'].id} {r['hours']:.0f} h against "
                                                           f"{r['contract'].response_hours:g} h" for r in breaches)
                     + (f". Service credits due: {_eur(credit)}." if credit else "."),
                     "Raise them in the monthly service review and claim the credits.", "VENDOR",
                     [r["printer"].id for r in breaches])

    # -------------------------------------------------- decisions and summary
    def decisions(self) -> list[Decision]:
        out = []
        owner = self.s.owners.get("DECISION", "")
        due = self.today + timedelta(days=14)
        codes = {f.code: f for f in self.findings}

        def add(decision, why, options, proposed):
            out.append(Decision(f"D{len(out) + 1}", decision, why, options, proposed, owner, due))
        if "SEC-RELEASE" in codes:
            f = codes["SEC-RELEASE"]
            add("Secure release for confidential areas", f.detail, "Secure release on these queues / move the printer out of the "
                "area / accept the risk in writing", "Secure release on these queues; the users badge or type a PIN at the device.")
        movable = [r for r in self.consolidation if r["target"]]
        if movable:
            add("Which low-use printers to remove", f"{len(movable)} printers print little and share a floor with a multifunction "
                "with spare capacity: " + ", ".join(r["printer"].id for r in movable) + ".", "Remove all / remove some after talking to each team / keep",
                "Remove them after a two-week notice to each team, with their queue redirected to the multifunction.")
        if "LIFE-LEASE" in codes:
            ending = [f for f in self.findings if f.code == "LIFE-LEASE"]
            add("Leases ending", f"{len(ending)} device(s): " + ", ".join(f.subject for f in ending) + ".",
                "Renew as they are / replace with the size the usage shows / consolidate", "Decide device by device with the "
                "usage figures; give notice where the answer is not a straight renewal.")
        if "PRN-DUP-QUEUE" in codes:
            f = codes["PRN-DUP-QUEUE"]
            add("Switch off the old print server", f"{len(f.items)} printers are still shared from the old server as well as the "
                "current one; users mapped to the old queues stop printing the day it goes.", "Move users and switch off now / keep it until "
                "the next refresh", "Move the users this month and switch it off after a week with no jobs on it.")
        if "USE-COLOUR" in codes:
            add("Mono by default", codes["USE-COLOUR"].detail, "Mono default on these queues / on every queue / leave it",
                "Mono by default on every queue; colour stays one click away.")
        return out

    def run(self) -> dict:
        self.check_fleet()
        self.check_supplies()
        self.check_usage()
        self.check_security()
        self.check_lifecycle()
        self.check_service()
        order = {RED: 0, AMBER: 1}
        self.findings.sort(key=lambda f: (order[f.severity], list(GROUPS).index(f.group), f.subject))
        return {"review": self, "findings": self.findings, "decisions": self.decisions()}


def review(d: Data) -> dict:
    return Review(d).run()


def printer_status(rv: dict, p: Printer) -> str:
    sev = [f.severity for f in rv["findings"] if p.id in f.items]
    return RED if RED in sev else AMBER if AMBER in sev else GREEN


def site_rows(d: Data, rv: dict) -> list[dict]:
    r: Review = rv["review"]
    out = []
    for site in sorted({p.site for p in r.active}):
        ps = [p for p in r.active if p.site == site]
        st = [printer_status(rv, p) for p in ps]
        down = sum(any(f.code == "PRN-DOWN" and p.id in f.items for f in rv["findings"]) for p in ps)
        out.append({"site": site, "printers": len(ps), "red": st.count(RED), "amber": st.count(AMBER), "green": st.count(GREEN),
                    "down": down, "pages": sum(r.usage.get(p.id, {}).get("total", 0) for p in ps),
                    "cost": sum(r.cost.get(p.id, 0) for p in ps),
                    "status": RED if down or st.count(RED) else AMBER if st.count(AMBER) else GREEN})
    return out


def summary(d: Data, rv: dict) -> dict:
    r: Review = rv["review"]
    fs = rv["findings"]
    red = sum(f.severity == RED for f in fs)
    amber = sum(f.severity == AMBER for f in fs)
    down = {i for f in fs if f.code == "PRN-DOWN" for i in f.items}
    supplies = sum(f.count for f in fs if f.code in ("SUP-EMPTY", "SUP-SOON"))
    sec = {i for f in fs if f.group == "security" for i in f.items}
    movable = [x for x in r.consolidation if x["target"]]
    credits = 0.0
    for x in r.sla_rows:
        if x["breach"]:
            credits += x["contract"].credit
    return {"status": RED if red else AMBER if amber else GREEN, "red": red, "amber": amber, "printers": len(r.active),
            "sites": len({p.site for p in r.active}), "up": len(r.active) - len(down), "down": len(down),
            "availability": (len(r.active) - len(down)) / len(r.active) * 100 if r.active else 100.0,
            "supplies": supplies, "security": len(sec), "pages": sum(u["total"] for u in r.usage.values()),
            "cost": sum(r.cost.values()), "consolidate": len(movable),
            "saving": sum(x["monthly_cost"] for x in movable) * 12, "credits": credits, "decisions": len(rv["decisions"])}
