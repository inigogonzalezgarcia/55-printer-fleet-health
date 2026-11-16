"""Command line: `demo` writes the fictional Northwind Traders fleet to sample_data/ and builds the outputs; `review` runs on your own
files."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report, simulate
from .checks import review, summary
from .model import load

OUTPUTS = ("report.html", "review-pack.md", "printers.csv", "supplies-forecast.csv", "queues-review.csv", "usage-and-cost.csv",
           "consolidation.csv", "vendor-sla.csv", "findings.csv", "actions.csv")


def run(data: Path, out: Path, title: str | None = None) -> dict:
    d = load(data)
    rv = review(d)
    title = title or f"{d.settings.organisation} · printer fleet review"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, rv, title), encoding="utf-8")
    (out / "review-pack.md").write_text(report.pack_md(d, rv, title), encoding="utf-8")
    report.write_printers(d, rv, out / "printers.csv")
    report.write_supplies(rv, out / "supplies-forecast.csv")
    report.write_queues(d, rv, out / "queues-review.csv")
    report.write_usage(d, rv, out / "usage-and-cost.csv")
    report.write_consolidation(rv, out / "consolidation.csv")
    report.write_sla(rv, out / "vendor-sla.csv")
    report.write_findings(rv, out / "findings.csv")
    report.write_actions(rv, out / "actions.csv")
    return summary(d, rv)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="printfleet", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional fleet to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own files")
    rv.add_argument("data", type=Path, help="folder with printers.csv and the optional exports")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", help="title of the report and the pack")
    a = p.parse_args(argv)
    try:
        if a.cmd == "demo":
            simulate.write(a.data)
            sm = run(a.data, a.out)
        else:
            sm = run(a.data, a.out, a.title)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{sm['status']}: {sm['up']} of {sm['printers']} printers working, {sm['supplies']} consumables to order, "
          f"{sm['security']} printers with a security finding, {sm['red']} red and {sm['amber']} amber findings, "
          f"{sm['decisions']} decisions")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
