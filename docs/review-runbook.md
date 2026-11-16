# Monthly printer review

## The cycle

| When | What | Who |
|---|---|---|
| First working day | Export the queues (`Export-PrintQueues.ps1`), the device, consumables and counter reports from the print portal, the tickets and last month's register changes | Print services team |
| Same day | `python -m printfleet review data/`; send report.html to the site leads | Print services team |
| Same day | Reds: printers down, stuck queues, queues on the wrong address, empty consumables, default passwords | Service desk, IT security |
| Within a week | The review meeting with review-pack.md: decisions, leases, vendor service | Site leads, vendor manager |
| After | Actions in the ITSM tool with owner and date; vendor credits claimed | Owners |

## Reading the result

1. **Is everything printing?** Printers down, stuck queues and queues pointing to the wrong address are today's work. A queue on an old address is the usual reason behind repeated "printer offline" tickets: give the printer a reservation or a fixed address and fix the port, instead of restarting the queue every week.
2. **Will it keep printing?** Consumables that run out before the next delivery, then repeat tickets (open a problem record) and late vendor calls.
3. **Is it safe?** Default admin passwords first (anyone on the network can read the address book and redirect scans), secure release where documents are confidential, then protocols, SNMP, firmware and drivers in a planned window.
4. **Is it the right fleet?** Low-use printers next to a multifunction, overworked devices, colour share, age and leases: these become decisions, not tickets.

## Changes without surprises

- **Queue ports:** change the port address in print management; the clients keep their mapping. Then reserve the address in DHCP.
- **Removing a printer:** warn the team two weeks before, point its queue at the multifunction for a month, then delete it.
- **Firmware and drivers:** one device or one client of each model first, then the rest; keep the previous driver package for rollback.
- **Old print server:** move users by group policy or print management, watch that no jobs reach the old server for a week, then switch it off.
- **Secure release:** test the badge or PIN flow with two users of the area before turning it on for everyone.

## Evidence

findings.csv and actions.csv with their dates, the decisions in review-pack.md and vendor-sla.csv are the record of the month; keep them with the review minutes.
