"""
Command line generator for Variant Effect Predictor (VEP)
"""
from cwas.utils.check import check_is_file


class VepCmdGenerator:
    def __init__(self, vep_path: str, input_vcf_path: str) -> None:
        self._vep_path = vep_path
        self._check_vep_path()
        self._input_vcf_path = input_vcf_path
        self._check_input_vcf_path()
        self._output_vcf_path = input_vcf_path.replace(".vcf", ".vep.vcf")
        self._bw_custom_annotations = []

    def _check_vep_path(self):
        try:
            check_is_file(self._vep_path)
        except ValueError:
            raise ValueError(f"Invalid VEP path: {self._vep_path}")
        except:
            raise

    def _check_input_vcf_path(self):
        try:
            check_is_file(self._input_vcf_path)
        except ValueError:
            raise ValueError(f"Invalid VCF path: {self._input_vcf_path}")
        except:
            raise

    def add_bw_custom_annotation(self, bw_path: str, annotation_key: str):
        check_is_file(bw_path)
        self._bw_custom_annotations.append((bw_path, annotation_key))

    @property
    def vep_path(self) -> str:
        return self._vep_path

    @property
    def input_vcf_path(self) -> str:
        return self._input_vcf_path

    @property
    def output_vcf_path(self) -> str:
        return self._output_vcf_path

    @property
    def cmd(self) -> str:
        args = [
            self._vep_path,
            "-i",
            self._input_vcf_path,
            "-o",
            self._output_vcf_path,
        ]
        args += self.cmd_option_basic
        args += self.cmd_option_pick_one_gene_isoform
        args += self.cmd_option_pick_nearest_gene
        args += self.cmd_option_bw_custom_annotations
        return " ".join(args)

    @property
    def cmd_option_basic(self) -> list:
        """Return basic options (no plugins) of VEP"""
        return [
            "--assembly",
            "GRCh38",
            "--offline",
            "--force_overwrite",
            "--format",
            "vcf",
            "--vcf",
            "--no_stats",
            "--polyphen p",
        ]

    @property
    def cmd_option_pick_one_gene_isoform(self) -> list:
        """Return options in order to pick a gene isoform 
        with most severe consequence"""
        return [
            "--per_gene",
            "--pick",
            "--pick_order",
            "canonical,appris,tsl,biotype,ccds,rank,length",
        ]

    @property
    def cmd_option_pick_nearest_gene(self) -> list:
        """Return options in order to pick the nearest gene"""
        return ["--distance", "2000", "--nearest", "symbol", "--symbol"]

    @property
    def cmd_option_bw_custom_annotations(self) -> list:
        result = []

        for bw_path, annotation_key in self._bw_custom_annotations:
            result += [
                "--custom",
                ",".join([bw_path, annotation_key, "bigwig", "overlap", "0"]),
            ]

        return result
