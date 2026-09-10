"""Test infrastructure only: tighten one explicitly synthetic browser game's deadline."""

import sys

from server.persistence import engine_for, one, run, uid


def main():
    wid, game = sys.argv[1:3]
    url = (
        "postgresql+psycopg://dfs_runtime@127.0.0.1:55436/dfs_release"
        if "--release-drill" in sys.argv
        else "postgresql+psycopg://dfs_runtime@127.0.0.1:55432/dfs_increment2"
    )
    engine = engine_for(url)
    with engine.begin() as db:
        w = one(
            db,
            "SELECT w.* FROM workspace w JOIN contest c ON c.id=w.contest_id "
            "WHERE w.id=:id AND c.yahoo_id LIKE 'late-browser-%' FOR UPDATE OF c",
            id=wid,
        )
        if not w:
            raise ValueError("Only a labeled synthetic browser workspace is allowed")
        old = one(
            db,
            "SELECT d.* FROM lock_head h JOIN lock_decision d ON d.id=h.decision_id "
            "JOIN game g ON g.id=h.game_id WHERE h.contest_id=:cid AND g.id=:gid "
            "AND g.event_key LIKE 'synthetic-%'",
            cid=w["contest_id"],
            gid=game,
        )
        if not old:
            raise ValueError("Only a synthetic game is allowed")
        lid = uid()
        run(
            db,
            "INSERT INTO lock_decision(id,contest_id,game_id,schedule_id,previous_id,deadline) "
            "VALUES (:id,:cid,:gid,:sid,:old,clock_timestamp()-interval '1 second')",
            id=lid,
            cid=w["contest_id"],
            gid=game,
            sid=old["schedule_id"],
            old=old["id"],
        )
        run(
            db,
            "UPDATE lock_head SET decision_id=:id WHERE contest_id=:cid AND game_id=:gid",
            id=lid,
            cid=w["contest_id"],
            gid=game,
        )
    print("Synthetic game deadline tightened; no application clock override")


if __name__ == "__main__":
    main()
