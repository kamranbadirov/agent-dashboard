URGENCY = ["your_move", "setting_up", "working", "reviewing", "in_review", "done", "ended"]


def rank(session):
    status = session["status"]
    return URGENCY.index(status) if status in URGENCY else len(URGENCY)


def newest_first(sessions):
    return sorted(sessions, key=lambda s: s.get("lastActivity") or "", reverse=True)


def lead_of(sessions):
    live = [s for s in sessions if s.get("alive")]
    pool = live or sessions
    return min(newest_first(pool), key=rank)


def merged_prs(sessions):
    out = {}
    for s in sessions:
        for p in s["prs"]:
            out.setdefault(p["key"], p)
    return list(out.values())


def ticket_title(ticket, sessions, prs):
    titled = [p for p in prs if ticket.lower() in (p.get("title") or "").lower()]
    if titled:
        return max(titled, key=lambda p: p.get("updatedAt") or "")["title"]
    return newest_first(sessions)[0]["title"]


def ticket_item(ticket, sessions):
    ordered = newest_first(sessions)
    urgent = min(ordered, key=rank)
    prs = merged_prs(ordered)
    tickets = list(dict.fromkeys([ticket] + [t for s in ordered for t in s["tickets"]]))
    return {
        **urgent,
        "sessionId": f"ticket:{ticket}",
        "title": ticket_title(ticket, ordered, prs),
        "tickets": tickets,
        "prs": prs,
        "alive": any(s.get("alive") for s in ordered),
        "lastActivity": ordered[0].get("lastActivity"),
        "group": ordered,
        "lead": lead_of(ordered),
        "job": None,
        "proc": None,
    }


def group(sessions):
    by_ticket = {}
    order = []
    for s in sessions:
        ticket = s["tickets"][0] if s.get("tickets") else None
        if not ticket:
            order.append(("session", s))
            continue
        if ticket not in by_ticket:
            by_ticket[ticket] = []
            order.append(("ticket", ticket))
        by_ticket[ticket].append(s)
    out = []
    for kind, value in order:
        if kind == "session":
            out.append(value)
        elif len(by_ticket[value]) == 1:
            out.append(by_ticket[value][0])
        else:
            out.append(ticket_item(value, by_ticket[value]))
    return out
