"""Hand-written recursive descent + precedence climbing parser for SQL.

Formal Grammar (EBNF):
----------------------
Statement       = SelectStmt , [ ";" ] ;

SelectStmt      = "SELECT" , [ "DISTINCT" ] , SelectList ,
                  [ "FROM" , FromClause ] ,
                  [ "WHERE" , Expression ] ,
                  [ "GROUP" , "BY" , ExpressionList ] ,
                  [ "HAVING" , Expression ] ,
                  [ "ORDER" , "BY" , OrderByList ] ,
                  [ "LIMIT" , NumberLiteral , [ ( "OFFSET" | "," ) , NumberLiteral ] ] ;

SelectList      = SelectItem , { "," , SelectItem } ;
SelectItem      = ( "*" | Identifier "." "*" | Expression ) , [ [ "AS" ] , Identifier ] ;
FromClause      = TableRef , { JoinClause } ;
TableRef        = Identifier , [ [ "AS" ] , Identifier ] ;
JoinClause      = [ "INNER" | "LEFT" ] , "JOIN" , TableRef , "ON" , Expression ;

Expression      = OrExpr ;
OrExpr          = AndExpr , { "OR" , AndExpr } ;
AndExpr         = NotExpr , { "AND" , NotExpr } ;
NotExpr         = [ "NOT" ] , ComparisonExpr ;
ComparisonExpr  = ArithExpr , [ CompTail ] ;
CompTail        = ( "=" | "!=" | "<>" | "<" | "<=" | ">" | ">=" | "LIKE" ) , ArithExpr
                | [ "NOT" ] , "BETWEEN" , ArithExpr , "AND" , ArithExpr
                | [ "NOT" ] , "IN" , "(" , ExpressionList , ")"
                | "IS" , [ "NOT" ] , "NULL" ;
ArithExpr       = Term , { ( "+" | "-" ) , Term } ;
Term            = Factor , { ( "*" | "/" ) , Factor } ;
Factor          = [ "+" | "-" ] , Primary ;
Primary         = Literal | FunctionCall | ColumnRef | "(" , Expression , ")" ;
FunctionCall    = AggregateName , "(" , [ "DISTINCT" ] , ( "*" | Expression ) , ")" ;
AggregateName   = "COUNT" | "SUM" | "AVG" | "MIN" | "MAX" ;
ColumnRef       = [ Identifier , "." ] , Identifier ;
Literal         = NumberLiteral | StringLiteral | "NULL" | "TRUE" | "FALSE" ;

Note on Left Recursion Elimination:
-----------------------------------
Traditional left-recursive grammar rules (e.g. Expr -> Expr + Term) cause infinite
recursion in top-down parsers. This implementation eliminates left recursion by:
1. Converting left-recursive rules into iterative loops: `Term { ("+" | "-") Term }*`.
2. Using precedence climbing across binary operator tiers (OR -> AND -> comparisons -> additive -> multiplicative).
"""

from __future__ import annotations

from typing import Optional

from sqlcompiler.frontend.lexer import Token, tokenize, format_caret_snippet
from sqlcompiler.frontend.ast_nodes import (
    SelectStmt, SelectItem, TableRef, Join, OrderByItem,
    Expression, Star, ColumnRef, Literal, BinaryOp, UnaryOp,
    Between, InList, IsNull, FunctionCall
)


class ParseError(SyntaxError):
    """Structured parser error with line, column, expected, found, and snippet."""

    def __init__(
        self,
        message: str,
        line: int = 1,
        column: int = 1,
        snippet: str = "",
        expected: str = "",
        found: str = "",
        suggestion: str = "",
    ):
        self.message = message
        self.line = line
        self.column = column
        self.expected = expected
        self.found = found
        self.suggestion = suggestion
        self.snippet = snippet

        detail = f"Syntax error at line {line}, column {column}: {message}"
        if snippet:
            detail += f"\n{snippet}"
        if suggestion:
            detail += f"\nSuggestion: {suggestion}"
        super().__init__(detail)


CLAUSE_KEYWORDS = {
    "FROM", "WHERE", "GROUP", "HAVING", "ORDER", "LIMIT", "OFFSET",
    "JOIN", "INNER", "LEFT", "RIGHT", "UNION", ";"
}

AGGREGATE_FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}


class Parser:
    """Recursive descent parser with precedence climbing for SQL SELECT statements."""

    def __init__(self, tokens: list[Token], raw_sql: str = ""):
        self.tokens = tokens
        self.pos = 0
        self.raw_sql = raw_sql

    def current(self) -> Optional[Token]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def peek(self, offset: int = 1) -> Optional[Token]:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return None

    def advance(self) -> Optional[Token]:
        tok = self.current()
        if tok is not None:
            self.pos += 1
        return tok

    def _line_col(self) -> tuple[int, int]:
        tok = self.current()
        if tok is not None:
            return tok.line, tok.column
        if self.tokens:
            last = self.tokens[-1]
            return last.line, last.column + len(last.value)
        return 1, 1

    def _error(self, message: str, expected: str = "", found: str = "", suggestion: str = "") -> ParseError:
        line, col = self._line_col()
        snippet = format_caret_snippet(self.raw_sql, line, col) if self.raw_sql else ""
        if not found:
            tok = self.current()
            found = tok.value if tok else "end of input"
        return ParseError(
            message=message,
            line=line,
            column=col,
            snippet=snippet,
            expected=expected,
            found=found,
            suggestion=suggestion,
        )

    def accept_keyword(self, kw: str) -> bool:
        tok = self.current()
        if tok and tok.value.upper() == kw.upper():
            self.advance()
            return True
        return False

    def accept_punct(self, p: str) -> bool:
        tok = self.current()
        if tok and tok.value == p:
            self.advance()
            return True
        return False

    def accept_op(self, op: str) -> bool:
        tok = self.current()
        if tok and tok.value.upper() == op.upper():
            self.advance()
            return True
        return False

    def expect_keyword(self, kw: str, suggestion: str = "") -> Token:
        tok = self.current()
        if not tok or tok.value.upper() != kw.upper():
            found = tok.value if tok else "end of input"
            raise self._error(
                f"Expected keyword '{kw}', found {found!r}",
                expected=kw,
                found=found,
                suggestion=suggestion,
            )
        return self.advance()  # type: ignore

    def expect_punct(self, p: str, suggestion: str = "") -> Token:
        tok = self.current()
        if not tok or tok.value != p:
            found = tok.value if tok else "end of input"
            raise self._error(
                f"Expected '{p}', found {found!r}",
                expected=p,
                found=found,
                suggestion=suggestion,
            )
        return self.advance()  # type: ignore

    def parse(self) -> SelectStmt:
        """Parse complete SELECT statement with statement-level error handling."""
        if not self.tokens:
            raise ParseError("Cannot parse empty query", 1, 1)

        self.expect_keyword("SELECT", suggestion="Query must begin with SELECT")
        distinct = self.accept_keyword("DISTINCT")

        columns = self.parse_select_list()

        from_table = None
        joins: list[Join] = []
        if self.accept_keyword("FROM"):
            from_table = self.parse_table_ref()
            joins = self.parse_joins()

        where = None
        if self.accept_keyword("WHERE"):
            if not self.current() or self.current().value.upper() in CLAUSE_KEYWORDS:
                raise self._error("WHERE requires a condition", expected="expression", suggestion="Add a predicate after WHERE, e.g. WHERE gpa >= 8.0")
            where = self.parse_expression()

        group_by: list[Expression] = []
        if self.accept_keyword("GROUP"):
            self.expect_keyword("BY", suggestion="GROUP must be followed by BY")
            group_by = self.parse_expression_list()

        having = None
        if self.accept_keyword("HAVING"):
            if not self.current() or self.current().value.upper() in CLAUSE_KEYWORDS:
                raise self._error("HAVING requires a condition", expected="expression", suggestion="Add an aggregate condition after HAVING")
            having = self.parse_expression()

        order_by: list[OrderByItem] = []
        if self.accept_keyword("ORDER"):
            self.expect_keyword("BY", suggestion="ORDER must be followed by BY")
            order_by = self.parse_order_by_list()

        limit = None
        offset = None
        if self.accept_keyword("LIMIT"):
            limit_tok = self.current()
            if not limit_tok or limit_tok.type != "NUMBER":
                raise self._error("LIMIT requires a non-negative integer", expected="integer", suggestion="Provide a positive integer after LIMIT")
            if "." in limit_tok.value:
                raise self._error("LIMIT must be an integer", expected="integer", suggestion="Remove decimal point from LIMIT")
            val = int(limit_tok.value)
            if val < 0:
                raise self._error("LIMIT must be non-negative", expected="non-negative integer")
            limit = val
            self.advance()

            if self.accept_keyword("OFFSET"):
                off_tok = self.current()
                if not off_tok or off_tok.type != "NUMBER" or "." in off_tok.value:
                    raise self._error("OFFSET requires an integer", expected="integer")
                offset = int(off_tok.value)
                self.advance()
            elif self.accept_punct(","):
                # MySQL-style LIMIT offset, count
                off_tok = self.current()
                if not off_tok or off_tok.type != "NUMBER" or "." in off_tok.value:
                    raise self._error("OFFSET requires an integer", expected="integer")
                offset = limit
                limit = int(off_tok.value)
                self.advance()

        self.accept_punct(";")

        if self.current() is not None:
            tok = self.current()
            raise self._error(
                f"Unexpected token {tok.value!r} after end of query",
                found=tok.value,
                suggestion="Check for extra trailing clauses or misplaced semicolons",
            )

        return SelectStmt(
            distinct=distinct,
            columns=columns,
            from_table=from_table,
            joins=joins,
            where=where,
            group_by=group_by,
            having=having,
            order_by=order_by,
            limit=limit,
            offset=offset,
        )

    def parse_select_list(self) -> list[SelectItem]:
        items = []
        while True:
            tok = self.current()
            if not tok:
                raise self._error("Expected column or expression in SELECT list", expected="expression")

            if tok.value == "*":
                star_tok = tok
                self.advance()
                items.append(SelectItem(Star(line=star_tok.line, column=star_tok.column), line=star_tok.line, column=star_tok.column))
            elif tok.type == "IDENTIFIER" and self.peek() and self.peek().value == "." and self.peek(2) and self.peek(2).value == "*":
                star_tok = tok
                tbl = tok.value
                self.advance()  # ident
                self.advance()  # .
                self.advance()  # *
                items.append(SelectItem(Star(table=tbl, line=star_tok.line, column=star_tok.column), line=star_tok.line, column=star_tok.column))
            else:
                expr = self.parse_expression()
                alias = None
                if self.accept_keyword("AS"):
                    alias = self.expect_identifier("Expected alias name after AS")
                elif self.current() and self.current().type == "IDENTIFIER" and self.current().value.upper() not in CLAUSE_KEYWORDS:
                    alias = self.advance().value
                items.append(SelectItem(expr=expr, alias=alias, line=expr.line, column=expr.column))

            if not self.accept_punct(","):
                break
        return items

    def expect_identifier(self, error_msg: str = "Expected identifier") -> str:
        tok = self.current()
        if not tok or tok.type not in ("IDENTIFIER", "KEYWORD"):
            raise self._error(error_msg, expected="identifier")
        self.advance()
        return tok.value

    def parse_table_ref(self) -> TableRef:
        tbl_tok = self.current()
        if not tbl_tok or tbl_tok.type not in ("IDENTIFIER", "KEYWORD"):
            raise self._error("Expected a table name after FROM", expected="table name", suggestion="Specify a valid table name, e.g. 'students'")
        name = tbl_tok.value
        line = tbl_tok.line
        col = tbl_tok.column
        self.advance()

        alias = None
        if self.accept_keyword("AS"):
            alias = self.expect_identifier("Expected alias after AS")
        elif (
            self.current()
            and self.current().type == "IDENTIFIER"
            and self.current().value.upper() not in CLAUSE_KEYWORDS
        ):
            alias = self.advance().value

        return TableRef(name=name, alias=alias, line=line, column=col)

    def parse_joins(self) -> list[Join]:
        joins = []
        while True:
            join_type = "INNER"
            if self.accept_keyword("LEFT"):
                join_tok = self.tokens[self.pos - 1]
                join_type = "LEFT"
                self.expect_keyword("JOIN", suggestion="LEFT must be followed by JOIN")
            elif self.accept_keyword("INNER"):
                join_tok = self.tokens[self.pos - 1]
                join_type = "INNER"
                self.expect_keyword("JOIN", suggestion="INNER must be followed by JOIN")
            elif self.accept_keyword("JOIN"):
                join_tok = self.tokens[self.pos - 1]
                join_type = "INNER"
            else:
                break

            tbl = self.parse_table_ref()
            self.expect_keyword("ON", suggestion="JOIN clause requires an ON condition")
            on_expr = self.parse_expression()
            joins.append(Join(join_type=join_type, table=tbl, on=on_expr, line=join_tok.line, column=join_tok.column))
        return joins

    def parse_expression_list(self) -> list[Expression]:
        exprs = []
        while True:
            exprs.append(self.parse_expression())
            if not self.accept_punct(","):
                break
        return exprs

    def parse_order_by_list(self) -> list[OrderByItem]:
        items = []
        while True:
            expr = self.parse_expression()
            direction = "ASC"
            if self.accept_keyword("DESC"):
                direction = "DESC"
            elif self.accept_keyword("ASC"):
                direction = "ASC"
            items.append(OrderByItem(expr=expr, direction=direction))
            if not self.accept_punct(","):
                break
        return items

    # --- Precedence Climbing Expression Parsing ---

    def parse_expression(self) -> Expression:
        return self.parse_or()

    def parse_or(self) -> Expression:
        left = self.parse_and()
        while self.accept_keyword("OR"):
            op_tok = self.tokens[self.pos - 1]
            right = self.parse_and()
            left = BinaryOp(op="OR", left=left, right=right, line=op_tok.line, column=op_tok.column)
        return left

    def parse_and(self) -> Expression:
        left = self.parse_not()
        while self.accept_keyword("AND"):
            op_tok = self.tokens[self.pos - 1]
            right = self.parse_not()
            left = BinaryOp(op="AND", left=left, right=right, line=op_tok.line, column=op_tok.column)
        return left

    def parse_not(self) -> Expression:
        if self.accept_keyword("NOT"):
            op_tok = self.tokens[self.pos - 1]
            operand = self.parse_not()
            return UnaryOp(op="NOT", operand=operand, line=op_tok.line, column=op_tok.column)
        return self.parse_comparison()

    def parse_comparison(self) -> Expression:
        left = self.parse_arith()

        # Check for IS [NOT] NULL
        if self.accept_keyword("IS"):
            op_tok = self.tokens[self.pos - 1]
            not_null = self.accept_keyword("NOT")
            self.expect_keyword("NULL", suggestion="Expected 'NULL' after 'IS' or 'IS NOT'")
            return IsNull(expr=left, not_null=not_null, line=op_tok.line, column=op_tok.column)

        # Check for [NOT] BETWEEN
        is_not = self.accept_keyword("NOT")
        if self.accept_keyword("BETWEEN"):
            op_tok = self.tokens[self.pos - 1]
            low = self.parse_arith()
            self.expect_keyword("AND", suggestion="BETWEEN requires 'AND' between range values")
            high = self.parse_arith()
            return Between(expr=left, low=low, high=high, not_between=is_not, line=op_tok.line, column=op_tok.column)
        elif is_not:
            op_tok = self.tokens[self.pos - 1]
            # We consumed NOT, now check if IN or LIKE follows
            if self.accept_keyword("IN"):
                self.expect_punct("(", suggestion="Expected '(' after IN")
                vals = self.parse_expression_list()
                self.expect_punct(")", suggestion="Expected ')' after IN values list")
                return InList(expr=left, values=vals, not_in=True, line=op_tok.line, column=op_tok.column)
            elif self.accept_keyword("LIKE"):
                right = self.parse_arith()
                return UnaryOp(op="NOT", operand=BinaryOp(op="LIKE", left=left, right=right, line=op_tok.line, column=op_tok.column), line=op_tok.line, column=op_tok.column)
            else:
                raise self._error("Unexpected NOT in comparison", expected="BETWEEN, IN, or LIKE")

        # Check for regular IN
        if self.accept_keyword("IN"):
            op_tok = self.tokens[self.pos - 1]
            self.expect_punct("(", suggestion="Expected '(' after IN")
            vals = self.parse_expression_list()
            self.expect_punct(")", suggestion="Expected ')' after IN values list")
            return InList(expr=left, values=vals, not_in=False, line=op_tok.line, column=op_tok.column)

        # Check for binary comparison operators
        tok = self.current()
        if tok and tok.value in ("<=", ">=", "<>", "!=", "=", "<", ">", "LIKE"):
            op = tok.value
            op_tok = tok
            self.advance()
            right = self.parse_arith()
            return BinaryOp(op=op, left=left, right=right, line=op_tok.line, column=op_tok.column)

        return left

    def parse_arith(self) -> Expression:
        left = self.parse_term()
        while True:
            tok = self.current()
            if tok and tok.value in ("+", "-"):
                op = tok.value
                op_tok = tok
                self.advance()
                right = self.parse_term()
                left = BinaryOp(op=op, left=left, right=right, line=op_tok.line, column=op_tok.column)
            else:
                break
        return left

    def parse_term(self) -> Expression:
        left = self.parse_factor()
        while True:
            tok = self.current()
            if tok and tok.value in ("*", "/"):
                op = tok.value
                op_tok = tok
                self.advance()
                right = self.parse_factor()
                left = BinaryOp(op=op, left=left, right=right, line=op_tok.line, column=op_tok.column)
            else:
                break
        return left

    def parse_factor(self) -> Expression:
        tok = self.current()
        if tok and tok.value in ("+", "-"):
            op = tok.value
            op_tok = tok
            self.advance()
            operand = self.parse_factor()
            return UnaryOp(op=op, operand=operand, line=op_tok.line, column=op_tok.column)
        return self.parse_primary()

    def parse_primary(self) -> Expression:
        tok = self.current()
        if not tok:
            raise self._error("Unexpected end of input, expected expression")

        # Parenthesized expression
        if self.accept_punct("("):
            expr = self.parse_expression()
            self.expect_punct(")", suggestion="Missing closing parenthesis")
            return expr

        # Literals
        if tok.type == "NUMBER":
            num_tok = tok
            self.advance()
            val = float(num_tok.value) if "." in num_tok.value else int(num_tok.value)
            return Literal(value=val, raw=num_tok.value, is_string=False, line=num_tok.line, column=num_tok.column)

        if tok.type == "STRING":
            str_tok = tok
            self.advance()
            # Unquote string literal
            raw = str_tok.value
            content = raw[1:-1].replace("''", "'") if raw.startswith("'") else raw[1:-1].replace('\\"', '"')
            return Literal(value=content, raw=raw, is_string=True, line=str_tok.line, column=str_tok.column)

        if tok.value.upper() == "NULL":
            null_tok = tok
            self.advance()
            return Literal(value=None, raw="NULL", is_string=False, line=null_tok.line, column=null_tok.column)

        if tok.value.upper() == "TRUE":
            bool_tok = tok
            self.advance()
            return Literal(value=True, raw="TRUE", is_string=False, line=bool_tok.line, column=bool_tok.column)

        if tok.value.upper() == "FALSE":
            bool_tok = tok
            self.advance()
            return Literal(value=False, raw="FALSE", is_string=False, line=bool_tok.line, column=bool_tok.column)

        # Aggregate functions
        if tok.value.upper() in AGGREGATE_FUNCTIONS:
            func_name = tok.value.upper()
            func_tok = tok
            if self.peek() and self.peek().value == "(":
                self.advance()  # func_name
                self.advance()  # (
                distinct = self.accept_keyword("DISTINCT")
                if self.current() and self.current().value == "*":
                    star_tok = self.current()
                    self.advance()
                    args: list[Expression] = [Star(line=star_tok.line, column=star_tok.column)]
                else:
                    args = self.parse_expression_list()
                self.expect_punct(")", suggestion=f"Expected ')' closing {func_name}(...)")
                return FunctionCall(name=func_name, args=args, distinct=distinct, line=func_tok.line, column=func_tok.column)

        # Identifier or Qualified column
        if tok.type in ("IDENTIFIER", "KEYWORD"):
            name = tok.value
            id_tok = tok
            self.advance()
            if self.accept_punct("."):
                # Qualified column: tbl.col
                col_tok = self.current()
                if not col_tok or col_tok.type not in ("IDENTIFIER", "KEYWORD"):
                    raise self._error(f"Expected column name after '{name}.'", expected="column name")
                col_name = col_tok.value
                self.advance()
                return ColumnRef(name=col_name, table=name, line=col_tok.line, column=col_tok.column)
            return ColumnRef(name=name, line=id_tok.line, column=id_tok.column)

        raise self._error(f"Unexpected token {tok.value!r} in expression", expected="expression")


def parse_sql(sql: str) -> SelectStmt:
    """Tokenize and parse a SQL string using the hand-written compiler front end."""
    tokens = tokenize(sql)
    return Parser(tokens, raw_sql=sql).parse()
