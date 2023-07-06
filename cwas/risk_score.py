import os, sys, argparse
import pandas as pd
import numpy as np
import cwas.utils.log as log
from pathlib import Path
from tqdm import tqdm
from glmnet import ElasticNet
from cwas.core.common import cmp_two_arr
from cwas.utils.check import check_is_file, check_num_proc
from cwas.runnable import Runnable
from typing import Optional, Tuple
from contextlib import contextmanager
from collections import defaultdict
import matplotlib.pyplot as plt

class RiskScore(Runnable):
    def __init__(self, args: argparse.Namespace):
        super().__init__(args)
        self._sample_info = None
        self._categorization_result = None
        self._adj_factor = None
        self._category_set_path = None
        self._category_set = None
        self._datasets = None
        self._covariates = None
        self._test_covariates = None
        self._response = None
        self._test_response = None
        self._result_dict = defaultdict(dict)
        self._permutation_dict = defaultdict(dict)
        self._filtered_combs = None
    
    @staticmethod
    def _print_args(args: argparse.Namespace):
        log.print_arg(
            "Categorization result file", 
            args.categorization_result_path
                if args.categorization_result_path
                else "Not specified: $CATEGORIZATION_RESULT will be used")
        log.print_arg("Sample information file", args.sample_info_path)
        log.print_arg("Adjustment factor list", args.adj_factor_path)
        log.print_arg(
            "Category set file", 
            args.category_set_path
                if args.category_set_path
                else "Not specified: all rare categories will be used")
        if args.tag:
            log.print_arg("Output tag (prefix of output files)", args.tag)
        log.print_arg("If the number of carriers is used for calculating R2 or not", args.use_n_carrier)
        log.print_arg(
            "Threshold for selecting rare categories",
            f"{args.ctrl_thres: ,d}",
        )
        log.print_arg("Fraction of the training set", f"{args.train_set_f: ,f}")
        log.print_arg(
            "No. regression trials to calculate a mean of R squares",
            f"{args.num_reg: ,d}",
        )
        log.print_arg(
            "No. folds for CV",
            f"{args.fold: ,d}",
        )
        log.print_arg("Use Logistic regression", args.logistic)
        log.print_arg(
            "No. permutation used to calculate the p-value",
            f"{args.n_permute: ,d}",
        )
        log.print_arg("Skip the permutation test", args.predict_only)
        log.print_arg(
            "No. worker processes for permutation",
            f"{args.num_proc: ,d}",
        )

    @staticmethod
    def _check_args_validity(args: argparse.Namespace):
        check_is_file(args.sample_info_path)
        check_num_proc(args.num_proc)
        if args.categorization_result_path:
            check_is_file(args.categorization_result_path)
        if args.adj_factor_path is not None:
            check_is_file(args.adj_factor_path)
        if args.category_set_path:
            check_is_file(args.category_set_path)
    
    @property
    def categorization_result_path(self) -> Path:
        return (
            self.args.categorization_result_path.resolve()
            if self.args.categorization_result_path 
            else Path(self.get_env("CATEGORIZATION_RESULT"))
        )

    @property
    def adj_factor_path(self) -> Optional[Path]:
        return (
            self.args.adj_factor_path.resolve()
            if self.args.adj_factor_path
            else None
        )

    @property
    def plot_path(self) -> Optional[Path]:
        tag = '' if self.tag is None else ''.join([self.tag, '_'])
        return Path(
            f"{self.out_dir}/" +
            str(self.categorization_result_path.name).replace('.categorization_result.txt.gz', f'.lasso_histogram_{tag}thres_{self.ctrl_thres}.pdf')
        )

    @property
    def category_set_path(self) -> Optional[Path]:
        return (
            self.args.category_set_path.resolve()
            if self.args.category_set_path
            else None
        )

    @property
    def out_dir(self) -> Path:
        return(self.args.output_dir_path.resolve())

    @property
    def category_set(self) -> pd.DataFrame:
        if self._category_set is None and self.category_set_path:
            self._category_set = pd.read_csv(self.category_set_path, sep='\t')
        return self._category_set

    @property
    def sample_info_path(self) -> Path:
        return self.args.sample_info_path.resolve()

    @property
    def use_n_carrier(self) -> bool:
        return self.args.use_n_carrier

    @property
    def tag(self) -> str:
        return self.args.tag

    @property
    def num_proc(self) -> int:
        return self.args.num_proc

    @property
    def num_reg(self) -> int:
        return self.args.num_reg

    @property
    def train_set_f(self) -> float:
        return self.args.train_set_f

    @property
    def filtered_combs(self) -> list:
        if self.category_set_path:
            self._filtered_combs = self.category_set["Category"]
        else:
            self._filtered_combs = pd.Series([col for col in self.categorization_result.columns if col != 'SAMPLE'])
        return self._filtered_combs

    @property
    def fold(self) -> int:
        return self.args.fold

    @property
    def n_permute(self) -> int:
        return self.args.n_permute
    
    @property
    def ctrl_thres(self) -> int:
        return self.args.ctrl_thres
    
    @property
    def logistic(self) -> bool:
        return self.args.logistic
    
    @property
    def predict_only(self) -> bool:
        return self.args.predict_only
    
    @property
    def sample_info(self) -> pd.DataFrame:
        if self._sample_info is None:
            self._sample_info = pd.read_table(
                self.sample_info_path, index_col="SAMPLE"
            )
            if ("SET" not in self._sample_info.columns):
                log.print_log("LOG", 
                              "No 'SET' column in sample information file. "
                              "Training and test sets will be assigned randomly.")
                
                case_count = sum(self._sample_info['PHENOTYPE'] == 'case')
                ctrl_count = sum(self._sample_info['PHENOTYPE'] == 'ctrl')
                min_size = int(np.rint(min(case_count, ctrl_count) * self.train_set_f))
                
                log.print_log("LOG",
                              "Use {} samples from each phenotype as training set."
                              .format(min_size))
                
                test_idx = self._sample_info.groupby('PHENOTYPE').sample(n=min_size, random_state=42).index
                self._sample_info["SET"] = np.where(self._sample_info.index.isin(test_idx), "test", "training")
        return self._sample_info

    @property
    def adj_factor(self) -> pd.DataFrame:
        if self._adj_factor is None and self.adj_factor_path:
            self._adj_factor = pd.read_table(
                self.adj_factor_path, index_col="SAMPLE"
            )
        return self._adj_factor
    
    @property
    def categorization_result(self) -> pd.DataFrame:
        if self._categorization_result is None:
            log.print_progress("Load the categorization result")
            self._categorization_result = pd.read_table(
                self.categorization_result_path, index_col="SAMPLE"
            )
            if self.adj_factor is not None:
                self._adjust_categorization_result()
            if self.use_n_carrier:
                self._categorization_result = self._categorization_result.applymap(lambda x: 1 if x > 0 else 0)
            log.print_log("LOG",
                          "Categorization result has {} samples and {} categories."
                          .format(self._categorization_result.shape[0], self._categorization_result.shape[1]))
        return self._categorization_result
    
    def _adjust_categorization_result(self):
        if not self._contain_same_index(
           self._categorization_result, self._adj_factor
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

    @staticmethod
    def _contain_same_index(table1: pd.DataFrame, table2: pd.DataFrame) -> bool:
        return cmp_two_arr(table1.index.values, table2.index.values)
    
    @property
    def datasets(self) -> np.ndarray:
        if self._datasets is None:
            self._datasets = np.vectorize(
                lambda sample_id: self.sample_info.to_dict()["SET"][
                    sample_id
                ]
            )(self.categorization_result.index.values)
        return self._datasets

    @property
    def covariates(self) -> pd.DataFrame:
        if self._covariates is None:
            self._covariates = self.categorization_result[self.datasets == "training"]
        return self._covariates
    
    @property
    def test_covariates(self) -> pd.DataFrame:
        if self._test_covariates is None:
            self._test_covariates = self.categorization_result[self.datasets == "test"]
        return self._test_covariates
    
    @property
    def response(self) -> np.ndarray:
        if self._response is None:
            self._response = np.vectorize(
                lambda sample_id: self.sample_info.to_dict()["PHENOTYPE"][
                    sample_id
                ] == "case"
            )(self.categorization_result[self.datasets == "training"].index.values)
        return self._response
    
    @property
    def test_response(self) -> np.ndarray:
        if self._test_response is None:
            self._test_response = np.vectorize(
                lambda sample_id: self.sample_info.to_dict()["PHENOTYPE"][
                    sample_id
                ] == "case"
            )(self.categorization_result[self.datasets == "test"].index.values)
        return self._test_response

    @property
    def coef_path(self) -> Path:
        tag = '' if self.tag is None else ''.join([self.tag, '_'])
        return Path(
            f"{self.out_dir}/" +
            str(self.categorization_result_path.name).replace('.categorization_result.txt.gz', f'.lasso_coef_{tag}thres_{self.ctrl_thres}.txt')
        )
    
    @property
    def result_path(self) -> Path:
        tag = '' if self.tag is None else ''.join([self.tag, '_'])
        return Path(
            f"{self.out_dir}/" +
            str(self.categorization_result_path.name).replace('.categorization_result.txt.gz', f'.lasso_results_{tag}thres_{self.ctrl_thres}.txt')
        )

    @property
    def null_model_path(self) -> Path:
        tag = '' if self.tag is None else ''.join([self.tag, '_'])
        return Path(
            f"{self.out_dir}/" +
            str(self.categorization_result_path.name).replace('.categorization_result.txt.gz', f'.lasso_null_models_{tag}thres_{self.ctrl_thres}.txt')
        )

    def run(self):
        self.prepare()
        self.risk_scores()
        if not self.predict_only:
            self.permute_pvalues()
        self.save_results()
        self.update_env()
        log.print_progress("Complete")

    def prepare(self):
        if not self._contain_same_index(
            self.categorization_result, self.sample_info
        ):
            raise ValueError(
                "The sample IDs from the sample information are "
                "not the same with the sample IDs "
                "from the categorization result."
            )
            
    def risk_scores(self):
        """Generate risk scores for various seeds """
        log.print_progress(self.risk_scores.__doc__)
        
        seeds = np.arange(99, 99 + self.num_reg * 10, 10)
        for seed in seeds:
            self.risk_score_per_category(result_dict=self._result_dict, seed=seed)
            
    def risk_score_per_category(self, result_dict: defaultdict, seed: int = 42, swap_label: bool = False):
        """Lasso model selection """
        if swap_label:
            np.random.seed(seed)
            response, test_response = np.random.permutation(self.response), np.random.permutation(self.test_response)
        else:
            response, test_response = self.response, self.test_response

        ctrl_var_counts = pd.concat(
            [self.covariates[self.filtered_combs][~response],
             self.test_covariates[self.filtered_combs][~test_response]],
        ).sum()
        rare_idx = (ctrl_var_counts < self.ctrl_thres).values
        log.print_progress(f"# of rare categories (Seed: {seed}): {rare_idx.sum()}")
        cov = self.covariates[self.filtered_combs].iloc[:, rare_idx]
        test_cov = self.test_covariates[self.filtered_combs].iloc[:, rare_idx]
        if cov.shape[1] == 0:
            log.print_warn(f"There are no rare categories (Seed: {seed}).")
            return
        y = np.where(response, 1.0, -1.0)
        test_y = np.where(test_response, 1.0, -1.0)
        log.print_progress(f"Running LassoCV (Seed: {seed})")
        lasso_model = ElasticNet(alpha=1, n_lambda=100, standardize=True, n_splits=self.fold, n_jobs=self.num_proc,
                                 scoring='mean_squared_error', random_state=seed)
        lasso_model.fit(cov, y, self.custom_cv_folds())
        opt_model_idx = np.argmax(getattr(lasso_model, 'cv_mean_score_'))
        coeffs = getattr(lasso_model, 'coef_path_')
        opt_coeff = np.zeros(len(rare_idx))
        opt_coeff[rare_idx] = coeffs[:, opt_model_idx]
        opt_lambda = getattr(lasso_model, 'lambda_max_')
        n_select = np.sum(np.abs(opt_coeff) > 0.0)
        pred_responses = lasso_model.predict(test_cov, lamb=opt_lambda)
        mean_response = np.mean(test_y)
        rsq = 1 - np.sum((test_y - pred_responses) ** 2) / np.sum((test_y - mean_response) ** 2)
        result_dict['result'][seed] = [opt_lambda, rsq, n_select, opt_coeff]
        
        log.print_progress("Done")
            
    def custom_cv_folds(self, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
        np.random.seed(seed)
        nobs = np.sum(self.datasets == "training")
        rand_idx = np.random.permutation(nobs)
        foldid = np.repeat(0, nobs)
        i=0
        while i<=self.fold:
            idx_val = rand_idx[np.arange(nobs * (i - 1) / self.fold, nobs * i / self.fold, dtype=int)]
            foldid[idx_val] = i
            i+=1
    
    def permute_pvalues(self):
        """Run LassoCV to get permutated pvalues"""
        log.print_progress(self.permute_pvalues.__doc__)
        
        @contextmanager
        def nullify_output(suppress_stdout: bool=True, suppress_stderr: bool=True):
            stdout = sys.stdout
            stderr = sys.stderr
            devnull = open(os.devnull, "w")
            try:
                if suppress_stdout:
                    sys.stdout = devnull
                if suppress_stderr:
                    sys.stderr = devnull
                yield
            finally:
                if suppress_stdout:
                    sys.stdout = stdout
                if suppress_stderr:
                    sys.stderr = stderr
                    
        seeds = np.arange(1001, 1001+self.n_permute)
        for seed in tqdm(seeds):
            with nullify_output():
                self.risk_score_per_category(result_dict=self._permutation_dict, seed=seed, swap_label=True)
                

    def save_results(self):
        """Save the results to a file """
        log.print_progress(self.save_results.__doc__)
        result_table = []
        cat = list(self._result_dict.keys())[0]
        choose_idx = np.all([self._result_dict[cat][seed][3] != 0 
                            for seed in self._result_dict[cat].keys()], axis=0)
        ## Get the categories which are selected by the LassoCV for all seeds
        coef_df = pd.DataFrame.from_dict(
            {seed: self._result_dict[cat][seed][3][choose_idx]
            for seed in self._result_dict[cat].keys()},
            orient="index",
            columns = self.filtered_combs[choose_idx]
        )
        coef_df.to_csv(
            self.coef_path,
            sep="\t"
        )
        parameter = np.mean([self._result_dict[cat][seed][0]
                           for seed in self._result_dict[cat].keys()])
        r2 = np.mean([self._result_dict[cat][seed][1]
                      for seed in self._result_dict[cat].keys()])
            
        if not self.predict_only:
            null_models = []
            cat2 = list(self._permutation_dict.keys())[0]
            r2_scores = np.array([self._permutation_dict[cat2][seed][1]
                                for seed in self._permutation_dict[cat2].keys()])
            null_models.append(['avg', r2_scores.mean(), r2_scores.std()])
            null_models.extend([[i+1] + [str(r2_scores[i])] + [''] for i in range(len(r2_scores))])
            null_models = pd.DataFrame(
                null_models,
                columns=["N_perm", "R2", "std"]
            )
            null_models.to_csv(self.null_model_path, sep="\t", index=False)

            result_table.append([cat, 'avg', parameter, r2, sum(choose_idx), (sum(r2_scores>=r2)+1)/(len(r2_scores)+1)])
            result_table += [[cat] + [str(seed)] + self._result_dict[cat][seed][:-1] + [(sum(r2_scores>=self._result_dict[cat][seed][1]+1))/(len(r2_scores)+1)]
                             for seed in self._result_dict[cat].keys()]

            result_table = pd.DataFrame(
                result_table, columns=["Category", "seed", "parameter", "R2", "n_select", "perm_P"]
            )
            result_table.to_csv(self.result_path, sep="\t", index=False)
            
            self.draw_histogram_plot(r2, r2_scores)
        else:
            result_table.append([cat, 'avg', parameter, r2, sum(choose_idx)])
            result_table += [[cat] + [str(seed)] + self._result_dict[cat][seed][:-1]
                             for seed in self._result_dict[cat].keys()]

            result_table = pd.DataFrame(
                result_table, columns=["Category", "seed", "parameter", "R2", "n_select"]
            )
            result_table.to_csv(self.result_path, sep="\t", index=False)
    

    def update_env(self):
        """Update the environment variables """
        log.print_progress(self.update_env.__doc__)
        
        self.set_env("LASSO_RESULTS", self.result_path)
        if not self.predict_only:
            self.set_env("LASSO_NULL_MODELS", self.null_model_path)
        self.save_env()
        
    def draw_histogram_plot(self, r2: float, perm_r2: np.ndarray):
        log.print_progress("Save histogram plot")
        
        # Set the font size
        plt.rcParams.update({'font.size': 8})
        
        # Set the figure size
        plt.figure(figsize=(4, 4))

        # Create the histogram plot
        plt.hist(perm_r2, bins=20, color='lightgrey', edgecolor='black')
        
        text_label1 = 'P={:.2f}'.format((sum(perm_r2>=r2)+1)/(len(perm_r2)+1))
        text_label2 = '$R^2$={:.2f}%'.format(r2*100)

        # Add labels and title
        plt.xlabel('$R^2$')
        plt.ylabel('Frequency')
        plt.title('Histogram Plot', fontsize = 8)
        plt.axvline(x=r2, color='red')
        plt.text(0.05, 0.95, text_label1, transform=plt.gca().transAxes, ha='left', va='top', fontsize=8, color='black')
        plt.text(0.05, 0.85, text_label2, transform=plt.gca().transAxes, ha='left', va='top', fontsize=8, color='red')
        plt.locator_params(axis='x', nbins=5)

        plt.savefig(self.plot_path)
