# SQL Compiler Grammar Specification (EBNF)

This document formalizes the grammar for the hand-written SQL compiler front end (Lexer and Parser).

---

## 1. Lexical Grammar

```ebnf
letter          = "A" .. "Z" | "a" .. "z" | "_" ;
digit           = "0" .. "9" ;
identifier      = letter , { letter | digit | "$" } ;

digit_seq       = digit , { digit } ;
number          = digit_seq , [ "." , digit_seq ] ;

string_literal  = "'" , { "''" | [^'] } , "'" 
                | '"' , { '\"' | [^"] } , '"' ;

whitespace      = " " | "\t" | "\r" | "\n" ;
comment         = "--" , { [^\n] } , ( "\n" | EOF )
                | "/*" , { any_char } , "*/" ;

keyword         = "SELECT" | "FROM" | "WHERE" | "AND" | "OR" | "NOT"
                | "IN" | "BETWEEN" | "LIKE" | "IS" | "NULL" | "AS"
                | "ORDER" | "BY" | "ASC" | "DESC" | "LIMIT" | "OFFSET"
                | "GROUP" | "HAVING" | "COUNT" | "SUM" | "AVG" | "MIN" | "MAX"
                | "DISTINCT" | "JOIN" | "INNER" | "LEFT" | "RIGHT" | "ON"
                | "TRUE" | "FALSE" ;

comparison_op   = "<=" | ">=" | "<>" | "!=" | "=" | "<" | ">" ;
additive_op     = "+" | "-" ;
multiplicative_op = "*" | "/" ;
punctuation     = "(" | ")" | "," | "." | ";" ;
```

---

## 2. Syntactic Grammar (EBNF)

```ebnf
Statement       = SelectStmt , [ ";" ] ;

SelectStmt      = "SELECT" , [ "DISTINCT" ] , SelectList ,
                  [ "FROM" , FromClause ] ,
                  [ "WHERE" , Expression ] ,
                  [ "GROUP" , "BY" , ExpressionList ] ,
                  [ "HAVING" , Expression ] ,
                  [ "ORDER" , "BY" , OrderByList ] ,
                  [ "LIMIT" , NumberLiteral , [ ( "OFFSET" | "," ) , NumberLiteral ] ] ;

SelectList      = SelectItem , { "," , SelectItem } ;

SelectItem      = ( "*" | ColumnRefStar | Expression ) , [ [ "AS" ] , Identifier ] ;

ColumnRefStar   = Identifier , "." , "*" ;

FromClause      = TableRef , { JoinClause } ;

TableRef        = Identifier , [ [ "AS" ] , Identifier ] ;

JoinClause      = [ "INNER" | "LEFT" ] , "JOIN" , TableRef , "ON" , Expression ;

ExpressionList  = Expression , { "," , Expression } ;

OrderByList     = OrderByItem , { "," , OrderByItem } ;

OrderByItem     = Expression , [ "ASC" | "DESC" ] ;
```

---

## 3. Expression Grammar and Operator Precedence

Precedence climbing and recursive descent are used to parse expressions. Precedence levels from lowest (loosest binding) to highest (tightest binding):

| Level | Operator(s) | Associativity | Description |
|-------|-------------|---------------|-------------|
| 1 | `OR` | Left | Logical disjunction |
| 2 | `AND` | Left | Logical conjunction |
| 3 | `NOT` | Right (prefix) | Logical negation |
| 4 | `=`, `!=`, `<>`, `<`, `<=`, `>`, `>=`, `LIKE`, `IN`, `BETWEEN`, `IS [NOT] NULL` | Non-associative | Comparisons / Predicates |
| 5 | `+`, `-` | Left | Addition, Subtraction |
| 6 | `*`, `/` | Left | Multiplication, Division |
| 7 | `+`, `-` (unary) | Right (prefix) | Positive / Negative signs |
| 8 | Primary | N/A | Column refs, literals, functions, `( expr )` |

```ebnf
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

Primary         = Literal
                | FunctionCall
                | ColumnRef
                | "(" , Expression , ")" ;

FunctionCall    = AggregateName , "(" , [ "DISTINCT" ] , ( "*" | Expression ) , ")" ;

AggregateName   = "COUNT" | "SUM" | "AVG" | "MIN" | "MAX" ;

ColumnRef       = [ Identifier , "." ] , Identifier ;

Literal         = NumberLiteral | StringLiteral | "NULL" | "TRUE" | "FALSE" ;
```

---

## 4. Elimination of Left Recursion

Classical textbook SQL grammars define arithmetic expressions with left-recursive productions such as:
```
E -> E + T | T
```
In a top-down recursive descent parser, this causes an infinite recursive loop (`parse_expr` immediately calls `parse_expr` without advancing the token stream).

We eliminate left recursion using two techniques:
1. **Iterative Loops for Binary Operators**: Transforming `E -> E + T | T` into `E -> T { ("+" | "-") T }*`. The parser reads the first operand (`T`), then loops in a `while` statement consuming binary operators and subsequent operands.
2. **Precedence Climbing / Pratt Parsing**: Managing operator precedence by passing `min_precedence` down the call stack and consuming operators while `precedence(next_op) >= min_precedence`.
This guarantees $O(N)$ linear-time deterministic parsing with bounded recursion depth matching expression nesting.
