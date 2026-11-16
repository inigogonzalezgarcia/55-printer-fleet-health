# Data format

Put the files in one folder and run `python -m printfleet review <folder>`. `printers.csv` is required; every other file adds its checks when it is there. Column names are forgiving (the alternatives are in `printfleet/model.py`), the delimiter can be a comma or a semicolon, and amounts accept `0,008` and `0.008`.

## printers.csv (the register)

| Column | Meaning |
|---|---|
| Printer | Id used everywhere else (usually the queue name) |
| Site, Location | Office or store, and floor or area: consolidation looks for a multifunction in the same place |
| Type | `mfp-a3`, `mfp-a4`, `desk`, `label`, `receipt` (free text is mapped: "A3 MFP", "label printer"…). Label and receipt printers are printed to directly, so they need no queue |
| Model, Serial, IP | Serial joins the device data, consumables and counters |
| Department | For the cost by department |
| Contract | Id in `contracts.csv`; empty for an owned device |
| Installed, LeaseEnd | Dates |
| SecureRelease, Sensitive | `yes`/`no`: a sensitive area (HR, legal, finance, executives) needs secure release |
| Status | `active` (default) or `retired` |

## queues.csv (print servers)

`scripts/Export-PrintQueues.ps1` writes it: Server, Name, ShareName, PrinterHostAddress (the address the port prints to), DriverName, DriverVersion, PrinterStatus, JobCount, OldestJobMinutes. A queue is matched to the register by name, share name or address.

## devices.csv (managed print portal or SNMP scan)

Serial, IP (the address the device has now), Model, LastSeen, Status (`Ready`, `Warning`, `Error`, `Offline`), Message, Firmware, Protocols (enabled management protocols, separated by `;`: `HTTPS;HTTP;Telnet;FTP`), SNMP (`v3`, `v2c`, `v1`, `off`), DefaultAdminPassword (`yes`/`no`, from the portal's security report).

## supplies.csv, counters.csv, contracts.csv, tickets.csv

- `supplies.csv`: Serial, Supply, Level (%), Level30DaysAgo (%), OnOrder. The use of the last 30 days gives the days left.
- `counters.csv`: Serial, Month (`2026-10`), Mono, Colour pages. The last three months are averaged.
- `contracts.csv`: Contract, Vendor, Type, ClickMono, ClickColour (price per page), MonthlyFee (per device), ResponseHours (break-fix response in the contract), End, NoticeDays, CreditPerBreach.
- `tickets.csv`: Ticket, Printer, Opened, Category, VendorCalled, VendorArrived, Resolved (from the ITSM tool; vendor times only for calls logged with the vendor).

## settings.json

| Key | Default | Meaning |
|---|---|---|
| organisation, review_date | | Shown in the outputs; due dates count from the review date (RED +2 days, AMBER +14) |
| approved_firmware | {} | Model → minimum firmware (your internal standard) |
| approved_drivers | {} | Driver name → minimum version |
| recommended_volume | mfp-a3 12,000 · mfp-a4 5,000 · desk 1,500 · label 20,000 | Pages a month each type is built for; above it is overworked |
| low_volume | mfp-a3 1,500 · mfp-a4 600 · desk 150 | Below it is a consolidation candidate |
| owned_cost_per_page, replacement_cost | desk 0.03 · mfp 0.02; desk 350 · mfp-a4 1,800 · mfp-a3 6,000 | Running cost of an owned device; replacements avoided by consolidating |
| supply_days, order_lead_days | 10, 3 | Warning window for consumables and delivery time |
| stuck_minutes, offline_hours | 30, 24 | A queue whose oldest job is older is stuck; a device not seen for longer is offline |
| max_age_years, lease_warning_days | 7, 120 | Age to replace; how early to warn before a lease ends |
| colour_share_max | 35 | Colour pages as a share of all pages per device |
| repeat_tickets, repeat_window_days | 3, 30 | Tickets on one printer that make it a repeat |
| insecure_protocols | telnet, ftp, http, snmpv1, snmpv2c | Management protocols that send credentials in clear |
| owners | | Who owns each kind of action: SUPPORT, PRINT, SECURITY, VENDOR, DECISION |
