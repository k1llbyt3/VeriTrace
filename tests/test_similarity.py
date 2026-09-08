import unittest

import numpy as np

from python.face.similarity import rank_similarities


class SimilarityRankingTests(unittest.TestCase):
    def test_ranks_highest_similarity_first_and_marks_above_threshold(self):
        reference = np.array([1.0, 0.0])
        candidates = [
            np.array([0.6, 0.8]),
            np.array([1.0, 0.0]),
            np.array([-1.0, 0.0]),
        ]

        results = rank_similarities(reference, candidates, threshold=0.9)

        self.assertEqual([result.index for result in results], [1, 0, 2])
        self.assertAlmostEqual(results[0].score, 1.0)
        self.assertTrue(results[0].passes_threshold)

    def test_marks_below_threshold_without_changing_similarity_score(self):
        reference = np.array([1.0, 0.0])
        candidate = np.array([0.8, 0.6])

        result = rank_similarities(reference, [candidate], threshold=0.99)[0]

        self.assertAlmostEqual(result.score, 0.8)
        self.assertFalse(result.passes_threshold)


if __name__ == "__main__":
    unittest.main()