"""Reset the demo in one command:  python seed.py

Creates 3 offices, 60 callers, 7 managers, 1 head and ~2,000 call records (metadata only).
The 20 real recordings are NOT seeded: upload them from the app (or "Load sample batch")."""
import csv
import random

from db import ROOT, init_db
from rules import RULES
from scoring import check_r1, recompute_score

OFFICES = ["Jogeshwari", "Lower Parel", "Bangalore"]
MANAGERS = [("Anand Kulkarni", "Jogeshwari"), ("Seema Joshi", "Jogeshwari"), ("Prakash Iyer", "Jogeshwari"),
            ("Meera Nair", "Lower Parel"), ("Rajesh Shetty", "Lower Parel"),
            ("Kiran Gowda", "Bangalore"), ("Lakshmi Rao", "Bangalore")]
FIRST = ["Amit", "Sunita", "Rahul", "Divya", "Manoj", "Pooja", "Naveen", "Shilpa", "Yogesh", "Asha", "Tushar",
         "Rekha", "Girish", "Nisha", "Santosh", "Vidya", "Harsh", "Smita", "Dinesh", "Anjali", "Mohan", "Usha"]
LAST = ["Patil", "Naik", "Kamat", "Shetty", "Gowda", "Reddy", "More", "Jadhav", "Sawant", "Pawar", "Hegde",
        "Menon", "Desai", "Bhat", "Kale", "Rane", "Salvi", "Pai"]
LANGS = ["Hindi", "English", "Marathi", "Kannada", "Hindi-English"]
N_CALLERS, N_CALLS = 60, 2000


def main(seed=42):
    rnd = random.Random(seed)
    c = init_db(reset=True)
    ids = {}
    for name in OFFICES:
        ids[name] = c.execute("INSERT INTO office (name) VALUES (?)", (name,)).lastrowid
    c.executemany("INSERT INTO rule (code, name, severity) VALUES (?,?,?)", [(k, v[0], v[1]) for k, v in RULES.items()])
    c.execute("INSERT INTO user (name, role) VALUES ('Head of Collections', 'head')")

    managers = {o: [] for o in OFFICES}
    for name, office in MANAGERS:
        managers[office].append(c.execute("INSERT INTO user (name, role, office_id) VALUES (?, 'manager', ?)",
                                          (name, ids[office])).lastrowid)

    # Callers named in the sample metadata keep their office, so the 20 uploads match the seed.
    fixed = {}
    with open(ROOT / "data" / "metadata.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fixed.setdefault(row["caller"], row["office"])
    callers, used = [], set(fixed)
    pairs = list(fixed.items())
    while len(pairs) < N_CALLERS:
        name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        if name not in used:
            used.add(name)
            pairs.append((name, OFFICES[len(pairs) % 3]))
    for i, (name, office) in enumerate(pairs):
        mgr = managers[office][i % len(managers[office])]
        callers.append(c.execute("INSERT INTO user (name, role, office_id, manager_id) VALUES (?, 'caller', ?, ?)",
                                 (name, ids[office], mgr)).lastrowid)

    # Metadata-only call records. R1 is a metadata check, so those flags are real; everything
    # else needs audio, so these calls stay "metadata_only" until a recording is uploaded.
    for n in range(1, N_CALLS + 1):
        day = rnd.randint(1, 28)
        hour = rnd.choices(range(6, 22), weights=[1, 1] + [9] * 11 + [2, 1, 1])[0]
        start = f"2026-09-{day:02d} {hour:02d}:{rnd.randint(0, 59):02d}:00"
        call_id = f"S{n:04d}"
        c.execute("""INSERT INTO call (id, caller_id, account, start_time, duration, language, status)
                     VALUES (?,?,?,?,?,?,'metadata_only')""",
                  (call_id, rnd.choice(callers), f"ACC-{rnd.randint(100000, 999999)}", start,
                   rnd.randint(40, 600), rnd.choice(LANGS)))
        r1 = check_r1(start)
        if r1:
            c.execute("INSERT INTO violation (call_id, rule_code, start, quote, reason, severity) VALUES (?,?,?,?,?,?)",
                      (call_id, "R1", 0, r1["quote"], r1["reason"], r1["severity"]))
        recompute_score(c, call_id)
    c.commit()
    n_users = c.execute("SELECT role, COUNT(*) n FROM user GROUP BY role").fetchall()
    print("Seeded:", {r["role"]: r["n"] for r in n_users}, "offices:", len(OFFICES), "calls:", N_CALLS)


if __name__ == "__main__":
    main()
