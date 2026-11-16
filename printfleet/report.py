"""Outputs: report.html (tiles, decisions, sites, the printers that need attention, consumables, queues, usage and cost, security,
service and every finding), review-pack.md (the page for the monthly review) and the CSVs: printers, supplies-forecast, queues-review,
usage-and-cost, consolidation, vendor-sla, findings and actions."""
from __future__ import annotations

import csv
import html
from collections import defaultdict
from pathlib import Path

from .checks import GROUPS, RED, Review, printer_status, site_rows, summary
from .model import FILES, KINDS, Data, version

e = html.escape
TODO = "**[TO COMPLETE]**"


def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _n(x: float) -> str:
    return f"{x:,.0f}"


def _eur(x: float) -> str:
    return _n(x) + " EUR"


def _day(x) -> str:
    return "" if not x else f"{x:%d %b %Y}"


def _codes(rv: dict, pid: str) -> list[str]:
    return sorted({f.code for f in rv["findings"] if pid in f.items})


# ---------------------------------------------------------------- csv

def write_printers(d: Data, rv: dict, path: Path) -> None:
    r: Review = rv["review"]
    rows = []
    for p in r.active:
        dev = r.device(p)
        u = r.usage.get(p.id, {})
        qs = r.queues_of(p)
        rows.append([p.id, p.site, p.location, KINDS[p.kind], p.model, p.serial, p.ip, dev.ip if dev else "", p.department,
                     "; ".join(f"{q.server}\\{q.queue}" for q in qs), dev.state if dev else "", dev.firmware if dev else "",
                     f"{u['total']:.0f}" if u else "", f"{u['colour_pct']:.0f}" if u else "", f"{r.cost.get(p.id, 0):.2f}",
                     p.contract, p.installed or "", p.lease_end or "", "yes" if p.secure_release else "no",
                     printer_status(rv, p), " ".join(_codes(rv, p.id))])
    _w(path, ["printer", "site", "location", "type", "model", "serial", "ip_register", "ip_seen", "department", "queues", "device_state",
              "firmware", "pages_per_month", "colour_pct", "cost_per_month_eur", "contract", "installed", "lease_end", "secure_release",
              "status", "findings"], rows)


def write_supplies(rv: dict, path: Path) -> None:
    r: Review = rv["review"]
    rows = sorted(r.supply_rows, key=lambda x: (x["days"] is None, x["days"] if x["days"] is not None else 0))
    _w(path, ["printer", "site", "supply", "level_pct", "used_per_day_pct", "days_left", "order_by", "on_order"],
       [[x["printer"].id, x["printer"].site, x["supply"], f"{x['level']:.0f}", "" if x["per_day"] is None else f"{x['per_day']:.2f}",
         "" if x["days"] is None else f"{x['days']:.0f}", x["order_by"] or "", "yes" if x["on_order"] else "no"] for x in rows])


def write_queues(d: Data, rv: dict, path: Path) -> None:
    r: Review = rv["review"]
    rows = []
    for q in d.queues:
        p = d.printer(q.printer)
        dev = r.device(p) if p else None
        issues = []
        if not p:
            issues.append("not in the register")
        if p and q.port_ip and ((dev and dev.ip) or p.ip) and q.port_ip != ((dev and dev.ip) or p.ip):
            issues.append("port address is not the printer's")
        if q.status != "normal":
            issues.append(q.status)
        if q.jobs and q.oldest >= d.settings.stuck_minutes:
            issues.append("stuck")
        need = d.settings.approved_drivers.get(q.driver)
        if need and version(q.driver_version) < version(need):
            issues.append("old driver")
        if p and len({x.server for x in d.queues if x.printer == p.id}) > 1:
            issues.append("shared from more than one server")
        rows.append([q.server, q.queue, q.share, q.printer, q.port_ip, q.driver, q.driver_version, q.status, q.jobs, f"{q.oldest:.0f}",
                     "; ".join(issues)])
    _w(path, ["server", "queue", "share", "printer", "port_ip", "driver", "driver_version", "status", "jobs", "oldest_job_min", "issues"],
       rows)


def write_usage(d: Data, rv: dict, path: Path) -> None:
    r: Review = rv["review"]
    rows = []
    for p in r.active:
        u = r.usage.get(p.id)
        if not u:
            continue
        rows.append([p.site, p.department, p.id, KINDS[p.kind], f"{u['mono']:.0f}", f"{u['colour']:.0f}", f"{u['colour_pct']:.0f}",
                     f"{u['trend_pct']:+.0f}", d.settings.recommended_volume.get(p.kind, ""),
                     f"{u['total'] / d.settings.recommended_volume[p.kind] * 100:.0f}" if d.settings.recommended_volume.get(p.kind) else "",
                     f"{r.cost.get(p.id, 0):.2f}"])
    _w(path, ["site", "department", "printer", "type", "mono_per_month", "colour_per_month", "colour_pct", "trend_pct",
              "recommended_volume", "load_pct", "cost_per_month_eur"], rows)


def write_consolidation(rv: dict, path: Path) -> None:
    r: Review = rv["review"]
    _w(path, ["printer", "site", "location", "department", "pages_per_month", "cost_per_month_eur", "move_users_to", "installed"],
       [[x["printer"].id, x["printer"].site, x["printer"].location, x["printer"].department, f"{x['pages']:.0f}",
         f"{x['monthly_cost']:.2f}", x["target"].id if x["target"] else "", x["printer"].installed or ""] for x in r.consolidation])


def write_sla(rv: dict, path: Path) -> None:
    r: Review = rv["review"]
    _w(path, ["ticket", "printer", "vendor", "contract", "called", "arrived", "response_hours", "sla_hours", "breach", "credit_eur"],
       [[x["ticket"].id, x["printer"].id, x["contract"].vendor, x["contract"].id, f"{x['ticket'].vendor_called:%Y-%m-%d %H:%M}",
         "" if x["open"] else f"{x['ticket'].vendor_arrived:%Y-%m-%d %H:%M}", f"{x['hours']:.1f}", f"{x['contract'].response_hours:g}",
         "yes" if x["breach"] else "no", f"{x['contract'].credit:g}" if x["breach"] else ""] for x in r.sla_rows])


def write_findings(rv: dict, path: Path) -> None:
    _w(path, ["severity", "code", "group", "site", "subject", "title", "detail", "action", "items", "owner", "due"],
       [[f.severity, f.code, GROUPS[f.group], f.site, f.subject, f.title, f.detail, f.action, " ".join(f.items), f.owner,
         f.due.isoformat() if f.due else ""] for f in rv["findings"]])


def write_actions(rv: dict, path: Path) -> None:
    _w(path, ["ref", "severity", "code", "subject", "action", "owner", "due", "done"],
       [[f"A-{i:03d}", f.severity, f.code, f.subject, f.action, f.owner, f.due.isoformat() if f.due else "", ""]
        for i, f in enumerate(rv["findings"], 1)])


# ---------------------------------------------------------------- the pack

def _md(x) -> str:
    return str(x).replace("|", "/").replace("\n", " ")


def pack_md(d: Data, rv: dict, title: str) -> str:
    r: Review = rv["review"]
    sm = summary(d, rv)
    out = [f"# {title}", "",
           f"> Monthly printer review, {r.now:%A %d %B %Y}. {sm['printers']} printers at {sm['sites']} sites. Sections marked {TODO} are "
           "for the meeting.", "",
           f"**Result: {sm['status']}.** {sm['up']} of {sm['printers']} printers working ({sm['availability']:.0f} %); "
           f"{sm['supplies']} consumables to order; {sm['security']} printers with a security finding; {_n(sm['pages'])} pages and "
           f"{_eur(sm['cost'])} a month; {sm['red']} red and {sm['amber']} amber findings and {sm['decisions']} decisions.", "",
           "## Headlines", ""]
    out += [f"- **{_md(f.title)}** ({f.subject}): {_md(f.detail)}" for f in rv["findings"] if f.severity == RED][:8]
    out += ["", "## Sites", "", "| Site | Printers | Not working | Red | Amber | Pages a month | Cost a month |", "|---|---|---|---|---|---|---|"]
    out += [f"| {x['site']} | {x['printers']} | {x['down']} | {x['red']} | {x['amber']} | {_n(x['pages'])} | {_eur(x['cost'])} |"
            for x in site_rows(d, rv)]
    out += ["", "## Decisions needed", "", "| # | Decision | Options | Proposed | Owner | Needed by | Outcome |", "|---|---|---|---|---|---|---|"]
    out += [f"| {x.id} | **{_md(x.decision)}**<br>{_md(x.why)} | {_md(x.options)} | {_md(x.proposed)} | {_md(x.owner)} | "
            f"{_day(x.needed_by)} | |" for x in rv["decisions"]]
    out += ["", "## Actions", "", "| Ref | Severity | Finding | Action | Owner | Due |", "|---|---|---|---|---|---|"]
    out += [f"| A-{i:03d} | {f.severity} | {_md(f.title)} ({_md(f.subject)}) | {_md(f.action)} | {_md(f.owner)} | {_day(f.due)} |"
            for i, f in enumerate(rv["findings"], 1)]
    soon = [x for x in r.supply_rows if x["days"] is not None and x["days"] <= d.settings.supply_days]
    if soon:
        out += ["", "## Consumables to order", "", "| Printer | Supply | Level | Days left | Order by | On order |", "|---|---|---|---|---|---|"]
        out += [f"| {x['printer'].id} | {x['supply']} | {x['level']:.0f} % | {x['days']:.0f} | {_day(x['order_by'])} | "
                f"{'yes' if x['on_order'] else 'no'} |" for x in sorted(soon, key=lambda x: x["days"])]
    if r.sla_rows:
        b = [x for x in r.sla_rows if x["breach"]]
        out += ["", "## Vendor", "", f"{len(r.sla_rows)} break-fix calls with a response time; {len(b)} late"
                + (f", {_eur(sum(x['contract'].credit for x in b))} of service credits to claim." if b else ".")]
    out += ["", "## Sources", "", "| Source | File | Rows |", "|---|---|---|"]
    out += [f"| {FILES.get(k, k)} | `{k}` | {v} |" for k, v in d.sources.items()]
    out += ["", "## Notes", "", f"- Attendees: {TODO}", f"- Decisions taken: {TODO}", f"- Next review: {TODO}", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--track:#e9ecef}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;
--warn:#f0a83a;--bad:#f2685c;--track:#2b333b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:24px}
.overall{display:inline-block;margin-top:14px;padding:6px 14px;border-radius:99px;font-weight:700;border:2px solid currentColor}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.red{color:var(--bad)}.amber{color:var(--warn)}.green{color:var(--ok)}
td.subj{min-width:140px}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);min-width:200px;max-width:340px}td.sm{font-size:13px}
.bar{display:inline-block;width:90px;height:8px;border-radius:4px;background:var(--track);vertical-align:middle;margin-right:8px;overflow:hidden}
.bar i{display:block;height:100%}.brk{overflow-wrap:anywhere;word-break:break-word}footer{margin-top:40px;font-size:13px}
"""


def _pill(x: str) -> str:
    return f"<span class='pill {x.lower()}'>{e(x)}</span>"


def _table(head: list[str], rows: list[str], empty: str = "Nothing to show.") -> str:
    if not rows:
        rows = [f"<tr><td colspan='{len(head)}'>{e(empty)}</td></tr>"]
    return "<div class='wrap'><table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" + "".join(rows) + "</table></div>"


def _bar(pct: float, cls: str) -> str:
    pct = max(0.0, min(100.0, pct))
    return f"<span class='bar'><i style='width:{pct:.0f}%;background:var(--{cls})'></i></span>"


def render_html(d: Data, rv: dict, title: str) -> str:
    r: Review = rv["review"]
    s = d.settings
    sm = summary(d, rv)
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>{e(s.organisation)} · {sm['printers']} printers at {sm['sites']} sites · "
         f"{len(d.queues)} queues on {len({q.server for q in d.queues})} print servers · {r.now:%A %d %B %Y, %H:%M}</p>",
         f"<span class='overall {sm['status'].lower()}'>{e(sm['status'])} · {sm['red']} red and {sm['amber']} amber findings</span>",
         "<div class='tiles'>"]
    tiles = [("Working", f"{sm['up']} of {sm['printers']}", f"{sm['availability']:.0f} % available now"),
             ("Consumables to order", str(sm["supplies"]), f"empty or out within {s.supply_days} days"),
             ("Security findings", str(sm["security"]), "printers with at least one"),
             ("Pages a month", _n(sm["pages"]), "average of the last three months"),
             ("Cost a month", _eur(sm["cost"]), "rental, clicks and consumables"),
             ("Printers to remove", str(sm["consolidate"]), "low use, a multifunction nearby"),
             ("Credits to claim", _eur(sm["credits"]), "late vendor responses")]
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(b)}</b><span class='muted'>{e(x)}</span></div>" for a, b, x in tiles]
    h.append("</div><h2>Decisions needed</h2>")
    h.append(_table(["#", "Decision", "Options", "Proposed", "Owner", "By"],
                    [f"<tr><td class='nw'>{e(x.id)}</td><td class='subj'><b>{e(x.decision)}</b><br><span class='sm muted'>{e(x.why)}</span></td>"
                     f"<td class='sm'>{e(x.options)}</td><td class='fix'>{e(x.proposed)}</td><td class='sm'>{e(x.owner)}</td>"
                     f"<td class='nw'>{e(_day(x.needed_by))}</td></tr>" for x in rv["decisions"]], "No decisions this month."))
    h.append("<h2>Sites</h2>")
    h.append(_table(["Site", "Status", "Printers", "Not working", "Red", "Amber", "Pages a month", "Cost a month"],
                    [f"<tr><td>{e(x['site'])}</td><td>{_pill(x['status'])}</td><td class='num'>{x['printers']}</td>"
                     f"<td class='num'>{x['down']}</td><td class='num'>{x['red']}</td><td class='num'>{x['amber']}</td>"
                     f"<td class='num'>{_n(x['pages'])}</td><td class='num'>{e(_eur(x['cost']))}</td></tr>" for x in site_rows(d, rv)]))
    attention = [p for p in r.active if printer_status(rv, p) == RED]
    h.append("<h2>Printers that need attention today</h2>")
    rows = []
    for p in attention:
        fs = [f for f in rv["findings"] if p.id in f.items and f.severity == RED]
        rows.append(f"<tr><td class='nw'><b>{e(p.id)}</b></td><td class='sm'>{e(p.site)}<br><span class='muted'>{e(p.location)} · "
                    f"{e(KINDS[p.kind])}</span></td><td class='sm brk'>" + "<br>".join(f"<b>{e(f.title)}</b>" for f in fs)
                    + f"</td><td class='fix'>{e(fs[0].action if fs else '')}</td></tr>")
    h.append(_table(["Printer", "Where", "Why", "First action"], rows, "No printer needs attention today."))
    soon = sorted([x for x in r.supply_rows if x["days"] is not None and x["days"] <= s.supply_days], key=lambda x: x["days"])
    h.append(f"<h2>Consumables</h2><p class='muted'>Empty or running out within {s.supply_days} days at the rate of the last 30 days; "
             f"order {s.order_lead_days} days before. The full list is in supplies-forecast.csv.</p>")
    h.append(_table(["Printer", "Supply", "Level", "Days left", "Order by", "On order"],
                    [f"<tr><td class='nw'>{e(x['printer'].id)}</td><td class='sm'>{e(x['supply'])}</td><td class='nw'>"
                     f"{_bar(x['level'], 'bad' if x['level'] <= 5 else 'warn')}{x['level']:.0f} %</td><td class='num'>{x['days']:.0f}</td>"
                     f"<td class='nw'>{e(_day(x['order_by']))}</td><td class='{'green' if x['on_order'] else 'red'}'>"
                     f"{'yes' if x['on_order'] else 'no'}</td></tr>" for x in soon], "Nothing runs out in the window."))
    h.append("<h2>Usage and cost</h2><p class='muted'>The printers outside the range for their type, on the average of the last three "
             "months: overworked, hardly used (consolidation.csv) or printing mostly in colour. Every printer is in usage-and-cost.csv.</p>")
    rows = []
    for p in sorted(r.active, key=lambda p: -r.usage.get(p.id, {}).get("total", 0)):
        u = r.usage.get(p.id)
        rec = s.recommended_volume.get(p.kind)
        if not u or not rec:
            continue
        load = u["total"] / rec * 100
        flag = "over" if load > 100 else ("low use" if p.kind in s.low_volume and u["total"] < s.low_volume[p.kind] else "")
        if u["colour_pct"] > s.colour_share_max and not flag:
            flag = "colour"
        if not flag:
            continue
        rows.append(f"<tr><td class='nw'>{e(p.id)}</td><td class='sm'>{e(p.site)} · {e(p.department)}</td><td class='num'>{_n(u['total'])}</td>"
                    f"<td class='nw'>{_bar(load, 'bad' if load > 100 else 'ok')}{load:.0f} %</td><td class='num'>{u['colour_pct']:.0f} %</td>"
                    f"<td class='num'>{e(_eur(r.cost.get(p.id, 0)))}</td><td class='sm {'red' if flag == 'over' else 'amber'}'>{e(flag)}</td></tr>")
    h.append(_table(["Printer", "Site · department", "Pages a month", "Load", "Colour", "Cost a month", ""], rows,
                    "Every printer is within the range for its type."))
    by_dept = defaultdict(float)
    for p in r.active:
        by_dept[p.department or "Unassigned"] += r.cost.get(p.id, 0)
    h.append("<h2>Cost by department</h2>")
    h.append(_table(["Department", "Cost a month", "Cost a year"],
                    [f"<tr><td>{e(k)}</td><td class='num'>{e(_eur(v))}</td><td class='num'>{e(_eur(v * 12))}</td></tr>"
                     for k, v in sorted(by_dept.items(), key=lambda x: -x[1])]))
    h.append("<h2>Every finding</h2>")
    h.append(_table(["Severity", "Area", "Finding", "Action", "Owner", "Due"],
                    [f"<tr><td>{_pill(f.severity)}</td><td class='sm'>{e(GROUPS[f.group])}</td><td class='sm brk'><b>{e(f.title)}</b> · "
                     f"{e(f.subject)}<br>{e(f.detail)}</td><td class='fix'>{e(f.action)}</td><td class='sm'>{e(f.owner)}</td>"
                     f"<td class='nw'>{e(_day(f.due))}</td></tr>" for f in rv["findings"]], "No findings."))
    h.append("<footer class='muted'>Generated by printfleet. Fictional demo data unless you ran it on your own files. The page for "
             "the monthly review is review-pack.md.</footer></main></body></html>")
    return "".join(h)
