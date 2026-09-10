"""Small operational checks. Administration is deliberately outside HTTP commands."""

from sqlalchemy.engine import Connection

from server.persistence import one


def check(db: Connection, *, production: bool = False) -> dict:
    state = one(db, "SELECT * FROM operational_state")
    if not state or state["schema_version"] != "0005_increment6":
        raise ValueError("Migration compatibility check failed")
    if production:
        role = one(
            db,
            "SELECT current_user AS name, rolsuper, rolcreatedb, rolcreaterole "
            "FROM pg_roles WHERE rolname=current_user",
        )
        unsafe = one(
            db,
            "SELECT has_schema_privilege(current_user,'public','CREATE') AS ddl, "
            "has_table_privilege(current_user,'draft_revision','UPDATE') AS rewrite, "
            "has_table_privilege(current_user,'operational_state','UPDATE') AS admin",
        )
        if (
            role["name"] != "dfs_runtime"
            or any(role[k] for k in ("rolsuper", "rolcreatedb", "rolcreaterole"))
            or any(unsafe.values())
        ):
            raise ValueError("Runtime database grants are unsafe")
    return state
