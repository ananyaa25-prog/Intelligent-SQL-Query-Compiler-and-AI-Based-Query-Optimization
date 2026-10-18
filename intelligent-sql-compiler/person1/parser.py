
from dataclasses import dataclass, field
from typing import Optional

from lexer import Token, tokenize


@dataclass
class SelectAST:
    columns: list[str]
    table: str
    where: Optional[str] = None
    order_by: Optional[str] = None
    limit: Optional[int] = None


class Parser:
    """Parser for a basic SELECT SQL grammar."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def current(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def accept(self, value: str) -> bool:
        token = self.current()
        if token and token.value.upper() == value.upper():
            self.pos += 1
            return True
        return False

    def expect(self, value: str):
        if not self.accept(value):
            token = self.current()
            found = token.value if token else "end of input"
            raise SyntaxError(
                f"Expected {value!r}, but found {found!r}"
            )

    def parse(self) -> SelectAST:
        self.expect("SELECT")

        columns = []
        while True:
            token = self.current()
            if token is None:
                raise SyntaxError("Expected a column name")

            if token.value == "*":
                columns.append(token.value)
                self.pos += 1
            elif token.type in {"IDENTIFIER", "KEYWORD"}:
                columns.append(token.value)
                self.pos += 1
            else:
                raise SyntaxError(
                    f"Expected a column name, found {token.value!r}"
                )

            if not self.accept(","):
                break

        self.expect("FROM")

        table_token = self.current()
        if not table_token or table_token.type != "IDENTIFIER":
            raise SyntaxError("Expected a table name after FROM")

        table = table_token.value
        self.pos += 1

        where = None
        order_by = None
        limit = None

        if self.accept("WHERE"):
            parts = []
            while self.current() and self.current().value.upper() not in {
                "ORDER", "LIMIT", ";"
            }:
                parts.append(self.current().value)
                self.pos += 1

            if not parts:
                raise SyntaxError("WHERE requires a condition")

            where = " ".join(parts)

        if self.accept("ORDER"):
            self.expect("BY")
            parts = []

            while self.current() and self.current().value.upper() not in {
                "LIMIT", ";"
            }:
                parts.append(self.current().value)
                self.pos += 1

            if not parts:
                raise SyntaxError("ORDER BY requires a column")

            order_by = " ".join(parts)

        if self.accept("LIMIT"):
            token = self.current()
            if not token or token.type != "NUMBER":
                raise SyntaxError("LIMIT requires a non-negative integer")

            if "." in token.value:
                raise SyntaxError("LIMIT must be an integer")

            limit = int(token.value)
            self.pos += 1

        self.accept(";")

        if self.current():
            raise SyntaxError(
                f"Unexpected token {self.current().value!r}"
            )

        return SelectAST(
            columns=columns,
            table=table,
            where=where,
            order_by=order_by,
            limit=limit,
        )


def parse_sql(sql: str) -> SelectAST:
    tokens = tokenize(sql)
    return Parser(tokens).parse()


if __name__ == "__main__":
    sql = "SELECT name FROM students WHERE gpa >= 9.0;"
    ast = parse_sql(sql)
    print(ast)
