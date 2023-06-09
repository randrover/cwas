"""
CWAS Annotation Step

This step annotate user's VCF file using annotation data specified
in the CWAS configuration step. This step mainly uses
Variant Effect Predictor (VEP) to annotate user's VCF file.
"""
import argparse
from pathlib import Path
from typing import Optional

import yaml

from cwas.core.annotation.bed import annotate as _annotate_using_bed
from cwas.core.annotation.vep import VepCmdGenerator
from cwas.runnable import Runnable
from cwas.utils.check import check_is_file
from cwas.utils.check import check_is_dir
from cwas.utils.check import check_num_proc
from cwas.utils.cmd import CmdExecutor, compress_using_bgzip, index_using_tabix
from cwas.utils.log import print_arg, print_log, print_progress

import dotenv
import multiprocessing as mp
from functools import partial
import vcf


class Annotation(Runnable):
    def __init__(self, args: argparse.Namespace):
        super().__init__(args)

    @staticmethod
    def _print_args(args: argparse.Namespace):
        print_arg("Target VCF file", args.vcf_path)
        print_arg("Output directory", args.output_dir_path)
        print_arg("Number of worker processes", args.num_proc)

    @staticmethod
    def _check_args_validity(args: argparse.Namespace):
        check_is_file(args.vcf_path)
        check_is_dir(args.output_dir_path)
        check_num_proc(args.num_proc)

    @property
    def vcf_path(self):
        return self.args.vcf_path.resolve()
    
    @property
    def num_proc(self):
        return self.args.num_proc

    @property
    def output_dir_path(self):
        return self.args.output_dir_path.resolve()

    @property
    def vep_cmd(self):
        vep_cmd_generator = VepCmdGenerator(
            self.get_env("VEP"),
            self.get_env("VEP_CACHE_DIR"), self.get_env("VEP_CONSERVATION_FILE"), 
            self.get_env("VEP_LOFTEE"), self.get_env("VEP_HUMAN_ANCESTOR_FA"), 
            self.get_env("VEP_GERP_BIGWIG"), self.get_env("VEP_MPC"),
            str(self.vcf_path), str(self.num_proc),
        )
        vep_cmd_generator.output_vcf_path = self.vep_output_vcf_path
        return vep_cmd_generator.cmd

    @property
    def vep_output_vcf_path(self):
        if self.vcf_path.suffix == '.gz':
            return (
                f"{self.output_dir_path}/"
                f"{self.vcf_path.stem.replace('.vcf', '.vep.vcf')}"
            )
        else:
            return (
                f"{self.output_dir_path}/"
                f"{self.vcf_path.name.replace('.vcf', '.vep.vcf')}"
            )

    @property
    def vep_output_vcf_gz_path(self):
        return self.vep_output_vcf_path.replace(".vcf", ".vcf.gz")

    @property
    def annotated_vcf_path(self):
        return (
            f"{self.output_dir_path}/"
            f"{self.vcf_path.name.replace('.vcf', '.annotated.vcf')}"
        )

    def run(self):
        self.annotate_using_vep()
        self.process_vep_vcf()
        self.annotate_using_bed()
        self.update_env()

    def annotate_using_vep(self):
        print_progress("Annotation via VEP")
        if (
            Path(self.vep_output_vcf_path).is_file()
            or Path(self.vep_output_vcf_gz_path).is_file()
        ):
            print_log(
                "NOTICE",
                "You have already done the VEP annotations.",
                True,
            )
            return
        
        if self.num_proc == 1:
            vep_bin, *vep_args = self.vep_cmd
            CmdExecutor(vep_bin, vep_args).execute_raising_err()
        else:
            vep_bin, _, _, _, _, *vep_args = self.vep_cmd
            
            print_progress("For multiprocessing, the input VCF should be indexed")
            chroms = self.fetch_chromosomes(self.vcf_path)
            
            multi_inputs = []
            args_list = []
            tmp_output_list = []
            for i in chroms:
                multi_inputs.append(' '.join(['tabix -h', self.vcf_path, i, '|']))
                replace_name = '.' + i + '.vep.vcf'
                tmp_output_vcf_path = self.vcf_path.replace(".vcf.gz", replace_name)
                args_list.append(' '.join(['-o', tmp_output_vcf_path, *vep_args]))
                tmp_output_list.append(tmp_output_vcf_path)
            
            num_processes = self.num_proc if self.num_proc < len(chroms) else len(chroms)
            
            _run_multiple_vep = partial(self.execute_CMD_mp,
                                        bin=vep_bin)            
            
            # Create a multiprocessing pool
            pool = mp.Pool(processes=num_processes)

            # Use starmap to pass args_list and multi_inputs
            pool.starmap(_run_multiple_vep, zip(args_list, multi_inputs))

            # Close the pool and wait for all processes to finish
            pool.close()
            pool.join()
            
            print_progress("Merge output files into a single bgzipped file")
            args_merge = ' '.join([*tmp_output_list, '| bgzip >', self.vep_output_vcf_gz_path])
            CmdExecutor("cat", args_merge).execute_raising_err()
            print_progress("Remove temporary outputs")
            args_remove = ' '.join([*tmp_output_list])
            CmdExecutor("rm", args_remove).execute_raising_err()

    def execute_CMD_mp(self, bin: str, args: list = [], multi_input: Optional[str] = None):
        return CmdExecutor(bin, args, multi_input).execute_raising_err()
    
    def fetch_chromosomes(vcf_file):
        chromosomes = ['chr' + str(i) for i in range(1, 23)] + ['chrX', 'chrY']
        chr_list = []
        for chromosome in chromosomes:
            try:
                vcf_reader = vcf.Reader(filename=vcf_file)
                variants = vcf_reader.fetch(chromosome)
                next(variants)  # Attempt to fetch the first variant
                chr_list.append(chromosome)
            except StopIteration:
                pass
            except Exception:
                pass
        return chr_list

    def process_vep_vcf(self):
        if self.num_proc == 1:
            print_progress("Compress the VEP output using bgzip")
            vcf_gz_path = compress_using_bgzip(self.vep_output_vcf_path)
            print_progress("Create an index of the VEP output using tabix")
            index_using_tabix(vcf_gz_path)
        else:
            print_progress("Create an index of the VEP output using tabix")
            index_using_tabix(self.vep_output_vcf_gz_path)

    def annotate_using_bed(self):
        print_progress("BED custom annotation")
        if Path(self.annotated_vcf_path).is_file():
            print_log(
                "NOTICE",
                "You have already done the BED custom annotation.",
                True,
            )
            return
        
        annotate_vcf = _annotate_using_bed(
            self.vep_output_vcf_gz_path,
            self.annotated_vcf_path,
            self.get_env("MERGED_BED"),
            self.num_proc,
        )

        annotate_vcf.bed_custom_annotate()

    def update_env(self):
        self.set_env("ANNOTATED_VCF", self.annotated_vcf_path)
        self.save_env()
