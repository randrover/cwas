import argparse
from abc import abstractmethod
from pathlib import Path

import pandas as pd

from cwas.core.common import cmp_two_arr
from cwas.runnable import Runnable
from cwas.utils.check import check_is_file
from cwas.utils.log import print_arg, print_log, print_progress


class BurdenTest(Runnable):
    def __init__(self, args: argparse.Namespace):
        super().__init__(args)
        self._sample_info = None
        self._adj_factor = None
        self._categorization_result = None

    @staticmethod
    def _create_arg_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="Arguments of Burden Tests",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        parser.add_argument(
            "-s",
            "--sample_info",
            dest="sample_info_path",
            required=True,
            type=Path,
            help="File listing information of your samples",
        )
        parser.add_argument(
            "-a",
            "--adjustment_factor",
            dest="adj_factor_path",
            required=False,
            default=None,
            type=Path,
            help="File listing adjustment factors of each sample",
        )
        return parser

    @staticmethod
    def _print_args(args: argparse.Namespace):
        print_arg("Sample information file", args.sample_info_path)
        print_arg("Adjustment factor list", args.adj_factor_path)

    @staticmethod
    def _check_args_validity(args: argparse.Namespace):
        check_is_file(args.sample_info_path)
        if args.adj_factor_path is not None:
            check_is_file(args.adj_factor_path)

    @property
    def sample_info(self) -> pd.DataFrame:
        if self._sample_info is None:
            self._sample_info = pd.read_table(
                self.sample_info_path, index_col="SAMPLE"
            )
        return self._sample_info

    @property
    def adj_factor(self) -> pd.DataFrame:
        if self.adj_factor_path is None:
            return None
        if self._adj_factor is None:
            self._adj_factor = pd.read_table(
                self.adj_factor_path, index_col="SAMPLE"
            )
        return self._adj_factor

    @property
    def categorization_result(self) -> pd.DataFrame:
        if self._categorization_result is None:
            print_progress("Load the categorization result")
            self._categorization_result = pd.read_table(
                self.get_env("CATEGORIZATION_RESULT"), index_col="SAMPLE"
            )
            if self.adj_factor is not None:
                self._adjust_categorization_result()
        return self._categorization_result

    def _adjust_categorization_result(self):
        if not _contain_same_index(
            self._categorization_result, self.adj_factor
        ):
            raise ValueError(
                "The sample IDs from the adjustment factor list are "
                "not the same with the sample IDs "
                "from the categorization result."
            )
        adj_factors = [
            self.adj_factor.to_dict()["AdjustFactor"][sample_id]
            for sample_id in self._categorization_result.index.values
        ]
        self._categorization_result = self._categorization_result.multiply(
            adj_factors, axis="index"
        )

    def run(self):
        print_log("Notice", "Not implemented yet.")

    @abstractmethod
    def test(self):
        raise RuntimeError(
            "This method cannot be called via the instance of BurdenTest."
        )


def _contain_same_index(table1: pd.DataFrame, table2: pd.DataFrame) -> bool:
    return cmp_two_arr(table1.index.values, table2.index.values)
