
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    department TEXT NOT NULL,
    age INTEGER NOT NULL CHECK (age BETWEEN 16 AND 100),
    gpa REAL NOT NULL CHECK (gpa BETWEEN 0.0 AND 10.0)
);

CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    department TEXT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits BETWEEN 1 AND 6)
);

CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    grade TEXT,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (course_id) REFERENCES courses(course_id),
    UNIQUE (student_id, course_id),
    CHECK (grade IS NULL OR grade IN ('S', 'A', 'B', 'C', 'D', 'F'))
);

CREATE INDEX IF NOT EXISTS idx_students_department
ON students(department);

CREATE INDEX IF NOT EXISTS idx_students_gpa
ON students(gpa);

CREATE INDEX IF NOT EXISTS idx_enrollments_student
ON enrollments(student_id);

CREATE INDEX IF NOT EXISTS idx_enrollments_course
ON enrollments(course_id);
