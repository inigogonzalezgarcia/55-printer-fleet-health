import csv
import json
from pathlib import Path

import pytest

from printfleet import simulate
from printfleet.checks import RED, review, summary
from printfleet.cli import OUTPUTS, main, run
from printfleet.model import device_state, kind, load, num, queue_status, version

NOW = "2026-11-16 08:30"
P_HEAD = ["Printer", "Site", "Location", "Type", "Model", "Serial", "IP", "Department", "Contract", "Installed", "LeaseEnd",
          "SecureRelease", "Sensitive", "Status"]
Q_HEAD = ["Server", "Name", "ShareName", "PrinterHostAddress", "DriverName", "DriverVersion", "PrinterStatus", "JobCount",
          "OldestJobMinutes"]
D_HEAD = ["Serial", "IP", "Model", "LastSeen", "Status", "Message", "Firmware", "Protocols", "SNMP", "DefaultAdminPassword"]


def write(path: Path, head: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        w.writerows(rows)


def fleet(tmp_path: Path, printers=None, queues=None, devices=None, supplies=None, counters=None, tickets=None, settings=None) -> Path:
    """Two healthy printers on one floor: an A3 multifunction under contract and an owned desk printer."""
    write(tmp_path / "printers.csv", P_HEAD, printers if printers is not None else [
        ["MFP1", "HQ", "Floor 1", "mfp-a3", "M-A3", "S1", "10.0.1.21", "Finance", "C1", "2024-01-10", "2028-01-31", "yes", "yes", "active"],
        ["P01", "HQ", "Floor 1", "desk", "D-1", "S2", "10.0.1.31", "Finance", "", "2023-05-01", "", "no", "no", "active"]])
    write(tmp_path / "queues.csv", Q_HEAD, queues if queues is not None else [
        ["PRT1", "MFP1", "MFP1", "10.0.1.21", "Uni", "7.4.0.0", "Normal", 0, 0],
        ["PRT1", "P01", "P01", "10.0.1.31", "Uni", "7.4.0.0", "Normal", 0, 0]])
    write(tmp_path / "devices.csv", D_HEAD, devices if devices is not None else [
        ["S1", "10.0.1.21", "M-A3", "2026-11-16 08:20", "Ready", "", "4.12.3", "HTTPS", "v3", "no"],
        ["S2", "10.0.1.31", "D-1", "2026-11-16 08:25", "Ready", "", "2.4.0", "HTTPS", "v3", "no"]])
    write(tmp_path / "supplies.csv", ["Serial", "Supply", "Level", "Level30DaysAgo", "OnOrder"], supplies if supplies is not None else [
        ["S1", "Black toner", 70, 90, "no"], ["S2", "Black toner", 60, 70, "no"]])
    write(tmp_path / "counters.csv", ["Serial", "Month", "Mono", "Colour"], counters if counters is not None else
          [[s, m, v, c] for s, v, c in (("S1", 4000, 500), ("S2", 400, 0)) for m in ("2026-08", "2026-09", "2026-10")])
    write(tmp_path / "contracts.csv", ["Contract", "Vendor", "Type", "ClickMono", "ClickColour", "MonthlyFee", "ResponseHours", "End",
                                       "NoticeDays", "CreditPerBreach"], [["C1", "Vendor", "MPS", "0,008", "0,05", "40", "8", "2028-12-31",
                                                                           "60", "150"]])
    write(tmp_path / "tickets.csv", ["Ticket", "Printer", "Opened", "Category", "VendorCalled", "VendorArrived", "Resolved"],
          tickets or [])
    (tmp_path / "settings.json").write_text(json.dumps({"organisation": "Test", "review_date": NOW,
                                                         "approved_firmware": {"M-A3": "4.12.3", "D-1": "2.4.0"},
                                                         "approved_drivers": {"Uni": "7.4.0.0"}, **(settings or {})}))
    return tmp_path


def codes(rv) -> dict:
    out = {}
    for f in rv["findings"]:
        out.setdefault(f.code, f.severity)
    return out


def test_parsers():
    assert num("0,008") == pytest.approx(0.008) and num("0.055") == pytest.approx(0.055) and num("1.250") == 1250 and num("40") == 40
    assert kind("", "A3 colour MFP") == "mfp-a3" and kind("Label printer") == "label" and kind("desk") == "desk"
    assert version("Fw 4.12.3") == (4, 12, 3) and version("4.9.0") < version("4.12.3")
    assert queue_status("Offline") == "offline" and queue_status("Paper jam") == "error" and queue_status("Normal") == "normal"
    assert device_state("No response") == "offline" and device_state("Warning: toner low") == "warning"


def test_clean_fleet_is_green(tmp_path):
    d = load(fleet(tmp_path))
    rv = review(d)
    assert rv["findings"] == [], [f.code for f in rv["findings"]]
    sm = summary(d, rv)
    assert sm["status"] == "GREEN" and sm["down"] == 0
    # 40 EUR rental + 4,000 mono at 0.008 + 500 colour at 0.05 = 97 EUR; the owned desk printer 400 pages at 0.03 = 12 EUR
    assert rv["review"].cost["MFP1"] == pytest.approx(97) and rv["review"].cost["P01"] == pytest.approx(12)


def test_queue_points_to_old_address_and_repeat_tickets(tmp_path):
    dev = [["S1", "10.0.1.57", "M-A3", NOW, "Ready", "", "4.12.3", "HTTPS", "v3", "no"],
           ["S2", "10.0.1.31", "D-1", NOW, "Ready", "", "2.4.0", "HTTPS", "v3", "no"]]
    tk = [[f"T{i}", "MFP1", f"2026-11-{d:02d} 09:00", "Offline", "", "", ""] for i, d in enumerate((2, 6, 10), 1)]
    rv = review(load(fleet(tmp_path, devices=dev, tickets=tk)))
    c = codes(rv)
    assert c["PRN-QUEUE-IP"] == RED and c["SVC-REPEAT"] == "AMBER"
    rep = next(f for f in rv["findings"] if f.code == "SVC-REPEAT")
    assert "PRN-QUEUE-IP" in rep.detail


def test_down_stuck_and_paused(tmp_path):
    q = [["PRT1", "MFP1", "MFP1", "10.0.1.21", "Uni", "7.4.0.0", "Normal", 12, 75],
         ["PRT1", "P01", "P01", "10.0.1.31", "Uni", "7.4.0.0", "Paused", 0, 0]]
    dev = [["S1", "10.0.1.21", "M-A3", NOW, "Ready", "", "4.12.3", "HTTPS", "v3", "no"],
           ["S2", "10.0.1.31", "D-1", "2026-11-14 08:00", "Offline", "", "2.4.0", "HTTPS", "v3", "no"]]
    rv = review(load(fleet(tmp_path, queues=q, devices=dev)))
    c = codes(rv)
    assert c["PRN-QUEUE-STUCK"] == RED and c["PRN-DOWN"] == RED and c["PRN-PAUSED"] == "AMBER"
    assert summary(load(tmp_path), rv)["down"] == 1


def test_unregistered_duplicate_and_unknown(tmp_path):
    q = [["PRT1", "MFP1", "MFP1", "10.0.1.21", "Uni", "7.4.0.0", "Normal", 0, 0],
         ["PRT1", "P01", "P01", "10.0.1.31", "Uni", "7.4.0.0", "Normal", 0, 0],
         ["OLD1", "MFP1", "MFP1-OLD", "10.0.1.21", "Uni", "7.4.0.0", "Normal", 0, 0],
         ["PRT1", "PLOTTER", "PLOTTER", "10.0.1.60", "Plot", "1", "Normal", 0, 0]]
    dev = [["S1", "10.0.1.21", "M-A3", NOW, "Ready", "", "4.12.3", "HTTPS", "v3", "no"],
           ["S2", "10.0.1.31", "D-1", NOW, "Ready", "", "2.4.0", "HTTPS", "v3", "no"],
           ["X9", "10.0.1.240", "Inkjet", NOW, "Ready", "", "1", "HTTP", "v1", "yes"]]
    c = codes(review(load(fleet(tmp_path, queues=q, devices=dev))))
    assert {"PRN-DUP-QUEUE", "PRN-UNREGISTERED", "PRN-UNKNOWN-DEVICE"} <= set(c)
    assert "SEC-DEFAULT-ADMIN" not in c            # the unknown device is reported once, as unknown


def test_supplies_forecast(tmp_path):
    sup = [["S1", "Black toner", 3, 40, "no"], ["S1", "Cyan toner", 12, 60, "no"], ["S2", "Black toner", 4, 40, "yes"]]
    rv = review(load(fleet(tmp_path, supplies=sup)))
    c = codes(rv)
    assert c["SUP-EMPTY"] == RED and c["SUP-SOON"] == "AMBER"
    empty = next(f for f in rv["findings"] if f.code == "SUP-EMPTY")
    assert empty.items == ["MFP1"]                 # the one already on order is not a finding
    cyan = next(r for r in rv["review"].supply_rows if r["supply"] == "Cyan toner")
    assert cyan["days"] == pytest.approx(12 / (48 / 30)) and str(cyan["order_by"]) == "2026-11-20"


def test_usage_low_over_and_colour(tmp_path):
    ps = [["MFP1", "HQ", "Floor 1", "mfp-a3", "M-A3", "S1", "10.0.1.21", "Marketing", "C1", "2024-01-10", "", "no", "no", "active"],
          ["P01", "HQ", "Floor 1", "desk", "D-1", "S2", "10.0.1.31", "Marketing", "", "2017-05-01", "", "no", "no", "active"],
          ["P02", "HQ", "Floor 2", "desk", "D-1", "S3", "10.0.2.31", "Sales", "", "2023-05-01", "", "no", "no", "active"]]
    cnt = [[s, m, v, c] for s, v, c in (("S1", 1500, 1600), ("S2", 60, 0), ("S3", 2200, 0)) for m in ("2026-08", "2026-09", "2026-10")]
    rv = review(load(fleet(tmp_path, printers=ps, counters=cnt, queues=[], devices=[], supplies=[])))
    c = codes(rv)
    assert {"USE-UNDER", "USE-OVER", "USE-COLOUR", "LIFE-AGE"} <= set(c)
    cons = rv["review"].consolidation
    assert len(cons) == 1 and cons[0]["printer"].id == "P01" and cons[0]["target"].id == "MFP1"
    under = next(f for f in rv["findings"] if f.code == "USE-UNDER")
    assert "350 EUR of replacements" in under.detail


def test_security(tmp_path):
    ps = [["MFP1", "HQ", "Floor 1", "mfp-a3", "M-A3", "S1", "10.0.1.21", "HR", "C1", "2024-01-10", "", "no", "yes", "active"],
          ["P01", "HQ", "Floor 1", "desk", "D-1", "S2", "10.0.1.31", "HR", "", "2023-05-01", "", "no", "no", "active"]]
    dev = [["S1", "10.0.1.21", "M-A3", NOW, "Ready", "", "4.9.0", "HTTPS;Telnet;FTP", "v2c", "yes"],
           ["S2", "10.0.1.31", "D-1", NOW, "Ready", "", "2.4.0", "HTTPS", "v3", "no"]]
    q = [["PRT1", "MFP1", "MFP1", "10.0.1.21", "Uni", "7.1.2.0", "Normal", 0, 0], ["PRT1", "P01", "P01", "10.0.1.31", "Uni", "7.4.0.0",
                                                                                   "Normal", 0, 0]]
    rv = review(load(fleet(tmp_path, printers=ps, devices=dev, queues=q)))
    c = codes(rv)
    assert c["SEC-DEFAULT-ADMIN"] == RED and c["SEC-RELEASE"] == RED
    assert {"SEC-PROTOCOLS", "SEC-SNMP", "SEC-FIRMWARE", "SEC-DRIVER"} <= set(c)
    assert rv["decisions"][0].decision.startswith("Secure release")


def test_lease_notice(tmp_path):
    ps = [["MFP1", "HQ", "Floor 1", "mfp-a3", "M-A3", "S1", "10.0.1.21", "Finance", "C1", "2021-01-10", "2027-01-20", "yes", "no",
           "active"],
          ["P01", "HQ", "Floor 1", "desk", "D-1", "S2", "10.0.1.31", "Finance", "C1", "2023-05-01", "2027-02-28", "no", "no", "active"]]
    rv = review(load(fleet(tmp_path, printers=ps)))
    lease = {f.subject: f.severity for f in rv["findings"] if f.code == "LIFE-LEASE"}
    assert lease == {"MFP1": RED, "P01": "AMBER"}          # notice by 21 Nov (5 days) and by 30 Dec


def test_vendor_sla_and_credits(tmp_path):
    tk = [["T1", "MFP1", "2026-11-02 09:00", "Print quality", "2026-11-02 09:30", "2026-11-03 09:30", "2026-11-03 12:00"],
          ["T2", "MFP1", "2026-11-09 09:00", "Print quality", "2026-11-09 09:30", "2026-11-09 13:30", "2026-11-09 15:00"]]
    d = load(fleet(tmp_path, tickets=tk))
    rv = review(d)
    assert codes(rv)["SVC-VENDOR-SLA"] == "AMBER"
    assert [x["breach"] for x in rv["review"].sla_rows] == [True, False] and summary(d, rv)["credits"] == 150


def test_other_column_names_and_semicolons(tmp_path):
    (tmp_path / "printers.csv").write_text("Name;Office;Floor;Device type;Model name;Serial number;IP address;Team;Status\n"
                                           "MFP1;HQ;Floor 1;A3 MFP;M-A3;S1;10.0.1.21;Finance;active\n", encoding="utf-8")
    d = load(tmp_path)
    assert d.printers[0].kind == "mfp-a3" and d.printers[0].site == "HQ" and d.printers[0].ip == "10.0.1.21"


def test_missing_register(tmp_path):
    with pytest.raises(FileNotFoundError):
        load(tmp_path)
    assert main(["review", str(tmp_path)]) == 2


def test_demo_end_to_end(tmp_path):
    simulate.write(tmp_path / "data")
    sm = run(tmp_path / "data", tmp_path / "out")
    assert sm["status"] == RED and sm["printers"] == 37 and sm["down"] == 3 and sm["decisions"] == 5
    for name in OUTPUTS:
        assert (tmp_path / "out" / name).stat().st_size > 100, name
    pack = (tmp_path / "out" / "review-pack.md").read_text(encoding="utf-8")
    assert "Decisions needed" in pack and "ST-BGR-MFP" in pack
    findings = list(csv.DictReader(open(tmp_path / "out" / "findings.csv", encoding="utf-8")))
    rep = next(f for f in findings if f["code"] == "SVC-REPEAT" and f["subject"] == "ST-BGR-MFP")
    assert "PRN-QUEUE-IP" in rep["detail"]


def test_demo_is_deterministic(tmp_path):
    simulate.write(tmp_path / "a")
    simulate.write(tmp_path / "b")
    for f in (tmp_path / "a").iterdir():
        assert f.read_bytes() == (tmp_path / "b" / f.name).read_bytes(), f.name
