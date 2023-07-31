'''
- This code is based on the network analysis in An et al., 2018
- Source : https://github.com/lingxuez/WGS-Analysis/tree/master/network/supernodeWGS
'''

import pandas as pd
import numpy as np
import os
from scipy.optimize import minimize_scalar
from scipy.stats import norm
from scipy.stats import rankdata
import rpy2.robjects as robjects
from rpy2.robjects.packages import importr
from rpy2.robjects import numpy2ri
import random
import igraph
import itertools
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt


class supernodeWGS_func:
    def __init__(self, corr_mat: pd.DataFrame, fit_res, max_cluster: int, cores: int,
                 output_dir_path: str, tag: str, seed: int, verbose=True) -> None:
        self._corr_mat = corr_mat
        self._fit_res = fit_res
        self._max_cluster = max_cluster # max_cluster
        self._cores = cores
        self._output_dir_path = output_dir_path
        self._tag = tag
        self._clusters = None
        self._seed = seed
        self._verbose = verbose
        self.PMA = importr('PMA')

    @property
    def corr_mat(self) -> pd.DataFrame:
        return self._corr_mat

    @property
    def fit_res(self):
        return self._fit_res
    
    @property
    def max_cluster(self) -> int:
        return self._max_cluster

    @property
    def cores(self) -> int:
        return self._cores
    
    @property
    def output_dir_path(self) -> str:
        return self._output_dir_path
    
    @property
    def tag(self) -> str:
        return self._tag

    @property
    def clusters(self):
        if self._clusters is None:
            clusters_ = list(self.fit_res['cluster'])
        return clusters_

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def verbose(self) -> bool:
        return self._verbose

    @property
    def supernodeDir(self):
        supernodeDir_ = self._create_supernodeDir()
        return supernodeDir_
    
    def _create_supernodeDir(self):
        supernode_outDir_ = os.path.join(self.output_dir_path, "supernodeWGS_results", "blocks_"+self.tag)
        if not os.path.exists(supernode_outDir_):
            os.makedirs(supernode_outDir_)
        return supernode_outDir_
    
    def corr_mat_blocks(self, i):
        idx = self._index_to_pair(i, self.max_cluster)
        idx1 = list(np.where([x == idx[0] for x in self.clusters])[0])
        idx2 = list(np.where([x == idx[1] for x in self.clusters])[0])

        cor_block = self.corr_mat.iloc[idx1, idx2]
        cor_block.reset_index(drop=True, inplace=True)

        file_dir = os.path.join(self.supernodeDir, '{}.pickle'.format(i))
        cor_block.to_pickle(file_dir)

    def _index_to_pair(self, val, max_val=200):
        assert (isinstance(val, int)) and (val % 1 == 0) and (val > 0) and (val <= max_val*(max_val-1)/2+max_val)

        vec = [0] + list(np.cumsum(range(max_val, 0, -1)))
        idx1 = max(np.where(np.array(vec)<val)[0])+1
        idx2 = val - vec[idx1-1] - 1 + idx1
        return (idx1, idx2)

    def dawn_preprocess(self, category_count, permut_test, count_threshold_, size_threshold_):
        cluster_names = self.fit_res['annotation'].tolist()

        cat_count_permut_ = pd.merge(category_count, permut_test, on='Category').set_index(pd.Index(list(range(1, len(permut_test)+1))))
        category_names = cat_count_permut_.Category.tolist()

        ctrl_categories = (cat_count_permut_['Relative_Risk'] <= 1)&(cat_count_permut_['P'] < 0.5) # Control-directed categories. # Permutated p-values.
        cat_count_permut_.loc[ctrl_categories, 'P'] = 1 - cat_count_permut_.loc[ctrl_categories, 'P']

        idx = self._matching_(np.array(cluster_names), np.array(category_names)) # 각 cluster의 category에 해당하는 category name 매칭하여 그것의 index를 get, 그냥 match(cluster_names, category_names) 같음
        idx = list(map(int, idx))

        cat_count_permut_ = cat_count_permut_.loc[idx] # sort by index matched cluster to category
        cat_count_permut_['flag'] = cat_count_permut_.raw_counts.apply(lambda x: True if x < count_threshold_ else False) # Categories with variants less than 20 are TRUE
        cat_count_permut_.loc[cat_count_permut_.P.isna(), 'flag'] = True # So we will going to remove categories that are TRUE in this index.

        if self.tag != 'coding':
            bool_screen = self._screen_name_(cluster_names) # Check if there are coding regions included
            cat_count_permut_.loc[np.array(bool_screen)==0, 'flag'] = True # if bool_screen == False, categories_flag <- True

        cluster_size = self._cluster_size_(np.array(cat_count_permut_['P']), np.array(self.clusters), np.array(cat_count_permut_['flag'])) # The size of the cluster. The number of categories in each cluster.
        cluster_idx = np.where(np.array(cluster_size) >= size_threshold_)[0] + 1 # Minimum number of categories. # R-indexed (1-based)
        self.cluster_size_ = cluster_size
        self.cluster_idx_ = cluster_idx

        ## transform p-value
        cat_count_permut_.loc[cat_count_permut_.P.notna(), 'P'] = norm.ppf(1 - cat_count_permut_.loc[cat_count_permut_.P.notna(), 'P']) # Z-score where each value of P is a p-value in a normal distribution.
        max_zscore = abs(cat_count_permut_.loc[(cat_count_permut_.P.notna()) & (~np.isinf(cat_count_permut_.P)), 'P'].max()) # The max value of finite z-score. This is to set the infinite value as the max value among z-scores.
        # Convert infinite values into finite values.
        cat_count_permut_.loc[(np.isinf(cat_count_permut_.P))&(cat_count_permut_.P > 0), 'P'] = 1.1 * max_zscore
        cat_count_permut_.loc[(np.isinf(cat_count_permut_.P))&(cat_count_permut_.P > 0), 'P'] = -1.1 * max_zscore
        cat_count_permut_['Relative_Risk'] = cat_count_permut_['Relative_Risk'].apply(np.log) # Relative risk in log scale. Now, positive risks are case-enriched.
        cat_count_permut_['flag2'] = cat_count_permut_.flag
        cat_count_permut_.loc[np.isinf(cat_count_permut_.Relative_Risk), 'flag2'] = True # Categories with infinite relative risks are set to TRUE.
        
        return cat_count_permut_, cluster_idx, cluster_size

    def _matching_(self, name1, name2, safety=True):
        if safety:
            assert np.all(np.in1d(name1, name2))
        
        idx = np.where(np.in1d(name1, name2))[0]
        vec = np.full(len(name1), np.nan)
        vec[idx] = np.vectorize(dict(zip(name2, range(1, len(name2) + 1))).get)(name1[idx])
        return vec

    def _screen_name_(self, vec ,position=4, stopwords=None):
        stopwords = ["Any", "CodingRegion", "FrameshiftRegion", "LoFRegion", "MissenseRegion", "SilentRegion", "MissenseHVARDRegionSimple"]
        bool_vec = [not any(np.in1d(np.array(stopwords), np.array(x.split('_')[position-1]))) for x in vec]
        return bool_vec

    def _cluster_size_(self, vec, clustering, flag_vec):
        assert len(vec) == len(flag_vec), "Length of flag_vec and vec must be the same"

        idx = lambda x: np.where(np.array(clustering) == x)[0]
        result = [len(set(np.where(~np.isnan(vec[idx(x)]))[0]) & set(np.where(~flag_vec[idx(x)])[0])) for x in range(1, max(clustering) + 1)]
        return result

    def form_graph_from_correlation(self, cor_mat, func=None, k=200):
        if func is None:
            func = lambda x: x > 0.15
        
        if isinstance(k, int): # k is integer
            assert len(cor_mat) == k*(k-1)//2
            idx_mat = list(itertools.combinations(list(np.arange(1, k+1)), 2))
        else: # k is list
            assert len(cor_mat) == len(k)*((len(k)-1)//2)
            num_node = len(k)
            idx_mat = list(itertools.combinations(list(np.arange(1, num_node+1)), 2))
        
        idx = np.where(np.array([func(x) for x in cor_mat]))[0]
        edges = np.array(idx_mat)[idx]
        edges = np.array([[edges[i,0]-1, edges[i,1]-1] for i in range(len(edges))])

        g = igraph.Graph()
        g.add_vertices(num_node)

        if len(k) > 1:
            g.vs['name'] = [str(n) for n in k]

        g.add_edges(edges)
        return g

    def hmrf(self, z, adj, seedindex=None, null_mean=0, null_sigma=np.nan, pthres=0.05, iter=100, verbose=False, tol=1e-3):
        assert len(z) == len(seedindex) and adj.shape[0] == len(z) and adj.shape[1] == len(z)

        if seedindex is None:
            seedindex = [0 for x in len(z)]

        d = len(z)
        idx = random.sample(range(d), d)
        z = np.array(z)[idx]
        adj = adj.iloc[idx,idx]
        seedindex = np.array(seedindex)[idx]

        i_vec = np.int64(z > norm.ppf(1-pthres, loc=null_mean, scale=(1 if np.isnan(null_sigma) else null_sigma)))
        b = 0; c = 0

        mu2 = np.mean(z[(i_vec==1) & (seedindex==0)])
        mu1 = null_mean

        if np.isnan(null_sigma):
            sigma2 = np.var(z)
            sigma1 = sigma2
        else:
            sigma2 = null_sigma
            sigma1 = null_sigma

        posterior = [0 for x in range(d)]

        for iteri in range(1, iter+1):
            if verbose:
                print("Start iteration : {}".format(iteri))

            res = self._optimize_bc(adj, i_vec, 20)
            b_new = res['b']; c_new = res['c']

            if (abs(c - c_new) < tol) & (abs(b - b_new) < tol):
                break
            
            b = b_new; c = c_new

            for i in range(d):
                new1 = np.exp(b * i_vec[i] + c * i_vec[i] * adj.iloc[i,] @ i_vec)
                new2 = np.exp(b * (1 - i_vec[i]) + c * (1 - i_vec[i]) * adj.iloc[i,] @ i_vec)

                p1 = norm.pdf(z[i], mu2 * i_vec[i] + mu1 * (1 - i_vec[i]), np.sqrt(sigma2 * i_vec[i] + sigma1 * (1 - i_vec[i]))) * new1 / (new1 + new2)
                p2 = norm.pdf(z[i], mu2 * (1 - i_vec[i]) + mu1 * i_vec[i], np.sqrt(sigma2 * (1 - i_vec[i]) + sigma1 * i_vec[i])) * new2 / (new1 + new2)               

                if (i_vec[i] == 1):
                    posterior[i] = p1 / (p1 + p2)
                else:
                    posterior[i] = p2 / (p1 + p2)
                    
                if p2 > p1:
                    i_vec[i] = 1 - i_vec[i]
                if seedindex[i] != 0:
                    i_vec[i] = 1
                    
            mu2 = sum(np.array(posterior)[seedindex==0] * z[seedindex==0]) / sum(np.array(posterior)[seedindex==0])
            sigma2 = sum(np.array(posterior)[seedindex==0] * (z[seedindex==0]-mu2) ** 2) / sum(np.array(posterior)[seedindex==0])

            if np.isnan(null_sigma):
                sigma1 = sum((1 - np.array(posterior)[seedindex==0]) * (z[seedindex==0]) ** 2) / sum(1 - np.array(posterior)[seedindex==0])
                sigmas = (sigma1 * sum(np.array(posterior)[seedindex==0]) + sigma2 * sum(1 - np.array(posterior)[seedindex==0])) / len(posterior)
                sigma2 = sigmas; sigma1 = sigmas
                
            if verbose:
                print("Iteration: {} has {} genes set with Iupdate = 1.".format(iteri, sum(i_vec)))
                print("Parameters: {}, {} // {}, {}".format(round(mu1,3), round(mu2,3), round(sigma1,3), round(sigma2,3)))
                
        i_vec = np.array(i_vec)[sorted(idx)]
        posterior = np.array(posterior)[sorted(idx)]

        return {'Iupdate': i_vec, 'post': posterior, 'b': b, 'c': c, 'mu1': mu1, 'mu2': mu2, 'sigma1': sigma1, 'sigma2': sigma2}


    def _partial_likelihood_(self, b, c, graph_term, i_vec):
        d = len(i_vec)
            
        def fv_fun(i):
            new1 = np.exp(b * i_vec[i] + c * i_vec[i] * graph_term[i])
            new2 = np.exp(b * (1 - i_vec[i]) + c * (1 - i_vec[i]) * graph_term[i])
            fvalue = np.log(new1 / (new1 + new2))
            return fvalue

        return np.sum([fv_fun(i) for i in range(d)])

    def _optimize_bc(self, adj, i_vec, times, tol=1e-5, b_range=(-10, 10), c_range=(-10, 10)):
        b = 0
        c = 1

        graph_term = np.dot(i_vec, adj)
        for k in range(times):
            res_b = minimize_scalar(lambda b_val: -self._partial_likelihood_(b_val, c, graph_term, i_vec), bounds=b_range, method='bounded')
            b_new = res_b.x

            res_c = minimize_scalar(lambda c_val: -self._partial_likelihood_(b_new, c_val, graph_term, i_vec), bounds=c_range, method='bounded')
            c_new = res_c.x

            if abs(b_new - b) < tol and abs(c_new - c) < tol:
                break

            b = b_new
            c = c_new

        return {'b': b, 'c': c}

    def report_results(self, vec, posterior, pvalue, Iupdate):
        assert len(vec) == len(posterior) and len(vec) == len(pvalue) and len(vec) == len(Iupdate)

        d = len(1-posterior)
        rankpost = sorted(1-posterior)
        localfdr = list(map(lambda x: np.mean(rankpost[:x]), range(1, d+1)))

        flocalfdr = [0 for x in range(d)]
        rankp = np.int64(rankdata(1-posterior, method="average"))
        flocalfdr = np.array(localfdr)[rankp-1]

        return pd.DataFrame({"Name":vec, "p.value":pvalue, "FDR":flocalfdr, "indicator":Iupdate})
    
    def dawn_plot(self, g, zval, annot):
        random.seed(self.seed)

        node_size = [sum(np.array(self.clusters)==x) for x in self.cluster_idx_]
        node_size = (node_size - min(node_size)) / max(node_size)
        node_size = 2 * (node_size + 1) ** 2
        
        maxz = max(zval)
        minz = min(zval)
        node_col = list(map(lambda x: self._node_color_(maxz=maxz, minz=minz, x=x), zval))

        layout = g.layout(layout='auto')
        layout_mat = pd.DataFrame(layout[:], columns=['X.pos','Y.pos'])
        layout_mat = pd.concat([pd.DataFrame({'Cluster.index':g.vs['name']}), layout_mat, pd.DataFrame({"node.size":node_size, "node.color":node_col})], axis=1)
        
        comm_leiden = g.community_leiden(objective_function='modularity')
        comm_membership = [comm_leiden.membership[v] for v in range(g.vcount())]
        comm_df = pd.DataFrame({'Cluster.index':g.vs['name'], 'Community':comm_membership})
        cluster_df = pd.merge(layout_mat, comm_df, on='Cluster.index')
        cluster_df["Category"] = annot
        comm_cat = pd.DataFrame(cluster_df.groupby("Community")["Category"].apply(lambda x: sum(x, []))).reset_index()
        comm_cat["Represent_term"] = comm_cat["Category"].apply(lambda x: self._term_freq(x))
        cluster_df = pd.merge(cluster_df, comm_cat.loc[:,["Community","Represent_term"]], on="Community")

        x_pos_list = cluster_df.groupby('Community')["X.pos"].max()
        y_pos_list = cluster_df.groupby('Community')["Y.pos"].mean()

        fig, ax = plt.subplots(figsize=(7,7))
        igraph.plot(comm_leiden,
                    mark_groups=True,
                    vertex_size=node_size*5*10e-3,
                    vertex_label=None,
                    vertex_color=node_col,
                    edge_width=.7,
                    layout=layout,
                    bbox=(300,300),
                    margin=20,
                    target=ax)
        for i in cluster_df["Community"].unique():
            ax.annotate(cluster_df.loc[cluster_df["Community"]==i, "Represent_term"].values[0], (x_pos_list[i]+.1,y_pos_list[i]+.1), fontsize=10)
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir_path, "{}.iplot.igraph_with_community.pdf".format(self.tag)))
        print("(1/4) {} saved!".format(os.path.join(self.output_dir_path, "{}.iplot.igraph_with_community.pdf".format(self.tag))))

        fig, ax = plt.subplots(figsize=(7,7))
        igraph.plot(g,
                    vertex_size=node_size*5*10e-3,
                    vertex_color=node_col,
                    vertex_label=None,
                    edge_width=.7,
                    layout=layout,
                    bbox=(300,300),
                    target=ax)
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir_path, "{}.iplot.igraph.pdf".format(self.tag)))      
        print("(2/4) {} saved!".format(os.path.join(self.output_dir_path, "{}.iplot.igraph.pdf".format(self.tag)))) 

        fig, ax = plt.subplots(figsize=(7,7))
        igraph.plot(g,
                    vertex_size=node_size*5*10e-3,
                    vertex_color=node_col,
                    vertex_label=g.vs['name'],
                    vertex_label_size=10,
                    edge_width=.7,
                    layout=layout,
                    bbox=(300,300),
                    target=ax)
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir_path, "{}.iplot.igraph_with_number.pdf".format(self.tag)))      
        print("(3/4) {} saved!".format(os.path.join(self.output_dir_path, "{}.iplot.igraph_with_number.pdf".format(self.tag))))  
        
        layout_mat.to_csv(os.path.join(self.output_dir_path, "{}.graph_layout.csv".format(self.tag)), index=False)      
        print("(4/4) {} saved!".format(os.path.join(self.output_dir_path, "{}.graph_layout.csv".format(self.tag))))

    def _term_freq(self, x):
        tmp = sum(list(map(lambda x: x.split("_"), x)), [])
        word_count = pd.DataFrame(columns=['cnt'])
        except_terms = ["All","Any","SNV","Indel"]

        for t in tmp:
            if (not t in except_terms) and (not self.tag in t.lower()):
                if not t in word_count.index:
                    word_count.loc[t, 'cnt'] = 1
                else:
                    word_count.loc[t, 'cnt'] = word_count.loc[t, 'cnt'] + 1

        max_cnt = word_count.cnt.max()
        rep_term = '&'.join(word_count.loc[word_count['cnt'] == max_cnt].index.tolist())
        return rep_term

    def _node_color_(self, maxz, minz, x):
        tmp = (maxz - x) / (maxz-minz)
        tmp = 1 / (1 + np.exp(-10 * (tmp - 0.2)))
        return mcolors.to_hex((1, tmp, tmp))


class data_collection:
    def __init__(self, path: str, cores: int, max_cluster=None, verbose=True) -> None:
        self._path = path
        self._cores = cores
        self._verbose = verbose
        self._max_cluster = max_cluster
    
    @property
    def path(self) -> str:
        return self._path
    
    @property
    def cores(self) -> str:
        return self._cores

    @property
    def max_cluster(self):
        return self._max_cluster
    
    @property
    def verbose(self):
        return self._verbose
    
    def _pair_to_index_(self, idx1, idx2, max_val=200):
        assert isinstance(idx1, int) and isinstance(idx2, int), "idx1 and idx2 must be integers."
        assert (idx1 > 0) and (idx2 > 0) and (idx1 % 1 == 0) and (idx2 % 1 == 0),  "idx1 and idx2 must be positive integers."
        assert (max_val > 0) and (max_val % 1 == 0), "max_val must be a positive integer."
        assert (max_val >= idx1) and (max_val >= idx2), "max_val must be greater than or equal to idx1 and idx2."

        i = min(idx1, idx2); j = max(idx1, idx2)
        tmp = sum(np.arange(max_val, (max_val-(i-2))-1, -1)) if i > 1 else 0
        return tmp + (j-i+1)

    def form_correlation(self, k=200):
        pool = ProcessPoolExecutor(max_workers=self.cores)

        if isinstance(k, int):
            self.max_cluster = k
            num_node = k
            combn_mat = list(itertools.combinations(list(np.arange(1,num_node+1)), 2))
        else:
            assert self.max_cluster is not None
            idx_mat = list(itertools.combinations(list(np.arange(1,len(k)+1)), 2))
            combn_mat = [(k[x[0]-1], k[x[1]-1]) for x in idx_mat]
            
        self._combn_mat = combn_mat
        results = list(pool.map(self._cor_func_, range(len(combn_mat))))

        return results

    def _cor_func_(self, i):
        idx = self._pair_to_index_(int(self._combn_mat[i][0]), int(self._combn_mat[i][1]), max_val=self.max_cluster)
        cor_block = 0
        cor_block = pd.read_pickle(os.path.join(self.path, "{}.pickle".format(idx)))
        return np.mean(np.array(cor_block))
    
    def form_testvec(self, vec, clustering=None, flag_vec=None, k=200, sparse=False, sumabsv=4):
        self._vec = vec
        self._clustering = clustering
        self._flag_vec = flag_vec
        self._k = k
        self._sparse = sparse
        self._sumabsv = sumabsv
        
        assert len(vec) == len(clustering)
        pool = ProcessPoolExecutor(max_workers=self.cores)

        if flag_vec is None:
            self._flag_vec = [False for i in range(len(vec))]
        
        if isinstance(k, int): # k is integer
            cluster_vec = list(range(1, k+1))
            self.max_cluster = k
        else:
            cluster_vec = k
            assert self.max_cluster is not None

        res = pd.DataFrame(pool.map(self._test_func_, cluster_vec))
        return res

    def _test_func_(self, i):          
        cluster_idx_tmp = np.where(np.array(self._clustering) == i)[0]
        testvec = np.array(self._vec)[cluster_idx_tmp]
        testflag = np.array(self._flag_vec)[cluster_idx_tmp]
        keep_idx = list(set(np.where(~np.isnan(testvec))[0]) & set(np.where(~testflag)[0]))
        testvec = testvec[keep_idx]

        idx = self._pair_to_index_(int(i), int(i), max_val=self.max_cluster)
        cor_block = 0
        cor_block = pd.read_pickle(os.path.join(self.path, "{}.pickle".format(idx)))
        cor_block = cor_block.iloc[keep_idx, keep_idx]

        if len(cor_block)==0:
            return {'vec':np.nan, 'index':np.nan, 'sparsity':np.nan}

        eig = self._extract_eigenvector_(cor_block, sparse=self._sparse, sumabsv=self._sumabsv)
        unsigned = np.sqrt((eig @ testvec) ** 2 / (eig @ cor_block @ eig))
        sign = self._determine_sign_(np.outer(np.array(eig),np.array(eig)) @ testvec)

        assert len(eig) == len(keep_idx)
        return {'vec':sign*unsigned, 'index':cluster_idx_tmp[np.array(keep_idx)[np.where(np.abs(eig) >= 1e-5)[0]]],'sparsity':len(np.array(keep_idx)[np.where(np.abs(eig) >= 1e-5)[0]])/len(eig)}

    def _determine_sign_(self, vec):
        pos = len(np.where(vec > 0)[0])
        neg = len(np.where(vec < 0)[0])
        if (pos > neg):
            return 1
        elif (pos < neg):
            return -1
        return np.random.binomial(1, 0.5) * 2 - 1
    
    def _extract_eigenvector_(self, mat, sparse=False, sumabsv=4):
        if sparse & (len(mat.columns)>sumabsv**2):
            mat = np.array(mat)
            mat = numpy2ri.py2rpy(mat)
            eig = self.PMA.SPC(mat, trace=robjects.BoolVector([False]), sumabsv=sumabsv)
            eig_res = dict(zip(eig.names, list(eig)))
            return eig_res['v'].flatten()
        else:
            eig = np.linalg.eig(mat)
            eig_vectors = eig[1] * (-1)
            return [x[0] for x in eig_vectors]