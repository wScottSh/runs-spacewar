"""G6 counts an edit in replicated C once per copy.

tests/g6/copies.c lays out `total + 5` in two inline copies and `total + 7`
in two unrolled iterations, and makes the same `add (5` and `add (7` once
more outside them. It also lays out two `total + 9` statements in each of
two inline copies. Each test edits one constant in the copies and hands G6
the output of a compiler that rewrote the wrong two identical words.

Usage: uv run python -m unittest discover -s tests"""
import unittest
from pathlib import Path

from pdp1cc.gate import predict

FIXTURE = Path(__file__).parent / "g6" / "copies.c"


class OneRewritePerCopy(unittest.TestCase):
    def setUp(self):
        self.p = predict.prepared(FIXTURE)

    def site(self, constant: int, line: int | None = None) -> predict.Site:
        [site] = [s for s in self.p.sites if s.describe == f"constant {constant:06o} -> {constant + 1:06o}"
                  and s.copies == 2 and line in (None, s.line)]
        return site

    def rewrite(self, constant: int, picks: list[int]) -> list[predict.Line]:
        """The original lines with the picked occurrences of `add (c` made `add (c+1`."""
        at = [i for i, (_, instr) in enumerate(self.p.old) if instr == f"add ({constant:o}"]
        new = list(self.p.old)
        for k in picks:
            new[at[k]] = (new[at[k]][0], f"add ({constant + 1:o}")
        return new

    def test_fixture_lays_out_three_identical_words(self):
        for c in (5, 7):
            self.assertEqual(sum(instr == f"add ({c:o}" for _, instr in self.p.old), 3)

    def test_each_copy_rewritten_matches(self):
        for c in (5, 7):
            self.assertTrue(self.site(c).matches(self.p.old, self.rewrite(c, [0, 1]), self.p.where))

    def test_compiler_passes(self):
        for k, site in enumerate(self.p.sites):
            self.assertEqual(predict.check_site(FIXTURE, k), (site.kind, None))

    def test_a_copy_and_a_word_outside_the_copies_fails(self):
        for c in (5, 7):
            for picks in ([0, 2], [1, 2]):
                with self.subTest(constant=c, picks=picks):
                    self.assertFalse(self.site(c).matches(self.p.old, self.rewrite(c, picks), self.p.where))

    def test_one_copy_twice_fails(self):
        """The first `total + 9` edited; the compiler rewrote both 9s of the first copy."""
        first = FIXTURE.read_text().splitlines().index("    total = total + 9;") + 1
        site = self.site(9, first)
        self.assertTrue(site.matches(self.p.old, self.rewrite(9, [0, 2]), self.p.where))
        self.assertFalse(site.matches(self.p.old, self.rewrite(9, [0, 1]), self.p.where))


if __name__ == "__main__":
    unittest.main()
