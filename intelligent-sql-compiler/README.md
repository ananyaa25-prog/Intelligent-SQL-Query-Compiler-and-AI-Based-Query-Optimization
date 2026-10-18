# Intelligent SQL Query Compiler with AI-Based Query Optimization



## 1. Project Overview



The **Intelligent SQL Query Compiler** is a Python-based application that demonstrates SQL compilation concepts, rule-based query optimization, database validation, safe query execution, and query performance evaluation.



The application provides a Streamlit web interface where users can enter SQL queries or describe supported database requests in natural language. Natural-language requests are converted into SQL using a local rule-based generator.



The generated SQL can then be validated and executed against a sample university database. The application also supports query-plan analysis and performance comparison between original and optimized SQL statements.



## 2. Objectives



\- Implement lexical analysis and SQL tokenization.

\- Perform basic syntax analysis and construct an Abstract Syntax Tree (AST).

\- Apply rule-based SQL optimization.

\- Convert supported natural-language requests into SQL.

\- Validate SQL queries against the database schema.

\- Execute permitted read-only SQL queries safely.

\- Analyze query execution plans using SQLite EXPLAIN functionality.

\- Compare the results and execution performance of original and optimized queries.

\- Provide an interactive web interface using Streamlit.



## 3. Technologies Used



\- **Python** â€” Core programming language.

\- **Streamlit** â€” Interactive web application.

\- **SQLite** â€” Relational database.

\- **Pandas** â€” Tabular result display and data processing.

\- **SQLGlot** â€” SQL parsing and validation support.

\- **Regular Expressions** â€” Token recognition and rule-based SQL optimization.

\- **Unittest** â€” Testing the optimizer.



## 4. System Architecture



The application consists of two primary modules.



### Person 1: SQL Compiler and Optimization



\- `lexer.py` â€” Tokenizes SQL statements into keywords, identifiers, operators, numbers, and punctuation.

\- `parser.py` â€” Parses supported SELECT statements and creates an AST.

\- `optimizer.py` â€” Applies basic rule-based SQL optimization.

\- `compiler.py` â€” Integrates lexical analysis, syntax analysis, and optimization.

\- `nl\_to\_sql.py` â€” Converts supported English requests into SQL using predefined rules.

\- `test\_optimizer.py` â€” Tests the rule-based optimizer.



### Person 2: Database and Query Evaluation



\- `database.py` â€” Supports database setup and data preparation.

\- `schema.sql` â€” Defines the database schema.

\- `semantic\_analyzer.py` â€” Validates SQL queries and checks them against database rules.

\- `execution\_engine.py` â€” Executes permitted read-only SQL queries.

\- `evaluation.py` â€” Analyzes execution plans and compares query performance.

\- `university.db` â€” Sample university database.



### Application Interface



\- `app.py` â€” Connects the compiler, natural-language generator, database validation, query execution, and optimization evaluation through Streamlit.



## 5. Main Features



### 5.1 Lexical Analysis



The lexer divides a SQL statement into tokens and identifies their types and positions.



### 5.2 Syntax Analysis



The parser constructs an Abstract Syntax Tree containing supported query components, including selected columns, table name, WHERE condition, ORDER BY clause, and LIMIT clause.



### 5.3 Rule-Based SQL Optimization



The optimizer demonstrates a basic optimization rule by removing a redundant weaker numeric lower-bound condition connected using AND.



Example:



Original SQL:



&#x20;   SELECT student\_id, name

&#x20;   FROM students

&#x20;   WHERE gpa >= 9.0 AND gpa >= 8.0;



Optimized SQL:



&#x20;   SELECT student\_id, name

&#x20;   FROM students

&#x20;   WHERE gpa >= 9.0;



The optimization is demonstrated for supported query patterns and is not intended to handle every possible SQL expression.



### 5.4 Natural Language-to-SQL



Users can describe supported database requests in English. The local rule-based generator converts matching requests into SQL without requiring an external AI API or API key.



Example request:



&#x20;   Show the top 10 students



Generated SQL:



&#x20;   SELECT student\_id, name, gpa

&#x20;   FROM students

&#x20;   ORDER BY gpa DESC

&#x20;   LIMIT 10;



Other supported examples include requests to list courses, count students, count students by department, and retrieve students above a specified GPA.



### 5.5 Semantic Validation



Generated or manually entered SQL can be checked against the database schema and validation rules before execution.



### 5.6 Safe Query Execution



The application executes permitted read-only queries and displays the returned records and execution time.



### 5.7 Query Plan Analysis



The application displays query-plan information and indicators such as index usage, table scans, and temporary structures when available.



### 5.8 Performance Evaluation



The application compares original and optimized queries using result-equivalence checks, median execution times, measured improvement, and query execution plans.



## 6. Database



The project uses a sample university database containing:



\- 1,000 students

\- 10 courses

\- 3,000 enrollments



The database supports demonstrations involving student records, GPA filtering, course information, aggregations, and joins where supported by the database modules.



## 7. Installation and Setup



### Prerequisites



\- Python 3.11 or a compatible Python version.

\- pip package installer.

\- Windows, macOS, or Linux.



### Step 1: Open the project directory



Open PowerShell or a terminal in the directory containing `app.py`.



### Step 2: Install dependencies



Run:



&#x20;   python -m pip install streamlit pandas sqlglot



### Step 3: Run the application



Run:



&#x20;   python -m streamlit run app.py



Open the local URL displayed in the terminal, usually:



&#x20;   http://localhost:8501



## 8. Running Tests



To run the Person 1 optimizer tests:



&#x20;   python -m unittest discover -s person1 -p "test\_*.py" -v



The tests cover supported optimization behavior, including redundant lower-bound removal, preservation of stronger conditions, different columns, OR conditions, and queries without WHERE clauses.



## 9. How to Use the Application



1\. Start the Streamlit application.

2\. Enter a supported English request in the Natural Language-to-SQL section.

3\. Click **Generate SQL**.

4\. Review the generated SQL and its validation result.

5\. Click **Use Generated SQL in Workspace**.

6\. Use **Validate SQL** to check a query or **Validate \& Execute** to retrieve results.

7\. Use **Explain Plan** to inspect the execution plan.

8\. Enter an original query and its optimized version in Optimization Evaluation.

9\. Click **Compare Queries** to review result equivalence, execution timings, and query plans.



## 10. Limitations



\- The natural-language generator uses predefined patterns rather than a general-purpose generative AI model.

\- The lexer and parser support a limited subset of SQL syntax.

\- The optimizer implements basic rules and is not a complete cost-based optimizer.

\- Performance measurements can vary between runs and should not be treated as guaranteed speed improvements.

\- Complex queries should be tested using the database workspace and validation features rather than assuming the basic compiler parser supports all SQL constructs.



## 11. Future Enhancements



\- Expand SQL grammar support for joins, grouping, subqueries, and additional SQL constructs.

\- Add more optimization rules with equivalence checks.

\- Improve natural-language understanding and supported query patterns.

\- Add additional test cases for semantic validation and execution safety.

\- Improve benchmark reporting and repeatability.

\- Explore optional generative-AI integration for natural-language SQL generation.



## 12. Conclusion



The project demonstrates how compiler design concepts can be applied to SQL processing and optimization. By combining lexical analysis, basic syntax parsing, rule-based optimization, semantic validation, safe database execution, and performance evaluation in a single web application, it provides an educational demonstration of the SQL query processing workflow.




