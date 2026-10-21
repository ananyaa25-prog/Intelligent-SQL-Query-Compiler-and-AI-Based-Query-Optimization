
import unittest

from optimizer import optimize_sql


class TestOptimizer(unittest.TestCase):

    def test_removes_weaker_lower_bound(self):
        sql = (
            "SELECT student_id, name FROM students "
            "WHERE gpa >= 9.0 AND gpa >= 8.0;"
        )

        result = optimize_sql(sql)

        self.assertIn("gpa >= 9.0", result)
        self.assertNotIn("gpa >= 8.0", result)

    def test_keeps_stronger_lower_bound(self):
        sql = (
            "SELECT name FROM students "
            "WHERE gpa >= 8.0 AND gpa >= 9.0;"
        )

        result = optimize_sql(sql)

        self.assertIn("gpa >= 9.0", result)
        self.assertNotIn("gpa >= 8.0", result)

    def test_keeps_different_columns(self):
        sql = (
            "SELECT name FROM students "
            "WHERE gpa >= 9.0 AND age >= 8.0;"
        )

        result = optimize_sql(sql)

        self.assertIn("gpa >= 9.0", result)
        self.assertIn("age >= 8.0", result)

    def test_leaves_or_condition_unchanged(self):
        sql = (
            "SELECT name FROM students "
            "WHERE gpa >= 9.0 OR gpa >= 8.0;"
        )

        self.assertEqual(optimize_sql(sql), sql)

    def test_leaves_query_without_where_unchanged(self):
        sql = "SELECT name FROM students;"

        self.assertEqual(optimize_sql(sql), sql)


if __name__ == "__main__":
    unittest.main()
