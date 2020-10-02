"""
Tests for the sequence alignment in pipeline.py.
"""
import unittest

import numpy as np
import pandas as pd

from cassiopeia.ProcessingPipeline.process import pipeline


class TestErrorCorrectUMISequence(unittest.TestCase):
    def setUp(self):

        self.multi_case = pd.DataFrame.from_dict(
            {
                "cellBC": [
                    "A",
                    "A",
                    "A",
                    "B",
                    "B",
                    "C",
                    "C",
                    "C",
                    "C",
                    "D",
                    "D",
                ],
                "UMI": [
                    "AACCT",
                    "AACCG",
                    "AACCC",
                    "AACCT",
                    "AACCG",
                    "AACCT",
                    "AACCG",
                    "AAGGA",
                    "AACCT",
                    "AACCT",
                    "AAGGG",
                ],
                "ReadCount": [20, 30, 30, 40, 50, 10, 10, 15, 10, 10, 10],
                "Seq": [
                    "AACCTTGG",
                    "AACCTTGG",
                    "AACCTTCC",
                    "AACCTTGG",
                    "AACCTTGC",
                    "AACCTTCC",
                    "AACCTTCG",
                    "AACCTCAG",
                    "AACCTTGG",
                    "AACCTTGG",
                    "AACCTAAA",
                ],
                "intBC": [
                    "X",
                    "X",
                    "X",
                    "Y",
                    "Y",
                    "Z",
                    "Z",
                    "Z",
                    "W",
                    "V",
                    "V",
                ],
                "r1": ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1"],
                "r2": ["2", "2", "2", "2", "2", "2", "2", "2", "2", "2", "2"],
                "r3": ["3", "3", "3", "3", "3", "3", "3", "3", "3", "3", "3"],
                "AlignmentScore": [
                    "20",
                    "20",
                    "20",
                    "20",
                    "20",
                    "20",
                    "20",
                    "20",
                    "20",
                    "20",
                    "20",
                ],
                "CIGAR": [
                    "NA",
                    "NA",
                    "NA",
                    "NA",
                    "NA",
                    "NA",
                    "NA",
                    "NA",
                    "NA",
                    "NA",
                    "NA",
                ],
            }
        )
        self.multi_case["readName"] = self.multi_case.apply(
            lambda x: "_".join([x.cellBC, x.UMI, str(x.ReadCount)]), axis=1
        )

        self.multi_case["allele"] = self.multi_case.apply(
            lambda x: "_".join([x.r1, x.r2, x.r3]), axis=1
        )

    def test_format(self):

        aln_df = pipeline.error_correct_umis(
            self.multi_case, "test", max_UMI_distance=1
        )

        expected_columns = [
            "cellBC",
            "UMI",
            "AlignmentScore",
            "CIGAR",
            "Seq",
            "readName",
            "ReadCount",
            "intBC",
            "r1",
            "r2",
            "r3",
        ]
        for column in expected_columns:
            self.assertIn(column, aln_df.columns)

    def test_zero_dist(self):

        aln_df = pipeline.error_correct_umis(
            self.multi_case, "test", max_UMI_distance=0
        )

        self.assertEqual(aln_df.shape[0], self.multi_case.shape[0])

        for cellBC in self.multi_case["cellBC"].unique():
            self.assertIn(cellBC, aln_df["cellBC"].unique())

    def test_error_correct_two_dist(self):

        aln_df = pipeline.error_correct_umis(
            self.multi_case, "test", max_UMI_distance=2
        )

        expected_alignments = {
            "A_AACCG_80": 80,
            "B_AACCG_90": 90,
            "C_AACCT_20": 20,
            "C_AACCT_10": 10,
            "C_AAGGA_15": 15,
            "D_AACCT_10": 10,
            "D_AAGGG_10": 10,
        }

        for read_name in aln_df["readName"]:

            expected_readcount = expected_alignments[read_name]

            self.assertEqual(
                aln_df.loc[aln_df["readName"] == read_name, "ReadCount"].iloc[
                    0
                ],
                expected_readcount,
            )

if __name__ == "__main__":
    unittest.main()
