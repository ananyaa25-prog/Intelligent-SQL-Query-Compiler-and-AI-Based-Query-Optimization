
import re


def optimize_sql(sql: str) -> str:
    """
    Apply conservative optimization rules to simple SQL queries.

    Initial rule:
    Remove redundant numeric lower-bound conditions such as:
        gpa >= 9.0 AND gpa >= 8.0

    This initial implementation supports simple WHERE conditions
    joined by AND. It deliberately avoids rewriting other queries.
    """
    sql = sql.strip()

    pattern = re.compile(
        r"^\s*SELECT\s+.+?\s+FROM\s+"
        r"[A-Za-z_][A-Za-z0-9_]*\s+"
        r"WHERE\s+(.+?)\s*;?\s*$",
        re.IGNORECASE | re.DOTALL,
    )

    match = pattern.match(sql)

    if not match:
        return sql

    condition_text = match.group(1)

    # Only optimize simple conditions joined by AND.
    if re.search(r"\bOR\b|\bNOT\b", condition_text, re.IGNORECASE):
        return sql

    conditions = re.split(
        r"\s+AND\s+", condition_text, flags=re.IGNORECASE
    )

    numeric_lower_bounds = {}
    redundant_indexes = set()

    for index, condition in enumerate(conditions):
        item = re.fullmatch(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*>=\s*"
            r"(\d+(?:\.\d+)?)\s*",
            condition,
        )

        if not item:
            continue

        column = item.group(1).lower()
        value = float(item.group(2))

        if column not in numeric_lower_bounds:
            numeric_lower_bounds[column] = []

        numeric_lower_bounds[column].append((index, value))

    for bounds in numeric_lower_bounds.values():
        if len(bounds) < 2:
            continue

        strongest_value = max(value for _, value in bounds)

        for index, value in bounds:
            if value < strongest_value:
                redundant_indexes.add(index)

    if not redundant_indexes:
        return sql

    optimized_conditions = [
        condition
        for index, condition in enumerate(conditions)
        if index not in redundant_indexes
    ]

    optimized_where = " AND ".join(optimized_conditions)

    # Replace only the WHERE condition, preserving the rest of the query.
    where_start = match.start(1)
    where_end = match.end(1)

    return (
        sql[:where_start]
        + optimized_where
        + sql[where_end:]
    )


if __name__ == "__main__":
    original = (
        "SELECT student_id, name FROM students "
        "WHERE gpa >= 9.0 AND gpa >= 8.0;"
    )

    optimized = optimize_sql(original)

    print("Original SQL:")
    print(original)
    print("\nOptimized SQL:")
    print(optimized)
