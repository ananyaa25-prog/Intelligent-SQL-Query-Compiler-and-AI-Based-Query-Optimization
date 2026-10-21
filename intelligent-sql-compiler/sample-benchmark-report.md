# SQL Compiler Benchmark Report

Generated: 2026-10-21T19:02:57.891555+00:00

Input (SQL):

```
SELECT student_id, name FROM students WHERE gpa >= 9.0 AND gpa >= 8.0 LIMIT 10;
```


Original SQL:

```sql
SELECT student_id, name FROM students WHERE gpa >= 9.0 AND gpa >= 8.0 LIMIT 10;
```

Candidate SQL:

```sql
SELECT student_id, name FROM students WHERE gpa >= 9.0 LIMIT 10;
```

Validation: passed

Equivalence: verified on full current sample results



## Verification Gate (Three Layers)

Summary: A: results match on sample DB; B: 50 random in-memory databases checked; no difference found.; C: Z3 proved predicate equivalence (UNSAT)


## VDBE Bytecode Static Metrics (Primary Deterministic Metric)

- Original total opcodes: 19
- Candidate total opcodes: 15
- Opcode reduction: 4 (21.05%)
- Note: Opcode count is a deterministic static proxy for execution complexity; physical execution timing on tiny datasets is noisy.

## Execution Benchmark (Illustrative Only)

Equivalence: observed full result sets match (not a universal proof).

Repetitions: 5 measured after warm-up.

Original median: 0.017 ms (range 0.016 - 0.026 ms).

Candidate median: 0.017 ms (range 0.016 - 0.019 ms).

Measured difference: 0.0%.

Note on timing: On a 1,000-row database, sub-millisecond execution timing is noisy and machine-dependent; it should not be interpreted as an established speedup. VDBE opcode count is the primary deterministic metric.

## Selected query plan

- SEARCH students USING INDEX idx_students_gpa (gpa>?)

Conditions: local university SQLite sample database, read-only execution. Timing includes fetching query rows.

## Index suggestions

No index suggestion from the current plan evidence.